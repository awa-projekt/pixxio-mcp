import base64
import json

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from pixxio_mcp.client import Pixxio
from pixxio_mcp.config import api_url
from pixxio_mcp.server import StaticToken, create_server

API = "https://media.example.com/api/v1"
PNG = b"\x89PNG\r\n\x1a\n-not-really-a-png"


def server() -> Client:
    return Client(create_server(Pixxio(API, "secret-key")))


def sent(route: respx.Route) -> dict:
    """The query of the route's last request, JSON values decoded."""
    params = dict(route.calls.last.request.url.params)
    return {name: json.loads(value) if value[:1] in "[{" else value for name, value in params.items()}


def test_api_url_takes_any_form_of_the_mediaspace():
    for given in ("example.pixxio.media", "https://example.pixxio.media/", "https://example.pixxio.media/api/v1/"):
        assert api_url(given) == "https://example.pixxio.media/api/v1"


@respx.mock
async def test_search_files_matches_every_word_anywhere():
    route = respx.get(f"{API}/files").respond(
        json={"success": True, "quantity": 1, "files": [{"id": 7, "fileName": "Bicycle_Red.png"}]}
    )
    async with server() as client:
        result = await client.call_tool("search_files", {"query": "Red bicycle", "file_type": "image"})

    assert result.structured_content == {"quantity": 1, "page": 1, "files": [{"id": 7, "fileName": "Bicycle_Red.png"}]}
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-key"
    query = sent(route)
    assert query["filter"] == {
        "filterType": "connectorAnd",
        "filters": [
            {"filterType": "fileType", "fileType": "image"},
            {"filterType": "searchTerm", "term": "Red"},
            {"filterType": "searchTerm", "term": "bicycle"},
        ],
    }
    assert "semanticQuery" not in query


@respx.mock
async def test_search_files_by_name_looks_at_file_name_and_title():
    route = respx.get(f"{API}/files").respond(json={"success": True, "quantity": 0, "files": []})
    async with server() as client:
        await client.call_tool("search_files", {"query": "Campaign", "match": "name"})

    assert sent(route)["filter"] == {
        "filterType": "connectorOr",
        "filters": [{"filterType": "fileName", "term": "Campaign"}, {"filterType": "subject", "term": "Campaign"}],
    }


@respx.mock
async def test_semantic_search_sends_the_query_as_such():
    route = respx.get(f"{API}/files").respond(json={"success": True, "quantity": 0, "files": []})
    async with server() as client:
        await client.call_tool("search_files", {"query": "a red bicycle in front of a wall", "match": "semantic"})

    query = sent(route)
    assert query["semanticQuery"] == "a red bicycle in front of a wall"
    assert "filter" not in query


@respx.mock
async def test_search_images_answers_with_the_images_themselves():
    preview = "https://image.example.com/signed/1500/7.png"
    route = respx.get(f"{API}/files").respond(
        json={
            "success": True,
            "quantity": 12,
            "files": [
                {
                    "id": 7,
                    "fileName": "Bicycle_Red_Side.png",
                    "subject": "Red bicycle",
                    "recognizedText": ["ACME", "MODEL 3"],
                    "modifiedPreviewFileURLs": [preview],
                },
                {"id": 8, "fileName": "Bicycle_Blue.png", "modifiedPreviewFileURLs": []},
            ],
        }
    )
    image = respx.get(preview).respond(content=PNG, headers={"content-type": "image/png"})
    async with server() as client:
        result = await client.call_tool("search_images", {"query": "Bicycle", "limit": 2, "max_size": 800})

    assert result.structured_content is None
    kinds = [block.type for block in result.content]
    assert kinds == ["text", "text", "image", "text", "text"]
    assert result.content[0].text == "12 images match 'Bicycle'; the first 2 follow."
    assert "File 7: Bicycle_Red_Side.png — Red bicycle" in result.content[1].text
    assert "ACME | MODEL 3" in result.content[1].text
    assert result.content[2].mime_type == "image/png"
    assert base64.b64decode(result.content[2].data) == PNG
    assert result.content[4].text == "File 8 has no preview to look at."
    assert sent(route)["previewFileOptions"] == [{"maxSize": 800}]
    assert "Authorization" not in image.calls.last.request.headers


@respx.mock
async def test_a_semantic_image_search_says_the_images_are_the_closest():
    respx.get(f"{API}/files").respond(
        json={
            "success": True,
            "quantity": 639,
            "files": [{"id": 3, "fileName": "bicycle.png", "modifiedPreviewFileURLs": []}],
        }
    )
    async with server() as client:
        result = await client.call_tool(
            "search_images", {"query": "a bicycle at sunset", "match": "semantic", "limit": 1}
        )

    assert result.content[0].text == "The image closest to 'a bicycle at sunset' follows."


@respx.mock
async def test_view_files_keeps_the_order_asked_for():
    respx.get(f"{API}/files").respond(
        json={
            "success": True,
            "files": [
                {"id": 2, "fileName": "b.png", "modifiedPreviewFileURLs": []},
                {"id": 1, "fileName": "a.png", "modifiedPreviewFileURLs": []},
            ],
        }
    )
    async with server() as client:
        result = await client.call_tool("view_files", {"file_ids": [1, 2]})

    assert result.content[0].text.startswith("File 1: a.png")
    assert result.content[2].text.startswith("File 2: b.png")


@respx.mock
async def test_a_refused_request_is_the_tools_error():
    respx.get(f"{API}/files/99").respond(
        404, json={"success": False, "errorcode": 2454, "errormessage": "The specified file ID does not exist."}
    )
    async with server() as client:
        with pytest.raises(ToolError, match="The specified file ID does not exist"):
            await client.call_tool("get_file", {"file_id": 99})


@respx.mock
async def test_an_unreachable_pixxio_is_the_tools_error():
    respx.get(f"{API}/collections").mock(side_effect=httpx.ConnectError("refused"))
    async with server() as client:
        with pytest.raises(ToolError, match="not reachable"):
            await client.call_tool("list_collections", {})


async def test_every_tool_is_read_only():
    async with server() as client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools} == {
        "search_files",
        "get_file",
        "view_files",
        "search_images",
        "list_collections",
        "list_directories",
    }
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools)


async def test_the_token_has_to_match():
    verifier = StaticToken("s3cret")
    assert await verifier.verify_token("s3cret") is not None
    assert await verifier.verify_token("wrong") is None
