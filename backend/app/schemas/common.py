from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class StrictCamelModel(CamelModel):
    """Request body contract: a field the API does not have is an error.

    ``CamelModel`` keeps Pydantic's default ``extra="ignore"``, which makes a
    stale or invented field look like it was accepted. Nothing here serves an
    old cached client, so request models reject unknown keys instead of
    silently dropping them.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class DataEnvelope(CamelModel, Generic[T]):
    data: T


class Meta(CamelModel):
    page: int
    page_size: int
    total: int


class Paginated(CamelModel, Generic[T]):
    data: list[T]
    meta: Meta


class PaginationParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1, le=10000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 25,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def ok(data: Any, meta: dict | None = None) -> dict[str, Any]:
    body = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def paged(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    return {
        "data": items,
        "meta": {
            "page": page,
            "pageSize": page_size,
            "total": total,
        },
    }

