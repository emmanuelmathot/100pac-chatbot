import base64
import json
import os
import uuid
from io import BytesIO

import requests
import streamlit as st
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="Chatbot 100PAC", page_icon="🔥", layout="wide")
st.session_state.setdefault("messages", [])

# ---- App state ----
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🔥 Chatbot 100PAC")
st.caption(
    "Assistant sur l'audit ADEME/Enertech de 100 pompes à chaleur (rapport + mesures). "
    "Chaque réponse s'appuie sur des outils et cite ses sources."
)

# ---- Questions d'exemple (cliquables) ----
EXAMPLES = {
    "📄 Le rapport d'audit": [
        "Comment le rapport définit-il le SCOP et le COP de Carnot ?",
        "Quelles sont les principales causes de sous-performance des PAC ?",
        "Que conclut le rapport sur les pompes à chaleur géothermiques ?",
    ],
    "🏠 Le parc (100 logements)": [
        "Combien de PAC géothermiques compte l'étude ?",
        "Quelle est la répartition des logements par département ?",
        "Quel est le SCOP déclaré moyen du parc ?",
    ],
    "📊 Performances mesurées": [
        "COP réel de saison de chauffe du logement 002026 vs SCOP déclaré ?",
        "Compare la performance réelle des PAC air/eau et géothermiques",
        "Quelle est la consommation électrique annuelle du logement 011088 ?",
    ],
    "📈 Graphiques & figures": [
        "Trace le COP mensuel du parc, air/eau vs géothermique",
        "Trace la température météo du logement 002026",
        "Montre le graphique du COP saisonnier de chauffage du rapport",
    ],
}


def submit(question: str) -> None:
    st.session_state["pending_prompt"] = question


# ---- Barre latérale : guide & sources ----
with st.sidebar:
    st.header("🔥 Chatbot 100PAC")
    st.markdown(
        "Posez une question en français, ou cliquez un exemple ci-dessous. "
        "L'assistant **orchestre des outils** (recherche dans le rapport, calculs sur "
        "les mesures, graphiques) — il **ne devine jamais** un chiffre et **cite ses sources**."
    )

    if st.button("🆕 Nouvelle conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

    st.subheader("Exemples de questions")
    for category, questions in EXAMPLES.items():
        with st.expander(category, expanded=category.startswith("📄")):
            for q in questions:
                st.button(
                    q,
                    key=f"ex-{q}",
                    use_container_width=True,
                    on_click=submit,
                    args=(q,),
                )

    with st.expander("ℹ️ Comment ça marche / sources"):
        st.markdown(
            "**Sources de données (ADEME, ouvertes)**\n"
            "- [Jeu de mesures (100 PAC)](https://data.ademe.fr/datasets/pac-campagne-de-mesure-100-pacs)\n"
            "- [Rapport d'audit (PDF)](https://librairie.ademe.fr/batiment/8617-mesure-des-performances-de-100-pac-air-eau-et-eau-eau-installees-en-maisons-individuelles.html)\n\n"
            "**Indicateurs** sous les réponses :\n"
            "- 📈 Graphe · 📑 Citations du rapport (page) · 🔎 Traçabilité (requête/code)\n"
            "- 🛠️ détaille l'outil appelé et son résultat brut.\n\n"
            "Données : 100 logements, mesures au pas 1 min ; le COP réel se compare au "
            "SCOP déclaré par le constructeur."
        )


# ---- Helpers ----
STATE_LABELS = {
    "plot": "📈 Graphe",
    "citations": "📑 Citations du rapport",
    "provenance": "🔎 Traçabilité (code / requêtes)",
}


def state_label(key: str) -> str:
    return STATE_LABELS.get(key, key.replace("_", " ").title())


def render_base64_image(data: str):
    image_data = base64.b64decode(data)
    image = Image.open(BytesIO(image_data))
    st.image(image)


def handle_user_query(user_input: str):
    user_msg = {"role": "user", "content": user_input}
    st.session_state.messages.append(user_msg)
    _, c2 = st.columns([2, 20], gap="small")
    with c2:
        st.chat_message("user", avatar="👤").markdown(user_input)

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat",
            json={"query": user_input, "thread_id": st.session_state.thread_id},
            stream=True,
            timeout=120,
        )
        response.raise_for_status()
    except Exception as e:
        st.error(
            f"❌ Impossible de joindre l'API ({API_BASE_URL}). "
            f"Vérifiez que `scripts/api` tourne. Détail : {e}"
        )
        return

    status = st.empty()

    def set_status(text: str):
        status.empty()
        with status.container():
            st.chat_message("assistant", avatar="🤖").markdown(text)

    set_status("🤔 Je réfléchis…")

    answer = ""
    answer_box = None  # placeholder de la réponse streamée (créé au 1er token)

    try:
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.strip():
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue

            # 1) Tokens de la réponse : affichage progressif.
            if "token" in msg:
                if answer_box is None:
                    status.empty()
                    answer_box = st.chat_message("assistant", avatar="🤖").empty()
                answer += msg["token"]
                answer_box.markdown(answer + " ▌")
                continue

            # 2) Changements d'état (citations, graphe, traçabilité).
            if "state_change" in msg:
                state_payload = msg["state_change"]
                status.empty()
                with st.chat_message("state", avatar="📊"):
                    for key, value in state_payload.items():
                        plain_label = state_label(key)
                        if (
                            isinstance(value, dict)
                            and "type" in value
                            and "data" in value
                            and value["type"].startswith("image/")
                        ):
                            render_base64_image(value["data"])
                        else:
                            with st.expander(label=f"{plain_label}", expanded=False):
                                if isinstance(value, (dict, list)):
                                    st.json(value)
                                elif isinstance(value, str):
                                    try:
                                        st.json(json.loads(value))
                                    except json.JSONDecodeError:
                                        st.markdown(f"```\n{value}\n```")
                                else:
                                    st.write(value)
                st.session_state.messages.append(
                    {"role": "state", "content": state_payload}
                )
                set_status("✍️ Je rédige la réponse…")
                continue

            # 3) Messages complets : sorties d'outils (l'IA est déjà streamée).
            kwargs = msg.get("kwargs", {})
            msg_type = kwargs.get("type", "assistant")
            content = kwargs.get("content", "")
            tool_name = kwargs.get("name", "Tool Output")

            if msg_type in ("human", "ai") or not content.strip():
                continue  # ai = déjà affiché token par token

            status.empty()
            with st.chat_message("tool", avatar="🛠️"):
                with st.expander(label=f"{tool_name}", expanded=False):
                    st.markdown(content)
            st.session_state.messages.append(
                {"role": "tool", "content": {"name": tool_name, "body": content}}
            )
            set_status("✍️ Je rédige la réponse…")

        # Finalisation de la réponse streamée (retire le curseur, sauvegarde).
        status.empty()
        if answer_box is not None and answer:
            answer_box.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
    except requests.exceptions.ChunkedEncodingError:
        st.warning("⚠️ Connexion interrompue ; réponse partielle affichée.")
    finally:
        try:
            response.close()
        except Exception:
            pass


