"""Harnais de validation métier : exécute l'agent sur des questions de référence.

Vérifie que l'agent orchestre les bons outils et fournit des réponses cohérentes
avec le rapport / les mesures. Nécessite le modèle Zarr, l'index vectoriel et la
clé Mistral. Lancer via ``scripts/validate``.
"""

from __future__ import annotations

import asyncio
import uuid

from langchain_core.messages import HumanMessage

from chatbot.agent.agent import create_agent

# (question, outils attendus parmi les appels)
REFERENCE_QUESTIONS: list[tuple[str, list[str]]] = [
    ("Combien de pompes à chaleur géothermiques compte l'étude ?", ["describe_fleet"]),
    (
        "Quel est le COP réel de saison de chauffe du logement 002026, "
        "comparé au SCOP déclaré ?",
        ["compute_performance"],
    ),
    (
        "Quelle est la consommation électrique annuelle du logement 002026 en kWh ?",
        ["compute_performance", "query_measurement", "run_data_analysis"],
    ),
    (
        "Que dit le rapport sur les principales causes de sous-performance des PAC ?",
        ["search_report"],
    ),
    (
        "Trace la température météo du logement 002026.",
        ["plot_measurement"],
    ),
]


async def _ask(agent, question: str) -> tuple[list[str], str]:
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    tools_called: list[str] = []
    final = ""
    async for update in agent.astream(
        {"messages": [HumanMessage(content=question)]}, cfg, stream_mode="updates"
    ):
        for payload in update.values():
            for msg in payload.get("messages", []):
                for call in getattr(msg, "tool_calls", None) or []:
                    tools_called.append(call["name"])
                if msg.__class__.__name__ == "AIMessage" and msg.content:
                    final = msg.content
    return tools_called, final


async def main() -> None:
    agent = await create_agent()
    ok = 0
    for question, expected in REFERENCE_QUESTIONS:
        tools, answer = await _ask(agent, question)
        hit = any(t in expected for t in tools)
        ok += hit
        print(f"\n{'✓' if hit else '✗'} {question}")
        print(f"   outils: {tools} (attendus ∈ {expected})")
        print(f"   → {answer[:240].strip()}")
    print(
        f"\n{ok}/{len(REFERENCE_QUESTIONS)} questions ont déclenché un outil attendu."
    )


if __name__ == "__main__":
    asyncio.run(main())
