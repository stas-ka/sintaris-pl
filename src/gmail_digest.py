#!/usr/bin/env python3
"""
Gmail Daily Digest — IMAP + App Password version (no OAuth2 needed).
Reads INBOX + SPAM from last 24h, summarizes with OpenRouter,
sends digest to Telegram at 19:00 via cron.
"""
import os
import imaplib, email, json, datetime, sys, urllib.request
from email.header import decode_header, make_header
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
# Secrets are loaded from environment variables.
# On the Pi, set them in ~/.credentials/.pico_env (sourced by the cron wrapper)
# or export them in the shell before running manually.
GMAIL_USER     = os.environ.get('GMAIL_USER',     'stas.ulmer@gmail.com')
GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD', '')   # Gmail App Password
OPENROUTER_KEY = os.environ.get('OPENROUTER_KEY', '')
TG_TOKEN       = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT_ID     = os.environ.get('TELEGRAM_CHAT_ID',  '994963580')
MAX_BODY_CHARS     = 600   # per email sent to LLM
HOURS_BACK        = 24
LAST_DIGEST_FILE  = Path.home() / '.taris' / 'last_digest.txt'

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean(text):
    """Remove surrogate characters that break JSON encoding."""
    return text.encode('utf-8', errors='replace').decode('utf-8')


def tg_send(text):
    text = clean(text)
    if len(text) > 4000:
        for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            tg_send(chunk)
        return
    url  = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
    data = json.dumps({'chat_id': TG_CHAT_ID,
                       'text': text,
                       'disable_web_page_preview': True},
                      ensure_ascii=False).encode('utf-8')
    req  = urllib.request.Request(url, data=data,
                                  headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f'Telegram error: {e}')


def llm_summarize(prompt):
    url  = 'https://openrouter.ai/api/v1/chat/completions'
    body = json.dumps({
        'model': 'openai/gpt-4o-mini',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 1024,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENROUTER_KEY}',
    })
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())['choices'][0]['message']['content'].strip()


def decode_str(s):
    if s is None:
        return ''
    return str(make_header(decode_header(s)))


def get_body(msg):
    """Extract plain text body from email.message.Message."""
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain' and \
               'attachment' not in str(part.get('Content-Disposition', '')):
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or 'utf-8', errors='replace')
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or 'utf-8', errors='replace')
        except Exception:
            pass
    return body[:MAX_BODY_CHARS].strip()


def fetch_folder(imap, folder, hours=HOURS_BACK):
    """Fetch emails from the last `hours` hours in `folder`."""
    # Quote folder name for IMAP (required for names with special chars like [])
    quoted = f'"{folder}"' if '[' in folder else folder
    status, _ = imap.select(quoted, readonly=True)
    if status != 'OK':
        print(f'Cannot select folder {folder}: {status}')
        return []
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
             ).strftime('%d-%b-%Y')
    _, data = imap.search(None, f'(SINCE "{since}")')
    ids = data[0].split()
    emails = []
    for mid in ids[-50:]:   # max 50
        _, raw = imap.fetch(mid, '(RFC822)')
        msg = email.message_from_bytes(raw[0][1])
        emails.append({
            'subject': decode_str(msg.get('Subject', '(no subject)')),
            'sender':  decode_str(msg.get('From', '?')),
            'body':    get_body(msg),
        })
    return emails


def build_prompt(inbox, spam):
    sections = []
    if inbox:
        lines = '\n\n'.join(
            f'{i}. From: {e["sender"]}\n   Subject: {e["subject"]}\n   Body: {e["body"] or "(empty)"}'
            for i, e in enumerate(inbox, 1))
        sections.append(f'=== INBOX ({len(inbox)} emails) ===\n{lines}')
    if spam:
        lines = '\n\n'.join(
            f'{i}. From: {e["sender"]}\n   Subject: {e["subject"]}\n   Body: {e["body"] or "(empty)"}'
            for i, e in enumerate(spam, 1))
        sections.append(f'=== SPAM ({len(spam)} emails) ===\n{lines}')

    return (
        'You are an email assistant. Analyze the emails and produce a concise daily digest:\n\n'
        '📌 NEWS & NEWSLETTERS:\n'
        '• <Title/Subject> — <1-sentence summary>\n\n'
        '📬 OTHER EMAILS:\n'
        '• <Subject> | From: <sender> — <1-sentence summary>\n\n'
        '🚨 SPAM:\n'
        '• <Subject> | From: <sender> — <1-sentence summary>\n\n'
        'Rules: classify each as news/newsletter OR other. '
        'German and English both OK. Be concise.\n\n'
        + '\n\n'.join(sections)
    )


def save_last_digest(text: str) -> None:
    """Persist digest text to disk for the Telegram menu bot."""
    try:
        LAST_DIGEST_FILE.write_text(text, encoding='utf-8')
    except Exception as e:
        print(f'Warning: could not save last_digest.txt: {e}')


def main():
    # --stdout: print digest to stdout instead of sending to Telegram
    #           used by telegram_menu_bot.py "Refresh" button
    stdout_mode = '--stdout' in sys.argv

    print('Connecting to Gmail IMAP...')
    imap = imaplib.IMAP4_SSL('imap.gmail.com')
    imap.login(GMAIL_USER, GMAIL_PASSWORD)
    print('Logged in OK')

    inbox = fetch_folder(imap, 'INBOX')
    spam  = fetch_folder(imap, '[Google Mail]/Spam')
    imap.logout()
    print(f'Inbox: {len(inbox)}, Spam: {len(spam)}')

    if not inbox and not spam:
        today = datetime.date.today().strftime('%d.%m.%Y')
        digest = f'📭 Email Digest — {today}\nNo new emails in the last 24 hours.'
        save_last_digest(digest)
        if stdout_mode:
            print(digest)
        else:
            tg_send(digest)
        print('No emails — digest sent.')
        return

    print('Summarizing with LLM...')
    summary = llm_summarize(build_prompt(inbox, spam))
    today   = datetime.date.today().strftime('%d.%m.%Y')
    digest  = (f'📧 Email Digest — {today}\n'
               f'({len(inbox)} inbox, {len(spam)} spam)\n\n{summary}')

    # Always save for the menu bot, regardless of mode
    save_last_digest(digest)

    if stdout_mode:
        # Return text to caller (telegram_menu_bot.py captures this)
        print(digest)
    else:
        print('Sending to Telegram...')
        tg_send(digest)
    print('Done.')


if __name__ == '__main__':
    main()
