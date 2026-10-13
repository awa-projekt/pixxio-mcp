# pixxio-mcp

Deutsch | [English](README.en.md)

Ein [MCP](https://modelcontextprotocol.io)-Server für einen [pixx.io](https://www.pixx.io)-Mediaspace: seine
Dateien durchsuchen, ihre Metadaten lesen und seine Bilder ansehen. Nur lesend, auf der
[v1-REST-API](https://api.pixxio.com/docs) von pixx.io, standardmäßig über Streamable HTTP bereitgestellt.

## Tools

| Tool | Was es tut |
| --- | --- |
| `search_files` | Findet Dateien und listet ihre Metadaten: ID, Dateiname, Titel, Typ, Größe, Schlagwörter, Upload-Datum. Jedes Wort der Suche muss passen, überall dort, wo das Suchfeld von pixx.io sucht (`match: "anywhere"`), nur in Dateiname und Titel (`"name"`) oder nach Bedeutung (`"semantic"`, die semantische Suche von pixx.io). Schränkt nach Dateityp, Kollektion und Verzeichnis ein; sortiert und blättert. |
| `get_file` | Die Metadaten einer Datei: die obigen, dazu Beschreibung, Dateigröße, Datumsangaben, Ersteller, Bewertung, den Text, den pixx.io darauf erkannt hat, ihr Verzeichnis und ihre Kollektionen sowie eine Vorschau-URL. |
| `view_files` | Sieht sich Dateien per ID an: von jeder Name und Titel, den Text, den pixx.io darauf erkannt hat, dann das Bild selbst als MCP-Bildinhalt, sodass ein Modell es sieht. |
| `search_images` | `search_files` für Bilder und `view_files` für die ersten paar in einem Aufruf: wie viele passen, dann jedes Bild. |
| `list_collections` | Die Kollektionen nach Namen, mit der Anzahl ihrer Dateien. |
| `list_directories` | Die Verzeichnisse, eine Ebene nach der anderen. |

Kollektions- und Verzeichnis-IDs aus den letzten beiden schränken die Suchen ein. Bilder kommen als
Vorschauen, ihre lange Seite `max_size` Pixel (standardmäßig 1500): groß genug, um ein Etikett zu lesen,
klein genug für den Kontext eines Modells.

## Starten

```bash
uv sync
cp .env.example .env      # PIXXIO_URL und PIXXIO_API_KEY
uv run pixxio-mcp         # http://127.0.0.1:8000/mcp
```

| Variable | Standard | |
| --- | --- | --- |
| `PIXXIO_URL` | erforderlich | Der Mediaspace, z. B. `https://example.pixxio.media`; `/api/v1` kann dabei sein, muss aber nicht. |
| `PIXXIO_API_KEY` | erforderlich | Der API-Key eines pixx.io-Benutzers; der Server sieht, was dieser Benutzer sieht. |
| `PIXXIO_MCP_TOKEN` | nicht gesetzt | Ein Bearer-Token, das jede MCP-Anfrage mitbringen muss. Setze es, sobald andere den Server erreichen können. |
| `PIXXIO_MCP_TRANSPORT` | `http` | `stdio` für einen Client, der den Server selbst startet. |
| `PIXXIO_MCP_HOST` | `127.0.0.1` | `0.0.0.0` im Image. |
| `PIXXIO_MCP_PORT` | `8000` | |

`--transport`, `--host` und `--port` überschreiben die letzten drei.

Docker:

```bash
docker build -t pixxio-mcp .
docker run --env-file .env -p 8000:8000 pixxio-mcp
```

Die GitLab-CI (`.gitlab-ci.yml`) testet jeden Commit; auf dem Default-Branch baut sie außerdem das Image und
pusht es als `:latest` und `:<commit>` in die Registry des Projekts.

## Client verbinden

Claude Code:

```bash
claude mcp add --transport http pixxio http://127.0.0.1:8000/mcp
# mit gesetztem PIXXIO_MCP_TOKEN:
claude mcp add --transport http pixxio http://127.0.0.1:8000/mcp --header "Authorization: Bearer <token>"
```

Jeder andere Client, der Streamable HTTP spricht, nimmt dieselbe URL; ein Client, der nur stdio spricht,
startet `uv run --directory <checkout> pixxio-mcp --transport stdio`.

## Entwickeln

```bash
uv run pytest
```

Die Tests lassen den Server im Speicher gegen ein gemocktes pixx.io (`respx`) laufen, ganz ohne Mediaspace.

Aufbau: `src/pixxio_mcp/client.py` ist der Client für die pixx.io-API samt ihren Filtern, `server.py` enthält
die Tools und den Einstiegspunkt, `config.py` die Umgebung.

## Lizenz

Lizenziert unter der [Apache License 2.0](LICENSE). Copyright 2026 awa-projekt.
