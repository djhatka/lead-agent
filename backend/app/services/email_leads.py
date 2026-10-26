"""
The email lead reader.

Justdial, Sulekha, Practo, IndiaMART, 99acres... don't ring a doorbell: they
EMAIL every new lead to the business owner. So each business gets its own
private address,  leads-<secret>@in.yourdomain.in, and the owner tells Gmail
"forward emails from justdial.com to that address" (one-time setup).

For every email that arrives:
    1. read it  (raw email, or the JSON / form an email service sends)
    2. which business?   the secret part of the address it was sent TO
    3. which platform?   the sender's domain (justdial.com → Justdial)
    4. who is the customer?  lines like "Name: Ravi", "Mobile: 98110 12345",
       "Requirement: ceramic coating", "Area: Dwarka", plus any Indian mobile
       number in the text (but not the platform's own helpline)
    5. → a normal lead, exactly like a WhatsApp message (AI scores it, live alert)
Gmail's one-time "confirm forwarding" email is caught too: its code is shown
in Settings, so the owner can finish the setup without a real mailbox.

Platform emails change their layout from time to time; this reader looks for
LABELS instead of exact positions, so small changes don't break it. Anything it
can't read is kept as "unparsed" for the owner to check.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Business, InboundEmail
from app.schemas import IncomingMessage
from app.services.event_bus import bus

# Sender domain → our platform key (platforms.py)
DOMAINS = {
    "justdial.com": "justdial", "justdial.in": "justdial", "jdmail.in": "justdial",
    "sulekha.com": "sulekha", "sulekha.net": "sulekha",
    "indiamart.com": "indiamart", "tradeindia.com": "tradeindia",
    "practo.com": "practo", "lybrate.com": "lybrate",
    "urbanpro.com": "urbanpro", "superprof.co.in": "superprof", "superprof.com": "superprof",
    "99acres.com": "99acres", "magicbricks.com": "magicbricks", "housing.com": "housing",
    "nobroker.in": "nobroker", "cardekho.com": "cardekho",
}
NAMES = {"justdial": "Justdial", "sulekha": "Sulekha", "indiamart": "IndiaMART", "tradeindia": "TradeIndia",
         "practo": "Practo", "lybrate": "Lybrate", "urbanpro": "UrbanPro", "superprof": "Superprof",
         "99acres": "99acres", "magicbricks": "MagicBricks", "housing": "Housing.com", "nobroker": "NoBroker",
         "cardekho": "CarDekho"}

# "Label: value" lines we look for (lower case; longest labels are tried first)
LABELS = {
    "name": ["customer name", "caller name", "buyer name", "patient name", "student name", "enquirer name",
             "contact person", "sender name", "client name", "user name", "full name", "name"],
    "phone": ["mobile number", "mobile no", "mobile", "phone number", "phone no", "phone", "contact number",
              "contact no", "caller number", "whatsapp number", "whatsapp", "contact"],
    "email": ["email address", "email id", "e-mail", "email"],
    "area": ["locality", "location", "area", "city", "address"],
    "service": ["requirement", "looking for", "enquiry for", "enquired for", "interested in", "search keyword",
                "category", "treatment", "specialty", "course", "service", "product"],
    "message": ["enquiry details", "requirement details", "message", "description", "details", "comments",
                "query", "remarks"],
}
_LABEL_RE = {key: re.compile(r"^\s*(?:" + "|".join(re.escape(x) for x in sorted(words, key=len, reverse=True))
                             + r")\s*(?:[:\-–|]|\s{2,})\s*(.+?)\s*$", re.IGNORECASE)
             for key, words in LABELS.items()}
MOBILE = re.compile(r"(?<![\d+])(?:\+?91[\s\-]?|0)?([6-9]\d{4}[\s\-]?\d{5})(?!\d)")
NOT_CUSTOMER = re.compile(r"customer care|helpline|toll[\s-]?free|support|unsubscribe|call us|our number", re.I)
GMAIL_CODE = re.compile(r"Confirmation code:\s*(\d{6,12})", re.I)
GMAIL_LINK = re.compile(r"https://mail(?:-settings)?\.google\.com/mail/[^\s<>\"']+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class ParsedEmail:
    to: list[str]
    from_addr: str
    from_name: str
    subject: str
    text: str
    message_id: str = ""
    found: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Reading the email (any format an email service may send)
# ---------------------------------------------------------------------------
class _TextFromHtml(HTMLParser):
    """HTML → readable text. Table cells become 'Label : Value' so labels still match."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" : ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        lines = []
        for line in "".join(self.parts).splitlines():
            line = re.sub(r"[ \t\xa0]+", " ", line).strip().strip(":").strip()
            if line:
                lines.append(line)
        return "\n".join(lines)


