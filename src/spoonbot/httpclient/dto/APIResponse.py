from typing import Generic, TypeVar

from multidict import CIMultiDictProxy
from pydantic import BaseModel

Body = TypeVar("Body")


class APIResponse(BaseModel, Generic[Body], frozen=True):
    body: Body
    headers: CIMultiDictProxy[str]
