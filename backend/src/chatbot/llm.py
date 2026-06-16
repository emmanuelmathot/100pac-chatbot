from langchain_mistralai import ChatMistralAI
from pydantic import SecretStr

from chatbot.settings import get_settings

settings = get_settings()

mistral_small = ChatMistralAI(
    model_name="mistral-small-latest",
    api_key=SecretStr(settings.mistral_api_key),
    temperature=0.0,
)
