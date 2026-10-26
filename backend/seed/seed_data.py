r"""
Demo data maker - fills the database with realistic practice data.

Why? Our AI agents and charts need something to analyse. Real businesses
aren't connected yet, so we invent 3 believable Delhi businesses and about
100 enquiries each, spread over the last 90 days. Each business also gets
Instagram, Facebook and Google accounts with ~90 days of posts
(see seed_social.py), and many enquiries are linked to the post that brought them.

The data is NOT purely random. Each source has its own "personality",
just like in real life:
    - Instagram brings LOTS of enquiries, but few turn into sales
    - Google brings fewer enquiries, but many of them buy
    - Referrals are rare, but almost always buy
    - Fast replies win more customers than slow ones
That gives the AI real patterns to discover later.

The same "random seed" (42) is used every time, so everyone who runs this
gets exactly the same data. Handy for testing.

Run from the backend folder:
    .\.venv\Scripts\python.exe -m seed.seed_data            (only if empty)
    .\.venv\Scripts\python.exe -m seed.seed_data --reset    (wipe + refill)
    add --analyze to also run the AI workflow on every demo lead (free in mock mode)
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.database import SessionLocal, init_db, reset_database
from app.models import Business, Lead, Message, Payment, Subscription, User
from app.schemas import BusinessCreate, LeadCreate
from seed.seed_dues import make_dues
from seed.seed_renewals import make_renewals
from seed.seed_reviews import make_reviews
from seed.seed_social import link_lead, make_social

IST = timezone(timedelta(hours=5, minutes=30))  # India time, UTC+5:30

# ---------------------------------------------------------------------------
# Ingredients for fake people
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Aarav", "Priya", "Rohit", "Neha", "Karan", "Simran", "Aditya", "Ananya", "Vikram", "Pooja",
    "Rahul", "Sneha", "Arjun", "Kavya", "Manish", "Riya", "Sahil", "Isha", "Deepak", "Meera",
    "Harsh", "Tanya", "Nikhil", "Divya", "Yash", "Shreya", "Gaurav", "Nidhi", "Varun", "Aditi",
]
LAST_NAMES = ["Sharma", "Verma", "Gupta", "Singh", "Malhotra", "Kapoor", "Arora", "Bansal", "Chopra", "Mehta"]
DELHI_AREAS = [
    "Rajouri Garden", "Kirti Nagar", "Janakpuri", "Dwarka", "Karol Bagh", "Punjabi Bagh",
    "Moti Nagar", "Tilak Nagar", "Patel Nagar", "Paschim Vihar", "Vikaspuri", "Uttam Nagar",
]
CAMPAIGNS = ["diwali-offer", "new-year-sale", "reel-promo", "google-ads"]

# ---------------------------------------------------------------------------
# The 3 demo businesses. Each has:
#   profile   - goes into the businesses table
#   services  - name + typical price range in ₹ (used for job_value)
#   details   - function that invents industry-specific extras
#   messages  - first messages customers send ({...} gets filled in)
#   sources   - source: (how common, chance of becoming a sale)
#   hours     - which hours of the day enquiries usually arrive (IST)
# ---------------------------------------------------------------------------
BUSINESSES = [
    {
        "profile": dict(
            name="Iron Pulse Fitness", industry="gym", area="Rajouri Garden",
            description="Unisex gym with Zumba, yoga and personal training.",
            services=["Gym membership", "Zumba", "Personal training", "Yoga", "CrossFit"],
            brand_voice="energetic, motivating, Hinglish, uses emojis",
            target_audience="working professionals and college students, 18-40, West Delhi",
            phone="9810000001",
        ),
        "services": {
            "Gym membership": (4500, 15000), "Zumba": (2500, 6000), "Personal training": (8000, 25000),
            "Yoga": (2000, 5000), "CrossFit": (4000, 10000),
        },
        "details": lambda r: {
            "batch": r.choice(["morning", "evening"]),
            "goal": r.choice(["weight loss", "muscle gain", "general fitness", "flexibility"]),
        },
        "messages": [
            "Hi, what are the fees for {service}? Looking for the {batch} batch",
            "{service} ka monthly kitna hai? {area} se hu",
            "I want to start {service} from tomorrow itself, goal is {goal}. Please call me",
            "Is there a free trial class for {service}?",
            "Called twice and nobody picked up. Still want {service} details",
            "Bhai {service} ke liye best offer batao, {goal} karna hai",
            "Do you have a ladies {batch} batch for {service}?",
            "Joining today, please share {service} package details asap",
        ],
        "sources": {
            "instagram": (35, 0.08), "whatsapp": (25, 0.22), "google": (15, 0.30), "walk_in": (8, 0.45),
            "website": (7, 0.15), "justdial": (6, 0.05), "referral": (4, 0.50),
        },
        "hours": {6: 3, 7: 4, 8: 3, 10: 1, 12: 1, 14: 1, 17: 2, 18: 4, 19: 5, 20: 4, 21: 3, 22: 2},
    },
    {
        "profile": dict(
            name="Gloss Garage Detailing", industry="car_detailing", area="Kirti Nagar",
            description="Car detailing studio: ceramic coating, PPF, paint correction and deep cleaning.",
            services=["Ceramic coating", "PPF", "Interior deep cleaning", "Car wash & wax", "Paint correction"],
            brand_voice="premium, confident, car-enthusiast tone",
            target_audience="new car owners and car enthusiasts, 22-45, Delhi NCR",
            phone="9810000002",
        ),
        "services": {
            "Ceramic coating": (15000, 45000), "PPF": (40000, 120000), "Interior deep cleaning": (2000, 5000),
            "Car wash & wax": (800, 2000), "Paint correction": (8000, 20000),
        },
        "details": lambda r: {
            "car_model": r.choice([
                "Hyundai Creta", "Maruti Swift", "Tata Nexon", "Kia Seltos", "Mahindra XUV700",
                "Toyota Fortuner", "Honda City", "Mahindra Thar", "Maruti Baleno",
            ]),
        },
        "messages": [
            "Price for {service} on my {car_model}?",
            "{car_model} ke liye {service} kitne ka hai?",
            "Need {service} for my {car_model} today, can you take it?",
            "Does {service} come with a warranty? I have a {car_model}",
            "Sent 3 messages, no reply. Want a {service} quote for {car_model}",
            "Saw your reel, want {service} on my {car_model}",
            "Can you pick up the car? {car_model}, need {service}",
            "Urgent - wedding this weekend, need {service} on {car_model}",
        ],
        "sources": {
            "instagram": (30, 0.07), "google": (25, 0.32), "whatsapp": (20, 0.20), "justdial": (10, 0.05),
            "website": (8, 0.18), "referral": (7, 0.45),
        },
        "hours": {10: 2, 11: 3, 12: 3, 13: 2, 14: 2, 15: 2, 16: 3, 17: 3, 18: 4, 19: 4, 20: 3, 21: 2},
    },
    {
        "profile": dict(
            name="SmileCare Dental Clinic", industry="clinic", area="Janakpuri",
            description="Family dental clinic: cleaning, root canal, braces, implants and whitening.",
            services=["Dental cleaning", "Root canal", "Teeth whitening", "Braces", "Dental implant"],
            brand_voice="caring, trustworthy, simple English",
            target_audience="families and working adults, 25-60, West Delhi",
            phone="9810000003",
        ),
        "services": {
            "Dental cleaning": (800, 2000), "Root canal": (4000, 9000), "Teeth whitening": (5000, 15000),
            "Braces": (30000, 80000), "Dental implant": (25000, 45000),
        },
        "details": lambda r: {
            "preferred_day": r.choice(["Monday", "Wednesday", "Friday", "Saturday", "Sunday"]),
            "preferred_time": r.choice(["morning", "evening"]),
        },
        "messages": [
            "Need an appointment for {service} on {preferred_day} {preferred_time}",
            "Severe tooth pain since last night, need {service} asap. Can I come today?",
            "{service} ka cost kya hai?",
            "What is the price of {service}? Is EMI available?",
            "Booked online but nobody confirmed. Want {service} on {preferred_day}",
            "My child needs {service}, which doctor is available on {preferred_day}?",
            "Is {service} painful? How many sittings does it take?",
            "Do you accept insurance for {service}?",
        ],
        "sources": {
            "google": (35, 0.35), "whatsapp": (20, 0.25), "website": (15, 0.20), "justdial": (12, 0.10),
            "facebook": (10, 0.06), "phone_call": (8, 0.30),
        },
        "hours": {9: 3, 10: 4, 11: 4, 12: 3, 13: 2, 16: 2, 17: 3, 18: 4, 19: 3, 20: 2},
    },
]


# ---------------------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------------------
def pick_weighted(r: random.Random, options: dict):
    """Pick a key, where bigger numbers are picked more often."""
    keys = list(options)
    weights = [options[k][0] if isinstance(options[k], tuple) else options[k] for k in keys]
    return r.choices(keys, weights=weights)[0]


def random_time(r: random.Random, now: datetime, hours: dict, days_back: int = 90) -> datetime:
    """A believable time in the last `days_back` days, at a busy hour (IST)."""
    while True:
        day = (now.astimezone(IST) - timedelta(days=r.randint(0, days_back - 1))).date()
        hour = pick_weighted(r, hours)
        t = datetime(day.year, day.month, day.day, hour, r.randint(0, 59), tzinfo=IST)
        if t < now:                                    # never in the future
            return t.astimezone(timezone.utc)


def pick_status(r: random.Random, win_rate: float, age_days: float) -> str:
    """Decide how far this enquiry got. Very recent leads are still in progress."""
    if age_days < 2:
        return r.choices(["new", "contacted", "quoted"], weights=[5, 3, 2])[0]
    if r.random() < win_rate:
        return "won"
    if age_days < 14:
        return r.choices(["contacted", "quoted", "booked", "lost", "new"], weights=[3, 3, 2, 3, 1])[0]
    # Old leads that never became sales. Some were never even answered!
    return r.choices(["lost", "quoted", "new"], weights=[7, 2, 1])[0]


def make_lead(r: random.Random, biz: dict, business_id: int, now: datetime) -> Lead:
    """Invent one realistic enquiry (plus its chat messages)."""
    source = pick_weighted(r, biz["sources"])
    win_rate = biz["sources"][source][1]
    service = r.choice(list(biz["services"]))
    details = biz["details"](r)
    area = r.choice(DELHI_AREAS)
    first_name = r.choice(FIRST_NAMES)
    full_name = f"{first_name} {r.choice(LAST_NAMES)}"
    phone = f"{r.choice('9876')}{r.randint(100000000, 999999999)}"

    # Different channels give us different contact details
    name, handle = full_name, None
    if source in ("instagram", "facebook"):
        handle = f"{first_name.lower()}{r.choice(['_', '.', ''])}{r.randint(1, 999)}"
        name = full_name if r.random() < 0.4 else None
        phone = phone if r.random() < 0.3 else None
    elif source == "phone_call" and r.random() < 0.5:
        name = None

    text = r.choice(biz["messages"]).format(service=service, area=area, **details)

    # Run the invented data through the SAME rules as real data (Task 3)
    checked = LeadCreate(
        business_id=business_id, source=source, external_id=f"seed-{uuid.UUID(int=r.getrandbits(128))}",
        campaign=r.choice(CAMPAIGNS) if source in ("instagram", "website", "facebook") and r.random() < 0.4 else None,
        name=name, phone=phone, handle=handle, area=area,
        service=service, details=details, first_message=text,
    )

    created = random_time(r, now, biz["hours"])
    age_days = (now - created).total_seconds() / 86400
    # How fast did the business reply? Mostly quick, sometimes very slow.
    # Like in real life, FAST replies win more customers, slow ones lose them.
    delay = r.choice([r.randint(3, 30), r.randint(30, 180), r.randint(180, 1440)])
    speed_factor = 1.5 if delay <= 30 else 1.0 if delay <= 180 else 0.5
    status = pick_status(r, min(0.9, win_rate * speed_factor), age_days)

    lead = Lead(**checked.model_dump(), status=status, created_at=created, updated_at=created)
    lead.messages.append(Message(direction="inbound", text=text, sent_at=created))

    if status != "new":
        replied = min(created + timedelta(minutes=delay), now)
        lead.first_response_at = replied
        low, high = biz["services"][service]
        lead.messages.append(Message(
            direction="outbound", sent_at=replied,
            text=f"Hi{' ' + first_name if name else ''}! Thanks for contacting "
                 f"{biz['profile']['name']}. {service} starts at ₹{low:,}. When would you like to come in?",
        ))
        if status in ("quoted", "booked", "won", "lost"):
            price = round(r.randint(low, high), -2)
            quoted_at = min(replied + timedelta(hours=r.randint(1, 24)), now)
            lead.messages.append(Message(direction="outbound", sent_at=quoted_at,
                                         text=f"For {service}, the price would be ₹{price:,}. Shall I book a slot?"))
            if status == "won":
                lead.job_value = price
                lead.won_at = quoted_at
            lead.updated_at = quoted_at
    return lead


# ---------------------------------------------------------------------------
# The main job
# ---------------------------------------------------------------------------
def seed(db: Session, leads_per_business: int = 100, rng_seed: int = 42) -> list[Business]:
    """Create the demo businesses, their social accounts + posts, their leads, and a few customer payments."""
    r = random.Random(rng_seed)
    r_social = random.Random(rng_seed + 1)                   # separate dice for social data
    now = datetime.now(timezone.utc)
    created = []
    for biz in BUSINESSES:
        profile = BusinessCreate(**biz["profile"])           # checked by Task 3 rules
        business = Business(**profile.model_dump())
        db.add(business)
        db.flush()                                           # gives the business its id
        published = make_social(db, r_social, business, now)  # accounts + ~90 days of posts
        make_reviews(db, r_social, business, now)             # ~20 Google/Practo/Facebook reviews
        for _ in range(leads_per_business):
            lead = make_lead(r, biz, business.id, now)
            link_lead(r_social, lead, published)             # which post brought them?
            db.add(lead)
        created.append(business)
    make_demo_users(db, created)
    make_demo_subscriptions(db, created, now)
    db.flush()                                               # gives the leads their ids
    r_dues = random.Random(rng_seed + 2)                     # separate dice: the leads above stay the same
    for business in created:
        make_dues(db, r_dues, business, now)                 # UPI ID + a few customer payments (Task 31)
        make_renewals(db, r_dues, business, now)              # memberships/services about to expire (Task 32)
    db.commit()
    return created


# ---------------------------------------------------------------------------
# Demo logins (one owner per business, one staff member, and you: the admin)
# ---------------------------------------------------------------------------
DEMO_PASSWORD = "demo1234"
ADMIN_PASSWORD = "admin1234"
DEMO_OWNER_EMAILS = ["gym@demo.in", "garage@demo.in", "clinic@demo.in"]
_hashes: dict[str, str] = {}      # hashing is slow on purpose, so hash each demo password once


def _hash(password: str) -> str:
    if password not in _hashes:
        _hashes[password] = hash_password(password)
    return _hashes[password]


# ---------------------------------------------------------------------------
# Demo plans: one of each situation
# ---------------------------------------------------------------------------
DEMO_PLANS = [  # (plan, status, days until the trial/paid period ends, months already paid)
    ("growth", "active", 20, 3),        # gym: paying customer on Growth
    ("growth", "trialing", 9, 0),       # garage: free trial, 9 days left
    ("pro", "active", 12, 2),           # clinic: paying customer on Pro
]


def make_demo_subscriptions(db: Session, businesses: list[Business], now: datetime) -> None:
    from app.plans import PLANS
    for business, (plan, status, days, months) in zip(businesses, DEMO_PLANS):
        ends = now + timedelta(days=days)
        sub = Subscription(business_id=business.id, plan=plan, status=status,
                           trial_ends_at=ends if status == "trialing" else now - timedelta(days=30 * months),
                           current_period_end=ends if status == "active" else None,
                           gateway_subscription_id=f"sub_demo_{business.id}" if status == "active" else None)
        db.add(sub)
        db.flush()
        for m in range(months):
            db.add(Payment(business_id=business.id, subscription_id=sub.id, plan=plan, amount=PLANS[plan].price,
                           gateway_payment_id=f"pay_demo_{business.id}_{m}",
                           paid_at=ends - timedelta(days=30 * (m + 1))))


def make_demo_users(db: Session, businesses: list[Business]) -> None:
    for email, business in zip(DEMO_OWNER_EMAILS, businesses):
        db.add(User(email=email, name=f"{business.name} owner", password_hash=_hash(DEMO_PASSWORD),
                    role="owner", business_id=business.id))
    db.add(User(email="staff@demo.in", name="Gym front desk", password_hash=_hash(DEMO_PASSWORD),
                role="staff", business_id=businesses[0].id))
    db.add(User(email="admin@demo.in", name="Platform admin", password_hash=_hash(ADMIN_PASSWORD), role="admin"))


def print_summary(db: Session) -> None:
    """Show a small table per business: leads, sales and money per source."""
    for business in db.query(Business).order_by(Business.id):
        print(f"\n{business.name} ({business.industry}) - {len(business.leads)} leads")
        print(f"  {'source':<11}{'leads':>6}{'won':>5}{'conv %':>8}{'revenue ₹':>12}")
        by_source: dict[str, list[Lead]] = {}
        for lead in business.leads:
            by_source.setdefault(lead.source, []).append(lead)
        for source, leads in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
            won = [l for l in leads if l.status == "won"]
            revenue = sum(l.job_value or 0 for l in won)
            print(f"  {source:<11}{len(leads):>6}{len(won):>5}{100 * len(won) / len(leads):>7.0f}%{revenue:>12,}")
        from app.services.billing_service import access
        print(f"  plan: {access(db, business.id).message}")
        posts = [p for a in business.social_accounts for p in a.posts if p.status == "published"]
        linked = sum(1 for lead in business.leads if lead.post_id)
        print(f"  + {len(business.social_accounts)} social accounts, {len(posts)} published posts, "
              f"{linked} enquiries linked to a post, {len(business.reviews)} reviews")


def main() -> None:
    from app.config import settings
    if settings.is_production:
        raise SystemExit("Refusing: this is the LIVE server (ENVIRONMENT=production). Demo data would mix fake "
                         "businesses and demo passwords into real customers' data.")
    parser = argparse.ArgumentParser(description="Fill the database with demo data")
    parser.add_argument("--reset", action="store_true", help="delete ALL existing data first")
    parser.add_argument("--per-business", type=int, default=100, help="leads per business (default 100)")
    parser.add_argument("--analyze", action="store_true", help="run the AI workflow on every lead afterwards")
    args = parser.parse_args()

    if args.reset:
        reset_database()                                     # empty every table
        print("Old data deleted.")
    init_db()                                                # make sure tables exist

    with SessionLocal() as db:
        if db.query(Business).count() > 0:
            print("The database already has data. Run again with --reset to replace it.")
            return
        seed(db, leads_per_business=args.per_business)
        print_summary(db)
        if args.analyze:
            from app.services.lead_pipeline import analyze_lead   # imported here: only needed with --analyze
            lead_ids = [lead_id for (lead_id,) in db.query(Lead.id).order_by(Lead.id)]
            print(f"\nRunning the AI workflow on {len(lead_ids)} leads...")
            hot = 0
            for lead_id in lead_ids:
                run = analyze_lead(db, lead_id)
                hot += any(step["agent"] == "hot_alert" for step in run.steps)
            print(f"Done: {len(lead_ids)} leads analysed, {hot} marked HOT.")
        print("\nDone! Demo data saved to data/leads.db")
        print("\nDemo logins (POST /auth/login):")
        for email, business in zip(DEMO_OWNER_EMAILS, db.query(Business).order_by(Business.id)):
            print(f"  {email:<16} {DEMO_PASSWORD}   owner of {business.name}")
        print(f"  {'staff@demo.in':<16} {DEMO_PASSWORD}   staff at the gym")
        print(f"  {'admin@demo.in':<16} {ADMIN_PASSWORD}  admin: sees every business")


if __name__ == "__main__":
    main()
