# AGENTS.md

Guidelines for AI agents working on the `sabi` project. Read this before making changes.

## Project overview

`sabi` extracts company records from [SABI Informa](https://sabi.informa.es) to CSV and SQLite, with optional embeddings for similarity search. It includes a Model Context Protocol (MCP) server so AI agents can query the API.

Project name: `sabi` (renamed from `sabi-extractor`).
Package: `src/`
Entry points: `sabi` (CLI), `sabi-mcp` (MCP server).

## Module map

| File | Purpose |
|------|---------|
| `src/cli.py` | CLI (`sabi` console script). Parses args, establishes session, searches, writes CSV, upserts to SQLite. |
| `src/mcp_server.py` | MCP server (`sabi-mcp` console script). Exposes 7 tools over stdio/streamable-http. |
| `src/extractor.py` | `SABIClient`: HTTP client with credential + network/IP auth, search, pagination, detail-page fetching, HTML parsing via CSS selectors. |
| `src/models.py` | `Record` dataclass (name, cif, address, city, province, postal_code, phone, activity, detail_url, extras). |
| `src/utils.py` | `CSV_FIELDS`, `clean()`, `record_to_row()`, `write_csv()`. |
| `src/embeddings.py` | `EmbeddingStore`: SQLite-backed store with deterministic-hash or sentence-transformers embeddings, upsert, similarity search. |
| `src/__init__.py` | Package marker, `__version__ = "1.0.0"`. |
| `bin/sabi` | Executable wrapper for `src.cli:main` (no install needed). |
| `bin/sabi-mcp` | Executable wrapper for `src.mcp_server:main`. |
| `__main__.py` | Root entry point (`python /path/to/repo`). |
| `tests/test_extractor.py` | Unit tests (7 tests). |
| `pyproject.toml` | Packaging, ruff config, pytest config, console scripts. |
| `docker/Dockerfile` | Multi-stage image (base/deps/runtime/dev), exposes port 8000. |
| `docker-compose.yml` | `sabi` (CLI) + `sabi-mcp` (streamable-http on :8000) services. |
| `requirements.txt` | Runtime deps: requests, beautifulsoup4, mcp. |
| `USAGE.md` | Full CLI/MCP usage reference with examples. |
| `README.md` | Project overview, quick start, MCP tools table, Docker. |

## Authentication modes

`SABIClient.login(username="", password="")` supports two modes:

1. **Credential flow** — when username and password are provided: two-step POST (username, then password) with CSRF token discovery from the login page.
2. **Network/IP flow** — when no credentials are given: fetches login + search pages to establish a session via IP-authenticated network (e.g. NOVA SBE wifi). Sets `authenticated = True`.

The CLI never requires credentials anymore. Run `./bin/sabi --search "..."` directly on an IP-authenticated network. Provide `--username`/`--password` (or `SABI_USERNAME`/`SABI_PASSWORD`) for credential-based auth.

## MCP tools

`src/mcp_server.py` exposes these tools (all return JSON strings):

| Tool | Key args | Description |
|------|----------|-------------|
| `sabi_login` | — | Authenticate via env vars or network auth |
| `sabi_search` | `query`, `max_pages`, `detail` | Search companies, paginated |
| `sabi_get_record` | `detail_url` | Fetch single detail page |
| `sabi_export_csv` | `query`, `max_pages`, `output`, `fields`, `detail` | Search + export to CSV |
| `sabi_store_records` | `query`, `max_pages`, `detail`, `db_path` | Search + upsert to SQLite |
| `sabi_similarity_search` | `query`, `limit`, `db_path` | Semantic similarity over stored records |
| `sabi_list_stored` | `db_path` | List all stored records |

Run MCP server: `sabi-mcp --transport stdio` or `--transport streamable-http --port 8000`.

## Development workflow

Install dev dependencies:
```bash
pip install -e ".[dev]"
```

Run tests:
```bash
pytest
```

Lint:
```bash
ruff check .
ruff format --check .
```

Format:
```bash
ruff format .
```

Typecheck (mentioned in README, not enforced in CI yet):
```bash
mypy src/
```

## Coding conventions

- Python 3.10+ (`requires-python = ">=3.10"` in pyproject.toml)
- Use `from __future__ import annotations` at top of every module
- Line length: 88 (ruff config)
- Import order: stdlib, third-party, then `from .` relative imports (isort `known-first-party = ["src"]`)
- Use `X | None` union syntax instead of `Optional[X]`
- Use `collections.abc` for `Iterable`, `Mapping`, `Sequence` instead of `typing`
- No comments unless asked (per project instructions)
- All tools return JSON strings; wrap exceptions in `{"error": "..."}` or `{"status": "error", "error": "..."}`
- Dataclass `Record` uses `extras: dict = field(default_factory=dict)` for passthrough fields
- Tests live in `tests/test_extractor.py`, run with pytest

## Key constants

- `BASE_URL = "https://sabi.informa.es"` (extractor.py)
- `LOGIN_PAGE_URL = BASE_URL + "/ip"`
- `SEARCH_URL = BASE_URL + "/R1/SabiInforma/Search"`
- `CSV_FIELDS = [name, cif, address, city, province, postal_code, phone, activity, detail_url]` (utils.py)
- `SELECTORS` dict maps CSS selectors for record rows and fields (extractor.py)

## Docker

Build: `docker build -t sabi -f docker/Dockerfile .`
Run CLI: `docker run --rm -v ./data:/data sabi --search "..." --output /data/out.csv`
Run MCP: `docker compose up sabi-mcp` (streamable-http on :8000)

## Git conventions

Conventional Commits format: `<type>(scope): <short description>`. Types: feat, fix, refactor, docs, test, chore, build. Atomic commits only — group logically related changes, skip lock files/build artifacts.
