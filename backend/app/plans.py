"""
The price list: what each subscription plan costs and what it includes.

Change prices or limits HERE and the whole app follows (the pricing page,
the paywall, the limits). Money is in whole rupees, per month.

Every plan includes the core: the lead inbox with AI scoring and hot alerts
on every platform, the content planner + writer, the scheduler, review
replies, and the live feed. Higher plans add more people, more social
accounts, and the "growth coach" features.

New businesses get a free trial of TRIAL_PLAN (settings.trial_days long).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price: int                         # ₹ per month
    tagline: str
    staff_seats: int                   # people besides the owner who can log in
    social_accounts: int               # Instagram, Facebook, Google... profiles connected
    storage_mb: int                    # space for uploaded photos and videos
    weekly_review: bool                # the Monday AI growth review
    review_requests: bool              # automatic "please review us" WhatsApps after a sale
    highlights: tuple[str, ...] = field(default_factory=tuple)   # bullet points for the pricing page


PLANS: dict[str, Plan] = {
    "starter": Plan(
        code="starter", name="Starter", price=999, tagline="Never miss an enquiry",
        staff_seats=1, social_accounts=2, storage_mb=1024, weekly_review=False, review_requests=False,
        highlights=("Every enquiry in one inbox, from 36 platforms", "AI scores leads and flags 🔥 hot ones",
                    "AI plans and writes your posts", "AI drafts replies to your reviews",
                    "1 staff login, 2 social accounts"),
    ),
    "growth": Plan(
        code="growth", name="Growth", price=2499, tagline="Your AI growth partner",
        staff_seats=3, social_accounts=6, storage_mb=5120, weekly_review=True, review_requests=True,
        highlights=("Everything in Starter", "Weekly AI growth review with your top 3 actions",
                    "Automatic 'please review us' WhatsApps", "Up to 6 social accounts, 3 staff"),
    ),
    "pro": Plan(
        code="pro", name="Pro", price=4999, tagline="For busy teams and multiple branches",
        staff_seats=10, social_accounts=20, storage_mb=20480, weekly_review=True, review_requests=True,
        highlights=("Everything in Growth", "Up to 20 social accounts, 10 staff", "Priority support"),
    ),
}

TRIAL_PLAN = "growth"            # what a free trial includes
PLAN_CODES = tuple(PLANS)        # ("starter", "growth", "pro")


def get_plan(code: str) -> Plan:
    return PLANS.get(code, PLANS[TRIAL_PLAN])


def cheapest_with(feature: str) -> Plan:
    """The cheapest plan that includes a feature, for 'Upgrade to Growth to ...' messages."""
    return min((p for p in PLANS.values() if getattr(p, feature)), key=lambda p: p.price)