def html_to_text(html: str) -> str:
    reader = _TextFromHtml()
    reader.feed(html or "")
    return reader.text()


def from_raw(raw: bytes, envelope_to: str = "") -> ParsedEmail:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))
    text = plain.get_content() if plain is not None else ""
    if html is not None and len(text.strip()) < 40:
        text = html_to_text(html.get_content())
    name, addr = parseaddr(str(msg.get("From", "")))
    present = [str(msg[h]) for h in ("To", "Cc", "Delivered-To") if msg[h]]   # only the lines that exist
    to = [a for _, a in getaddresses(present) if "@" in a]
    if envelope_to:
        to.insert(0, envelope_to)
    return ParsedEmail(to=to, from_addr=addr.lower(), from_name=name, subject=str(msg.get("Subject", "")),
                       text=text, message_id=str(msg.get("Message-ID", "")).strip())


def from_fields(fields: dict) -> ParsedEmail:
    """JSON or form posts from email services (Postmark, Mailgun, SendGrid, or our simple format)."""
    def pick(*keys):
        return next((str(fields[k]) for k in keys if fields.get(k)), "")
    if pick("raw", "email") and "\n" in pick("raw", "email"):
        return from_raw(pick("raw", "email").encode(), pick("recipient", "OriginalRecipient", "envelope_to"))
    name, addr = parseaddr(pick("from", "From", "sender"))
    to = [a for _, a in getaddresses([pick("recipient", "OriginalRecipient", "To", "to")]) if a]
    text = pick("text", "TextBody", "body-plain", "stripped-text")
    html = pick("html", "HtmlBody", "body-html")
    if len(text.strip()) < 40 and html:
        text = html_to_text(html)
    return ParsedEmail(to=to, from_addr=addr.lower(), from_name=name, subject=pick("subject", "Subject"),
                       text=text, message_id=pick("message_id", "MessageID", "Message-Id"))


# ---------------------------------------------------------------------------
# 2-4. Business, platform, customer details
# ---------------------------------------------------------------------------
def address_for(db: Session, business: Business) -> str:
    if not business.inbound_token:
        business.inbound_token = secrets.token_hex(4) + secrets.choice("abcdefghjkmnpqrstuvwxyz")
        db.commit()
    return f"leads-{business.inbound_token}@{settings.inbound_email_domain}"


def find_business(db: Session, addresses: list[str]) -> Optional[Business]:
    for addr in addresses:
        local = addr.split("@", 1)[0].lower()
        match = re.fullmatch(r"leads[-+]([a-z0-9]{6,20})", local)
        if match:
            business = db.scalar(select(Business).where(Business.inbound_token == match.group(1)))
            if business:
                return business
    return None


def _forwarded_sender(text: str) -> str:
    """When an owner forwards by hand, the real sender is inside: 'From: Justdial <x@justdial.com>'."""
    match = re.search(r"^\s*From:\s*.*?([\w.+-]+@[\w.-]+)", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).lower() if match else ""


def detect_platform(email: ParsedEmail) -> str:
    for addr in (email.from_addr, _forwarded_sender(email.text)):
        domain = addr.rsplit("@", 1)[-1]
        for known, platform in DOMAINS.items():
            if domain == known or domain.endswith("." + known):
                return platform
    subject = email.subject.lower()
    for platform, name in NAMES.items():
        if name.lower() in subject:
            return platform
    return "email"


