from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from chatbot.agent.state import AgentState
from chatbot.llm import mistral_small
from chatbot.tools.analyze import run_data_analysis
from chatbot.tools.data import (
    compute_performance,
    describe_fleet,
    plot_measurement,
    query_measurement,
)
from chatbot.tools.report import search_report

SYSTEM_PROMPT = """
Tu es un assistant d'analyse pour une campagne de mesure ADEME/Enertech portant sur
100 pompes à chaleur (PAC) en résidentiel individuel : 90 air/eau et 10 géothermiques
(eau/eau), qui ont remplacé des chaudières gaz ou fioul. Tu réponds en français.

Tu disposes de deux familles d'outils :
- search_report : recherche dans le RAPPORT d'audit (méthodologie, conclusions,
  enseignements, définitions, comparaison européenne, causes de sous-performance...).
- describe_fleet / compute_performance / query_measurement / plot_measurement /
  run_data_analysis : interrogation des DONNÉES de mesure (modèle Zarr).

Règles impératives :
- Tu ORCHESTRES des outils, tu ne calcules ni n'inventes jamais de chiffres toi-même.
  Tout résultat numérique doit provenir d'un outil.
- Cite systématiquement tes sources : pour le rapport, indique la page ; pour les
  données, rappelle le logement / la période utilisés.
- Pour une question de COP/SCOP réel, privilégie compute_performance avec
  heating_season_only=true (le COP estival n'a pas de sens). Compare au SCOP déclaré.
- Une seule installation possède actuellement des séries temporelles détaillées
  (logement 002026) ; les métadonnées couvrent les 100 logements. Si on te demande des
  mesures sur un logement non instrumenté, dis-le clairement.
- Si aucun outil ne permet de répondre, dis-le explicitement plutôt que d'inventer.
"""


async def create_agent() -> CompiledStateGraph:
    tools: list[BaseTool] = [
        search_report,
        describe_fleet,
        compute_performance,
        query_measurement,
        plot_measurement,
        run_data_analysis,
    ]

    checkpointer = InMemorySaver()

    return create_react_agent(
        mistral_small,
        tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        state_schema=AgentState,
    )
