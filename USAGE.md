# Usage

`sabi-extractor` extracts company records from [SABI Informa](https://sabi.informa.es) and exports them to CSV, with optional SQLite storage and embeddings for similarity search.

## Prerequisites

- Python 3.10+
- A valid SABI Informa account with credentials

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

## Basic usage

Run a search and write results to CSV:

```bash
python -m src.cli \
    --username "$SABI_USERNAME" \
    --password "$SABI_PASSWORD" \
    --search "madrid software" \
    --output records.csv
```

This logs in, searches for "madrid software", paginates through all result pages, and writes `records.csv`.

## Using the installed entry point

After installation, the `sabi-extractor` console script is available:

```bash
sabi-extractor --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software" \
    --output records.csv \
    --db records.sqlite
```

Or via the executable `bin` script without installing:

```bash
./bin/sabi-extractor --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software"
```

## CLI options

### Authentication

| Option | Env var | Description |
|--------|---------|-------------|
| `--username` | `SABI_USERNAME` | SABI Informa username |
| `--password` | `SABI_PASSWORD` | SABI Informa password |
| `--login-page-url` | — | Login page URL (default: `https://sabi.informa.es/ip`) |

Both `--username` and `--password` are required unless `--no-login` is set or the corresponding env vars are defined.

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

## Examples

Search and export to CSV only:

```bash
sabi-extractor --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "barcelona consulting" \
    --output barcelona_consulting.csv \
    --no-embeddings
```

Paginate at most 5 pages and store with embeddings in SQLite:

```bash
sabi-extractor --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software" \
    --max-pages 5 \
    --output records.csv \
    --db records.sqlite
```

Fetch detail pages for each record (slower, enriches name/CIF):

```bash
sabi-extractor --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software" \
    --detail \
    --output records_detail.csv
```

Export a custom subset of CSV fields:

```bash
sabi-extractor --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software" \
    --fields name,cif,city,activity \
    --output records.csv
```

Skip login (e.g. reusing an existing authenticated session):

```bash
sabi-extractor --no-login --search "madrid software" --output records.csv
```

## Docker

Build the image:

```bash
docker build -t sabi-extractor -f docker/Dockerfile .
```

Run with a mounted output directory:

```bash
docker run --rm \
  -e SABI_USERNAME="$SABI_USERNAME" \
  -e SABI_PASSWORD="$SABI_PASSWORD" \
  -v "$PWD/data:/data" \
  sabi-extractor --search "madrid software" \
    --output /data/sabi_records.csv \
    --db /data/sabi_records.sqlite
```

## Output

### CSV

The CSV contains one row per record with the standard fields: `name`, `cif`, `address`, `city`, `province`, `postal_code`, `phone`, `activity`, `detail_url`.

### SQLite

When embeddings are enabled, records are upserted (keyed on `cif`) into a SQLite table with an `embedding` BLOB column. Use `store.search_similar(query)` or the `all()` method to query stored records.

## Exit codes

- `0` — success
- `1` — login or extraction failure