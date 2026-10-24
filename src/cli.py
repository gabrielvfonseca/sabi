"""Command-line interface for the SABI Informa extractor."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from .embeddings import EmbeddingStore
from .extractor import LOGIN_PAGE_URL, SABIClient
from .models import Record
from .utils import CSV_FIELDS, coerce_record, list_fields, read_csv, to_json, write_csv

logger = logging.getLogger("sabi_extractor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sabi",
        description="Extract SABI Informa company records to CSV, JSON, and SQLite.",
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
        help="Skip login; use an already-authenticated session (e.g. reuse cookies)",
    )
    auth.add_argument(
        "--cookie-file",
        default="",
        help="Netscape cookie file to load before login and save after login",
    )

    src = parser.add_argument_group("source")
    src.add_argument(
        "--search", "-q", default="", help="Search query to run after login"
    )
    src.add_argument(
        "--search-url",
        default="",
        help="Override the search results URL (default: auto-detected)",
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
        "--retry",
        type=int,
        default=3,
        help="Number of retries on transient HTTP errors (default: 3)",
    )
    src.add_argument(
        "--backoff",
        type=float,
        default=1.5,
        help="Backoff multiplier between retries (default: 1.5)",
    )
    src.add_argument(
        "--import-csv",
        default="",
        help="Import records from a CSV file instead of searching SABI",
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "--output",
        "-o",
        default="sabi_records.csv",
        help="Output CSV path (default: sabi_records.csv)",
    )
    out.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not write a CSV file",
    )
    out.add_argument(
        "--json",
        default="",
        help="Also write records to a JSON file path",
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
    out.add_argument(
        "--no-db",
        action="store_true",
        help="Do not store records in SQLite",
    )
    out.add_argument(
        "--list-fields",
        action="store_true",
        help="Print the available CSV field names and exit",
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

    if args.list_fields:
        for field in list_fields():
            print(field)
        return 0

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]

    client = SABIClient(
        login_page_url=args.login_page_url,
        timeout=args.timeout,
        retries=args.retry,
        backoff=args.backoff,
        cookie_file=args.cookie_file,
    )
    if args.search_url:
        client.search_url = args.search_url

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
        if args.cookie_file:
            client.save_cookies(args.cookie_file)
    else:
        client.authenticated = True
        logger.info("skipping login (--no-login)")

    records: list[Record] = []

    if args.import_csv:
        logger.info("importing records from %s", args.import_csv)
        for row in read_csv(args.import_csv):
            records.append(coerce_record(row))
    else:
        logger.info("searching%s", f" for '{args.search}'" if args.search else "")
        try:
            for record in client.iter_search(
                query=args.search, max_pages=args.max_pages
            ):
                if args.detail and record.detail_url:
                    seqnr = record.extras.get("seqnr", "") if record.extras else ""
                    record = client.get_record(record.detail_url, seqnr)
                records.append(record)
        except Exception as exc:  # noqa: BLE001
            logger.error("extraction failed: %s", exc)
            return 1

    if args.json:
        with Path(args.json).open("w", encoding="utf-8") as fh:
            fh.write(to_json(records))
        logger.info("wrote %d records to %s", len(records), args.json)

    if not args.no_csv:
        count = write_csv(records, args.output, fields=fields)
        logger.info("wrote %d records to %s", count, args.output)

    if not args.no_db:
        store = EmbeddingStore(db_path=args.db)
        try:
            stored = store.upsert_many(records)
            logger.info("stored %d records with embeddings in %s", stored, args.db)
        finally:
            store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
