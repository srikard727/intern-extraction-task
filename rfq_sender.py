import os
import re
import sys
import time
import base64
import argparse
from email.message import EmailMessage
from email.utils import make_msgid

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly"
]
CREDENTIALS = "credentials.json"
TOKEN = "token_send.json"
EMAILS_FILE = "Emails.txt"

RECIPIENT = os.getenv("RFQ_RECIPIENT", "me")  # "me" sends to the authenticated account itself
SENDER_NAME = os.getenv("RFQ_SENDER_NAME", "Glass Customer")


def get_service():
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def parse_emails(path):
    text = open(path, encoding="utf-8").read()
    chunks = re.split(r"Email:\s*\d+", text)
    emails = []
    for c in chunks[1:]:                       # skip preamble before first marker
        lines = [ln for ln in c.splitlines()
                 if set(ln.strip()) != {"-"} and ln.strip() != ""]
        body = "\n".join(lines).strip()
        if not body:
            continue
        subj = "Request for Quote"
        for ln in lines:
            s = ln.strip(); low = s.lower()
            if low.startswith(("hello", "good morning", "hi", "could you",
                               "please", "i ", "can you", "i am", "i would")):
                continue
            if any(ch.isdigit() for ch in s) or "glass" in low or "igu" in low or "mirror" in low:
                subj = "RFQ: " + (s[:60] + ("..." if len(s) > 60 else ""))
                break
        emails.append({"subject": subj, "body": body})
    return emails


def send_one(service, subject, body, account_addr):
    msg = EmailMessage()
    to_addr = account_addr if RECIPIENT == "me" else RECIPIENT
    msg["To"] = to_addr
    msg["From"] = f"{SENDER_NAME} <{account_addr}>"
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="mail.gmail.com")
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.0,
                    help="seconds to wait between sends (simulate a live stream)")
    ap.add_argument("--one", metavar="FILE",
                    help="send a single new email read from FILE instead of Emails.txt")
    args = ap.parse_args()

    service = get_service()
    me = service.users().getProfile(userId="me").execute()["emailAddress"]

    if args.one:
        body = open(args.one, encoding="utf-8").read().strip()
        first = next((l for l in body.splitlines() if l.strip()), "Request for Quote")
        subj = "RFQ: " + first[:60] if any(ch.isdigit() for ch in first) else "Request for Quote"
        send_one(service, subj, body, me)
        print(f"sent 1 email to {me if RECIPIENT=='me' else RECIPIENT}")
        return

    emails = parse_emails(EMAILS_FILE)
    print(f"sending {len(emails)} emails to {me if RECIPIENT=='me' else RECIPIENT} ...\n")
    for i, e in enumerate(emails, 1):
        send_one(service, e["subject"], e["body"], me)
        print(f"  [{i:2d}/{len(emails)}] sent: {e['subject']}")
        if args.delay and i < len(emails):
            time.sleep(args.delay)
    print("\ndone.")


if __name__ == "__main__":
    main()
