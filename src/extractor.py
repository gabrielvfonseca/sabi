"""HTTP client and extraction logic for SABI Informa."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urljoin

import requests  # type: ignore[import-untyped]
from bs4 import BeautifulSoup

from .models import Record
from .utils import clean

logger = logging.getLogger("sabi_extractor")

BASE_URL = "https://sabi.informa.es"

# Default login page URL. The SABI login form is rendered here and POSTs to
# the sign-in endpoint. Adjust if your account is served a different path.
LOGIN_PAGE_URL = urljoin(BASE_URL, "/ip")

# Default search results URL. Adjust to the search view used by your account.
SEARCH_URL = urljoin(BASE_URL, "/R1/SabiInforma/Search")


@dataclass
class ExtractResult:
    records: list[Record]
    page: int
    has_next: bool


# CSS selectors used to locate records on the search results page. Adjust these
# to match the markup returned after you log in.
SELECTORS = {
    "records": "table tr.record, .record-row, .company-row",
    "name": "td.name a, .company-name a, h3 a",
    "cif": "td.cif, .cif, .tax-id",
    "address": "td.address, .address",
    "city": "td.city, .city",
    "province": "td.province, .province",
    "postal_code": "td.postal, .postal-code",
    "phone": "td.phone, .phone",
    "activity": "td.activity, .activity, .cnae",
    "detail_link": "td.name a, .company-name a",
}


class SABIClient:
    """HTTP client that maintains an authenticated session with SABI Informa."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        login_page_url: str = LOGIN_PAGE_URL,
        search_url: str = SEARCH_URL,
        timeout: int = 30,
    ):
        self.base_url = base_url
        self.login_page_url = login_page_url
        self.search_url = search_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; sabi/1.0; +https://sabi.informa.es/)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            }
        )
        self.authenticated = False
        self.login_action_url: str | None = None

    # ------------------------------------------------------------------ #
    # authentication
    # ------------------------------------------------------------------ #
    def login(self, username: str = "", password: str = "") -> bool:
        """Authenticate with SABI Informa.

        Supports two modes:
        - Credential flow: two-step username/password POST when *username* and
          *password* are provided.
        - Network/IP flow: when no credentials are given, establish the
          session by fetching the login and search pages. Useful behind an
          IP-authenticated network (e.g. university wifi) that recognizes
          your address and lets you in without a password.

        Returns True if authentication appears to have succeeded.
        """
        if not username and not password:
            return self._login_network()

        resp = self.session.get(self.login_page_url, timeout=self.timeout)
        resp.raise_for_status()
        self.login_action_url, token = self._discover_login_form(resp.text)
        if not self.login_action_url:
            self.login_action_url = self.login_page_url
        if not token:
            raise RuntimeError("Could not find CSRF token on login page")

        # Step 1: submit the username (first screen of the flow).
        step1 = self._base_form_data(token)
        step1["user"] = username
        resp = self.session.post(
            self.login_action_url, data=step1, timeout=self.timeout
        )
        resp.raise_for_status()

        # The password screen may re-render with a new token.
        token = self._extract_csrf_token(resp.text) or token

        # Step 2: submit the password (second screen).
        step2 = self._base_form_data(token)
        step2["pw"] = password
        step2["stayLoggedIn"] = "1"
        resp = self.session.post(
            self.login_action_url, data=step2, timeout=self.timeout
        )
        resp.raise_for_status()

        self.authenticated = self._is_authenticated(resp)
        return self.authenticated

    def _login_network(self) -> bool:
        """Establish an IP/network-authenticated session without credentials.

        Useful when behind a network (e.g. university wifi) that
        authenticates by IP address. We fetch the login page and search
        page to set up session cookies, then consider ourselves
        authenticated.
        """
        logger.info("using network/IP authentication (no credentials provided)")
        # Fetch login page to establish session cookies via IP auth.
        resp = self.session.get(self.login_page_url, timeout=self.timeout)
        resp.raise_for_status()

        # Probe the search page to confirm network access and finalize
        # the session.
        resp = self.session.get(self.search_url, timeout=self.timeout)
        resp.raise_for_status()

        self.authenticated = self._is_authenticated(resp)
        return self.authenticated

    def _base_form_data(self, token: str) -> dict:
        return {
            "__RequestVerificationToken": token,
            "ResponseRegionId": "R1",
            "Next": "",
            "productFlow": "/sabiinforma/flow",
        }

    @staticmethod
    def _discover_login_form(html: str) -> tuple[str | None, str | None]:
        """Return (form_action_url, csrf_token) from the login page markup."""
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", id="LoginForm") or soup.find("form")
        action = form.get("action") if form else None
        action_url = urljoin(BASE_URL, str(action)) if action else None
        token = None
        if form:
            tag = form.find("input", {"name": "__RequestVerificationToken"})
            if tag and tag.get("value"):
                token = str(tag["value"])
        return action_url, token

    @staticmethod
    def _extract_csrf_token(html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("input", {"name": "__RequestVerificationToken"})
        if tag and tag.get("value"):
            return str(tag["value"])
        return None

    def _is_authenticated(self, resp: requests.Response) -> bool:
        """Heuristic: logged-in responses should not contain the login form."""
        html = resp.text.lower()
        return (
            'id="loginform"' not in html
            and 'name="user"' not in html
            and resp.url.rstrip("/") != self.login_page_url.rstrip("/")
        )

    # ------------------------------------------------------------------ #
    # search / extraction
    # ------------------------------------------------------------------ #
    def search(self, query: str = "", page: int = 1) -> ExtractResult:
        """Run a search and return parsed records for one page."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        params = {"q": query, "page": page} if query else {"page": page}
        resp = self.session.get(self.search_url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_search_page(resp.text, resp.url, page)

    def get_record(self, detail_url: str) -> Record:
        """Fetch a single company detail page and parse it into a Record."""
        resp = self.session.get(detail_url, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_detail_page(resp.text, detail_url)

    def _parse_search_page(self, html: str, page_url: str, page: int) -> ExtractResult:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Record] = []

        for row in soup.select(SELECTORS["records"]):
            record = self._parse_record_row(row, page_url)
            if record.name or record.cif:
                records.append(record)

        has_next = bool(soup.select_one("a.next, .pagination .next, [rel='next']"))
        return ExtractResult(records=records, page=page, has_next=has_next)

    def _parse_record_row(self, row, page_url: str) -> Record:
        def text(sel: str) -> str:
            tag = row.select_one(sel)
            return clean(tag.get_text(" ", strip=True)) if tag else ""

        def attr(sel: str, attribute: str) -> str:
            tag = row.select_one(sel)
            return tag.get(attribute, "") if tag else ""

        name = text(SELECTORS["name"])
        detail_rel = attr(SELECTORS["detail_link"], "href")
        detail_url = urljoin(page_url, detail_rel) if detail_rel else ""

        return Record(
            name=name,
            cif=text(SELECTORS["cif"]),
            address=text(SELECTORS["address"]),
            city=text(SELECTORS["city"]),
            province=text(SELECTORS["province"]),
            postal_code=text(SELECTORS["postal_code"]),
            phone=text(SELECTORS["phone"]),
            activity=text(SELECTORS["activity"]),
            detail_url=detail_url,
        )

    @staticmethod
    def _parse_detail_page(html: str, detail_url: str) -> Record:
        soup = BeautifulSoup(html, "html.parser")

        def text(sel: str) -> str:
            tag = soup.select_one(sel)
            return clean(tag.get_text(" ", strip=True)) if tag else ""

        return Record(
            name=text("h1, .company-name, .denominacion") or "",
            cif=text(".cif, .nif, .tax-id") or "",
            detail_url=detail_url,
        )

    # ------------------------------------------------------------------ #
    # pagination helper
    # ------------------------------------------------------------------ #
    def iter_search(
        self,
        query: str = "",
        max_pages: int | None = None,
    ) -> Iterable[Record]:
        """Yield records across search pages until exhaustion or max_pages."""
        page = 1
        while True:
            result = self.search(query=query, page=page)
            yield from result.records
            page += 1
            if not result.has_next:
                break
            if max_pages is not None and page > max_pages:
                break
