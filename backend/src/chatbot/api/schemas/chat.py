from pydantic import UUID4, BaseModel


class ChatRequestBody(BaseModel):
    query: str
    thread_id: UUID4
