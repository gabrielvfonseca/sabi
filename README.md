# SABI

Extract company records from [SABI Informa](https://sabi.informa.es) to CSV and SQLite, with optional embeddings for similarity search.

## Features

- Authenticated two-step login to SABI Informa
- Search and paginate company listings
- Parse records into CSV (name, CIF, address, city, province, postal code, phone, activity)
- Store records with embeddings in SQLite for similarity search
- Deterministic hash embeddings by default (no ML dependencies required)
- Optional `sentence-transformers` backend for real embeddings

## Installation

```bash
pip install -e .
```

With embeddings support:

```bash
pip install -e ".[embeddings]"
```

## Usage

```bash
python -m src.cli --username "$SABI_USERNAME" --password "$SABI_PASSWORD" \
    --search "madrid software" --output records.csv --db records.sqlite
```

Credentials can also be provided via the `SABI_USERNAME` and `SABI_PASSWORD` environment variables.

### Docker

Build the image:

```bash
docker build -t sabi-extractor -f docker/Dockerfile .
```

Run it, mounting a local directory for outputs:

```bash
docker run --rm \
  -e SABI_USERNAME="$SABI_USERNAME" \
  -e SABI_PASSWORD="$SABI_PASSWORD" \
  -v "$PWD/data:/data" \
  sabi-extractor --search "madrid software" \
    --output /data/sabi_records.csv \
    --db /data/sabi_records.sqlite
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
```

## License

MIT
