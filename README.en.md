# pixxio-mcp

[Deutsch](README.md) | English

An [MCP](https://modelcontextprotocol.io) server for a [pixx.io](https://www.pixx.io) mediaspace: search
its files, read their metadata and look at its images. Read-only, on pixx.io's
[v1 REST API](https://api.pixxio.com/docs), served over streamable HTTP by default.

## Tools

| Tool | What it does |
| --- | --- |
| `search_files` | Finds files and lists their metadata: id, file name, title, type, size, keywords, upload date. Every word of the query has to match, anywhere pixx.io's search box looks (`match: "anywhere"`), only in the file name and title (`"name"`), or by meaning (`"semantic"`, pixx.io's semantic search). Narrows by file type, collection and directory; sorts and pages. |
| `get_file` | One file's metadata: the above, and its description, file size, dates, creator, rating, the text pixx.io recognized on it, its directory and collections, and a preview URL. |
| `view_files` | Looks at files by id: each one's name and title, the text pixx.io recognized on it, then the image itself as MCP image content, so a model sees it. |
| `search_images` | `search_files` for images and `view_files` for the first few in one call: how many match, then each image. |
| `list_collections` | The collections by name, with how many files each holds. |
| `list_directories` | The directories, one level at a time. |

Collection and directory ids from the last two narrow the searches. Images come as previews, their long
side `max_size` pixels (1500 by default): large enough to read a label, small enough for a model's
context.

## Run

```bash
uv sync
cp .env.example .env      # PIXXIO_URL and PIXXIO_API_KEY
uv run pixxio-mcp         # http://127.0.0.1:8000/mcp
```

| Variable | Default | |
| --- | --- | --- |
| `PIXXIO_URL` | required | The mediaspace, e.g. `https://example.pixxio.media`; `/api/v1` may be given or not. |
| `PIXXIO_API_KEY` | required | The API key of a pixx.io user; the server sees what that user sees. |
| `PIXXIO_MCP_TOKEN` | unset | A bearer token every MCP request has to carry. Set it whenever others can reach the server. |
| `PIXXIO_MCP_TRANSPORT` | `http` | `stdio` for a client that starts the server itself. |
| `PIXXIO_MCP_HOST` | `127.0.0.1` | `0.0.0.0` in the image. |
| `PIXXIO_MCP_PORT` | `8000` | |

`--transport`, `--host` and `--port` override the last three.

Docker:

```bash
docker build -t pixxio-mcp .
docker run --env-file .env -p 8000:8000 pixxio-mcp
```

The GitLab CI (`.gitlab-ci.yml`) tests every commit; on the default branch it also builds the image and
pushes it to the project's registry as `:latest` and `:<commit>`.

## Connect a client

Claude Code:

```bash
claude mcp add --transport http pixxio http://127.0.0.1:8000/mcp
# with PIXXIO_MCP_TOKEN set:
claude mcp add --transport http pixxio http://127.0.0.1:8000/mcp --header "Authorization: Bearer <token>"
```

Anything else that speaks streamable HTTP takes the same URL; a client that only speaks stdio runs
`uv run --directory <checkout> pixxio-mcp --transport stdio`.

## Develop

```bash
uv run pytest
```

The tests run the server in memory against a mocked pixx.io (`respx`), no mediaspace needed.

Layout: `src/pixxio_mcp/client.py` is the pixx.io API client and its filters, `server.py` the tools
and the entry point, `config.py` the environment.

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright 2026 awa-projekt.
