"""Tool d'analyse par code : le LLM écrit du code, exécuté côté serveur.

Incarne le principe « analyse par code reproductible » : pour les questions non
couvertes par les tools paramétrés, l'agent génère un court script
xarray/pandas. Il est exécuté dans un **environnement restreint** (datasets en
lecture seule, builtins limités, pas d'import ni d'I/O), seul un **résultat résumé**
revient au contexte, et le **code est persisté** dans l'état (provenance/audit).
"""

from __future__ import annotations

import ast
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
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "hasattr",
        "int",
        "isinstance",
        "len",
        "list",
        "map",
        "max",
        "min",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
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


def _exec_capturing_last(code: str, env: dict) -> object:
    """Exécute ``code`` et renvoie la valeur de la dernière expression (façon REPL).

    Si la dernière instruction est une simple expression (ex. ``fleet.head()``),
    sa valeur est renvoyée comme résultat implicite — sinon on retombe sur la
    variable ``result``. Cela évite que les introspections sans affectation
    (``fleet.columns.tolist()``) ne renvoient « aucun résultat ».
    """
    tree = ast.parse(code, mode="exec")
    last_value = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = ast.Expression(tree.body.pop().value)
        exec(compile(tree, "<analysis>", "exec"), env)  # noqa: S102
        last_value = eval(compile(last_expr, "<analysis>", "eval"), env)  # noqa: S307
    else:
        exec(compile(tree, "<analysis>", "exec"), env)  # noqa: S102
    return last_value if last_value is not None else env.get("result")


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
    Affecte le résultat à ``result``, ou laisse une expression en dernière ligne
    (comme un notebook) : ``fleet.columns.tolist()`` ou ``fleet.head()`` renvoient
    leur valeur. ``print`` est aussi capturé.
    Pas d'import, pas d'accès fichier/réseau. Certaines colonnes numériques de
    ``fleet`` sont de type ``object`` (chaînes comme ``'10.9'``) : convertis-les
    avec ``pd.to_numeric(fleet[col], errors='coerce')`` plutôt qu'à la main.
    Exemple :
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
            value = _exec_capturing_last(code, env)
        out = _summarize(value)
        printed = stdout.getvalue().strip()
        content = "\n".join(p for p in (printed, out) if p) or "(aucun résultat)"
        status = "ok"
    except Exception as e:  # noqa: BLE001 — on renvoie l'erreur au modèle
        content = f"Erreur d'exécution : {type(e).__name__}: {e}"
        if isinstance(e, ImportError):
            content += (
                " — les imports sont interdits ici. np/pd et les datasets "
                "(fleet, raw, hourly, daily, monthly) sont déjà disponibles. "
                "Pour produire un graphique, utilise plutôt les tools plot_measurement "
                "ou plot_fleet_metric."
            )
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


# Description de base, sans le schéma (qui dépend des données chargées au runtime).
_BASE_DESCRIPTION = run_data_analysis.description


def enrich_with_fleet_schema() -> None:
    """Injecte la liste réelle des colonnes de ``fleet`` dans la description du tool.

    Le modèle devine sinon des noms de colonnes inexistants (``puissance_installee_kw``…)
    et enchaîne les ``KeyError``. Idempotent : reconstruit depuis la description de base.
    """
    try:
        df = access.fleet_dataframe()
        cols = ", ".join(f"{c} ({df[c].dtype})" for c in df.columns)
        run_data_analysis.description = (
            f"{_BASE_DESCRIPTION}\n\nColonnes de `fleet` : {cols}."
        )
    except Exception:  # noqa: BLE001 — schéma indisponible : on garde la description de base
        run_data_analysis.description = _BASE_DESCRIPTION
