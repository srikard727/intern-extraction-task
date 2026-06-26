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
DEFAULT_FOLLOW_UP_PATTERN = "1,2,0"

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


def send_one(service, subject, body, account_addr, thread=None):
    msg = EmailMessage()
    to_addr = account_addr if RECIPIENT == "me" else RECIPIENT
    message_id = make_msgid(domain="mail.gmail.com")
    send_subject = _reply_subject(thread["subject"]) if thread else subject
    msg["To"] = to_addr
    msg["From"] = f"{SENDER_NAME} <{account_addr}>"
    msg["Subject"] = send_subject
    msg["Message-ID"] = message_id
    if thread:
        msg["In-Reply-To"] = thread["last_message_id"]
        msg["References"] = " ".join([*thread["references"], thread["last_message_id"]])
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if thread and thread.get("thread_id"):
        payload["threadId"] = thread["thread_id"]
    response = service.users().messages().send(userId="me", body=payload).execute()
    return {
        "email_id": response.get("id"),
        "thread_id": response.get("threadId"),
        "message_id": message_id,
        "subject": send_subject,
    }


def _reply_subject(subject):
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def _send_conversation(service, emails, account_addr):
    thread = None
    sent = []
    for index, email in enumerate(emails):
        result = send_one(
            service,
            email["subject"],
            email["body"],
            account_addr,
            thread=thread,
        )
        sent.append(result)
        if thread is None:
            thread = {
                "thread_id": result["thread_id"],
                "subject": result["subject"],
                "last_message_id": result["message_id"],
                "references": [],
            }
        else:
            thread["references"].append(thread["last_message_id"])
            thread["last_message_id"] = result["message_id"]
    return sent


def _related_conversation(email, follow_ups):
    messages = [email]
    for index in range(1, max(0, follow_ups) + 1):
        messages.append(
            {
                "subject": email["subject"],
                "body": _follow_up_body(email["body"], index),
            }
        )
    return messages


def _parse_follow_up_pattern(raw):
    pattern = []
    for part in (raw or "").split(","):
        value = part.strip()
        if not value:
            continue
        try:
            pattern.append(max(0, int(value)))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"follow-up pattern must be comma-separated non-negative integers: {raw}"
            ) from exc
    if not pattern:
        raise argparse.ArgumentTypeError("follow-up pattern must include at least one number")
    return pattern


def _follow_up_count(index, fixed_follow_ups, pattern):
    if fixed_follow_ups is not None:
        return max(0, fixed_follow_ups)
    return pattern[index % len(pattern)]


def _follow_up_body(original_body, index):
    summary = _rfq_summary(original_body)
    if index == 1:
        return (
            "Hi team,\n\n"
            f"Following up on my RFQ below for this request: {summary}. "
            "Please keep this in the same quote thread. "
            "If anything is missing, let me know what you need and I can send it over.\n\n"
            "Thanks"
        )
    if index == 2:
        return (
            "Hi again,\n\n"
            f"One more note on this request: {summary}. Please include current lead time with the pricing. "
            "Use the dimensions and glass details from my earlier message in this conversation.\n\n"
            "Thanks"
        )
    return (
        "Hi,\n\n"
        f"Checking in on this quote request from the thread: {summary}. Please confirm you have enough "
        "information to price it.\n\n"
        "Thanks"
    )


def _rfq_summary(body):
    for line in body.splitlines():
        text = line.strip()
        if not text:
            continue
        lower = text.lower()
        if lower in {"hi", "hello", "hello team", "good morning", "good afternoon"}:
            continue
        if any(char.isdigit() for char in text) or any(
            word in lower for word in ("glass", "igu", "mirror", "laminated", "tempered")
        ):
            return text[:90].rstrip(" .") + ("..." if len(text) > 90 else "")
    return "the glass RFQ"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.0,
                    help="seconds to wait between sends (simulate a live stream)")
    ap.add_argument("--one", metavar="FILE",
                    help="send a single new email read from FILE instead of Emails.txt")
    ap.add_argument("--follow-ups", type=int, default=None,
                    help="fixed number of related replies after each RFQ sample; overrides --follow-up-pattern")
    ap.add_argument(
        "--follow-up-pattern",
        default=os.getenv("RFQ_FOLLOW_UP_PATTERN", DEFAULT_FOLLOW_UP_PATTERN),
        help="comma-separated related reply counts repeated across samples; default: 1,2,0",
    )
    args = ap.parse_args()
    follow_up_pattern = _parse_follow_up_pattern(args.follow_up_pattern)

    service = get_service()
    me = service.users().getProfile(userId="me").execute()["emailAddress"]

    if args.one:
        body = open(args.one, encoding="utf-8").read().strip()
        first = next((l for l in body.splitlines() if l.strip()), "Request for Quote")
        subj = "RFQ: " + first[:60] if any(ch.isdigit() for ch in first) else "Request for Quote"
        sent = _send_conversation(
            service,
            _related_conversation(
                {"subject": subj, "body": body},
                _follow_up_count(0, args.follow_ups, follow_up_pattern),
            ),
            me,
        )
        print(
            f"sent {len(sent)} email(s) in one conversation to "
            f"{me if RECIPIENT=='me' else RECIPIENT}"
        )
        return

    emails = parse_emails(EMAILS_FILE)
    conversations = [
        _related_conversation(
            email,
            _follow_up_count(index, args.follow_ups, follow_up_pattern),
        )
        for index, email in enumerate(emails)
    ]
    total_messages = sum(len(conversation) for conversation in conversations)
    print(
        f"sending {total_messages} emails in {len(conversations)} related conversation(s) "
        f"to {me if RECIPIENT=='me' else RECIPIENT} ...\n"
    )
    sent_count = 0
    for conv_index, conversation in enumerate(conversations, 1):
        sent = _send_conversation(service, conversation, me)
        conv_thread_id = sent[0]["thread_id"] if sent else "(none)"
        for reply_index, (email, result) in enumerate(zip(conversation, sent), 1):
            sent_count += 1
            label = "new" if reply_index == 1 else "reply"
            print(
                f"  [{sent_count:2d}/{total_messages}] conv {conv_index:02d} "
                f"{label}: {email['subject']} "
                f"(email_id={result['email_id']}, thread_id={result['thread_id'] or conv_thread_id})"
            )
            if args.delay and sent_count < total_messages:
                time.sleep(args.delay)
    print("\ndone.")


if __name__ == "__main__":
    main()
