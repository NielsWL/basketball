from playwright.sync_api import sync_playwright
import pandas as pd
import os
import json
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.bbl.scb.world/v2"
API_KEYS = {
    "nbbl": "8dc905d70eac940c38313e1284b2d5c0",
    "jbbl": "81e03c389456a1d3441cd89ce9703d88",
}


class _TableHTMLParser(HTMLParser):
    """Very small HTML table parser that avoids optional dependencies."""

    def __init__(self) -> None:
        super().__init__()
        self._current_row: Optional[List[str]] = None
        self._current_cell: List[str] = []
        self._current_row_is_header = False
        self.header: Optional[List[str]] = None
        self.rows: List[List[str]] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag == "tr":
            self._current_row = []
            self._current_row_is_header = False
        elif tag in {"td", "th"}:
            if self._current_row is None:
                self._current_row = []
            self._in_cell = True
            self._current_cell = []
            if tag == "th":
                self._current_row_is_header = True

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"td", "th"}:
            if self._in_cell and self._current_row is not None:
                cell_text = "".join(self._current_cell).strip()
                self._current_row.append(cell_text)
            self._in_cell = False
            self._current_cell = []
        elif tag == "tr" and self._current_row:
            if self._current_row_is_header and self.header is None:
                self.header = self._current_row
            else:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._in_cell:
            self._current_cell.append(data)


def _html_table_to_dataframe(html: str) -> pd.DataFrame:
    parser = _TableHTMLParser()
    parser.feed(html)
    header = parser.header
    rows = parser.rows

    if header and all(len(row) == len(header) for row in rows):
        return pd.DataFrame(rows, columns=header)
    return pd.DataFrame(rows)

# --- Einstellungen ---
url = "https://nbbl-basketball.de/jbbl/matches/2003550?status=0"
save_dir = os.path.join("docs", "data")
os.makedirs(save_dir, exist_ok=True)

file_path = os.path.join(save_dir, "boxscore_2003550.csv")


def _extract_league_and_match_id(match_url: str) -> Optional[tuple[str, str]]:
    parsed = urlparse(match_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3:
        return None
    league = parts[0].lower()
    match_id = parts[-1]
    return league, match_id


def _fetch_team_names(match_url: str) -> List[str]:
    extracted = _extract_league_and_match_id(match_url)
    if not extracted:
        return []
    league, match_id = extracted
    api_key = API_KEYS.get(league)
    if not api_key:
        return []
    request = Request(
        f"{API_BASE_URL}/game/{match_id}",
        headers={
            "x-api-key": api_key,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:  # nosec: B310 - trusted domain
            data = json.load(response)
    except HTTPError as exc:  # pragma: no cover - network issues
        print(f"⚠️ Teamnamen-Anfrage fehlgeschlagen (Status {exc.code}).")
        return []
    except URLError as exc:  # pragma: no cover - network issues
        print(f"⚠️ Teamnamen konnten nicht geladen werden: {exc.reason}")
        return []

    team_names: List[str] = []
    home_team = data.get("homeTeam") or {}
    guest_team = data.get("guestTeam") or {}
    if isinstance(home_team, dict):
        name = home_team.get("name")
        if isinstance(name, str) and name.strip():
            team_names.append(name.strip())
    if isinstance(guest_team, dict):
        name = guest_team.get("name")
        if isinstance(name, str) and name.strip():
            team_names.append(name.strip())
    return team_names


# --- Playwright starten ---
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "() => {"
            "  const tables = document.querySelectorAll('table');"
            "  return tables.length > 0 && tables[0].querySelectorAll('tr').length > 2;"
            " }",
            timeout=20_000,
        )
    except Exception:
        page.wait_for_timeout(2_000)

    team_names = _fetch_team_names(url)

    # --- Tabellen finden ---
    tables = page.locator("table")
    count = tables.count()

    if count == 0:
        print("❌ Keine Tabellen gefunden – evtl. Seite wird dynamisch geladen.")
        browser.close()
        raise SystemExit()

    all_dfs = []

    for i in range(count):
        html = tables.nth(i).inner_html()
        df = _html_table_to_dataframe(html)

        # Optional: Teamname aus Überschrift ermitteln
        heading = f"Team_{i + 1}"
        try:
            heading = page.locator("h2").nth(i).inner_text().strip() or heading
        except Exception:
            pass

        team_name = team_names[i] if i < len(team_names) else heading
        df.insert(0, "Team", team_name)
        all_dfs.append(df)

    context.close()
    browser.close()

# --- Alle Tabellen kombinieren ---
df_all = pd.concat(all_dfs, ignore_index=True)

# --- CSV speichern ---
df_all.to_csv(file_path, index=False, encoding="utf-8-sig")

print(f"✅ Boxscores gespeichert als CSV:\n{file_path}")
print(f"📊 Tabellen zusammengeführt: {len(all_dfs)} | Zeilen: {len(df_all)}")
