from playwright.sync_api import sync_playwright
import pandas as pd
import os

# --- Einstellungen ---
url = "https://nbbl-basketball.de/jbbl/matches/2003550?status=0"
save_dir = os.path.join("docs", "data")
os.makedirs(save_dir, exist_ok=True)

file_path = os.path.join(save_dir, "boxscore_2003550.xlsx")

# --- Playwright starten ---
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")

    # --- Tabellen finden ---
    tables = page.locator("table")
    count = tables.count()

    if count == 0:
        print("❌ Keine Tabellen gefunden – evtl. Seite noch nicht geladen.")
        browser.close()
        raise SystemExit()

    writer = pd.ExcelWriter(file_path, engine="openpyxl")

    for i in range(count):
        html = tables.nth(i).inner_html()
        df = pd.read_html("<table>" + html + "</table>")[0]
        sheet_name = f"Tabelle_{i + 1}"
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    writer.close()
    browser.close()

print(f"✅ Boxscores gespeichert unter: {file_path}")
