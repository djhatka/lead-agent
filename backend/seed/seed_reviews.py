"""
Demo reviews for the 3 demo businesses: ~20 each over 90 days, mostly happy,
some complaints (slow replies, waiting, price), like a real local business.
Older ones already have a posted reply; recent ones don't yet, so the
Review Reply agent has work to do.
"""

import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.agents.nodes.review_reply_agent import find_topics
from app.models import Business, Review

TEXTS = {
    5: ["Excellent {service}! The team was very friendly and professional.",
        "Best {service} in {area}. Highly recommended!",
        "Very happy with the result. Staff explained everything clearly.",
        "Great experience, clean place and polite staff. Will come again.",
        ""],
    4: ["Good {service}, result was great. Slightly expensive but worth it.",
        "Nice experience overall, had to wait a little but the work was good.",
        "Friendly team and good quality work."],
    3: ["Work was okay but I had to wait almost an hour.",
        "Average experience. Price is on the higher side.",
        "Good result but nobody replied to my WhatsApp for a day."],
    2: ["Called twice, no response. Finally went in person, service was average.",
        "Overcharged compared to what was told on the phone."],
    1: ["Very rude staff and waited 2 hours. Worst experience.",
        "Booked an appointment but they didn't respect the time. Not coming again."],
}
FIRST = ["Rohit", "Neha", "Karan", "Simran", "Aditya", "Pooja", "Rahul", "Sneha", "Arjun", "Kavya",
         "Manish", "Riya", "Sahil", "Isha", "Deepak", "Meera", "Harsh", "Tanya", "Nikhil", "Divya"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Malhotra", "Kapoor", "Arora", "Bansal"]


def make_reviews(db: Session, r: random.Random, business: Business, now: datetime, count: int = 20) -> None:
    business.google_review_link = f"https://g.page/r/demo-{business.id}/review"
    platforms = ["google"] * 8 + (["practo"] if business.industry == "clinic" else ["facebook"])
    for i in range(count):
        rating = r.choices([5, 4, 3, 2, 1], weights=[50, 25, 10, 7, 8])[0]
        when = now - timedelta(days=r.uniform(0, 90))
        text = r.choice(TEXTS[rating]).format(service=r.choice(business.services).lower(),
                                              area=business.area or business.city)
        review = Review(business_id=business.id, platform=r.choice(platforms), external_id=f"demo-{business.id}-{i}",
                        author_name=f"{r.choice(FIRST)} {r.choice(LAST)}", rating=rating, text=text,
                        reviewed_at=when, created_at=when, topics=find_topics(text),
                        sentiment="positive" if rating >= 4 else "neutral" if rating == 3 else "negative")
        if now - when > timedelta(days=14) and r.random() < 0.6:        # older ones: already replied
            review.reply_status = "posted"
            review.reply_text = f"Thank you for your feedback! - Team {business.name}"
            review.replied_at = when + timedelta(hours=r.uniform(2, 72))
        else:
            review.needs_attention = rating <= 2          # unhappy and not answered yet
        db.add(review)
