# Scheduled task — repair step (runs 20:15 Europe/London, daily)

Paste everything below the line as the task prompt. It does nothing on nights where the script read every page.

---

You maintain the nightly online check for Sessions validation brands. The script `online_check.py` ran at 20:00.
Your only job is to fix pages it could not read, by updating `markers.json`. Never edit `online_check.py`.

Principle: read-only on sessions-core-data. You never write to BigQuery. Results live in the Google Sheet "Brand online check".

1. Open the Sheet's `failures` tab and look for rows with today's `check_date`. If there are none, stop — nothing to do.

2. For each failure row (`page_text` is the rendered page text as the script saw it):
   - Decide from the text and screenshot whether the store was ONLINE (orderable: delivery time shown, add-to-basket active)
     or OFFLINE (closed / unavailable / opens later), or whether the page is a bot wall or didn't load (then leave it alone).
   - Identify the exact wording that now expresses that state, near the platform's anchor ("Store info" on Uber Eats,
     "Basket" on Just Eat). If the anchor itself has changed, note the new one.

3. Work out the change to `markers.json` (the file lives in the GitHub repo `brand-online-check`):
   - Add a regex for the new wording to the right list (`UBR`/`JET` → `offline` or `online`), or update `anchor`.
     Keep existing patterns unless they are clearly obsolete. Set `_version` to today's date.
   - Be conservative: a pattern must match the saved text for the failed page and must not match the opposite state
     (test it against both the new text and the existing examples: "Delivery 25-40 min" is online, "Delivery Unavailable" is offline).

4. Verify: re-classify each failure row's `page_text` with the proposed markers (same logic as `classify` in `online_check.py`:
   check `blocked`, then the platform's `offline` list, then `online`, within 400 characters after the anchor) and confirm every failed
   page now returns online or offline. If any still returns unknown, do not guess — report it instead.

5. Correct tonight's results: in the Sheet's `results` tab, update the rows for today where `status` is unknown or blocked and
   the page is now readable, setting `status` and `detail`.

6. Report in one short message: which platform's wording changed, the exact new `markers.json` content to commit in GitHub, and the
   corrected statuses. If nothing could be repaired, say why (bot wall / page error / ambiguous) and that a human should look at the page.
