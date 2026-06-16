"""Tool d'analyse par code : le LLM écrit du code, exécuté côté serveur.

Incarne le principe « analyse par code reproductible » : pour les questions non
couvertes par les tools paramétrés, l'agent génère un court script
xarray/pandas. Il est exécuté dans un **environnement restreint** (datasets en
lecture seule, builtins limités, pas d'import ni d'I/O), seul un **résultat résumé**
revient au contexte, et le **code est persisté** dans l'état (provenance/audit).
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Annotated

import numpy as np
import pandas as pd
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.types import Command

from chatbot.data import access

# Builtins autorisés (pas d'open/eval/exec/__import__).
_SAFE_BUILTINS = {
    name: __builtins__[name]
    if isinstance(__builtins__, dict)
    else getattr(__builtins__, name)
    for name in (
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "print",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    )
}

_MAX_OUTPUT = 2000


def _summarize(value: object) -> str:
    """Réduit un résultat à une forme compacte (jamais les séries complètes)."""
    if value is None:
        return ""
    if isinstance(value, (int, float, np.floating, np.integer)):
        return str(value)
    if isinstance(value, pd.DataFrame):
        return value.head(20).to_string()
    if isinstance(value, pd.Series):
        return value.head(40).to_string()
    text = repr(value)
    return text[:_MAX_OUTPUT] + (" …(tronqué)" if len(text) > _MAX_OUTPUT else "")


@tool("run_data_analysis")
async def run_data_analysis(
    code: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Exécute un court script Python d'analyse des données mesurées (xarray/pandas).

    À utiliser pour les calculs non couverts par les autres tools. Variables
    disponibles (lecture seule) :
      - ``fleet`` : DataFrame des 100 logements (index = identifiant logement).
      - ``raw``, ``hourly``, ``daily``, ``monthly`` : xarray.Dataset (dims logement × time).
      - ``np``, ``pd`` : numpy, pandas.
    Affecte le résultat à une variable nommée ``result`` (ou utilise ``print``).
    Pas d'import, pas d'accès fichier/réseau. Exemple :
      ``result = float(daily['t_meteo'].sel(logement='002026').mean())``
    """
    env = {
        "__builtins__": _SAFE_BUILTINS,
        "np": np,
        "pd": pd,
        "fleet": access.fleet_dataframe(),
        "raw": access.measurements("raw"),
        "hourly": access.measurements("hourly"),
        "daily": access.measurements("daily"),
        "monthly": access.measurements("monthly"),
    }
    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            exec(code, env)  # noqa: S102 — exécution volontaire en environnement restreint
        out = _summarize(env.get("result"))
        printed = stdout.getvalue().strip()
        content = "\n".join(p for p in (printed, out) if p) or "(aucun résultat)"
        status = "ok"
    except Exception as e:  # noqa: BLE001 — on renvoie l'erreur au modèle
        content = f"Erreur d'exécution : {type(e).__name__}: {e}"
        status = "error"

    return Command(
        update={
            "provenance": [
                {"tool": "run_data_analysis", "status": status, "code": code}
            ],
            "messages": [
                ToolMessage(content=content[:_MAX_OUTPUT], tool_call_id=tool_call_id)
            ],
        }
    )
