from playwright.sync_api import sync_playwright
import pandas as pd
import os
from html.parser import HTMLParser
from typing import List, Optional


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

# --- Playwright starten ---
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")

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
        try:
            heading = page.locator("h2").nth(i).inner_text()
        except:
            heading = f"Team_{i + 1}"

        df.insert(0, "Team", heading)
        all_dfs.append(df)

    browser.close()

# --- Alle Tabellen kombinieren ---
df_all = pd.concat(all_dfs, ignore_index=True)

# --- CSV speichern ---
df_all.to_csv(file_path, index=False, encoding="utf-8-sig")

print(f"✅ Boxscores gespeichert als CSV:\n{file_path}")
print(f"📊 Tabellen zusammengeführt: {len(all_dfs)} | Zeilen: {len(df_all)}")
