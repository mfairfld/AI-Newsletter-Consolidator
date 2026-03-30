# AI Newsletter Consolidator

A GitHub Actions bot that reads your newsletters every morning, consolidates them into one clean daily briefing using Gemini, and sends it to your inbox (and optionally BCCs a list of recipients).

---

## What It Does

- Fetches all emails received since the last run from a designated Outlook inbox via Composio
- Cleans and strips HTML noise (footers, unsubscribe links, tracking junk, etc.)
- Passes the consolidated content to Gemini with a finance-focused Smart Brevity editorial prompt
- Deduplicates stories against yesterday's newsletter so you never see the same thing twice
- Sends the finished digest to a primary recipient and BCCs any additional recipients
- Saves state between runs so no emails are missed or double-counted

---

## Output Format

The digest is organized into sections (only included when relevant):

- **Market Update**
- **IB / M&A / Transactions**
- **Companies / Strategy**
- **AI Developments**
- **Real Estate**
- **Industrials**
- **Politics / Policy**
- **Geopolitics / Major Global Stories**
- **Finance Careers / Industry**
- **Other Worth Knowing**

Each story follows a two-bullet format:
- What happened (facts, deal sizes, parties involved)
- **Why it matters** (implications, strategic significance)

---

## Setup

### 1. Prerequisites

- A Microsoft Outlook account that receives your newsletters
- A [Composio](https://composio.dev) account with Outlook connected
- A [Google Gemini](https://aistudio.google.com) API key

### 2. Fork or clone this repo

### 3. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Description |
|---|---|
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `COMPOSIO_API_KEY` | Your Composio API key |
| `COMPOSIO_USER_ID` | Your Composio user ID |
| `NEWSLETTER_TO` | Primary recipient email (visible in the To field) |
| `NEWSLETTER_RECIPIENTS` | Comma-separated list of BCC recipients (e.g. `a@gmail.com,b@gmail.com`) |

### 4. Update the workflow schedule

In `.github/workflows/newsletter.yml`, adjust the cron schedule to your preferred send time:

```yaml
- cron: '0 11 * * *'  # 11:00 AM UTC = 7:00 AM ET
```

Common options:
- 6 AM ET → `'0 10 * * *'`
- 7 AM ET → `'0 11 * * *'`
- 8 AM ET → `'0 12 * * *'`

---

## Running Manually

Go to **Actions → Daily Newsletter Digest → Run workflow → Run workflow** to trigger it immediately without waiting for the schedule.

---

## How State Works

The bot saves a `bot_state.json` file (via GitHub Actions cache) after each run containing:
- The timestamp of the last run — used to fetch only new emails next time
- Yesterday's newsletter — used to deduplicate stories

On the first run, it fetches the last 25 hours of email.

---

## Customizing the Prompt

The Gemini prompt is in `newsletter_bot.py` inside the `summarize()` function. You can edit:
- **Reader interests** — what topics to prioritize
- **Section structure** — which sections to include
- **Editorial tone** — currently tuned to Axios / Smart Brevity style
- **Deprioritization rules** — what to filter out

---

## Dependencies

```
google-genai
composio
python-dotenv
html2text
```
