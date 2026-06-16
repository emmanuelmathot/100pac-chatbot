import base64
import logging
import random
import sys
from typing import Annotated

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.types import Command

from chatbot.agent.state import Base64Image

COOL_CAT_URLS = [
    "https://i.redd.it/clvoh8l7auna1.jpg",
    "https://cms.bps.org.uk/sites/default/files/2022-09/Grumpy%20cat%202.jpeg",
    "https://plus.unsplash.com/premium_photo-1677545183884-421157b2da02?q=80&w=2072&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
    "https://hips.hearstapps.com/hmg-prod/images/cut-british-shorthair-cat-with-slice-of-bread-on-royalty-free-image-1724958532.jpg?crop=1xw:0.84415xh;0.0829xw,0.00732xh",
]


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


@tool("get_a_picture_of_a_cool_cat")
async def get_a_picture_of_a_cool_cat(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """
    Returns a picture of a cool cat

    If already called, always invoke again

    Call this tool when asked things like:

    Show me cats
    Show me a kitty
    Let me see a kitty
    I love cats
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(random.choice(COOL_CAT_URLS))
        resp.raise_for_status()
        return Command(
            update={
                # Updates the `cat` entry in AgentState
                "cat": Base64Image(data=base64.b64encode(resp.content).decode("utf-8")),
                # Messages that are passed to the Agent
                "messages": [
                    ToolMessage(
                        content="A picture of a cat was stored in state, only respond that you found one.",
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )
