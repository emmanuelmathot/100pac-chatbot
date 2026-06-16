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


@tool("compare_fleet_performance")
async def compare_fleet_performance(
    group_by: str = "type_source_froide",
    heating_season_only: bool = True,
) -> str:
    """Compare le COP réel moyen du parc, regroupé par un attribut des logements.

    Idéal pour « performance moyenne des PAC air/eau vs géothermiques » : agrège le COP
    réel mesuré de chaque logement par ``group_by`` et le compare au SCOP déclaré moyen.
    ``group_by`` est libre : **n'importe quel attribut du parc** (colonne de
    describe_fleet) — par défaut ``type_source_froide`` (air/eau vs eau/eau), aussi
    ``type_pac``, ``departement``, ``fluide_frigorigene``, ``emetteurs``...
    ``heating_season_only=true`` recommandé.
    """
    return _dump(
        analytics.fleet_performance(
            group_by=group_by, heating_season_only=heating_season_only
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


@tool("plot_fleet_metric")
async def plot_fleet_metric(
    tool_call_id: Annotated[str, InjectedToolCallId],
    metric: str = "cop",
    resolution: str = "monthly",
    group_by: Optional[str] = None,
    heating_season_only: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Command:
    """Trace une métrique AGRÉGÉE SUR TOUT LE PARC dans le temps et l'affiche.

    À utiliser pour « le COP moyen de tous les logements par mois », « la consommation
    totale du parc »... ``metric="cop"`` calcule le COP de l'ensemble par pas de temps
    (Σ thermique net / Σ électrique). Autre ``metric`` : un canal (``pac``,
    ``elec_energy_wh``, ``t_meteo``...) agrégé sur les logements.
    ``group_by`` est libre : **n'importe quel attribut du parc** (colonne de
    describe_fleet), ex. ``type_source_froide`` (air/eau vs géothermie), ``type_pac``,
    ``departement``, ``fluide_frigorigene`` -> une courbe par valeur du groupe.
    ``resolution`` ∈ daily|monthly recommandé (raw/hourly trop bruités à l'échelle parc).
    """
    png = analytics.fleet_metric_png(
        metric,
        resolution=resolution,
        group_by=group_by,
        start=start,
        end=end,
        heating_season_only=heating_season_only,
    )
    return Command(
        update={
            "plot": Base64Image(data=png),
            "provenance": [
                {
                    "tool": "plot_fleet_metric",
                    "metric": metric,
                    "resolution": resolution,
                    "group_by": group_by,
                    "heating_season_only": heating_season_only,
                    "period": [start, end],
                }
            ],
            "messages": [
                ToolMessage(
                    content=(
                        f"Graphe parc '{metric}' ({resolution}"
                        + (f", par {group_by}" if group_by else "")
                        + ") produit et affiché."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
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
