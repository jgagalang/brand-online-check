# Scheduled task — fill the dashboard (daily, 20:30 Europe/London)

Paste everything below the line as the task prompt. Replace PASTE_YOUR_SHEET_ID_HERE first.

---

Copy tonight's online-check results from the Google Sheet into the dashboard artifact. Do not reply to anyone; do not read or write
anything in BigQuery.

1. Open the Google Sheet with id PASTE_YOUR_SHEET_ID_HERE, tab `results`. Read the rows where `check_date` equals today (Europe/London).
   Columns: check_date, checked_at, brand, site, platform (ROO / UBR / JET), status, detail, url. If there are no rows for today, stop.

2. Build one document and write it with the Artifact tool (action write_db, set) to https://claude.ai/artifact/F6KXW219jBjVhnk6wACpNZ,
   collection `checks`, doc id = today's date YYYY-MM-DD:

   {"date": "YYYY-MM-DD", "checked_at": "<checked_at from the rows>", "label": "8pm",
    "sites": [ one entry per site, in the order the sites appear in the Sheet, grouped by brand:
      {"brand": "<brand>", "site": "<site>",
       "deliveroo": {"status": "<status>", "note": "<detail>"},
       "uber":      {"status": "<status>", "note": "<detail>", "url": "<url>"},
       "justeat":   {"status": "<status>", "note": "<detail>", "url": "<url>"}} ]}

   Map platform ROO → deliveroo, UBR → uber, JET → justeat. Status values pass through as-is (online, offline, n/a, unknown, blocked;
   write blocked as "unknown"). Omit `note` when detail is empty and `url` when the url is empty.

3. Stop. Nothing else to do.