def extract(text: str) -> dict:
    found: dict = {}
    for line in text.splitlines():
        for key, pattern in _LABEL_RE.items():
            if key in found:
                continue
            match = pattern.match(line)
            if match and match.group(1).strip(" :-"):
                found[key] = match.group(1).strip(" :-")[:300]
                break
    # The phone: the labelled one, else the first mobile number that isn't a helpline
    labelled = MOBILE.search(found.get("phone", ""))
    if labelled:
        found["phone"] = labelled.group(1)
    else:
        found.pop("phone", None)
        for match in MOBILE.finditer(text):
            just_before = text[max(0, match.start() - 40):match.start()]
            if NOT_CUSTOMER.search(just_before):           # "customer care: 1800..." is the platform's number
                continue
            found["phone"] = match.group(1)
            break
    if "email" in found:
        address = EMAIL_RE.search(found["email"])
        found["email"] = address.group(0).lower() if address else found.pop("email")
    return found


def _clean_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw)[-10:]


# ---------------------------------------------------------------------------
# 5. Save
# ---------------------------------------------------------------------------
def handle(db: Session, email: ParsedEmail) -> tuple[Optional[InboundEmail], Optional[IncomingMessage]]:
    """Returns (log row, the lead message to save) - the message is None when there's no lead."""
    business = find_business(db, email.to)
    if business is None:
        return None, None
    preview = email.text[:2000]
    msg_key = email.message_id or hashlib.sha1(f"{email.from_addr}|{email.subject}|{email.text}".encode()).hexdigest()
    log = InboundEmail(business_id=business.id, from_addr=email.from_addr[:200], subject=email.subject[:300],
                       preview=preview, message_id=msg_key[:300], status="received")

    # Gmail's "please confirm forwarding" email
    if email.from_addr.endswith("@google.com") and "forwarding" in (email.subject + email.from_addr).lower():
        code = GMAIL_CODE.search(email.text)
        link = GMAIL_LINK.search(email.text)
        log.status, log.platform = "confirmation", "gmail"
        log.note = f"code={code.group(1) if code else ''} link={link.group(0) if link else ''}"
        db.add(log)
        db.commit()
        bus.publish(business.id, "email.confirm", "Confirm Gmail forwarding",
                    f"Code {code.group(1) if code else '(open Settings)'}: paste it in Gmail to finish setup.",
                    {"code": code.group(1) if code else "", "link": link.group(0) if link else ""})
        return log, None

    platform = detect_platform(email)
    found = extract(email.text)
    is_direct = platform == "email"
    name = found.get("name") or (email.from_name if is_direct else None)
    contact_email = found.get("email") or (email.from_addr if is_direct else None)
    phone = _clean_phone(found["phone"]) if found.get("phone") else None
    said = found.get("message") or found.get("service") or email.subject
    if is_direct:
        body = "\n".join(line for line in email.text.splitlines() if line.strip() and not line.startswith(">"))
        said = f"{email.subject}\n{body}".strip()
    log.platform = platform
    details = {k: v for k, v in {"email": contact_email, "email_subject": email.subject[:200]}.items() if v}
    who = name or (contact_email if not phone else None)          # no name or phone? the email address will do
    try:
        incoming = IncomingMessage(
            business_id=business.id, source=platform, external_id=f"email:{msg_key}"[:150],
            name=who[:100] if who else None, phone=phone, area=(found.get("area") or "")[:100] or None, service=(found.get("service") or "")[:100] or None,
            details=details, first_message=(said or "Enquiry by email")[:4000])
    except ValidationError:
        incoming = None
    if incoming is None or not (incoming.phone or incoming.name):
        log.status = "unparsed"
        log.note = "No customer name or phone number found. Open the email and add the lead by hand."
        db.add(log)
        db.commit()
        return log, None
    log.platform = platform
    db.add(log)
    db.flush()
    return log, incoming
