import json
import logging
import sys
from contextlib import aclosing, asynccontextmanager
from typing import Any, AsyncGenerator, cast

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pydantic import UUID4

from chatbot.agent.agent import create_agent
from chatbot.api.schemas.chat import ChatRequestBody
from chatbot.settings import get_settings

load_dotenv()
settings = get_settings()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.chatbot = await create_agent()
    yield


app = FastAPI(title="100PAC Chatbot API", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"message": "Healthy!"})


async def stream_chat(
    query: str, thread_id: UUID4, chatbot: CompiledStateGraph, request: Request
) -> AsyncGenerator[bytes, None]:
    config: RunnableConfig = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    # Question de l'utilisateur : tracée pour retrouver les requêtes dans les logs.
    logger.info(
        json.dumps({"user_query": {"thread_id": str(thread_id), "query": query}})
    )

    # Deux modes combinés :
    # - "messages" : tokens du LLM au fil de l'eau (réponse progressive) ;
    # - "updates"  : messages d'outils + changements d'état (citations, graphe...).
    stream = cast(
        AsyncGenerator[tuple[str, Any], None],
        chatbot.astream(
            input={"messages": [HumanMessage(content=query)]},
            config=config,
            stream_mode=["messages", "updates"],
        ),
    )

    try:
        async with aclosing(stream):
            async for mode, data in stream:
                if await request.is_disconnected():
                    logger.info("Client disconnected; stopping stream.")
                    break

                if mode == "messages":
                    # Tokens de la réponse de l'IA : on les renvoie un à un.
                    chunk, _meta = data
                    content = getattr(chunk, "content", None)
                    if (
                        chunk.__class__.__name__ == "AIMessageChunk"
                        and isinstance(content, str)
                        and content
                    ):
                        yield (json.dumps({"token": content}) + "\n").encode("utf-8")
                    continue

                # mode == "updates"
                agent = next(iter(data.keys()))
                payload = data[agent]

                for msg in payload.get("messages", []):
                    # La réponse de l'IA est déjà streamée token par token ;
                    # on ne ré-émet pas son contenu (sinon affiché en double).
                    if msg.__class__.__name__ == "AIMessage":
                        continue
                    line = json.dumps(msg.to_json()) + "\n"
                    logger.info(line)
                    yield line.encode("utf-8")

                for key, value in (
                    (k, v) for k, v in payload.items() if k != "messages"
                ):
                    line = await jsonify_value_and_create_ndjson_line(key, value)
                    logger.info(line)
                    yield line.encode("utf-8")

    except Exception as e:
        logger.warning("stream_chat error: %r", e)


async def jsonify_value_and_create_ndjson_line(key: str, value: Any):
    if isinstance(value, list) and value and hasattr(value[0], "model_dump"):
        value = [item.model_dump() for item in value]
    elif hasattr(value, "model_dump"):
        value = value.model_dump()
    line = json.dumps({"state_change": {key: value}}) + "\n"
    return line


@app.post("/chat")
async def chat(request: ChatRequestBody, http_request: Request) -> StreamingResponse:
    generator = stream_chat(
        query=request.query,
        thread_id=request.thread_id,
        chatbot=http_request.app.state.chatbot,
        request=http_request,
    )
    return StreamingResponse(
        generator,
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            # If you run behind nginx, this prevents buffering of the stream:
            "X-Accel-Buffering": "no",
        },
    )
