from typing import Generic, TypeVar

from pydantic import BaseModel

Body = TypeVar("Body")


class APIResponse(BaseModel, Generic[Body], frozen=True):
    body: Body
    headers: dict[str, list[str]]
