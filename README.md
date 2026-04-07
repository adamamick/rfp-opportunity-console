# Natrona County Opportunity Scanner

This app scans Natrona County RSS feeds and flags opportunities relevant to Wyoming Building Supply (windows, doors, glazing, contractor-facing projects).

## What This App Does
- Pulls RSS data from Natrona County feeds.
- Follows item links and scores each item for procurement + building-supply relevance.
- Writes reports to:
  - `reports/opportunities_latest.md`
  - `reports/opportunities_latest.json`
- Tracks already-seen opportunities in `state/seen_ids.json`.
- Optionally sends email alerts for new opportunities.

## How The Workflow Works
1. The scanner reads RSS feeds.
2. It calculates a score per item.
3. Items are labeled `LOW`, `MEDIUM`, or `HIGH`.
4. New items are identified using `state/seen_ids.json`.
5. A report is saved.
6. If email is configured, it sends alerts only for new items at your threshold.

## Quick Start
```bash
python3 src/opportunity_scanner.py
```

Useful options:
```bash
python3 src/opportunity_scanner.py --days 45 --max-items 200
python3 src/opportunity_scanner.py --feed-url /path/to/feed.xml --feed-url https://example.com/feed.xml
python3 src/opportunity_scanner.py --notify-email you@company.com --notify-on-level HIGH
```

## Email Alerts (Most Cost-Effective)
Use normal SMTP credentials from a mailbox you control.

Set environment variables before running:
```bash
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="alerts@yourdomain.com"
export SMTP_PASSWORD="your-app-password"
export SMTP_FROM="alerts@yourdomain.com"
```

Then run:
```bash
python3 src/opportunity_scanner.py --notify-email you@yourdomain.com --notify-on-level MEDIUM
```

Simulate the exact email first (no send):
```bash
python3 src/opportunity_scanner.py --notify-email you@yourdomain.com --notify-on-level MEDIUM --simulate-email --force-notify-current
```

Notes:
- `--notify-on-level MEDIUM` is a good default.
- For fewer alerts, use `HIGH`.
- For broad coverage, use `LOW`.

## Phone Text Option (Later)
A simple no-code way is email-to-SMS gateways.
- Verizon example: `3035551234@vtext.com`
- AT&T example: `3035551234@txt.att.net`

You can pass that address in `--notify-email` to receive text-like alerts.

## Local HTML Dashboard (No SMTP)
This gives you a private, on-demand Generate button experience.

Start server:
```bash
python3 src/dashboard_server.py
```

Open:
```text
http://localhost:8787
```

Or auto-open browser with one command:
```bash
python3 src/dashboard_server.py --open
```

What happens when you click **Generate Opportunities**:
1. The page calls `/api/generate`.
2. Server runs `src/opportunity_scanner.py`.
3. New report JSON is loaded.
4. Results render into summary cards + opportunity panels.

Tip:
- Keep **Use cached feed files** checked for stable local demos.
- Uncheck it to run against live feed URLs.

## Daily Automation (Local)
Run every day at 7:00 AM local time:
```bash
0 7 * * * /usr/bin/python3 /Users/adamamick/Downloads/RFP\ TRACKER/src/opportunity_scanner.py --notify-email you@yourdomain.com --notify-on-level MEDIUM
```

## Put This On GitHub
From `/Users/adamamick/Downloads/RFP TRACKER`:
```bash
git init
git add .
git commit -m "Initial Natrona opportunity scanner"
git branch -M main
git remote add origin https://github.com/<your-org>/<your-repo>.git
git push -u origin main
```

If the remote repo already exists, only run:
```bash
git add .
git commit -m "Update scanner and alerts"
git push
```

## Deploy Online Now (Render)
Fastest path to get a live URL:

1. Push this repo to GitHub.
2. Go to [https://render.com](https://render.com) and click **New +** -> **Web Service**.
3. Connect your GitHub repo.
4. Use these settings:
   - Runtime: `Python 3`
   - Build Command: `echo "no build step"`
   - Start Command: `./start.sh`
   - Auto-Deploy: On
5. Click **Create Web Service**.

After deploy, Render gives a URL like:
`https://your-app-name.onrender.com`

### Keep It Team-Only
In Render:
- `Settings` -> `Access Control`
- Turn on authentication so only your team can open it.

## Netlify + Backend (Recommended split)
If frontend is on Netlify, deploy backend separately (Render) and point the frontend to it.

1. Deploy backend on Render using this repo:
   - Start command: `./start.sh`
2. Copy backend URL, for example:
   - `https://rfp-opportunity-console.onrender.com`
3. In `web/config.js`, set:
```js
window.APP_CONFIG = {
  API_BASE: "https://rfp-opportunity-console.onrender.com"
};
```
4. Commit and push so Netlify redeploys.

Now the Generate button on Netlify will call the backend API.

## Default Feed Sources
- `https://www.natronacounty-wy.gov/RSSFeed.aspx?ModID=76&CID=All-0`
- `https://www.natronacounty-wy.gov/RSSFeed.aspx?ModID=1&CID=All-newsflash.xml`
- `https://www.natronacounty-wy.gov/RSSFeed.aspx?ModID=65&CID=All-0`

You can edit `FEED_URLS` in `src/opportunity_scanner.py`.
