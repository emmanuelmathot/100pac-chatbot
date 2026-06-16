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


st.session_state.setdefault("messages", [])

with st.container(horizontal=True, horizontal_alignment="right"):
    # New chat button
    if st.button("New chat", key="new-chat"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

st.title("Dev Sprint Chatbot")

# ---- App state ----
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


# ---- Helpers ----
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
        st.error(f"❌ Error connecting to API: {e}")
        return

    placeholder = st.empty()
    with placeholder.container():
        st.chat_message("assistant", avatar="🤖").markdown("🤔 Thinking about that...")

    try:
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.strip():
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue

            if "state_change" in msg:
                state_payload = msg["state_change"]
                placeholder.empty()
                with st.chat_message("state", avatar="📊"):
                    for key, value in state_payload.items():
                        plain_label = key.replace("_", " ").title()
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
                continue

            kwargs = msg.get("kwargs", {})
            msg_type = kwargs.get("type", "assistant")
            content = kwargs.get("content", "")
            tool_name = kwargs.get("name", "Tool Output")

            if msg_type == "human" or not content.strip():
                continue

            role = "assistant" if msg_type == "ai" else "tool"
            avatar = "🤖" if role == "assistant" else "🛠️"

            placeholder.empty()
            with st.chat_message(role, avatar=avatar):
                if role == "tool":
                    with st.expander(label=f"{tool_name}", expanded=False):
                        st.markdown(content)
                else:
                    st.markdown(content)

            if role == "tool":
                st.session_state.messages.append(
                    {"role": role, "content": {"name": tool_name, "body": content}}
                )
            else:
                st.session_state.messages.append({"role": role, "content": content})
    except requests.exceptions.ChunkedEncodingError:
        st.warning("⚠️ The connection dropped early. Showing the partial response.")
    finally:
        try:
            response.close()
        except Exception:
            pass


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
                    plain_label = key.replace("_", " ").title()
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

# ---- Chat input ----
if user_input := st.chat_input("Type your message here..."):
    handle_user_query(user_input)
