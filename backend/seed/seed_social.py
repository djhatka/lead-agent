"""
Demo social media data: accounts and ~90 days of posts for each demo business,
plus links from leads to the posts that brought them.

Like the leads, posts have hidden "personalities" the AI should discover:

    pillar           reach   enquiries   buyers
    trend            ★★★★★   ★           ☆          ← lots of likes, almost no customers
    transformation   ★★★★    ★★★         ★★
    offer            ★★      ★★★★        ★★★        ← brings enquiries that buy
    testimonial      ★★      ★★          ★★★★       ← few enquiries, but they really buy
    tips             ★★      ★           ★
    behind_scenes    ★★      ★           ★
    festival         ★★★     ★           ★

And reels reach more people than photos or stories.
Uses its own random generator, so the lead data from seed_data.py stays the same.
"""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Business, Lead, Post, SocialAccount

IST = timezone(timedelta(hours=5, minutes=30))

# pillar: (reach multiplier, chance of bringing enquiries, chance those enquiries buy)
PILLARS = {
    "trend": (2.2, 0.3, 0.2),
    "transformation": (1.6, 1.2, 1.0),
    "offer": (1.0, 1.6, 1.5),
    "testimonial": (0.7, 0.9, 2.0),
    "tips": (0.9, 0.6, 0.7),
    "behind_the_scenes": (0.8, 0.4, 0.6),
    "festival": (1.1, 0.5, 0.5),
}
KIND_REACH = {"reel": 2.0, "video": 1.5, "carousel": 1.2, "photo": 1.0, "text": 0.6, "story": 0.5}

ACCOUNTS = {  # platform: (followers range, days between posts, kinds with weights, pillar weights)
    "instagram": ((1200, 4000), 2.5,
                  {"reel": 45, "carousel": 25, "photo": 20, "story": 10},
                  {"trend": 20, "transformation": 20, "offer": 15, "tips": 15,
                   "behind_the_scenes": 10, "testimonial": 10, "festival": 10}),
    "facebook": ((500, 1500), 7,
                 {"photo": 50, "video": 30, "text": 20},
                 {"offer": 25, "testimonial": 20, "tips": 15, "festival": 15,
                  "transformation": 15, "behind_the_scenes": 10}),
    "google": ((0, 0), 7,
               {"photo": 70, "text": 30},
               {"offer": 35, "testimonial": 25, "tips": 20, "festival": 20}),
}

CAPTIONS = {
    "trend": ["POV: you finally booked {service} 😂 #relatable", "Nobody: ... Us at {name} every Monday 💀",
              "Trying the viral trend with our team 😅"],
    "transformation": ["Before ➡️ After: {service} results that speak for themselves 🔥",
                       "Swipe to see the difference! {service} at {name} 💯",
                       "From this... to THIS. {service} done right ✨"],
    "offer": ["{festival} special: 20% off {service} this week only! DM to book 📩",
              "Only 10 slots left for {service} this month. Message us now!",
              "Flat ₹500 off {service} for first-time customers. Valid till Sunday!"],
    "testimonial": ["\"Best decision I made this year\" - our happy customer on {service} ⭐⭐⭐⭐⭐",
                    "Real reviews, real results. Thank you for trusting {name} with {service} 🙏",
                    "Customer story: why they chose {name} for {service}"],
    "tips": ["3 things to know before you book {service} 👇",
             "Mistakes people make with {service} (and how to avoid them)",
             "Save this! Quick guide to {service} 📌"],
    "behind_the_scenes": ["A normal day at {name} 👀", "Meet the team behind your {service} 💪",
                          "How we prepare for every {service} session"],
    "festival": ["Happy {festival} from all of us at {name}! 🪔", "{festival} vibes at {name} 🎉",
                 "Wishing you and your family a joyful {festival}!"],
}
HASHTAGS = {
    "gym": ["fitness", "gym", "delhifitness", "workout", "zumba", "fitnessmotivation"],
    "car_detailing": ["cardetailing", "ceramiccoating", "ppf", "delhicars", "carcare", "detailing"],
    "clinic": ["dentist", "dentalcare", "smile", "delhidentist", "teethwhitening", "healthysmile"],
}


def _festival(day: datetime) -> str:
    return {7: "Monsoon", 8: "Independence Day", 9: "Ganesh Chaturthi", 10: "Navratri",
            11: "Diwali", 12: "New Year"}.get(day.month, "Festive")


def _pick(r: random.Random, weights: dict) -> str:
    return r.choices(list(weights), weights=list(weights.values()))[0]


