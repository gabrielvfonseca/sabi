# SABI

Extract company records from [SABI Informa](https://sabi.informa.es) to CSV and SQLite, with optional embeddings for similarity search. Includes a Model Context Protocol (MCP) server so agents can query the API.

## Features

- Dual authentication: credential-based (username/password) and network/IP-based (e.g. NOVA SBE wifi)
- Search and paginate company listings
- Parse records into CSV (name, CIF, address, city, province, postal code, phone, activity)
- Store records with embeddings in SQLite for similarity search
- Deterministic hash embeddings by default (no ML dependencies required)
- Optional `sentence-transformers` backend for real embeddings
- MCP server exposing search, export, storage, and similarity search as agent tools
- Executable `bin/` scripts for running without installation
- Multiple MCP transports: stdio, SSE, streamable-HTTP
- Cookie persistence (`--cookie-file`) for resuming authenticated sessions
- Retry with exponential backoff on transient HTTP errors
- CSV import/export round-trip and JSON output
- Full record fidelity in SQLite (all fields + extras serialized as JSON)

## Installation

```bash
pip install -e .
```

With embeddings support:

```bash
pip install -e ".[embeddings]"
```

## Quick start

### Run via `bin/` (no installation required)

```bash
export SABI_USERNAME="your-username"
export SABI_PASSWORD="your-password"

./bin/sabi --search "madrid software" \
    --output records.csv --db records.sqlite
```

### Run via the installed entry point

```bash
sabi --search "madrid software" \
    --output records.csv --db records.sqlite
```

### Run via root `__main__.py`

```bash
python /path/to/sabi --search "madrid software" \
    --output records.csv --db records.sqlite
```

Credentials can also be provided via the `SABI_USERNAME` and `SABI_PASSWORD` environment variables.

## MCP server (for agents)

The package includes an MCP server at `src.mcp_server` that exposes SABI Informa as queryable tools for AI agents.

Run over stdio (for agent/CLI clients):

```bash
sabi-mcp --transport stdio
```

Or over streamable-HTTP:

```bash
sabi-mcp --transport streamable-http --port 8000
```

Or via SSE:

```bash
sabi-mcp --transport sse --port 8000
```

Or via the executable bin script:

```bash
./bin/sabi-mcp --transport stdio
```

### MCP tools

| Tool | Description |
|------|-------------|
| `sabi_login` | Authenticate using `SABI_USERNAME` / `SABI_PASSWORD` env vars |
| `sabi_search` | Search companies matching a query (paginated, optional detail enrichment) |
| `sabi_get_record` | Fetch a single company detail page by URL |
| `sabi_export_csv` | Search and export matching records to CSV |
| `sabi_store_records` | Search and upsert records (with embeddings) into SQLite |
| `sabi_similarity_search` | Semantic similarity search over stored records |
| `sabi_list_stored` | List all records stored in the SQLite database |
| `sabi_list_fields` | List the available record field names |
| `sabi_import_csv` | Import records from a CSV file/text into the SQLite store |
| `sabi_delete_record` | Delete a stored record by CIF |

Example agent call:

```json
{
  "name": "sabi_search",
  "arguments": { "query": "madrid software", "max_pages": 3 }
}
```

## Docker

Build the image:

```bash
docker build -t sabi -f docker/Dockerfile .
```

Run it, mounting a local directory for outputs:

```bash
docker run --rm \
  -e SABI_USERNAME="$SABI_USERNAME" \
  -e SABI_PASSWORD="$SABI_PASSWORD" \
  -v "$PWD/data:/data" \
  sabi --search "madrid software" \
    --output /data/sabi_records.csv \
    --db /data/sabi_records.sqlite
```

Run the MCP server over streamable-http:

```bash
docker compose up sabi-mcp
```

## Development

```bash
# install dev dependencies
pip install -e ".[dev]"

# run tests
pytest

# lint
ruff check .
ruff format --check .

# typecheck
mypy src/
```

## License

MIT
