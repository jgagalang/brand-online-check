"""
Nightly online check for validation brands (script-first; Claude only repairs when a page can't be read).

Per site:
  Deliveroo  -> Serve's hourly menu health check in BigQuery (isLive)
  Uber Eats  -> consumer page in a headless browser, read with markers.json
  Just Eat   -> consumer page in a headless browser, read with markers.json

Principle: READ-ONLY on sessions-core-data. The only BigQuery call is one SELECT on Serve's health check.
Nothing is written to core.

Outputs:
  results    -> Google Sheet (tab "results"): one row per site/platform/night; plus results/<date>.json locally
  failures   -> Google Sheet (tab "failures"): page text saved when no marker matched, for the repair step

Run:  python online_check.py            (expects sites.csv and markers.json beside it)
Env:  SHEET_ID (the Google Sheet's id from its URL).
      Google login comes from Application Default Credentials: locally via `gcloud auth application-default login`,
      on GitHub Actions via the GOOGLE_APPLICATION_CREDENTIALS file the workflow writes from a secret.
      Pass --no-sheet to skip the Sheet (prints and saves locally only).
Setup once:  pip install playwright google-cloud-bigquery gspread && playwright install chromium
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/London")
PROJECT = "sessions-core-data"
SHEET_ID = os.environ.get("SHEET_ID", "")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PAGE_WAIT_MS = 4000
PAUSE_S = 2


@dataclass
class Row:
    check_date: str
    checked_at: str
    brand: str
    site: str
    platform: str          # ROO | UBR | JET
    status: str            # online | offline | n/a | unknown | blocked
    detail: str = ""       # text that decided the status, or why it couldn't
    url: str = ""


# ---------- inputs ----------

def load_sites() -> list[dict]:
    with open(HERE / "sites.csv", newline="") as f:
        return list(csv.DictReader(f))


def load_markers() -> dict:
    return json.loads((HERE / "markers.json").read_text())


# ---------- Deliveroo via Serve ----------

def deliveroo_status(sites: list[dict], today: dt.date) -> dict[tuple[str, str], tuple[str, str]]:
    """Returns {(venue_id, brand): (status, detail)} from Serve's latest health check today."""
    from google.cloud import bigquery
    bq = bigquery.Client(project=PROJECT)
    brands = sorted({s["brand"].split(" (")[0] for s in sites})
    sql = f"""
      SELECT venueId, brandName, publishData.deliveroo.isLive AS live,
             FORMAT_TIMESTAMP('%H:%M', publishData.deliveroo.healthCheckAt, 'Europe/London') AS checked
      FROM `{PROJECT}.serve.prod_venues_direct_delivery_menu_status`
      WHERE calendar_id = {today.strftime('%Y%m%d')} AND brandName IN UNNEST(@brands)
      QUALIFY ROW_NUMBER() OVER (PARTITION BY venueId, brandName ORDER BY hour DESC, updatedAt DESC) = 1
    """
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("brands", "STRING", brands)]))
    out = {}
    for r in job.result():
        out[(r["venueId"], r["brandName"])] = ("online" if r["live"] else "offline", f"Serve health check {r['checked']}")
    return out


# ---------- Uber / JET via headless browser ----------

def classify(platform: str, text: str, markers: dict) -> tuple[str, str]:
    t = re.sub(r"\s+", " ", text).lower()
    for p in markers["blocked"]:
        if re.search(p, t):
            return "blocked", p
    m = markers[platform]
    anchor = m.get("anchor", "").lower()
    i = t.find(anchor) if anchor else 0
    window = t[i:i + 400] if i >= 0 else t
    for status in ("offline", "online"):
        for p in m[status]:
            hit = re.search(p, window)
            if hit:
                return status, hit.group(0)
    return "unknown", ""


FAILED_PAGES: list[dict] = []   # {brand, site, platform, url, text} for the repair step


