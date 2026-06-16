from typing import Annotated, Any, Literal, Optional

from langgraph.prebuilt.chat_agent_executor import AgentStatePydantic
from pydantic import BaseModel


class Base64Image(BaseModel):
    type: Literal["image/png"] = "image/png"
    data: str


def _take_last(left: Any, right: Any) -> Any:
    """Reducer : conserve la dernière valeur non nulle (ex. dernier graphe)."""
    return right if right is not None else left


def _concat(left: Any, right: Any) -> Any:
    """Reducer : concatène deux listes (gère les valeurs nulles).

    Indispensable quand plusieurs outils du même tour (appels parallèles) mettent à
    jour la même clé — LangGraph exige sinon une seule écriture par étape.
    """
    if not left:
        return right or left
    if not right:
        return left
    return list(left) + list(right)


class AgentState(AgentStatePydantic):
    # Dernier graphe produit par un data tool (rendu comme image dans l'UI).
    plot: Annotated[Optional[Base64Image], _take_last] = None
    # Citations du rapport (section + page) — concaténées si plusieurs recherches.
    citations: Annotated[Optional[list[dict[str, Any]]], _concat] = None
    # Provenance : code/requêtes exécutés par les tools data (auditabilité).
    provenance: Annotated[Optional[list[dict[str, Any]]], _concat] = None
