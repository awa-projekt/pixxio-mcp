"""The MCP server: a pixx.io mediaspace's files to search, read and look at, read-only.

It serves over streamable HTTP at `/mcp` by default, `--transport stdio` for a local client.
"""

import argparse
import asyncio
import base64
import hmac
import os
from collections.abc import Awaitable
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import Field

from . import config
from .client import Match, Pixxio, PixxioError, term_filters

# What a search answers per file; get_file adds the rest.
FILE_FIELDS = ["id", "fileName", "subject", "fileType", "fileExtension", "width", "height", "keywords", "uploadDate"]
DETAIL_FIELDS = [
    *FILE_FIELDS,
    "description",
    "fileSize",
    "createDate",
    "modifyDate",
    "creator",
    "rating",
    "recognizedText",
    "directory",
    "staticCollections",
    "previewFileURL",
]
VIEW_FIELDS = ["id", "fileName", "subject", "recognizedText", "modifiedPreviewFileURLs"]

INSTRUCTIONS = (
    "A pixx.io media library. search_files finds files and lists their metadata, get_file reads one "
    "file's metadata, view_files shows images to look at, and search_images does both in one call. "
    "list_collections and list_directories show how the library is organized; their ids narrow a search."
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)

Query = Annotated[str, Field(description="Words to search for; every word has to match.")]
MatchIn = Annotated[
    Match,
    Field(
        description=(
            "Where the words have to match: 'anywhere' searches like pixx.io's search box (name, title, "
            "keywords, description and more), 'name' only the file name and title, 'semantic' searches "
            "by meaning, e.g. 'a red bicycle in front of a brick wall'."
        )
    ),
]
CollectionId = Annotated[int | None, Field(description="Only files in this collection, see list_collections.")]
DirectoryId = Annotated[
    int | None, Field(description="Only files in this directory and its subdirectories, see list_directories.")
]
PreviewSize = Annotated[int, Field(ge=100, le=4000, description="Long side of each image in pixels.")]


