# Nightly online check — setup (GitHub route, no Google Cloud admin needed)

**What this gives you.** At 20:00 London every night, GitHub runs the script on one of its machines: Deliveroo via Serve (read-only),
Uber Eats and Just Eat via their consumer pages in a headless browser. Results are appended to a Google Sheet you own. At 20:30 a
small Claude task copies that night's rows into the dashboard artifact. In the morning you open the artifact. Your laptop is not involved.

**Principle.** Read-only on sessions-core-data. The script runs as you (your own Google login, stored as a GitHub secret), so it can
do exactly what you can do in BigQuery and nothing more. It writes only to your Sheet.

**You need:** a GitHub account (Part 0 below walks through creating one), and the folder
`/Users/johngagalang/Documents/Platform scraper` with the files from the zip.

Grey boxes are pasted into Terminal exactly as written. Everything else is explanation or done in a browser.

---

## Part 0 — A GitHub account (5 minutes, browser)

GitHub is a website that stores code and can run it on a schedule for you. You only need the free tier.

1. Go to **github.com** and click **Sign up**.
2. Enter your work email (john@sessions.co.uk), choose a password, and pick a username (e.g. `john-sessions`). Complete the puzzle it shows.
3. GitHub emails you a code; type it in.
4. If it asks questions about your team or interests, you can skip them. Choose the **Free** plan if asked.
5. You land on your GitHub home page. That's it. You're signed in and ready for Part C.

One thing worth doing straight away for security: click your profile picture (top right) → **Settings** → **Password and authentication** →
**Enable two-factor authentication**, and follow the prompts with your phone's authenticator app. GitHub will ask you to do this within a
few days anyway.

If Sessions already has a GitHub organisation and you'd rather the repository lived there, ask whoever manages it to invite your new
account; the steps below are the same either way.

---

## Part A — The Sheet (2 minutes, browser)

In Google Drive create a new Sheet called **Brand online check**. Copy its id from the URL: the long string between `/d/` and `/edit`.
Keep it handy for Part C.

---

## Part B — Your Google login as a file (3 minutes, Terminal)

This re-does your Google sign-in with permission to read BigQuery *and* write Sheets, and copies the resulting credentials to the clipboard
so you can paste them into GitHub as a secret in Part C.

Paste:

```
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/drive
```

A browser opens; sign in with your Sessions account and click Allow (it will mention Sheets and Drive this time).

Paste:

```
gcloud auth application-default set-quota-project sessions-core-data
```

(If this one says you lack permission, ignore it and carry on; it isn't essential.)

Paste (copies the credentials file to your clipboard; nothing is printed):

```
pbcopy < ~/.config/gcloud/application_default_credentials.json
```

Don't paste the clipboard anywhere except the GitHub secret in Part C. It's your login.

---

## Part C — The GitHub repository (10 minutes, browser)

1. Signed in to github.com, click the **+** at the top right → **New repository**. Name it `brand-online-check`, choose **Private**,
   leave everything else as it is, click **Create repository**.

2. The new repository page has a line that says "…or **uploading an existing file**". Click that link. Open Finder at
   `/Users/johngagalang/Documents/Platform scraper` and drag these six files onto the GitHub page: `online_check.py`, `markers.json`,
   `sites.csv`, `REPAIR_TASK_PROMPT.md`, `DASHBOARD_TASK_PROMPT.md`, `SETUP.md`. Wait for the ticks, then click the green
   **Commit changes** button at the bottom. ("Commit" just means save.)

3. Add the workflow file (this is what tells GitHub when to run the script). Click **Add file → Create new file**. In the box that
   says "Name your file…" type exactly: `.github/workflows/online-check.yml` — typing each `/` turns the text before it into a
   folder, which is what you want. Now open the file `online-check.yml` from your Platform scraper folder in TextEdit, select all,
   copy, and paste it into the big empty box on GitHub. Click **Commit changes** (top right), then **Commit changes** again in the pop-up.

4. Add the two secrets (private values the script needs; nobody else can read them). In the repository, click the **Settings** tab
   (right-hand end of the tabs). In the left menu click **Secrets and variables** → **Actions**. Click **New repository secret**:
   - Name: `GOOGLE_CREDENTIALS_JSON`. Secret: paste (Cmd-V) — this is your clipboard from Part B. Click **Add secret**.
   - Click **New repository secret** again. Name: `SHEET_ID`. Secret: the Sheet id from Part A. Click **Add secret**.
   If you did Part B a while ago and have copied something else since, re-run the last Part B line to put the credentials back on the clipboard.

---

## Part D — Test it (5 minutes, browser)

Click the **Actions** tab → **Nightly online check** (left) → **Run workflow** → **Run workflow**. A run appears; click it to watch.
It takes three to four minutes. When it's green, open the Sheet: a `results` tab now has 51 rows for today.

If it's red, click into the failed step, copy the last 20 lines of output and paste them into Claude.

Nothing else to do for scheduling: the workflow file already says to run at 20:00 London every day (it fires at both possible UTC
hours and skips the wrong one, so it survives the clock change on Sunday).

---

## Part E — Fill the dashboard (3 minutes, Claude)

In Claude, create a **scheduled task**: daily, **20:30 Europe/London**, prompt = contents of `DASHBOARD_TASK_PROMPT.md` with the Sheet id
filled in where marked. It reads tonight's rows from the Sheet and writes them into the artifact at
https://claude.ai/artifact/F6KXW219jBjVhnk6wACpNZ. The Google Sheets connector needs to be enabled for the task.

---

## Each morning

Open the artifact. Tonight's row is shown by default; the dropdown goes back through previous nights. The Sheet's `results` tab is the full history.

---

## Later: adding or removing a site

In the GitHub repo open `sites.csv`, click the pencil icon, edit (one line per site: brand, site, Serve venue id, Uber URL, Just Eat URL,
closed days), **Commit changes**. The next 20:00 run uses the new list. No redeploy.

## Later: a platform changes its page wording

The script writes the unreadable page to the Sheet's `failures` tab and marks that site UNKNOWN. Run `REPAIR_TASK_PROMPT.md` in Claude;
it tells you the new pattern to add to `markers.json`, which you edit in GitHub the same way as `sites.csv`.

## Cost

GitHub Actions gives private repos 2,000 free minutes a month; this uses about 100. Nothing is billed on Google Cloud for reading.
