"""MCP server exposing SABI Informa extraction to an agent.

Requires valid SABI Informa credentials via SABI_USERNAME / SABI_PASSWORD
environment variables. Auth is not bypassed — the server logs in with the
configured credentials before querying.

Run (stdio transport, for agents/CLI clients):
    python -m src.mcp_server

Run (streamable-HTTP transport):
    python -m src.mcp_server --transport streamable-http --port 8000
"""

from __future__ import annotations

import argparse
import json
import os

from mcp.server.mcpserver import MCPServer

from .embeddings import EmbeddingStore
from .extractor import LOGIN_PAGE_URL, SABIClient
from .models import Record
from .utils import CSV_FIELDS, write_csv

server = MCPServer(
    name="sabi",
    instructions="Extract company records from SABI Informa (sabi.informa.es). "
    "Set SABI_USERNAME and SABI_PASSWORD environment variables to authenticate.",
)

_client: SABIClient | None = None
_store: EmbeddingStore | None = None


def _get_client() -> SABIClient:
    global _client
    if _client is None:
        username = os.environ.get("SABI_USERNAME", "")
        password = os.environ.get("SABI_PASSWORD", "")
        _client = SABIClient(login_page_url=LOGIN_PAGE_URL)
        if not _client.login(username, password):
            raise RuntimeError(
                "SABI session setup failed — check network access or credentials"
            )
    return _client


def _get_store(db_path: str = "sabi_records.sqlite") -> EmbeddingStore:
    global _store
    if _store is None or _store.db_path != db_path:
        if _store is not None:
            _store.close()
        _store = EmbeddingStore(db_path=db_path)
    return _store


def _records_to_json(records: list[Record]) -> str:
    return json.dumps(
        [
            {
                "name": r.name,
                "cif": r.cif,
                "address": r.address,
                "city": r.city,
                "province": r.province,
                "postal_code": r.postal_code,
                "phone": r.phone,
                "activity": r.activity,
                "detail_url": r.detail_url,
                "extras": r.extras,
            }
            for r in records
        ],
        ensure_ascii=False,
    )


@server.tool()
def sabi_login() -> str:
    """Authenticate to SABI Informa using SABI_USERNAME / SABI_PASSWORD.

    Returns a status message. Credentials must be set as environment variables.
    """
    try:
        client = _get_client()
        return json.dumps(
            {"status": "ok", "authenticated": client.authenticated},
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


@server.tool()
def sabi_search(
    query: str = "",
    max_pages: int = 1,
    detail: bool = False,
) -> str:
    """Search SABI Informa for company records matching *query*.

    Args:
        query: Search string (company name, CIF, city, etc.). Empty returns all.
        max_pages: Maximum number of result pages to paginate (default 1).
        detail: If true, fetch each company detail page to enrich records (slower).

    Returns a JSON array of record objects.
    """
    try:
        client = _get_client()
        records: list[Record] = []
        for record in client.iter_search(query=query, max_pages=max_pages):
            if detail and record.detail_url:
                record = client.get_record(record.detail_url)
            records.append(record)
        return _records_to_json(records)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@server.tool()
def sabi_get_record(detail_url: str) -> str:
    """Fetch a single company detail page by URL and return its parsed record."""
    try:
        client = _get_client()
        record = client.get_record(detail_url)
        return _records_to_json([record])
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@server.tool()
def sabi_export_csv(
    query: str = "",
    max_pages: int = 1,
    output: str = "sabi_records.csv",
    fields: str = ",".join(CSV_FIELDS),
    detail: bool = False,
) -> str:
    """Search SABI Informa and export matching records to a CSV file.

    Args:
        query: Search string. Empty returns all.
        max_pages: Maximum number of result pages.
        output: Destination CSV path.
        fields: Comma-separated list of CSV columns.
        detail: Enrich each record via its detail page before exporting.

    Returns a JSON status with the row count and output path.
    """
    try:
        client = _get_client()
        field_list = [f.strip() for f in fields.split(",") if f.strip()]
        records: list[Record] = []
        for record in client.iter_search(query=query, max_pages=max_pages):
            if detail and record.detail_url:
                record = client.get_record(record.detail_url)
            records.append(record)
        count = write_csv(records, output, fields=field_list)
        return json.dumps(
            {"status": "ok", "rows": count, "output": output},
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


@server.tool()
def sabi_store_records(
    query: str = "",
    max_pages: int = 1,
    detail: bool = False,
    db_path: str = "sabi_records.sqlite",
) -> str:
    """Search SABI Informa and upsert matching records (with embeddings) into SQLite.

    Args:
        query: Search string. Empty returns all.
        max_pages: Maximum number of result pages.
        detail: Enrich each record via its detail page.
        db_path: SQLite database path.

    Returns a JSON status with the number of stored records.
    """
    try:
        client = _get_client()
        store = _get_store(db_path)
        count = 0
        for record in client.iter_search(query=query, max_pages=max_pages):
            if detail and record.detail_url:
                record = client.get_record(record.detail_url)
            store.upsert(record)
            count += 1
        return json.dumps(
            {"status": "ok", "stored": count, "db_path": db_path},
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


@server.tool()
def sabi_similarity_search(
    query: str,
    limit: int = 10,
    db_path: str = "sabi_records.sqlite",
) -> str:
    """Semantic similarity search over stored records in SQLite.

    Args:
        query: Natural-language query (e.g. "software companies in Madrid").
        limit: Maximum number of results.
        db_path: SQLite database path.

    Returns a JSON array of records ranked by similarity.
    """
    try:
        store = _get_store(db_path)
        results = store.search_similar(query, limit=limit)
        return json.dumps(results, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@server.tool()
def sabi_list_stored(
    db_path: str = "sabi_records.sqlite",
) -> str:
    """List all records currently stored in the SQLite database."""
    try:
        store = _get_store(db_path)
        return json.dumps(store.all(), ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sabi-mcp",
        description="MCP server for SABI Informa extraction.",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="Transport to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for HTTP/SSE transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP/SSE transport (default: 8000)",
    )
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        server.run()
    else:
        server.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
