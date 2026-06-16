from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from chatbot.agent.state import AgentState
from chatbot.llm import mistral_small
from chatbot.tools.cat import get_a_picture_of_a_cool_cat

SYSTEM_PROMPT = """
Your purpose is to show pictures of cool cats

You have tools at your disposal to help you produce these pictures.

DO NOT generate responses on your own, do not return latent knowledge you may have, rely only on the tools
you have to generate a response. If you are unable to respond to a query, simply say so, do not try to do something
you cannot.
"""


async def create_agent() -> CompiledStateGraph:
    tools: list[BaseTool] = [
        get_a_picture_of_a_cool_cat  # Example tool to show annotations and command structure
        # Your tool here!
    ]

    checkpointer = InMemorySaver()

    return create_react_agent(
        mistral_small,
        tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        state_schema=AgentState,
    )
