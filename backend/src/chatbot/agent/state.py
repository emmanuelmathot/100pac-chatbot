from typing import Annotated, Any, Literal, Optional

from langgraph.prebuilt.chat_agent_executor import AgentStatePydantic
from pydantic import BaseModel


class Base64Image(BaseModel):
    type: Literal["image/png"] = "image/png"
    data: str


class AgentState(AgentStatePydantic):
    # Dernier graphe produit par un data tool (rendu comme image dans l'UI).
    plot: Optional[
        Annotated[Base64Image, "Graphe PNG (base64) produit par un tool"]
    ] = None
    # Citations du rapport (section + page) accompagnant la dernière réponse.
    citations: Optional[list[dict[str, Any]]] = None
    # Provenance : code/requêtes exécutés par les tools data (auditabilité).
    provenance: Optional[list[dict[str, Any]]] = None
