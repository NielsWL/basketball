from playwright.sync_api import sync_playwright
import pandas as pd
from io import StringIO
import os

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
        # StringIO nutzen, damit kein lxml nötig ist
        df = pd.read_html(StringIO("<table>" + html + "</table>"))[0]

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
