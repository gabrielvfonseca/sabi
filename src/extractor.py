"""HTTP client and extraction logic for SABI Informa."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urljoin

import requests  # type: ignore[import-untyped]
from bs4 import BeautifulSoup

from .models import Record
from .utils import clean

logger = logging.getLogger("sabi_extractor")

BASE_URL = "https://sabi.informa.es"
LOGIN_PAGE_URL = urljoin(BASE_URL, "/ip")


@dataclass
class ExtractResult:
    records: list[Record]
    page: int
    has_next: bool


class SABIClient:
    """HTTP client that maintains an authenticated session with SABI Informa."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        login_page_url: str = LOGIN_PAGE_URL,
        search_url: str = "",
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
        self.version_prefix: str = ""
        self.viewstate: str = ""
        self.viewstategenerator: str = ""
        self.eventvalidation: str = ""
        self._list_page_html: str = ""

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

        raise NotImplementedError("Credential-based login not yet implemented for new site")

    def _login_network(self) -> bool:
        """Establish an IP/network-authenticated session without credentials."""
        logger.info("using network/IP authentication (no credentials provided)")

        resp = self.session.get(self.login_page_url, timeout=self.timeout)
        resp.raise_for_status()

        self.version_prefix = self._extract_version_prefix(resp.url)
        logger.info("detected version prefix: %s", self.version_prefix)

        search_url = self._build_search_url()
        resp = self.session.get(search_url, timeout=self.timeout)
        resp.raise_for_status()

        self._extract_form_tokens(resp.text)

        self.authenticated = self._is_authenticated(resp)
        return self.authenticated

    def _extract_version_prefix(self, url: str) -> str:
        match = re.search(r"(/version-\d+)", url)
        return match.group(1) if match else ""

    def _build_search_url(self) -> str:
        base = urljoin(self.base_url, self.version_prefix)
        return urljoin(base, "/Search.QuickSearch.serv?_CID=31&product=sabiinforma")

    def _build_list_url(self) -> str:
        base = urljoin(self.base_url, self.version_prefix)
        return urljoin(base, "/List.serv?_CID=42&product=sabiinforma&context=ext")

    def _extract_form_tokens(self, html: str) -> None:
        soup = BeautifulSoup(html, "html.parser")
        for inp in soup.find_all("input", {"type": "hidden", "name": True}):
            name = inp.get("name", "")
            value = inp.get("value", "")
            if name == "__VIEWSTATE":
                self.viewstate = value
            elif name == "__VIEWSTATEGENERATOR":
                self.viewstategenerator = value
            elif name == "__EVENTVALIDATION":
                self.eventvalidation = value

    def _is_authenticated(self, resp: requests.Response) -> bool:
        html = resp.text.lower()
        return (
            'id="loginform"' not in html
            and 'name="user"' not in html
            and "sabi informa" in html.lower()
        )

    def _build_postback_data(self, event_target: str, event_argument: str = "") -> dict:
        return {
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": event_argument,
            "__VIEWSTATE": self.viewstate,
            "__VIEWSTATEGENERATOR": self.viewstategenerator,
            "__EVENTVALIDATION": self.eventvalidation,
        }

    def search(self, query: str = "", page: int = 1) -> ExtractResult:
        """Run a search and return parsed records for one page."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

        search_url = self._build_search_url()

        resp = self.session.get(search_url, timeout=self.timeout)
        resp.raise_for_status()
        self._extract_form_tokens(resp.text)

        data = self._build_postback_data(
            "ContentContainer1$ctl00$Header$ctl00$ctl03$Ok2008",
            "EnterKeyPressed",
        )
        data["tbSearch"] = query
        data["ContentContainer1$ctl00$Header$ctl00$ctl03$SearchText2008"] = query
        data["ContentContainer1$ctl00$Header$ctl00$ctl03$IdConversionPopupAction"] = "Open"
        data["ContentContainer1$ctl00$Content$QuickSearch1$ctl02$PanelSelected"] = "TabAdvancedSearches"

        resp = self.session.post(search_url, data=data, timeout=self.timeout)
        resp.raise_for_status()

        list_url = self._build_list_url()
        resp = self.session.get(list_url, timeout=self.timeout)
        resp.raise_for_status()

        self._list_page_html = resp.text
        self._extract_form_tokens(resp.text)

        return self._parse_list_page(resp.text, resp.url, page)

    def _parse_list_page(self, html: str, page_url: str, page: int) -> ExtractResult:
        soup = BeautifulSoup(html, "html.parser")
        records = self._parse_results_table(soup, page_url)
        has_next = self._has_next_page(soup)
        return ExtractResult(records=records, page=page, has_next=has_next)

    # Deprecated methods for backward compatibility with tests
    def _parse_search_page(self, html: str, page_url: str, page: int) -> ExtractResult:
        """Deprecated: use _parse_list_page instead."""
        raise NotImplementedError("Old site structure no longer supported")

    @staticmethod
    def _discover_login_form(html: str) -> tuple[str | None, str | None]:
        """Deprecated: old login form structure no longer used."""
        raise NotImplementedError("Old login form structure no longer supported")

    def _parse_results_table(self, soup: BeautifulSoup, page_url: str) -> list[Record]:
        records: list[Record] = []

        table = soup.find("table", id=re.compile(r".*_ListCtrl1_LB1$"))
        if not table:
            table = soup.find("table", id="GridViewResultados")
        if not table:
            logger.warning("Results table not found")
            return records

        rows = table.find_all("tr")
        for row in rows[1:]:
            record = self._parse_result_row(row, page_url)
            if record.name and record.name not in ("Nombre", "Localidad", "Nombre empresa"):
                records.append(record)

        return records

    def _parse_result_row(self, row, page_url: str) -> Record:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            return Record(name="", cif="", detail_url="")

        def cell_text(idx: int) -> str:
            if idx < len(cells):
                return clean(cells[idx].get_text(" ", strip=True))
            return ""

        def cell_link(idx: int) -> str:
            if idx < len(cells):
                link = cells[idx].find("a", href=True)
                if link:
                    return urljoin(page_url, link["href"])
            return ""

        def cell_onclick(idx: int) -> str:
            if idx < len(cells):
                link = cells[idx].find("a", href=True)
                if link:
                    return link.get("onclick", "")
            return ""

        # Cell indices based on actual list table structure
        # Cell 0: empty/row number
        # Cell 4: first link (setMark)
        # Cell 6: second link (NoteLink) 
        # Cell 8: company name link (listContentClicked with SeqNr)
        # Cell 10: CIF
        # Cell 12: City
        # Cell 14: Country
        # Cell 20: Revenue
        name = cell_text(8) or cell_link(8)
        cif = cell_text(10)
        city = cell_text(12)
        country = cell_text(14)
        revenue = cell_text(20)

        detail_url = cell_link(8)
        onclick = cell_onclick(8)
        seqnr = ""
        match = re.search(r"Report\.serv\?_CID=\d+&product=sabiinforma&SeqNr=(\d+)", onclick)
        if match:
            seqnr = match.group(1)

        return Record(
            name=name,
            cif=cif,
            address="",
            city=city,
            province="",
            postal_code="",
            phone="",
            activity="",
            detail_url=detail_url,
            extras={"country": country, "revenue_eur": revenue, "seqnr": seqnr},
        )

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        pager = soup.find("table", id=re.compile(r".*_ListCtrl1_Pager$"))
        if not pager:
            pager = soup.find("tr", class_=re.compile(r".*Pager.*"))
        if pager:
            for link in pager.find_all("a"):
                text = link.get_text(strip=True).lower()
                if any(t in text for t in ["siguiente", "next", ">", ">>"]):
                    return True
        return False

    def get_record(self, detail_url: str, seqnr: str = "") -> Record:
        """Fetch and parse a company detail/report page."""
        is_list_url = not detail_url or detail_url.startswith("#") or "Scripts/List/#" in detail_url or "List.serv" in detail_url
        if is_list_url:
            if seqnr:
                base = urljoin(self.base_url, self.version_prefix)
                detail_url = urljoin(base, f"/Report.serv?_CID=136&product=sabiinforma&SeqNr={seqnr}")
            else:
                detail_url = self._resolve_detail_url(detail_url)
        resp = self.session.get(detail_url, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_detail_page(resp.text, detail_url)

    def _resolve_detail_url(self, list_url: str) -> str:
        """Resolve the list page link to a report URL by extracting SeqNr."""
        match = re.search(r"SeqNr=(\d+)", self._list_page_html)
        if match:
            seqnr = match.group(1)
            base = urljoin(self.base_url, self.version_prefix)
            return urljoin(base, f"/Report.serv?_CID=136&product=sabiinforma&SeqNr={seqnr}")
        return list_url

    def _parse_detail_page(self, html: str, detail_url: str) -> Record:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()
        # Replace non-breaking spaces
        text = text.replace("\xa0", " ")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        record = Record(detail_url=detail_url)

        # Parse the full page - don't limit to section, scan all lines
        for i, line in enumerate(lines):
            # Identity - company name
            if record.name == "" and self._is_company_name(line):
                record.name = clean(line)

            # CIF/NIF - extract from any line containing it
            elif "Código NIF" in line and not record.cif:
                match = re.search(r"Código NIF\s*([A-Z0-9]+)", line)
                if match:
                    cif = match.group(1)
                    # Remove trailing letter if present (check digit sometimes appended)
                    if len(cif) > 9 and cif[-1].isalpha():
                        cif = cif[:-1]
                    record.cif = cif

            # Address lines - multiple patterns
            elif not record.address and self._is_address_line(line):
                record.address = clean(line)
                # Also extract embedded fields
                if "Código NIF" in line and not record.cif:
                    match = re.search(r"Código NIF\s*([A-Z0-9]+)", line)
                    if match:
                        record.cif = match.group(1)
                if "Fecha últimas cuentas" in line and not record.latest_year:
                    match = re.search(r"Fecha últimas cuentas\s*(\d{2}/\d{2}/\d{4})", line)
                    if match:
                        record.latest_year = match.group(1)
                if "Global Ultimate Owner" in line and not record.global_ultimate_owner:
                    record.global_ultimate_owner = clean(line.split("Global Ultimate Owner")[-1].split("Código")[0])

            # Contact info section (street, postal+city, province, country, email)
            elif "Información de contacto" in line:
                # Parse following lines for address components
                addr_parts = []
                for j in range(i + 1, min(i + 6, len(lines))):
                    if lines[j] and not any(kw in lines[j].lower() for kw in ["email", "tel", "fax", "web", "información", "forma jurídica", "capital", "fecha"]):
                        addr_parts.append(lines[j])
                if addr_parts:
                    record.address = clean(" | ".join(addr_parts))

            elif "@" in line and "email" in line.lower() and not record.email:
                match = re.search(r"[\w\.-]+@[\w\.-]+", line)
                if match:
                    record.email = match.group(0)
            elif "Teléfono" in line and not record.phone:
                record.phone = clean(line.split("Teléfono")[-1].split("Fax")[0])
            elif "Fax" in line and "Dirección web" not in line:
                record.extras["fax"] = clean(line.split("Fax")[-1].split("Dirección")[0].split("web")[0])
            elif "Dirección web" in line or ("www." in line and not record.website):
                match = re.search(r"(https?://\S+|www\.\S+)", line)
                if match:
                    record.website = match.group(1)
                else:
                    record.website = clean(line.split("Dirección web")[-1].split("Información")[0])

            # Legal info
            elif "Forma jurídica" in line and "detallada" not in line and not record.legal_form:
                match = re.search(r"Forma jurídica\s*(.+)", line)
                if match:
                    record.legal_form = clean(match.group(1))
            elif "Fecha constitución" in line and not record.incorporation_date:
                match = re.search(r"Fecha constitución\s*(\d{2}/\d{2}/\d{4})", line)
                if match:
                    record.incorporation_date = match.group(1)
            elif "Capital social" in line and not record.share_capital:
                match = re.search(r"Capital social\s*\(?[\w\s]*\)?\s*([\d\.]+)", line)
                if match:
                    record.share_capital = match.group(1)
            elif "Estado" in line and "detallado" not in line and line.startswith("Estado") and not record.status:
                record.status = clean(line.split("Estado")[-1].split()[0] if line.split("Estado")[-1].split() else "")
            elif ("Ultimo año disponible" in line or "Último año disponible" in line) and not record.latest_year:
                match = re.search(r"(?:Ultimo|Último) año disponible\s*(\d{2}/\d{2}/\d{4})", line)
                if match:
                    record.latest_year = match.group(1)
            elif "Años disponibles" in line and not record.available_years:
                match = re.search(r"Años disponibles\s*(\d+)", line)
                if match:
                    record.available_years = int(match.group(1))

            # Financial
            elif "Ingresos explotación" in line and not record.revenue:
                match = re.search(r"Ingresos explotación\s*([\d\.]+)", line)
                if match:
                    record.revenue = match.group(1)
                elif i + 1 < len(lines):
                    record.revenue = clean(lines[i + 1].split()[0] if lines[i + 1].split() else "")
            elif "Resultado ejercicio" in line and not record.profit:
                match = re.search(r"Resultado ejercicio\s*([\d\.\-]+)", line)
                if match:
                    record.profit = match.group(1)
            elif "Total activo" in line and not record.total_assets:
                match = re.search(r"Total activo\s*([\d\.]+)", line)
                if match:
                    record.total_assets = match.group(1)
            elif "Fondos propios" in line and not record.equity:
                match = re.search(r"Fondos propios\s*([\d\.]+)", line)
                if match:
                    record.equity = match.group(1)
            elif "Número de empleados" in line and not record.employees:
                match = re.search(r"Número de empleados\s*(\d+)", line)
                if match:
                    record.employees = match.group(1)

            # Global Ultimate Owner
            elif "Global Ultimate Owner" in line and not record.global_ultimate_owner:
                record.global_ultimate_owner = clean(line.split("Global Ultimate Owner")[-1].split("Código")[0])

            # Directors - handle concatenated "Director ejecutivoName" format
            elif "Director ejecutivo" in line or "Presidente" in line:
                name = ""
                # Try to extract from same line first
                if "Director ejecutivo" in line:
                    match = re.search(r"Director ejecutivo\s*(.+)", line)
                    if match:
                        name = clean(match.group(1))
                elif "Presidente" in line:
                    match = re.search(r"Presidente\s*(.+)", line)
                    if match:
                        name = clean(match.group(1))

                # Fallback to next line
                if not name and i + 1 < len(lines):
                    name = clean(lines[i + 1])

                # Validate
                if (name and not name.startswith("P426") and 
                    not any(kw in name for kw in ["El director", "ocupa posiciones", "sólo en esta", "Información", "grupo", "tamaño", "Indicador", "Independencia"])):
                    name = name.replace("Don ", "").replace("Doña ", "")
                    record.directors.append({"name": name, "role": "Director ejecutivo" if "Director ejecutivo" in line else "Presidente"})
            elif "Sócio Gerente" in line or ("Sócio" in line and "Gerente" in line):
                name = ""
                match = re.search(r"Sócio Gerente\s*(.+)", line)
                if match:
                    name = clean(match.group(1))
                elif i + 1 < len(lines):
                    name = clean(lines[i + 1]).replace("Don ", "").replace("Doña ", "")
                if name and not name.startswith("P426"):
                    record.directors.append({"name": name, "role": "Sócio Gerente"})

            # Activity/CAE
            elif "Descripción actividad" in line and i + 1 < len(lines) and not record.activity:
                record.activity = clean(lines[i + 1])
            elif "Código(s) CAE" in line or "Código(s) primario" in line:
                cae_match = re.search(r"(\d{5})\s*[-:]\s*([^C]+)", line)
                if cae_match:
                    record.primary_cae = f"{cae_match.group(1)} - {clean(cae_match.group(2))}"

            # Last update
            elif "Última actualización" in line and not record.last_update:
                record.last_update = clean(line.split(":")[-1] if ":" in line else "")

        # Post-process address to extract components
        if record.address:
            self._parse_address_components(record)

        # Extract financial history from tables
        self._extract_financial_tables(soup, record)

        # Set city/country from list page extras if available
        if not record.city and record.extras.get("country"):
            record.country = record.extras.get("country", "")

        return record

    def _is_company_name(self, line: str) -> bool:
        """Check if a line is likely a company name."""
        if len(line) < 5 or line.isdigit():
            return False
        # Must contain typical company suffixes
        company_suffixes = ["LDA", "SLU", "SL", "SA", "S.A.", "S.L.", "S.L.U.", 
                            "S.A.U.", "LTD", "LIMITED", "INC", "CORP", "GMBH",
                            "PTY", "BV", "NV", "AG", "SE", "SCA", "SCS", "SAS",
                            "UNIPESSOAL", "UNIPERSONAL"]
        has_suffix = any(suffix in line.upper() for suffix in company_suffixes)
        if not has_suffix:
            return False
        skip_kws = ["Nombre", "director", "Nueva", "Suprimir", "Agregar", "Alertas", 
                    "Exportaciones", "Búsquedas", "Listas", "Informes", "Accionistas", 
                    "Análisis", "Configuración", "Grupos", "Secciones", "Ratios", 
                    "Datos", "Campos", "Plantillas", "Ayuda", "Herramientas", "Web", 
                    "Contact", "Cerrar", "Inicio", "Ocultar", "Volver", "Buscar", 
                    "Modificar", "Definir", "Formato", "Crear", "Añadir", "Mostrar", 
                    "Plantilla", "Title", "de", "Informe", "Grupo", "Mapa", "Editar", 
                    "Secciones", "Avíseme", "Exportar", "Enviar", "Imprimir",
                    "Secciones", "Opciones", "Spanish", "Portuguese", "companies",
                    "Empresas", "Contactos", "Noticias", "Alertas", "Búsquedas",
                    "Mis", "Cuenta", "Idioma", "Preferencias", "Impresora", "Envío",
                    "Consistencia", "Exportaciones", "Búsquedas", "Listas", "Accionistas",
                    "Análisis", "Comparación", "Personalizadas", "Ratios", "Importados",
                    "PowerPoint", "Cobertura", "Guía", "Manual", "Herramientas",
                    "Add-in", "Verificar", "VAT", "Cerrar", "Sesión", "Ocultar",
                    "Volver", "Buscar", "Modificar", "Definir", "Nuevo", "Añadir",
                    "Quitar", "Crear", "Plantilla", "Title", "Mapa", "Editar",
                    "Avíseme", "Enviar", "Imprimir", "Tu", "template", "is", "invalid",
                    "Sección", "Opciones", "Personalizada", "Definición", "Matriz",
                    "Cancelar", "Aceptar", "Sí", "No", "Atrás", "Siguiente",
                    "Guardar", "Eliminar", "Editar", "Ver", "Detalle", "Lista"]
        return not any(kw in line for kw in skip_kws)

    def _is_address_line(self, line: str) -> bool:
        """Check if a line contains address/postal code info."""
        # Spanish: 5 digits, Portuguese: 4 digits + hyphen + 3 digits
        return bool(re.search(r"\d{4,5}(?:-\d{3})?[\s\xa0]+\w+", line)) and "Código NIF" in line
    def _parse_address_components(self, record: Record) -> None:
            """Parse address string into components."""
            addr = record.address

            # Try Portuguese format first: split by | and find postal code + city
            parts = [p.strip() for p in addr.split("|")]
            for part in parts:
                match = re.search(r"(\d{4}-\d{3})[\s ]+(\w+)", part)
                if match:
                    record.postal_code = match.group(1)
                    record.city = match.group(2)
                    break

            # Try Spanish format: "28660 BOADILLA DEL MONTE (MADRID, ESPANA)..."
            if not record.postal_code:
                match = re.search(r"(\d{4,5}(?:-\d{3})?)[\s ]+([^\(]+)", addr)
                if match:
                    record.postal_code = match.group(1)
                    record.city = clean(match.group(2))

            # Extract country from parentheses (Spanish format)
            match = re.search(r"\(([^)]+)\)", addr)
            if match:
                location = match.group(1)
                if "," in location:
                    parts = [p.strip() for p in location.split(",")]
                    if not record.city:
                        record.city = parts[0] if parts else ""
                    record.country = parts[1] if len(parts) > 1 else ""
                else:
                    record.country = location

            # Try Portuguese pipe-separated format for country
            if not record.country and "|" in addr:
                parts = [p.strip() for p in addr.split("|")]
                if len(parts) >= 3:
                    if not record.city:
                        record.city = parts[-2]  # Second to last is usually city
                    record.country = parts[-1]   # Last is usually country

            # Try to extract email from address if embedded
            if not record.email:
                email_match = re.search(r"[\w\.-]+@[\w\.-]+", addr)
                if email_match:
                    record.email = email_match.group(0)



    def _extract_financial_tables(self, soup: BeautifulSoup, record: Record) -> None:
        """Extract multi-year financial data from report tables."""
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue

            # Check for financial table headers
            header_text = clean(rows[0].get_text(" ", strip=True))
            if any(kw in header_text for kw in ["31/12/", "EUR", "Ingresos", "Resultado", "Activo", "Fondos propios"]):
                # Extract year columns
                years = []
                for cell in rows[0].find_all(["td", "th"]):
                    txt = clean(cell.get_text(" ", strip=True))
                    if re.match(r"\d{2}/\d{2}/\d{4}", txt) or re.match(r"\d{4}", txt):
                        years.append(txt)

                # Extract data rows
                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if not cells:
                        continue
                    label = clean(cells[0].get_text(" ", strip=True))
                    values = [clean(c.get_text(" ", strip=True)) for c in cells[1:]]

                    if "Ingresos de explotación" in label or "Cifra de Ventas" in label:
                        record.financial_history["revenue"] = dict(zip(years, values))
                    elif "Resultado del Ejercicio" in label or "Resultado ejercicio" in label:
                        record.financial_history["profit"] = dict(zip(years, values))
                    elif "Total activo" in label or "Total Activo" in label:
                        record.financial_history["total_assets"] = dict(zip(years, values))
                    elif "Fondos propios" in label:
                        record.financial_history["equity"] = dict(zip(years, values))
                    elif "Número empleados" in label or "Número de empleados" in label:
                        record.financial_history["employees"] = dict(zip(years, values))

                # Extract ratios
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        label = clean(cells[0].get_text(" ", strip=True))
                        if any(kw in label for kw in ["Rentabilidad", "Liquidez", "Endeudamiento", "Rotación", "Margen", "Cobertura", "Solvencia", "Apalancamiento"]):
                            values = [clean(c.get_text(" ", strip=True)) for c in cells[1:]]
                            if years and len(values) == len(years):
                                record.ratios[label] = dict(zip(years, values))

    def iter_search(
        self,
        query: str = "",
        max_pages: int | None = None,
    ) -> Iterable[Record]:
        page = 1
        while True:
            result = self.search(query=query, page=page)
            yield from result.records
            page += 1
            if not result.has_next:
                break
            if max_pages is not None and page > max_pages:
                break