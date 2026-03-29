"""
Daily Newsletter Digest Bot
- Reads newsletters from mason.fairfield.news@outlook.com via Composio
- Uses html2text for clean, token-efficient email parsing
- Summarizes using a finance-focused Smart Brevity prompt via Gemini
- Deduplicates against yesterday's full newsletter
- Tracks last-run timestamp so no emails are missed or double-counted
- Sends to all recipients listed in NEWSLETTER_RECIPIENTS secret
"""

import os
import re
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
import html2text
from google import genai
from composio import Composio

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
COMPOSIO_KEY = os.getenv("COMPOSIO_API_KEY")
USER_ID      = os.getenv("COMPOSIO_USER_ID")
STATE_FILE   = Path("bot_state.json")

# Parse recipients — comma-separated emails in secret
raw_recipients = os.getenv("NEWSLETTER_RECIPIENTS", "")
RECIPIENTS = [r.strip() for r in raw_recipients.split(",") if r.strip()]

# Set up Gemini
client = genai.Client(api_key=GEMINI_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

# Set up Composio
composio = Composio(api_key=COMPOSIO_KEY)

TODAY = datetime.date.today().strftime("%B %d, %Y")

# ── html2text config ──────────────────────────────────────────────────────────
h = html2text.HTML2Text()
h.ignore_links    = True
h.ignore_images   = True
h.ignore_emphasis = False
h.body_width      = 0
h.ignore_tables   = False

# ── Noise patterns ────────────────────────────────────────────────────────────
NOISE_PATTERNS = [
    r"unsubscribe.*",
    r"view\s+(this\s+)?email\s+in.*browser.*",
    r"if you.*no longer.*wish.*",
    r"manage.*preferences.*",
    r"you.*receiving.*because.*",
    r"©\s*\d{4}.*",
    r"all rights reserved.*",
    r"privacy policy.*",
    r"terms of (service|use).*",
    r"click here to.*",
    r"forward this email.*",
    r"add .* to your address book.*",
    r"was this email.*forwarded.*",
    r"follow us on.*",
    r"connect with us.*",
    r"\*\*\*.*\*\*\*",
]

def clean_text(raw_html: str) -> str:
    text  = h.handle(raw_html)
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if any(re.search(p, stripped, re.IGNORECASE) for p in NOISE_PATTERNS):
            continue
        cleaned.append(stripped)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return text.strip()


# ── State management ──────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None, "yesterdays_newsletter": ""}

def save_state(last_run: str, newsletter_html: str):
    with open(STATE_FILE, "w") as f:
        json.dump({
            "last_run": last_run,
            "yesterdays_newsletter": newsletter_html
        }, f, indent=2)


# ── Step 1: Fetch emails since last run ───────────────────────────────────────
def fetch_newsletters(since: str) -> list:
    print(f"📥 Fetching newsletters since {since}...")

    list_result = composio.tools.execute(
        "OUTLOOK_LIST_MESSAGES",
        user_id=USER_ID,
        arguments={
            "folder_name": "Inbox",
            "filter": f"receivedDateTime ge {since}"
        },
        dangerously_skip_version_check=True
    )

    messages = list_result.get("data", {}).get("value", [])
    print(f"   Found {len(messages)} emails.")

    if not messages:
        print("   No new newsletters. Exiting.")
        return []

    full_emails = []
    for msg in messages:
        msg_id = msg.get("id")

        detail = composio.tools.execute(
            "OUTLOOK_GET_MESSAGE",
            user_id=USER_ID,
            arguments={"message_id": msg_id},
            dangerously_skip_version_check=True
        )

        raw_body = detail.get("data", {}).get("body", {}).get("content", "")
        sender   = msg.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
        subject  = msg.get("subject", "No Subject")
        clean_body = clean_text(raw_body)

        full_emails.append({
            "sender":  sender,
            "subject": subject,
            "body":    clean_body[:5000]
        })

    return full_emails


# ── Step 2: Build consolidated text ──────────────────────────────────────────
def build_consolidated_text(emails: list) -> str:
    return "\n\n".join(
        f"--- SOURCE: {e['sender']} | SUBJECT: {e['subject']} ---\n{e['body']}"
        for e in emails
    )


# ── Step 3: Summarize with Gemini ─────────────────────────────────────────────
def summarize(newsletters_text: str, yesterdays_newsletter: str) -> str:
    print("🤖 Summarizing with Gemini...")

    prompt = f"""# Consolidated Daily Newsletter Agent Prompt

## Role

You are an elite financial news editor and newsletter strategist creating a **finished, reader-facing daily newsletter** for a single user. Your job is to transform **aggregated raw newsletter text** into one **clean, concise, highly useful, well-organized daily briefing**.

You are writing for a reader who cares most about:

* markets and macro
* investment banking
* M&A and transactions
* corporate development and corporate strategy
* business developments with strategic or financial significance
* major policy or geopolitical developments only when they materially matter
* finance careers and adjacent developments when relevant
* AI developments with financial, strategic, or market significance
* real estate — commercial, residential, REIT, macro housing trends, notable transactions
* industrials — manufacturing, infrastructure, defense, energy, logistics, supply chain

Your writing style should reflect **Axios / Smart Brevity** principles:

* concise but not shallow
* highly scannable
* reader-first
* practical and informative
* crisp, clean, and polished
* focused on **why it matters**
* no fluff, no filler, no generic transitions

---

## Core Objective

Act as an **editor**, not a transcription engine.

1. Ignore noise and non-editorial junk.
2. Extract the real stories, developments, and themes.
3. Merge duplicate or overlapping coverage into single story items.
4. Rank items by relevance, novelty, and practical usefulness.
5. Organize into logical sections.
6. Write polished, reader-facing copy in Smart Brevity style.
7. Avoid repeating yesterday's stories unless there is a real update.

---

## Editorial Prioritization

Prioritize:
* markets, rates, inflation, credit, currencies, commodities, macro shifts
* M&A, capital markets, restructuring, financing, activist situations, major transactions
* corporate strategy, earnings with strategic implications, large partnerships, spin-offs, divestitures
* policy, regulation, antitrust, trade, taxation, industrial policy, sanctions, legal developments
* geopolitics only when materially consequential for markets, sectors, or capital flows
* finance careers, recruiting, compensation, industry structure
* AI developments with direct financial or strategic significance
* real estate transactions, REIT activity, housing data, commercial real estate trends
* industrials — defense contracts, infrastructure spending, manufacturing shifts, energy

Deprioritize or exclude:
* light product launches with no strategic significance
* routine consumer brand news
* minor executive commentary with no meaningful change
* low-signal political drama without policy or strategic relevance
* repetitive versions of the same story
* pure marketing emails with no editorial content

---

## Deduplication Rules

Within today's inputs: treat different wording of the same event as one story.
Against yesterday's newsletter: do not repeat unless there is a material update.

---

## Section Structure

Use these sections when relevant:

* **Market Update**
* **IB / M&A / Transactions**
* **Companies / Strategy**
* **AI Developments**
* **Real Estate**
* **Industrials**
* **Politics / Policy**
* **Geopolitics / Major Global Stories**
* **Other Worth Knowing**

Optional: Finance Careers / Industry, Credit / Restructuring, Earnings That Matter, Capital Markets, What Changed Since Yesterday.
Omit any section with nothing worth including.

---

## Required Story Item Format

<p><strong>Source:</strong> ...<br>
<strong>Author:</strong> ...<br>
<strong>Headline:</strong> ...</p>
<ul>
  <li>2-5 sentences: what happened, why it matters, what changed. Include specifics where available.</li>
</ul>

---

## Style Constraints

* Simple clean HTML only: `<h2>`, `<p>`, `<strong>`, `<br>`, `<ul>`, `<li>`
* No markdown, no code fences, no CSS, no wrapper tags
* No introductions, process notes, or AI mentions
* Output must be immediately usable as email body content

---

## Inputs

NEWSLETTERS_CONSOLIDATED:
{newsletters_text}

YESTERDAYS_NEWSLETTER:
{yesterdays_newsletter if yesterdays_newsletter else "No previous newsletter available."}

---

Return only the final consolidated newsletter as reader-facing email-safe HTML."""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )
    return response.text


