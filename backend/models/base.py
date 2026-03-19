from typing import Generic, TypeVar, List, Optional, Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    data: List[T]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(cls, data: list, total: int, page: int, limit: int):
        pages = (total + limit - 1) // limit if limit > 0 else 1
        return cls(data=data, total=total, page=page, limit=limit, pages=pages)


class ErrorResponse(BaseModel):
    type: str = "https://raxus.io/errors/generic"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    request_id: Optional[str] = None


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)