# ---- Accueil (conversation vide) ----
if not st.session_state.messages and "pending_prompt" not in st.session_state:
    st.info(
        "👋 Bienvenue ! Je réponds à vos questions sur l'audit de **100 pompes à chaleur** "
        "(rapport + mesures terrain).\n\n"
        "Essayez un **exemple** dans la barre latérale, ou demandez par exemple : "
        "*« Compare la performance réelle des PAC air/eau et géothermiques »*.\n\n"
        "💡 Je peux **chercher dans le rapport** (avec citations), **calculer des COP/SCOP**, "
        "**tracer des graphiques** et **afficher des figures** du rapport.",
        icon="🔥",
    )

# ---- Chat history ----
for message in st.session_state.messages:
    role = message["role"]
    avatar = {"user": "👤", "assistant": "🤖", "tool": "🛠️", "state": "📊"}.get(
        role, "💬"
    )

    if role == "user":
        # Put user messages into c2
        _, c2 = st.columns([2, 20], gap="small")
        with c2:
            st.chat_message("user", avatar=avatar).markdown(message["content"])
    elif role == "tool":
        with st.chat_message("tool", avatar=avatar):
            tool_data = message["content"]
            if (
                isinstance(tool_data, dict)
                and "name" in tool_data
                and "body" in tool_data
            ):
                with st.expander(label=f"{tool_data['name']}", expanded=False):
                    st.markdown(tool_data["body"])
            else:
                st.markdown(str(tool_data))
    elif role == "state":
        with st.chat_message("state", avatar=avatar):
            content = message["content"]
            if isinstance(content, dict):
                for key, value in content.items():
                    plain_label = state_label(key)
                    if (
                        isinstance(value, dict)
                        and "type" in value
                        and "data" in value
                        and value["type"].startswith("image/")
                    ):
                        render_base64_image(value["data"])
                    else:
                        with st.expander(label=f"{plain_label}", expanded=False):
                            if isinstance(value, (dict, list)):
                                st.json(value)
                            elif isinstance(value, str):
                                try:
                                    st.json(json.loads(value))
                                except json.JSONDecodeError:
                                    st.markdown(f"```\n{value}\n```")
                            else:
                                st.write(value)
    else:
        with st.chat_message(role, avatar=avatar):
            st.markdown(message["content"])

# ---- Saisie / question d'exemple ----
prompt = st.chat_input("Posez votre question sur le rapport ou les mesures…")
if not prompt:
    prompt = st.session_state.pop("pending_prompt", None)
if prompt:
    handle_user_query(prompt)
