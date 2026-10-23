"""Command-line interface for the SABI Informa extractor."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence

from .embeddings import EmbeddingStore
from .extractor import LOGIN_PAGE_URL, SEARCH_URL, SABIClient
from .utils import CSV_FIELDS, write_csv

logger = logging.getLogger("sabi_extractor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sabi-extractor",
        description="Extract SABI Informa company records to CSV and SQLite.",
    )

    auth = parser.add_argument_group("authentication")
    auth.add_argument(
        "--username",
        default=os.environ.get("SABI_USERNAME"),
        help="SABI Informa username (env: SABI_USERNAME; "
        "optional on IP-authenticated networks)",
    )
    auth.add_argument(
        "--password",
        default=os.environ.get("SABI_PASSWORD"),
        help="SABI Informa password (env: SABI_PASSWORD; "
        "optional on IP-authenticated networks)",
    )
    auth.add_argument(
        "--login-page-url",
        default=LOGIN_PAGE_URL,
        help="Login page URL (default: %(default)s)",
    )
    auth.add_argument(
        "--no-login",
        action="store_true",
        help="Skip login; use an already-authenticated session (cookies)",
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "--output",
        "-o",
        default="sabi_records.csv",
        help="Output CSV path (default: sabi_records.csv)",
    )
    out.add_argument(
        "--fields",
        default=",".join(CSV_FIELDS),
        help="Comma-separated CSV fields (default: all standard fields)",
    )
    out.add_argument(
        "--db",
        default="sabi_records.sqlite",
        help="SQLite database path (default: sabi_records.sqlite)",
    )

    src = parser.add_argument_group("source")
    src.add_argument(
        "--search", "-q", default="", help="Search query to run after login"
    )
    src.add_argument(
        "--search-url",
        default=SEARCH_URL,
        help="Search results URL (default: %(default)s)",
    )
    src.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of search pages to paginate through",
    )
    src.add_argument(
        "--detail",
        action="store_true",
        help="Fetch each detail page to enrich records (slower)",
    )
    src.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip embedding generation and SQLite storage",
    )
    src.add_argument(
        "--no-login",
        action="store_true",
        help="Skip login; use an already-authenticated session (cookies)",
    )

    misc = parser.add_argument_group("misc")
    misc.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    misc.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]

    client = SABIClient(
        login_page_url=args.login_page_url,
        search_url=args.search_url,
        timeout=args.timeout,
    )

    if not args.no_login:
        logger.info("establishing session with SABI Informa")
        try:
            ok = client.login(args.username or "", args.password or "")
        except Exception as exc:  # noqa: BLE001
            logger.error("session setup failed: %s", exc)
            return 1
        if not ok:
            logger.error("session setup failed: could not authenticate")
            return 1
        logger.info("session established")
    else:
        client.authenticated = True
        logger.info("skipping login; using existing session")

    logger.info("searching%s", f" for '{args.search}'" if args.search else "")

    try:
        records = []
        for record in client.iter_search(query=args.search, max_pages=args.max_pages):
            if args.detail and record.detail_url:
                record = client.get_record(record.detail_url)
            records.append(record)
    except Exception as exc:  # noqa: BLE001
        logger.error("extraction failed: %s", exc)
        return 1

    count = write_csv(records, args.output, fields=fields)
    logger.info("wrote %d records to %s", count, args.output)

    if not args.no_embeddings:
        store = EmbeddingStore(db_path=args.db)
        try:
            stored = store.upsert_many(records)
            logger.info("stored %d records with embeddings in %s", stored, args.db)
        finally:
            store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
