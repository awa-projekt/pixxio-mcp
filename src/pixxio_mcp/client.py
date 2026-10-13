"""pixx.io's v1 REST API (https://api.pixxio.com/docs), the read-only part this server needs.

Every request carries the API key as a bearer token. Arrays and objects in the query (`filter`,
`responseFields`, `previewFileOptions`) go as JSON. pixx.io answers `{"success": true, ...}`, or
`{"success": false, "errormessage": ...}`, with a 4xx status or without one.

Preview URLs come signed and are meant to be fetched as they are, so the key only goes to the API.
"""

import json
from typing import Any, Literal

import httpx

Match = Literal["anywhere", "name", "semantic"]


class PixxioError(Exception):
    """pixx.io refused a request or could not be reached; the message says why."""


def term_filters(query: str, match: Match) -> list[dict[str, Any]]:
    """Every word of `query` has to match: anywhere pixx.io's search box looks (`anywhere`), or in
    the file name or title (`name`). A semantic query is no filter but a parameter of its own."""
    if match == "semantic":
        return []
    if match == "name":
        return [
            {
                "filterType": "connectorOr",
                "filters": [{"filterType": "fileName", "term": word}, {"filterType": "subject", "term": word}],
            }
            for word in query.split()
        ]
    return [{"filterType": "searchTerm", "term": word} for word in query.split()]


def files_filter(filters: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not filters:
        return None
    return filters[0] if len(filters) == 1 else {"filterType": "connectorAnd", "filters": filters}


def query_params(params: dict[str, Any]) -> dict[str, str | int]:
    encoded: dict[str, str | int] = {}
    for name, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            encoded[name] = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            encoded[name] = json.dumps(value)
        else:
            encoded[name] = value
    return encoded


class Pixxio:
    def __init__(self, api_url: str, api_key: str, http: httpx.AsyncClient | None = None):
        self.api_url = api_url.rstrip("/")
        self._key = api_key
        self._http = http or httpx.AsyncClient(timeout=30)

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        try:
            response = await self._http.get(
                f"{self.api_url}{path}",
                headers={"Authorization": f"Bearer {self._key}"},
                params=query_params(params),
            )
        except httpx.HTTPError as error:
            raise PixxioError(f"pixx.io is not reachable: {type(error).__name__}: {error}") from error
        try:
            body = response.json()
        except ValueError as error:
            raise PixxioError(f"pixx.io answered {response.status_code} without JSON") from error
        if not isinstance(body, dict) or body.get("success") is not True:
            message = body.get("errormessage") if isinstance(body, dict) else None
            raise PixxioError(f"pixx.io refused the request: {message or f'status {response.status_code}'}")
        return body

    async def files(
        self,
        *,
        filters: list[dict[str, Any]],
        fields: list[str],
        page: int = 1,
        page_size: int = 20,
        semantic_query: str | None = None,
        sort_by: str | None = None,
        sort_direction: str | None = None,
        preview_size: int | None = None,
    ) -> dict[str, Any]:
        return await self.get(
            "/files",
            filter=files_filter(filters),
            responseFields=fields,
            page=page,
            pageSize=page_size,
            semanticQuery=semantic_query,
            sortBy=sort_by,
            sortDirection=sort_direction,
            previewFileOptions=[{"maxSize": preview_size}] if preview_size else None,
            approximateQuantity=True,
        )

    async def file(self, file_id: int, *, fields: list[str]) -> dict[str, Any]:
        body = await self.get(
            f"/files/{file_id}",
            responseFields=fields,
            directoryResponseFields=["id", "name"],
            staticCollectionsResponseFields=["id", "name"],
        )
        return body["file"]

    async def collections(self, *, query: str | None, page: int, page_size: int) -> dict[str, Any]:
        return await self.get(
            "/collections",
            searchTerm=query or None,
            responseFields=["id", "name", "description", "filesQuantity"],
            page=page,
            pageSize=page_size,
            sortBy="name",
            sortDirection="asc",
        )

    async def directories(self, *, parent_id: int | None) -> list[dict[str, Any]]:
        body = await self.get(
            "/directories/tree",
            parentID=parent_id,
            responseFields=["id", "name", "hasChildren", "quantity"],
            showChildren=True,
        )
        return body.get("children") or []

    async def preview(self, url: str) -> tuple[bytes, str]:
        """A preview image and its MIME type."""
        try:
            response = await self._http.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise PixxioError(f"pixx.io's preview could not be loaded: {type(error).__name__}: {error}") from error
        return response.content, response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