# ── Step 4: Send digest ───────────────────────────────────────────────────────
def send_digest(html_body: str):
    print(f"📤 Sending digest to: {', '.join(RECIPIENTS)}...")

 composio.tools.execute(
    "OUTLOOK_SEND_EMAIL",
    user_id=USER_ID,
    arguments={
        "to": ", ".join(RECIPIENTS),
        },
        dangerously_skip_version_check=True
    )
    print("   ✅ Sent!")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n🗞️  Newsletter Bot starting — {TODAY}\n")

    if not RECIPIENTS:
        print("❌ No recipients set. Add NEWSLETTER_RECIPIENTS to GitHub Secrets.")
        return

    if not USER_ID:
        print("❌ No Composio user ID. Add COMPOSIO_USER_ID to GitHub Secrets.")
        return

    state                 = load_state()
    last_run              = state.get("last_run")
    yesterdays_newsletter = state.get("yesterdays_newsletter", "")

    if last_run:
        since = last_run
        print(f"   Last run: {since}")
    else:
        since = (datetime.datetime.utcnow() - datetime.timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        print("   First run — fetching last 25 hours.")

    this_run = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    emails = fetch_newsletters(since)
    if not emails:
        return

    newsletters_text = build_consolidated_text(emails)
    print(f"   Consolidated {len(emails)} emails → {len(newsletters_text):,} characters.")

    digest_html = summarize(newsletters_text, yesterdays_newsletter)

    send_digest(digest_html)

    save_state(this_run, digest_html)
    print("   💾 State saved for tomorrow.")

    print("\n✅ Done! Check your inbox.\n")


if __name__ == "__main__":
    main()
