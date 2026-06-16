"""Tool de recherche dans le rapport d'audit (RAG vectoriel).

Renvoie des passages courts **avec leur source** (section + page) et enregistre
les citations dans l'état — conformément au principe de sourcing transparent.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.types import Command

from chatbot.agent.state import Base64Image
from chatbot.rag.figures import render_page_png
from chatbot.rag.index import search, search_figures


@tool("search_report")
async def search_report(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Recherche dans le rapport d'audit ADEME/Enertech sur les 100 pompes à chaleur.

    À utiliser pour toute question portant sur le **contenu du rapport** : méthodologie,
    conclusions, enseignements, recommandations, comparaison européenne, définitions
    (SCOP, COP de Carnot...), causes de sous-performance, etc.

    Renvoie les passages les plus pertinents avec leur source (section et page) ;
    appuie ta réponse sur ces extraits et cite la page.
    """
    passages = search(query, k=4)
    if not passages:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Aucun passage pertinent trouvé dans le rapport.",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    blocks = []
    citations = []
    for p in passages:
        source = f"p. {p.page}" + (f" — {p.section}" if p.section else "")
        blocks.append(f"[{source}]\n{p.text.strip()}")
        citations.append({"page": p.page, "section": p.section})

    content = "Extraits du rapport :\n\n" + "\n\n---\n\n".join(blocks)
    return Command(
        update={
            "citations": citations,
            "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)],
        }
    )


@tool("show_report_figure")
async def show_report_figure(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Affiche une figure ou un tableau du rapport correspondant à la demande.

    À utiliser quand l'utilisateur veut **voir** une illustration du rapport
    (« montre la figure des COP par température », « le graphique de répartition
    géographique », « le tableau de l'échantillon »...). Retrouve la figure par sa
    légende, rend la page correspondante et l'affiche. Réponds en mentionnant le
    numéro de figure et la page.
    """
    matches = search_figures(query, k=1)
    if not matches:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Aucune figure correspondante trouvée dans le rapport.",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    fig = matches[0]
    png = render_page_png(fig.page)
    return Command(
        update={
            "plot": Base64Image(data=png),
            "citations": [
                {
                    "page": fig.page,
                    "figure": f"{fig.kind} {fig.number}",
                    "caption": fig.caption,
                }
            ],
            "messages": [
                ToolMessage(
                    content=f"{fig.caption} (p. {fig.page}) — page affichée.",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
