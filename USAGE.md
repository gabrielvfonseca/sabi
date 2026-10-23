# Usage

`sabi` extracts company records from [SABI Informa](https://sabi.informa.es) and exports them to CSV, with optional SQLite storage and embeddings for similarity search. An MCP server (`sabi-mcp`) exposes the same capabilities as agent tools.

## Prerequisites

- Python 3.10+
- Network access to SABI Informa

Install the package:

```bash
pip install -e .
```

With embeddings support (optional `sentence-transformers` backend):

```bash
pip install -e ".[embeddings]"
```

## Credentials

Provide credentials either via flags or environment variables:

- `--username` / `--password`
- `SABI_USERNAME` / `SABI_PASSWORD` environment variables

Example:

```bash
export SABI_USERNAME="your-username"
export SABI_PASSWORD="your-password"
```

## Running the CLI

### Via the installed entry point

```bash
sabi --search "madrid software" \
    --output records.csv --db records.sqlite
```

### Via the executable `bin` script (no installation required)

```bash
./bin/sabi --search "madrid software"
```

With credentials:

```bash
./bin/sabi --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software"
```

### Via the root `__main__.py`

```bash
python /path/to/sabi --search "madrid software" \
    --output records.csv --db records.sqlite
```

This logs in, searches for "madrid software", paginates through all
result pages, and writes `records.csv`.

## MCP server

Run over stdio (for agents/CLI clients):

```bash
sabi-mcp --transport stdio
```

Or over streamable-HTTP:

```bash
sabi-mcp --transport streamable-http --port 8000
```

Or via bin:

```bash
./bin/sabi-mcp --transport stdio
```

Requires `SABI_USERNAME` and `SABI_PASSWORD` environment variables.

## CLI options

### Authentication

| Option | Env var | Description |
|--------|---------|-------------|
| `--username` | `SABI_USERNAME` | SABI Informa username |
| `--password` | `SABI_PASSWORD` | SABI Informa password |
| `--login-page-url` | — | Login page URL (default: `https://sabi.informa.es/ip`) |
| `--no-login` | — | Skip login; use an already-authenticated session (cookies) |

### Output

| Option | Default | Description |
|--------|---------|-------------|
| `--output`, `-o` | `sabi_records.csv` | Output CSV path |
| `--fields` | all standard fields | Comma-separated CSV fields |
| `--db` | `sabi_records.sqlite` | SQLite database path |

### Source

| Option | Default | Description |
|--------|---------|-------------|
| `--search`, `-q` | `""` | Search query to run after login |
| `--search-url` | `https://sabi.informa.es/R1/SabiInforma/Search` | Search results URL |
| `--max-pages` | no limit | Maximum number of search pages |
| `--detail` | disabled | Fetch each detail page to enrich records (slower) |
| `--no-embeddings` | disabled | Skip embedding generation and SQLite storage |
| `--no-login` | disabled | Skip login; use an already-authenticated session (cookies) |

### Misc

| Option | Default | Description |
|--------|---------|-------------|
| `--timeout` | `30` | HTTP timeout in seconds |
| `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## MCP tools API specs

All tools return JSON strings. Errors are returned as `{"error": "..."}`.

### sabi_login

Authenticate to SABI Informa using `SABI_USERNAME` / `SABI_PASSWORD` env vars.

Returns: `{"status": "ok", "authenticated": true}` or `{"status": "error", "error": "..."}`.

### sabi_search

Search SABI Informa for company records matching a query.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `query` | string | `""` | Search string (company name, CIF, city, etc.) |
| `max_pages` | integer | `1` | Maximum number of result pages to paginate |
| `detail` | boolean | `false` | Fetch each detail page to enrich records (slower) |

Returns a JSON array of record objects with fields: `name`, `cif`, `address`, `city`, `province`, `postal_code`, `phone`, `activity`, `detail_url`, `extras`.

### sabi_get_record

Fetch a single company detail page by URL.

| Argument | Type | Description |
|----------|------|-------------|
| `detail_url` | string | Company detail page URL |

Returns a JSON array containing one record object.

### sabi_export_csv

Search SABI Informa and export matching records to a CSV file.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `query` | string | `""` | Search string |
| `max_pages` | integer | `1` | Maximum number of result pages |
| `output` | string | `sabi_records.csv` | Destination CSV path |
| `fields` | string | all standard fields | Comma-separated CSV columns |
| `detail` | boolean | `false` | Enrich each record via its detail page |

Returns: `{"status": "ok", "rows": N, "output": "..."}`.

### sabi_store_records

Search SABI Informa and upsert matching records (with embeddings) into SQLite.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `query` | string | `""` | Search string |
| `max_pages` | integer | `1` | Maximum number of result pages |
| `detail` | boolean | `false` | Enrich each record via its detail page |
| `db_path` | string | `sabi_records.sqlite` | SQLite database path |

Returns: `{"status": "ok", "stored": N, "db_path": "..."}`.

### sabi_similarity_search

Semantic similarity search over stored records in SQLite.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `query` | string | (required) | Natural-language query (e.g. "software companies in Madrid") |
| `limit` | integer | `10` | Maximum number of results |
| `db_path` | string | `sabi_records.sqlite` | SQLite database path |

Returns a JSON array of records ranked by cosine similarity.

### sabi_list_stored

List all records currently stored in the SQLite database.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `db_path` | string | `sabi_records.sqlite` | SQLite database path |

Returns a JSON array of all stored records.

## Examples

Search and export to CSV only:

```bash
sabi --search "barcelona consulting" \
    --output barcelona_consulting.csv \
    --no-embeddings
```

Paginate at most 5 pages and store with embeddings in SQLite:

```bash
sabi --search "madrid software" \
    --max-pages 5 \
    --output records.csv \
    --db records.sqlite
```

Fetch detail pages for each record (slower, enriches name/CIF):

```bash
sabi --search "madrid software" \
    --detail \
    --output records_detail.csv
```

Export a custom subset of CSV fields:

```bash
sabi --search "madrid software" \
    --fields name,cif,city,activity \
    --output records.csv
```

Skip login (e.g. reusing an existing authenticated session):

```bash
sabi --no-login --search "madrid software" --output records.csv
```

## Docker

Build the image:

```bash
docker build -t sabi -f docker/Dockerfile .
```

Run with a mounted output directory:

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

## Output

### CSV

The CSV contains one row per record with the standard fields: `name`, `cif`, `address`, `city`, `province`, `postal_code`, `phone`, `activity`, `detail_url`.

### SQLite

When embeddings are enabled, records are upserted (keyed on `cif`) into a SQLite table with an `embedding` BLOB column. Use `store.search_similar(query)` or the `all()` method to query stored records.

## Exit codes

- `0` — success
- `1` — login or extraction failure
