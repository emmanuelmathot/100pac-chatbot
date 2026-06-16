"""Tools data paramétrés : requêtes déterministes sur le modèle Zarr.

Chaque tool s'exécute côté serveur et renvoie un **résultat compact** (JSON court
ou graphe), jamais les séries 1 min. Le LLM orchestre ces tools, il ne calcule pas.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.types import Command

from chatbot.agent.state import Base64Image
from chatbot.data import analytics


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


@tool("describe_fleet")
async def describe_fleet() -> str:
    """Décrit le parc des 100 logements instrumentés (caractéristiques statiques).

    À utiliser pour les questions « parc » : combien de PAC air/eau vs géothermiques
    (eau/eau), répartition par département, SCOP déclaré moyen, quels logements
    disposent de séries temporelles mesurées. Ne nécessite pas de période.
    """
    return _dump(analytics.fleet_summary())


@tool("compute_performance")
async def compute_performance(
    logement: str,
    heating_season_only: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> str:
    """Calcule le COP réel et le bilan énergétique d'un logement sur une période.

    Renvoie énergie électrique, énergie thermique (calo/frig/nette) en kWh, le COP
    réel mesuré et le SCOP constructeur déclaré pour comparaison. Mets
    ``heating_season_only=true`` pour un COP de saison de chauffe (oct→avr), seul
    pertinent (en été la PAC produit des frigories). Dates au format ISO
    (``YYYY-MM-DD``). ``logement`` ex. ``"002026"`` (voir describe_fleet).
    """
    return _dump(
        analytics.performance(
            logement, start=start, end=end, heating_season_only=heating_season_only
        )
    )


@tool("query_measurement")
async def query_measurement(
    variable: str,
    logement: str,
    how: str = "mean",
    resolution: str = "daily",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> str:
    """Agrège une variable mesurée sur une période pour un logement (scalaire).

    ``variable`` ex. ``t_meteo``, ``t_amb_sejour``, ``pac`` (W), ``elec_energy_wh``,
    ``thermal_net_wh`` (Wh)... ``how`` ∈ mean|sum|min|max. ``resolution`` ∈
    raw|hourly|daily|monthly. Dates ISO ``YYYY-MM-DD``.
    """
    return _dump(
        analytics.aggregate(
            variable,
            logement=logement,
            start=start,
            end=end,
            resolution=resolution,
            how=how,
        )
    )


@tool("plot_measurement")
async def plot_measurement(
    variable: str,
    logement: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    resolution: str = "daily",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Command:
    """Trace l'évolution temporelle d'une variable et l'affiche à l'utilisateur.

    À utiliser quand l'utilisateur veut visualiser une courbe (température,
    consommation...). Le graphe est rendu dans l'interface ; réponds simplement que
    le graphe a été produit. ``resolution`` ∈ raw|hourly|daily|monthly, dates ISO.
    """
    png = analytics.timeseries_png(
        variable, logement=logement, start=start, end=end, resolution=resolution
    )
    return Command(
        update={
            "plot": Base64Image(data=png),
            "provenance": [
                {
                    "tool": "plot_measurement",
                    "variable": variable,
                    "logement": logement,
                    "resolution": resolution,
                    "period": [start, end],
                }
            ],
            "messages": [
                ToolMessage(
                    content=(
                        f"Graphe de '{variable}' (logement {logement}, {resolution}) "
                        "produit et affiché."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
