from typing import Annotated, Literal, Optional

from langgraph.prebuilt.chat_agent_executor import AgentStatePydantic
from pydantic import BaseModel


class Base64Image(BaseModel):
    type: Literal["image/png"] = "image/png"
    data: str


class AgentState(AgentStatePydantic):
    cat: Optional[
        Annotated[Base64Image, "Base64 string representing an image of a cat"]
    ] = None