class StaticToken(TokenVerifier):
    """Requests carry `Authorization: Bearer <token>` with the one token the server is configured with."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token.encode()

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token.encode(), self._token):
            return None
        return AccessToken(token=token, client_id="pixxio-mcp", scopes=[])


def scope_filters(
    *, file_type: str | None = None, collection_id: int | None = None, directory_id: int | None = None
) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    if file_type:
        filters.append({"filterType": "fileType", "fileType": file_type})
    if collection_id is not None:
        filters.append({"filterType": "collection", "collectionID": collection_id})
    if directory_id is not None:
        filters.append({"filterType": "directory", "directoryID": directory_id, "includeSubdirectories": True})
    return filters


def describe(file: dict[str, Any]) -> str:
    named = " — ".join(str(part) for part in (file.get("fileName"), file.get("subject")) if part)
    text = f"File {file['id']}: {named}"
    recognized = [line for line in file.get("recognizedText") or [] if line]
    if recognized:
        text += "\nText pixx.io recognized on it: " + " | ".join(map(str, recognized))
    return text


def create_server(pixxio: Pixxio, *, token: str | None = None) -> FastMCP:
    mcp = FastMCP("pixxio", instructions=INSTRUCTIONS, auth=StaticToken(token) if token else None)

    async def call[T](request: Awaitable[T]) -> T:
        try:
            return await request
        except PixxioError as error:
            raise ToolError(str(error)) from error

    async def with_previews(files: list[dict[str, Any]]) -> list[TextContent | ImageContent]:
        """Each file as a line of text, then its image."""

        async def blocks(file: dict[str, Any]) -> list[TextContent | ImageContent]:
            text = TextContent(type="text", text=describe(file))
            previews = file.get("modifiedPreviewFileURLs") or []
            if not previews:
                return [text, TextContent(type="text", text=f"File {file['id']} has no preview to look at.")]
            try:
                data, mime_type = await pixxio.preview(previews[0])
            except PixxioError as error:
                return [text, TextContent(type="text", text=f"File {file['id']}: {error}")]
            return [text, ImageContent(type="image", data=base64.b64encode(data).decode("ascii"), mime_type=mime_type)]

        return [block for group in await asyncio.gather(*(blocks(file) for file in files)) for block in group]

    @mcp.tool(annotations=READ_ONLY)
    async def search_files(
        query: Query = "",
        match: MatchIn = "anywhere",
        file_type: Annotated[
            Literal["image", "video", "audio"] | None, Field(description="Only files of this type.")
        ] = None,
        collection_id: CollectionId = None,
        directory_id: DirectoryId = None,
        sort_by: Annotated[
            Literal["uploadDate", "modifyDate", "createDate", "fileName", "rating"] | None,
            Field(description="Sort order; pixx.io's own when unset (by relevance for a semantic search)."),
        ] = None,
        descending: bool = True,
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        """Search the media library's files and list their metadata: id, file name, title (subject),
        type, size in pixels, keywords and upload date. `quantity` says how many match in all; page
        through them with `page`. An empty query lists every file the filters allow."""
        filters = [
            *scope_filters(file_type=file_type, collection_id=collection_id, directory_id=directory_id),
            *term_filters(query, match),
        ]
        body = await call(
            pixxio.files(
                filters=filters,
                fields=FILE_FIELDS,
                page=page,
                page_size=page_size,
                semantic_query=query if match == "semantic" and query.strip() else None,
                sort_by=sort_by,
                sort_direction=("desc" if descending else "asc") if sort_by else None,
            )
        )
        return {"quantity": body.get("quantity", 0), "page": page, "files": body.get("files") or []}

    @mcp.tool(annotations=READ_ONLY)
    async def get_file(file_id: Annotated[int, Field(description="The file's id.")]) -> dict[str, Any]:
        """One file's metadata: what search_files lists, and its description, file size, dates,
        creator, rating, the text pixx.io recognized on it, its directory and collections, and a
        preview URL to show it."""
        return await call(pixxio.file(file_id, fields=DETAIL_FIELDS))

    @mcp.tool(annotations=READ_ONLY, output_schema=None)
    async def view_files(
        file_ids: Annotated[list[int], Field(min_length=1, max_length=10, description="The files' ids.")],
        max_size: PreviewSize = 1500,
    ) -> list[TextContent | ImageContent]:
        """Look at files: each file's id, name and title, the text pixx.io recognized on it, then the
        image itself. Works for images and for any file pixx.io renders a preview of (PDFs, videos)."""
        body = await call(
            pixxio.files(
                filters=[{"filterType": "files", "fileIDs": file_ids}],
                fields=VIEW_FIELDS,
                page_size=len(file_ids),
                preview_size=max_size,
            )
        )
        order = {file_id: index for index, file_id in enumerate(file_ids)}
        files = sorted(body.get("files") or [], key=lambda file: order.get(file["id"], len(order)))
        return await with_previews(files)

    @mcp.tool(annotations=READ_ONLY, output_schema=None)
    async def search_images(
        query: Query,
        match: MatchIn = "anywhere",
        collection_id: CollectionId = None,
        directory_id: DirectoryId = None,
        limit: Annotated[int, Field(ge=1, le=10, description="How many images to look at.")] = 4,
        max_size: PreviewSize = 1500,
    ) -> list[TextContent | ImageContent]:
        """Search the images and look at the first few: says how many match, then each image's id,
        name and title, the text pixx.io recognized on it, and the image itself. A more specific
        query narrows them."""
        filters = [
            *scope_filters(file_type="image", collection_id=collection_id, directory_id=directory_id),
            *term_filters(query, match),
        ]
        body = await call(
            pixxio.files(
                filters=filters,
                fields=VIEW_FIELDS,
                page_size=limit,
                semantic_query=query if match == "semantic" else None,
                preview_size=max_size,
            )
        )
        files = body.get("files") or []
        if not files:
            return [TextContent(type="text", text=f"No image matches {query!r}.")]
        quantity = body.get("quantity", len(files))
        if match == "semantic":
            summary = (
                f"The image closest to {query!r} follows."
                if len(files) == 1
                else f"The {len(files)} images closest to {query!r} follow, the closest first."
            )
        else:
            summary = f"{quantity} images match {query!r}" + (
                f"; the first {len(files)} follow." if quantity > len(files) else "."
            )
        return [TextContent(type="text", text=summary), *await with_previews(files)]

    @mcp.tool(annotations=READ_ONLY)
    async def list_collections(
        query: Annotated[str, Field(description="Only collections whose name has these words.")] = "",
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = 50,
    ) -> dict[str, Any]:
        """The library's collections by name: id, name, description and how many files each holds.
        A collection id narrows search_files and search_images."""
        body = await call(pixxio.collections(query=query, page=page, page_size=page_size))
        return {"quantity": body.get("quantity", 0), "page": page, "collections": body.get("collections") or []}

    @mcp.tool(annotations=READ_ONLY)
    async def list_directories(
        parent_id: Annotated[
            int | None, Field(description="List this directory's subdirectories; unset, the top level.")
        ] = None,
    ) -> list[dict[str, Any]]:
        """The library's directories, one level: id, name, whether it has subdirectories, and how many
        files it holds. A directory id narrows search_files and search_images."""
        return await call(pixxio.directories(parent_id=parent_id))

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a pixx.io mediaspace as MCP tools.")
    parser.add_argument("--transport", choices=["http", "stdio"], default=os.getenv("PIXXIO_MCP_TRANSPORT", "http"))
    parser.add_argument("--host", default=os.getenv("PIXXIO_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PIXXIO_MCP_PORT", "8000")))
    args = parser.parse_args()

    settings = config.load()
    server = create_server(Pixxio(settings.api_url, settings.api_key), token=settings.token)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
