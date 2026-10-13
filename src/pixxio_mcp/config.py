"""Settings, from the environment and a `.env` in the working directory."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    # A bearer token every MCP request must carry; unset, the server takes requests without one.
    token: str | None


def api_url(raw: str) -> str:
    """The mediaspace's v1 API, however much of it is given: `example.pixxio.media`,
    `https://example.pixxio.media` and `https://example.pixxio.media/api/v1` are the same."""
    url = raw.strip().rstrip("/")
    if "://" not in url:
        url = f"https://{url}"
    return url if url.endswith("/api/v1") else f"{url}/api/v1"


def load() -> Settings:
    load_dotenv()
    url = os.getenv("PIXXIO_URL", "").strip()
    key = os.getenv("PIXXIO_API_KEY", "").strip()
    missing = [name for name, value in (("PIXXIO_URL", url), ("PIXXIO_API_KEY", key)) if not value]
    if missing:
        raise SystemExit(f"pixxio-mcp: {' and '.join(missing)} not set, see .env.example")
    return Settings(api_url=api_url(url), api_key=key, token=os.getenv("PIXXIO_MCP_TOKEN") or None)
