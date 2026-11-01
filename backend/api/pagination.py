"""Library-backed pagination with bounded console defaults."""

from fastapi import Query
from fastapi_pagination import Page as BasePage
from fastapi_pagination import Params as BaseParams
from fastapi_pagination.ext.asyncpg import apaginate


class Params(BaseParams):
    size: int = Query(50, ge=1, le=1000)


class Page[T](BasePage[T]):
    __params_type__ = Params


async def query_page(db, query, args, params):
    """Run count and page queries in a consistent read snapshot."""
    async with db.transaction(isolation="repeatable_read", readonly=True):
        return await apaginate(db, query, *args, params=params)
