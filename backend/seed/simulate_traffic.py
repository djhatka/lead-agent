r"""
Traffic simulator - pretends to be customers messaging the demo businesses,
so you can watch leads (and 🔥 hot alerts) arrive live.

It rings the real doorbells (webhooks) of a RUNNING server, exactly like
WhatsApp / Instagram / a website would.

Run it in a second terminal while the server is running:
    .\.venv\Scripts\python.exe -m seed.simulate_traffic                 (every 5 seconds, until Ctrl + C)
    .\.venv\Scripts\python.exe -m seed.simulate_traffic --every 2 --count 10

Then watch:  http://127.0.0.1:8000/live/stream?business_id=1&token=YOUR_TOKEN  (log in first; or the dashboard)
"""

import argparse
import random
import time
import uuid

import httpx

from seed.seed_data import BUSINESSES, FIRST_NAMES, LAST_NAMES

URGENT_EXTRAS = ["", "", " Need it today please!", " Can I book a slot for tomorrow?", " Called twice, no reply!!"]


def whatsapp_payload(name: str, phone: str, text: str) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": "sim", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "contacts": [{"profile": {"name": name}, "wa_id": phone}],
        "messages": [{"from": phone, "id": f"wamid.SIM{uuid.uuid4().hex[:16]}", "timestamp": str(int(time.time())),
                      "type": "text", "text": {"body": text}}]}}]}]}


def instagram_payload(text: str) -> dict:
    sender = str(random.randint(10**15, 10**16 - 1))
    return {"object": "instagram", "entry": [{"id": "sim", "time": int(time.time() * 1000), "messaging": [
        {"sender": {"id": sender}, "recipient": {"id": "sim"}, "timestamp": int(time.time() * 1000),
         "message": {"mid": f"sim{uuid.uuid4().hex[:20]}", "text": text}}]}]}


def one_message(r: random.Random) -> tuple[str, int, dict]:
    """Invent one customer message for a random demo business."""
    business_id = r.randint(1, len(BUSINESSES))
    biz = BUSINESSES[business_id - 1]
    service = r.choice(list(biz["services"]))
    text = r.choice(biz["messages"]).format(service=service, area="Dwarka", **biz["details"](r)) + r.choice(URGENT_EXTRAS)
    if r.random() < 0.6:
        name = f"{r.choice(FIRST_NAMES)} {r.choice(LAST_NAMES)}"
        phone = f"91{r.choice('9876')}{r.randint(100000000, 999999999)}"
        return "whatsapp", business_id, whatsapp_payload(name, phone, text)
    return "instagram", business_id, instagram_payload(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send fake customer messages to a running server")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--every", type=float, default=5, help="seconds between messages")
    parser.add_argument("--count", type=int, default=0, help="how many (0 = until Ctrl + C)")
    args = parser.parse_args()
    if args.url.startswith("https://"):
        raise SystemExit("Refusing: that looks like the LIVE website. Fake customers are for your laptop only.")

    r = random.Random()
    sent = 0
    print(f"Sending a fake customer message every {args.every}s to {args.url} (Ctrl + C to stop)")
    try:
        while not args.count or sent < args.count:
            channel, business_id, payload = one_message(r)
            try:
                res = httpx.post(f"{args.url}/webhooks/{channel}", params={"business_id": business_id},
                                 json=payload, timeout=10)
                info = res.json()
                print(f"  → business {business_id} via {channel}: new={info.get('new_leads')} "
                      f"lead_ids={info.get('lead_ids')}")
            except httpx.HTTPError as problem:
                print(f"  ✗ couldn't reach the server ({problem}). Is it running?")
            sent += 1
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass
    print(f"Done: {sent} messages sent.")


if __name__ == "__main__":
    main()