def check_pages(targets: list[tuple[dict, str, str]], markers: dict, fail_dir: Path) -> dict[tuple[str, str, str], tuple[str, str]]:
    """targets: [(site_row, platform, url)] -> {(brand, site, platform): (status, detail)}"""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    results = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="en-GB", viewport={"width": 1280, "height": 900})
        for s, platform, url in targets:
            key = (s["brand"], s["site"], platform)
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(PAGE_WAIT_MS)
                text = page.inner_text("body")
                status, detail = classify(platform, text, markers)
                if status in ("unknown", "blocked"):
                    # keep what we saw so the repair step can work out the new wording
                    FAILED_PAGES.append({"brand": s["brand"], "site": s["site"], "platform": platform, "url": url,
                                         "text": re.sub(r"\s+", " ", text)[:4000]})
                    fail_dir.mkdir(parents=True, exist_ok=True)
                    stem = re.sub(r"[^a-z0-9]+", "-", f"{s['site']}-{platform}".lower()).strip("-")
                    (fail_dir / f"{stem}.txt").write_text(text)
                    detail = detail or "no marker matched; page saved for repair"
                results[key] = (status, detail)
            except PWTimeout:
                results[key] = ("blocked", "timeout loading page")
            except Exception as e:  # noqa: BLE001
                results[key] = ("blocked", str(e)[:200])
            finally:
                page.close()
            time.sleep(PAUSE_S)
        browser.close()
    return results


# ---------- outputs ----------

def write_sheet(rows: list[Row]) -> None:
    """Append tonight's rows to the 'results' tab and any unreadable pages to the 'failures' tab."""
    import google.auth
    import gspread
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets",
                                           "https://www.googleapis.com/auth/drive"])
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)
    cols = list(Row.__dataclass_fields__)
    try:
        ws = sh.worksheet("results")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("results", rows=1, cols=len(cols)); ws.append_row(cols)
    ws.append_rows([[getattr(r, c) for c in cols] for r in rows], value_input_option="RAW")
    if FAILED_PAGES:
        fcols = ["check_date", "brand", "site", "platform", "url", "page_text"]
        try:
            fw = sh.worksheet("failures")
        except gspread.WorksheetNotFound:
            fw = sh.add_worksheet("failures", rows=1, cols=len(fcols)); fw.append_row(fcols)
        fw.append_rows([[rows[0].check_date, f["brand"], f["site"], f["platform"], f["url"], f["text"]] for f in FAILED_PAGES],
                       value_input_option="RAW")



# ---------- main ----------

def main() -> None:
    now = dt.datetime.now(TZ)
    today = now.date()
    weekday = now.strftime("%A")
    sites = load_sites()
    markers = load_markers()
    fail_dir = HERE / "failures" / today.isoformat()

    roo = deliveroo_status(sites, today)

    targets = []
    for s in sites:
        if weekday in (s.get("closed_days") or "").split(";"):
            continue
        if s["uber_url"]:
            targets.append((s, "UBR", s["uber_url"]))
        if s["jet_url"]:
            targets.append((s, "JET", s["jet_url"]))
    web = check_pages(targets, markers, fail_dir)

    rows: list[Row] = []
    for s in sites:
        closed_today = weekday in (s.get("closed_days") or "").split(";")
        brand_name = s["brand"].split(" (")[0]
        for platform, url in (("ROO", ""), ("UBR", s["uber_url"]), ("JET", s["jet_url"])):
            if closed_today:
                status, detail = "n/a", f"scheduled closed on {weekday}s"
            elif platform == "ROO":
                status, detail = roo.get((s["serve_venue_id"], brand_name), ("unknown", "no Serve health check today"))
            elif not url:
                status, detail = "n/a", "not set up on this platform"
            else:
                status, detail = web[(s["brand"], s["site"], platform)]
            rows.append(Row(today.isoformat(), now.isoformat(), s["brand"], s["site"], platform, status, detail, url))

    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{today.isoformat()}.json").write_text(json.dumps([asdict(r) for r in rows], indent=1))
    if "--no-sheet" not in sys.argv and SHEET_ID:
        write_sheet(rows)
    failures = sum(1 for r in rows if r.status in ("unknown", "blocked"))

    for r in rows:
        print(f"{r.brand[:22]:22} {r.site[:30]:30} {r.platform}  {r.status:8} {r.detail[:50]}")
    print(f"\n{len(rows)} rows, {failures} unreadable")


if __name__ == "__main__":
    main()