def _stats(r: random.Random, post: Post, followers: int) -> None:
    """Invent believable numbers for a published post."""
    reach_mult, _, _ = PILLARS[post.pillar]
    base = followers * r.uniform(0.15, 0.4) if followers else r.uniform(100, 600)   # google: views
    reach = int(base * KIND_REACH[post.kind] * reach_mult * r.uniform(0.6, 1.5))
    post.reach = reach
    post.likes = int(reach * r.uniform(0.03, 0.08) * (1.5 if post.pillar == "trend" else 1))
    post.comments = int(reach * r.uniform(0.002, 0.01))
    post.shares = int(reach * r.uniform(0.001, 0.006) * (3 if post.pillar == "trend" else 1))
    post.saves = int(reach * r.uniform(0.002, 0.01) * (2 if post.pillar == "tips" else 1))
    post.profile_visits = int(reach * r.uniform(0.01, 0.03))
    post.link_clicks = int(reach * r.uniform(0.002, 0.01) * (2 if post.pillar == "offer" else 1))
    post.stats_updated_at = post.published_at + timedelta(days=2)


def make_social(db: Session, r: random.Random, business: Business, now: datetime) -> dict[str, list[Post]]:
    """Create accounts and posts for one business. Returns published posts per platform."""
    handle = business.name.lower().replace(" ", "").replace("&", "and")
    published: dict[str, list[Post]] = {}

    for platform, (followers_range, every_days, kinds, pillars) in ACCOUNTS.items():
        followers = r.randint(*followers_range) if followers_range[1] else 0
        account = SocialAccount(business_id=business.id, platform=platform, handle=handle,
                                display_name=business.name, followers=followers)
        db.add(account)
        db.flush()

        posts: list[Post] = []
        day = now - timedelta(days=90)
        while True:
            day += timedelta(days=every_days * r.uniform(0.6, 1.4))
            if day >= now - timedelta(hours=6):
                break
            local = day.astimezone(IST).replace(hour=r.choice([9, 13, 18, 19, 20]), minute=r.randint(0, 59))
            post = Post(business_id=business.id, account_id=account.id, platform=platform,
                        kind=_pick(r, kinds), pillar=_pick(r, pillars), status="published", created_by="owner",
                        published_at=local.astimezone(timezone.utc))
            post.created_at = post.published_at - timedelta(days=1)
            if post.published_at > now:
                continue
            _fill_text(r, post, business)
            _stats(r, post, followers)
            posts.append(post)
        db.add_all(posts)
        published[platform] = posts

        if platform == "instagram":          # a few upcoming ones, so the planner has something to show
            for status, days_ahead in (("scheduled", 1), ("scheduled", 3), ("draft", None), ("idea", None)):
                upcoming = Post(business_id=business.id, account_id=account.id, platform=platform,
                                kind=_pick(r, kinds), pillar=_pick(r, pillars), status=status, created_by="owner",
                                scheduled_for=now + timedelta(days=days_ahead, hours=2) if days_ahead else None)
                _fill_text(r, upcoming, business)
                db.add(upcoming)

    db.flush()
    for posts in published.values():
        for post in posts:
            post.campaign = f"post-{post.id}"
    return published


def _fill_text(r: random.Random, post: Post, business: Business) -> None:
    service = r.choice(business.services) if business.services else "our services"
    when = post.published_at or post.scheduled_for or datetime.now(timezone.utc)
    post.caption = r.choice(CAPTIONS[post.pillar]).format(
        service=service, name=business.name, festival=_festival(when))
    post.title = f"{post.pillar.replace('_', ' ').title()} {post.kind} - {service}"
    post.hashtags = r.sample(HASHTAGS.get(business.industry, ["local", "delhi"]), 4)


def link_lead(r: random.Random, lead: Lead, published: dict[str, list[Post]]) -> None:
    """Most Instagram/Facebook enquiries (and a few Google ones) came from a recent post.
    Pick which one, favouring pillars that bring enquiries (and buyers, for won leads)."""
    chance = {"instagram": 0.75, "facebook": 0.75, "google": 0.2}.get(lead.source, 0)
    if not chance or r.random() > chance:
        return
    recent = [p for p in published.get(lead.source, [])
              if timedelta(0) <= lead.created_at - p.published_at <= timedelta(days=10)]
    if not recent:
        return
    weights = [PILLARS[p.pillar][1] * (PILLARS[p.pillar][2] if lead.status == "won" else 1) for p in recent]
    lead.post = r.choices(recent, weights=weights)[0]
