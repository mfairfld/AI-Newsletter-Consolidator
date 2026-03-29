"""
Daily Newsletter Digest Bot
Reads newsletters from Outlook via Composio,
summarizes in Axios style using Gemini,
removes duplicates from yesterday, and sends the digest.
Supports multiple recipients via comma-separated NEWSLETTER_RECIPIENT secret.
"""

import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from composio import Composio

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

GEMINI_KEY      = os.getenv("GEMINI_API_KEY")
COMPOSIO_KEY    = os.getenv("COMPOSIO_API_KEY")
FOLDER_NAME     = os.getenv("NEWSLETTER_FOLDER", "Newsletters")
CACHE_FILE      = Path("yesterday_stories.json")

# Parse recipients — supports one or many comma-separated emails
# e.g. "you@email.com" or "you@email.com, friend@email.com, other@email.com"
raw_recipients  = os.getenv("NEWSLETTER_RECIPIENTS", "")
RECIPIENTS      = [
    {"emailAddress": {"address": r.strip()}}
    for r in raw_recipients.split(",")
    if r.strip()
]

# Set up Gemini
genai.configure(api_key=GEMINI_KEY)
model     = genai.GenerativeModel("gemini-2.5-flash")
composio  = Composio(api_key=COMPOSIO_KEY)

TODAY     = datetime.date.today().strftime("%B %d, %Y")


# ── Step 1: Fetch today's newsletters from Outlook ────────────────────────────
def fetch_newsletters():
    print("📥 Fetching newsletters from Outlook...")

    result = composio.actions.execute(
        action="OUTLOOK_LIST_MESSAGES",
        params={
            "folder_name": FOLDER_NAME,
            "filter": "receivedDateTime ge " + (
                datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    )

    messages = result.get("data", {}).get("value", [])
    print(f"   Found {len(messages)} newsletters.")

    if not messages:
        print("   No newsletters found today. Exiting.")
        return []

    full_emails = []
    for msg in messages:
        msg_id = msg.get("id")
        detail = composio.actions.execute(
            action="OUTLOOK_GET_MESSAGE",
            params={"message_id": msg_id}
        )
        body    = detail.get("data", {}).get("body", {}).get("content", "")
        sender  = msg.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
        subject = msg.get("subject", "No Subject")
        full_emails.append({
            "sender":  sender,
            "subject": subject,
            "body":    body[:8000]
        })

    return full_emails


# ── Step 2: Load yesterday's headlines for deduplication ─────────────────────
def load_yesterday_stories():
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return []


# ── Step 3: Summarize with Gemini in Axios style ──────────────────────────────
def summarize_newsletters(emails, yesterday_headlines):
    print("🤖 Summarizing with Gemini...")

    email_content = "\n\n---\n\n".join([
        f"FROM: {e['sender']}\nSUBJECT: {e['subject']}\n\n{e['body']}"
        for e in emails
    ])

    yesterday_block = (
        "YESTERDAY'S HEADLINES (remove duplicates of these):\n" +
        "\n".join(f"- {h}" for h in yesterday_headlines)
    ) if yesterday_headlines else "No previous digest — skip deduplication."

    prompt = f"""You are a newsletter editor. Today is {TODAY}.

Your job:
1. Read the newsletter emails below.
2. Extract the most important stories.
3. Remove any stories that duplicate yesterday's headlines.
4. Format the final digest in Axios "Smart Brevity" style.

AXIOS STYLE RULES:
- Open each story with a bold one-sentence hook.
- Use labels like "Why it matters:", "The big picture:", "Between the lines:", "What to watch:".
- Keep each story to 3-5 bullet points max.
- Simple, clear language. No jargon.
- Group stories by topic if there are many.
- End with a "1 fun thing" section if anything light came up.
- Format as clean HTML for email using <h2>, <p>, <ul>, <li>, <b> tags.
- Add a header: "Your Daily Digest — {TODAY}"

{yesterday_block}

---

TODAY'S NEWSLETTERS:
{email_content}

---

Return ONLY the HTML email body. No commentary, no markdown fences."""

    response    = model.generate_content(prompt)
    digest_html = response.text

    headlines_prompt = f"""From the digest below, extract a JSON list of headline strings.
Return ONLY a JSON array. No other text, no markdown fences.
Example: ["Headline one", "Headline two"]

Digest:
{digest_html}"""

    headlines_response = model.generate_content(headlines_prompt)

    try:
        today_headlines = json.loads(headlines_response.text.strip())
    except Exception:
        today_headlines = []

    return digest_html, today_headlines


# ── Step 4: Send the digest via Outlook to all recipients ─────────────────────
def send_digest(html_body):
    recipient_list = ", ".join(
        r["emailAddress"]["address"] for r in RECIPIENTS
    )
    print(f"📤 Sending digest to: {recipient_list}...")

    composio.actions.execute(
        action="OUTLOOK_SEND_EMAIL",
        params={
            "to": RECIPIENTS,       # full list — everyone gets the same email
            "subject": f"Your Daily Digest — {TODAY}",
            "body": {
                "contentType": "HTML",
                "content": html_body
            }
        }
    )
    print("   ✅ Sent!")


# ── Step 5: Save today's headlines for tomorrow ───────────────────────────────
def save_headlines(headlines):
    with open(CACHE_FILE, "w") as f:
        json.dump(headlines, f, indent=2)
    print(f"   💾 Saved {len(headlines)} headlines for tomorrow's deduplication.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n🗞️  Newsletter Bot starting — {TODAY}\n")

    if not RECIPIENTS:
        print("❌ No recipients configured. Set NEWSLETTER_RECIPIENTS in your secrets.")
        return

    emails = fetch_newsletters()
    if not emails:
        return

    yesterday_headlines = load_yesterday_stories()
    print(f"   Loaded {len(yesterday_headlines)} headlines from yesterday.")

    digest_html, today_headlines = summarize_newsletters(emails, yesterday_headlines)

    send_digest(digest_html)
    save_headlines(today_headlines)

    print("\n✅ Done! Check your inbox.\n")


if __name__ == "__main__":
    main()
