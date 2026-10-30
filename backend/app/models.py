"""
The database tables ("drawers in the filing cabinet").

Each class below = one table. Each `mapped_column(...)` = one column.
SQLAlchemy reads these classes and creates the real tables in leads.db.

    businesses      one row per business using the app (gym, salon, clinic...)
    leads           one row per customer enquiry
    messages        every chat message, linked to a lead
    lead_analysis   what the AI decided about a lead (tone, score, priority)
    agent_runs      a log of every time the AI team worked, step by step
    growth_reports  the weekly AI business report + content plan
    social_accounts a business's Instagram / Facebook / Google... profiles
    posts           every post: idea → draft → scheduled → published, with its numbers
    reviews         customer reviews (Google, Practo...) and the business's replies
    review_requests "please review us" messages sent to happy customers
    users           people who log in (owner, staff, or platform admin)
    auth_sessions   active logins (one per device), so we know who's asking
    subscriptions   each business's plan: free trial / paid / payment problem / cancelled
    payments        every payment received (or failed), for the billing history
    connections     a business's live link to WhatsApp / Instagram / Facebook / Google (keys locked)
    media           photos and videos the business uploaded (its media library)
    emails          every email we sent (or tried to), so nothing is sent twice
    password_resets one-time "set a new password" links
    inbound_emails  lead emails forwarded to the business's lead address (Justdial, Sulekha...)
    contact_messages  messages sent through the public website's contact form
    deleted_accounts  a small record kept after an account is deleted (payment records: tax law)
    roi_reports     the monthly "what Lead Intel did for you" report, one per business per month
    owner_alerts    WhatsApp alerts sent to the owner's own phone (e.g. "🔥 hot lead, call now")
    renewals        memberships/services about to expire, so the owner can offer a renewal
    competitors     3-5 nearby rivals the owner watches (rating, reviews, activity)
    competitor_alerts  one "they moved" note per noticed change
    bookings        booking slots inside WhatsApp: a shareable link, a time picked, no back-and-forth
    tracking_numbers  one phone number per business, for call tracking
    calls           every call through a tracking number: missed flagged, completed gets an AI note

How they connect:

    businesses ──< leads ──< messages        a business has MANY leads; a lead has MANY messages
                   leads ──○ lead_analysis   a lead has ONE analysis (or none yet)
    businesses ──< agent_runs                every AI run belongs to one business
    businesses ──< growth_reports            one report per business per week
    agent_runs ──○ growth_reports            a report comes from one AI run
    businesses ──< social_accounts ──< posts  a business has accounts; an account has posts
    posts ──< leads                          "this enquiry came from this post"
    businesses ──< reviews; leads ──○ review_requests (one request per won customer)
    businesses ──○ subscriptions ──< payments  one subscription per business; many payments
    businesses ──< connections ──○ social_accounts  a connection can power one social account
    businesses ──< media ──< posts           a post can use one photo/video from the library

Every important table has a `business_id`. That is what keeps each
business's data separate ("multi-tenant"): Redox Gym only ever sees rows
with Redox Gym's business_id.

"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.platforms import PLATFORMS, POSTING_PLATFORMS


def utc_now() -> datetime:
    """Current time in UTC (one world clock, so times never get mixed up)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Allowed values. Stored as plain text in the database; Task 3 (schemas)
# will reject anything that isn't in these lists.
# ---------------------------------------------------------------------------
INDUSTRIES = (
    "gym", "salon", "clinic", "restaurant", "cafe", "coaching", "real_estate",
    "auto_service", "car_detailing", "retail", "other",
)
# Every platform in app/platforms.py is an allowed lead source
LEAD_SOURCES = tuple(PLATFORMS)
SOCIAL_PLATFORMS = POSTING_PLATFORMS        # where a business can have an account and post
LEAD_STATUSES = ("new", "contacted", "quoted", "booked", "won", "lost")
MESSAGE_DIRECTIONS = ("inbound", "outbound")       # from customer / from business
SENTIMENTS = ("urgent", "casual", "frustrated")
PRIORITIES = ("hot", "normal")
WORKFLOWS = ("lead", "content_plan", "content_write", "growth")   # the AI jobs we log
RUN_STATUSES = ("running", "success", "failed")

# --- Reputation ---
REVIEW_PLATFORMS = ("google", "facebook", "practo", "lybrate", "justdial", "zomato", "swiggy",
                    "magicpin", "urbanpro", "urban_company", "other")
REPLY_STATUSES = ("none", "drafted", "posted")
REQUEST_STATUSES = ("pending", "sent", "reviewed", "skipped")

# --- Accounts ---
# owner: runs the business, can change settings and add staff
# staff: works on leads, posts and reviews, but can't change settings or the team
# admin: you, the platform owner: can see every business (for support)
ROLES = ("owner", "staff", "admin")

# --- Social media ---
POST_KINDS = ("reel", "photo", "carousel", "story", "video", "text")
POST_STATUSES = ("idea", "draft", "scheduled", "published", "failed")
# Content "pillars" = the TYPE of message a post carries. Tracking them lets
# the AI learn e.g. "offers bring buyers, trends bring likes but no customers".
CONTENT_PILLARS = (
    "transformation",      # before/after, results
    "offer",               # discount, limited deal
    "tips",                # useful advice
    "behind_the_scenes",   # the team, the place, how work is done
    "testimonial",         # happy customer stories, reviews
    "festival",            # Diwali, New Year...
    "trend",               # memes, trending audio
)


class Business(Base):
    """One business that uses the app. The AI reads this to understand who
    it's working for: a gym gets gym advice, a clinic gets clinic advice."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))                        # "Redox Gym"
    industry: Mapped[str] = mapped_column(String(30), index=True)         # one of INDUSTRIES
    city: Mapped[str] = mapped_column(String(100), default="Delhi")
    area: Mapped[Optional[str]] = mapped_column(String(100))              # "New Moti Nagar"
    description: Mapped[str] = mapped_column(Text, default="")            # what they do, in a few lines

    # Their menu of services, e.g. ["Zumba", "Personal training", "Aerobics"]
    services: Mapped[list] = mapped_column(JSON, default=list)
    # How their posts should sound, e.g. "energetic, Hinglish, lots of emojis"
    brand_voice: Mapped[str] = mapped_column(Text, default="")
    # Who they want to reach, e.g. "working women 25-40 in West Delhi"
    target_audience: Mapped[str] = mapped_column(Text, default="")

    phone: Mapped[Optional[str]] = mapped_column(String(20))
    website: Mapped[Optional[str]] = mapped_column(String(200))
    # The "write a review" link from Google Business Profile, e.g. https://g.page/r/XXXX/review
    google_review_link: Mapped[Optional[str]] = mapped_column(String(300))
    # The secret part of their lead-email address: leads-<this>@in.yourdomain.in
    inbound_token: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    # The owner's own WhatsApp number for alerts (not the business number) and their alert choices:
    #   {"hot_leads": true, "quiet_hours": false}  (quiet hours = hold alerts from 10pm until 8am)
    alert_phone: Mapped[Optional[str]] = mapped_column(String(20))
    alert_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Instant AI first reply (Task 29) to new WhatsApp / Instagram / Facebook enquiries:
    #   {"mode": "off" | "always" | "after_hours", "opens": "09:00", "closes": "21:00",
    #    "closed_days": [1], "note": "For emergencies call 98100 00000"}   (days: 0 = Monday)
    auto_reply_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Follow-up reminders (Task 30): {"enabled": true, "after_days": 2}
    followup_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Payments from customers (Task 31): money goes straight to the owner's own UPI ID
    #   {"upi_id": "ironpulse@okaxis", "payee_name": "Iron Pulse Fitness", "auto_reminders": false}
    payment_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Renewal reminders (Task 32): {"enabled": true, "remind_days_before": 5}
    renewal_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Fill your empty hours (Task 33): {"enabled": true, "min_days_since_won": 30}
    slow_hours_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Booking slots (Task 37): when customers can book, and how long each slot is
    #   {"slot_minutes": 30, "days_ahead": 7, "start_hour": 10, "end_hour": 19, "closed_weekdays": [6]}
    booking_settings: Mapped[Optional[dict]] = mapped_column(JSON)
    # Dashboard language (Task 39): "en" or "hi" - one switch, every screen follows it
    language: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # Links to this business's rows in other tables.
    # cascade="all, delete-orphan": delete a business → all its data goes too.
    leads: Mapped[list["Lead"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    growth_reports: Mapped[list["GrowthReport"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    social_accounts: Mapped[list["SocialAccount"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["Review"]] = relationship(back_populates="business", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Business #{self.id} {self.name} ({self.industry})>"


class Lead(Base):
    """One customer enquiry, from any channel, for one business."""

    __tablename__ = "leads"
    # The same WhatsApp message must never create two leads (Meta sometimes
    # sends a webhook twice). So within one business, source + external_id
    # must be unique.
    __table_args__ = (
        UniqueConstraint("business_id", "source", "external_id", name="uq_lead_business_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)  # 1, 2, 3... given automatically
    # ForeignKey = "this number must be the id of a real business".
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)

    # Where did they come from?
    source: Mapped[str] = mapped_column(String(20), index=True)           # e.g. "whatsapp"
    external_id: Mapped[Optional[str]] = mapped_column(String(100))       # the platform's own message ID
    campaign: Mapped[Optional[str]] = mapped_column(String(100))          # e.g. "diwali-offer" (from UTM links)
    # Which post brought this customer, if we know (e.g. a DM replying to a reel)
    post_id: Mapped[Optional[int]] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"), index=True)

    # Who are they? (any of these can be missing)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    handle: Mapped[Optional[str]] = mapped_column(String(100))            # Instagram/Facebook username
    area: Mapped[Optional[str]] = mapped_column(String(100))              # e.g. "Dwarka"

    # What do they want? (filled in by the Intake Agent)
    service: Mapped[Optional[str]] = mapped_column(String(100))           # e.g. "Zumba" or "Ceramic coating"
    # Industry-specific extras, different for each kind of business:
    #   gym      → {"batch": "evening", "goal": "weight loss"}
    #   clinic   → {"preferred_date": "Saturday", "treatment": "cleaning"}
    #   car shop → {"car_model": "Hyundai Creta"}
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    first_message: Mapped[str] = mapped_column(Text, default="")

    # How far did it get? new → contacted → quoted → booked → won / lost
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    job_value: Mapped[Optional[int]] = mapped_column(Integer)             # ₹ earned, only once won
    # When it became a sale, so a sale counts in the month it happened (the monthly ROI report)
    won_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)

    # Times (used for "average reply time" and "peak hours")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Follow-up reminders (Task 30): "remind me later" moves the reminder to this time;
    # followup_stopped = the owner said "stop reminding me about this one"
    followup_snoozed_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    followup_stopped: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # Fill your empty hours (Task 33): the last time we invited this (past, won) customer
    # back to fill a quiet slot, so we don't offer the same person again too soon.
    last_slow_offer_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Links to other tables. These are NOT columns; they let Python do
    # `lead.messages` or `lead.analysis` instead of writing a search by hand.
    business: Mapped["Business"] = relationship(back_populates="leads")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Message.sent_at"
    )
    analysis: Mapped[Optional["LeadAnalysis"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", uselist=False
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="lead")
    post: Mapped[Optional["Post"]] = relationship(back_populates="leads")

    def __repr__(self) -> str:  # how a lead looks when printed while debugging
        return f"<Lead #{self.id} {self.source} {self.name or self.phone or self.handle} [{self.status}]>"


class Message(Base):
    """One chat message, either from the customer or from the business."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(10), default="inbound")  # inbound / outbound
    text: Mapped[str] = mapped_column(Text)
    # The platform's own ID for this message (e.g. WhatsApp's "wamid...").
    # Lets us spot the same message arriving twice and ignore the copy.
    external_id: Mapped[Optional[str]] = mapped_column(String(150), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # For the business's replies: did it actually reach the customer?
    #   sent    → delivered to WhatsApp/Instagram/Facebook through a connection
    #   failed  → we tried; `delivery_error` says why (e.g. the 24-hour rule)
    #   logged  → only written down (no connection for that platform, or "just note it")
    delivery: Mapped[str] = mapped_column(String(10), default="")
    delivery_error: Mapped[str] = mapped_column(Text, default="")
    # True = the AI's instant first reply (Task 29), not typed by the owner
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # True = a follow-up the owner sent from a reminder (Task 30)
    followup: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    lead: Mapped["Lead"] = relationship(back_populates="messages")


class LeadAnalysis(Base):
    """The AI team's verdict on one lead (written by the lead workflow)."""

    __tablename__ = "lead_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True: each lead has at most ONE analysis. Re-analysing updates it.
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), unique=True)

    sentiment: Mapped[str] = mapped_column(String(20))                    # urgent / casual / frustrated
    sentiment_reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, index=True)               # 1–100
    score_reason: Mapped[str] = mapped_column(Text, default="")
    # The score's ingredients, e.g. {"source": 20, "phone_shared": 10, "ai_intent": 15}
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[str] = mapped_column(String(10), default="normal", index=True)  # hot / normal
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    lead: Mapped["Lead"] = relationship(back_populates="analysis")


class AgentRun(Base):
    """A log entry for one run of the AI team (so the dashboard can replay it)."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    workflow: Mapped[str] = mapped_column(String(20), index=True)         # "lead" or "growth"
    # Which lead it was about (empty for the weekly growth run).
    # ondelete="SET NULL": deleting a lead keeps the log but blanks this link.
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")    # running / success / failed
    # One entry per agent, e.g.
    # [{"agent": "sentiment", "output": {...}, "ms": 420}, {"agent": "scoring", ...}]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    ai_mode: Mapped[str] = mapped_column(String(10), default="mock")      # mock / real
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    business: Mapped["Business"] = relationship(back_populates="agent_runs")
    lead: Mapped[Optional["Lead"]] = relationship(back_populates="agent_runs")
    growth_report: Mapped[Optional["GrowthReport"]] = relationship(back_populates="agent_run", uselist=False)


class GrowthReport(Base):
    """One weekly growth report for one business (written by the growth workflow)."""

    __tablename__ = "growth_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)            # the Monday of that week
    agent_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))

    summary: Mapped[str] = mapped_column(Text, default="")                # owner-friendly report
    # The numbers the AI looked at, saved so the report can always be checked
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    weak_platforms: Mapped[list] = mapped_column(JSON, default=list)      # e.g. ["facebook"]
    presence_audit: Mapped[list] = mapped_column(JSON, default=list)      # checklist items
    top_actions: Mapped[list] = mapped_column(JSON, default=list)         # the 3 things to do this week
    content_plan: Mapped[list] = mapped_column(JSON, default=list)        # 7 days of post/reel ideas
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    business: Mapped["Business"] = relationship(back_populates="growth_reports")
    agent_run: Mapped[Optional["AgentRun"]] = relationship(back_populates="growth_report")


class SocialAccount(Base):
    """One profile of a business on one platform, e.g. @ironpulsefitness on Instagram."""

    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("business_id", "platform", "handle", name="uq_account_business_platform_handle"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))                     # one of SOCIAL_PLATFORMS
    handle: Mapped[str] = mapped_column(String(100))                      # "ironpulsefitness"
    display_name: Mapped[str] = mapped_column(String(150), default="")
    followers: Mapped[int] = mapped_column(Integer, default=0)
    # The platform's own ID for this account. When real accounts are connected,
    # this is how an incoming webhook is matched to the right business.
    external_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    connected: Mapped[bool] = mapped_column(default=False)               # real API connected yet?
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    business: Mapped["Business"] = relationship(back_populates="social_accounts")
    posts: Mapped[list["Post"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Post(Base):
    """One post, from first idea to published, with its numbers.

    Life of a post:  idea → draft → scheduled → published   (or failed)
    """

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), index=True)         # copied from the account, for quick filtering

    # What it is
    kind: Mapped[str] = mapped_column(String(20), default="photo")        # reel / photo / carousel...
    pillar: Mapped[str] = mapped_column(String(30), default="tips")       # what type of message (CONTENT_PILLARS)
    title: Mapped[str] = mapped_column(String(150), default="")           # short internal name, e.g. "Diwali offer reel"
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    script: Mapped[str] = mapped_column(Text, default="")                 # reel/video script: what to say and show
    media_note: Mapped[str] = mapped_column(Text, default="")             # what photo/video to shoot
    # A public link to the actual photo (JPEG) or video. Instagram needs one;
    # Facebook and Google can post text only.
    media_url: Mapped[str] = mapped_column(String(500), default="")
    media_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))   # from the library
    # Tracking tag for links in this post (?utm_campaign=post-12). Website leads
    # carrying this tag are automatically linked back to this post.
    campaign: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # Where it is in its life
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_by: Mapped[str] = mapped_column(String(10), default="owner")  # "ai" or "owner"
    ai_reason: Mapped[str] = mapped_column(Text, default="")             # why the AI suggested this post
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100))       # the platform's ID once published
    publish_error: Mapped[str] = mapped_column(Text, default="")          # why publishing failed, if it did

    # The numbers (latest values; updated by the performance tracker)
    reach: Mapped[int] = mapped_column(Integer, default=0)                # different people who saw it
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    profile_visits: Mapped[int] = mapped_column(Integer, default=0)
    link_clicks: Mapped[int] = mapped_column(Integer, default=0)
    stats_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    account: Mapped["SocialAccount"] = relationship(back_populates="posts")
    leads: Mapped[list["Lead"]] = relationship(back_populates="post")

    def __repr__(self) -> str:
        return f"<Post #{self.id} {self.platform} {self.kind}/{self.pillar} [{self.status}]>"


class Review(Base):
    """One customer review on Google / Practo / Zomato..., plus our reply."""

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("business_id", "platform", "external_id", name="uq_review_platform_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), default="google")
    external_id: Mapped[str] = mapped_column(String(150))                 # the platform's ID (stops duplicates)
    author_name: Mapped[str] = mapped_column(String(100), default="")
    rating: Mapped[int] = mapped_column(Integer)                          # 1-5 stars
    text: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    # Which customer wrote it, if we could match them to a lead
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))

    # Filled in by the Review Reply agent
    sentiment: Mapped[str] = mapped_column(String(10), default="")        # positive / neutral / negative
    topics: Mapped[list] = mapped_column(JSON, default=list)              # e.g. ["staff", "wait time"]
    needs_attention: Mapped[bool] = mapped_column(default=False)          # unhappy customer: owner should look

    # Our reply:  none → drafted (by AI) → posted (approved by the owner)
    reply_text: Mapped[str] = mapped_column(Text, default="")
    reply_status: Mapped[str] = mapped_column(String(10), default="none", index=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    business: Mapped["Business"] = relationship(back_populates="reviews")


class ReviewRequest(Base):
    """A polite 'please review us' WhatsApp message to a customer who just bought."""

    __tablename__ = "review_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), unique=True)  # once per customer
    phone: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)   # pending/sent/reviewed/skipped
    send_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Due(Base):
    """Money a customer owes the business (Task 31): an advance for a booking, a membership fee...
    The customer pays the OWNER directly by UPI through a small payment page (/pay/<token>);
    Lead Intel never touches the money. (Not to be confused with `Payment`: the owner paying us.)"""

    __tablename__ = "dues"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    # The enquiry it belongs to, if any (a walk-in's membership fee may have none)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)                          # whole rupees
    purpose: Mapped[str] = mapped_column(String(200))                     # "Advance for ceramic coating"
    due_date: Mapped[Optional[date]] = mapped_column(Date)                # empty = pay now (no automatic reminders)
    # open → paid / cancelled
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    # The secret part of the payment page address: /pay/<token>
    token: Mapped[str] = mapped_column(String(32), unique=True)
    # The customer pressed "I've paid" on the payment page: the owner checks their UPI app and confirms
    customer_says_paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    paid_via: Mapped[str] = mapped_column(String(12), default="")         # upi / cash / card / other
    auto_remind: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


RENEWAL_STATUSES = ("upcoming", "due", "expired", "renewed", "stopped")


class Renewal(Base):
    """A customer's membership or service that expires on a known date (Task 32).

    Different from follow-ups (enquiries gone quiet) and dues (money owed):
    a renewal tracks when something the customer already bought is about to end,
    so the owner can offer a renewal before the customer disappears.

    Status flow: upcoming → due (within remind_days_before) → expired (past expiry)
                 → renewed (customer renewed) or stopped (owner said stop reminding).
    """

    __tablename__ = "renewals"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    service: Mapped[str] = mapped_column(String(100))                      # "Monthly membership", "PPF package"
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    renewal_amount: Mapped[Optional[int]] = mapped_column(Integer)         # ₹ for the renewal (optional)
    # upcoming → due → expired → renewed / stopped
    status: Mapped[str] = mapped_column(String(12), default="upcoming", index=True)
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    renewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Competitor(Base):
    """A nearby rival the owner wants to keep an eye on (Task 35), at most 5 per business.

    No official Google ranking API exists, so the numbers below come from a paid
    map-search data service (e.g. DataForSEO) once DATAFORSEO_LOGIN/PASSWORD are set
    in .env; until then they're realistic, slowly-drifting pretend numbers (free mock mode).
    """

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("business_id", "name", "area", name="uq_competitor_business_name_area"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    area: Mapped[str] = mapped_column(String(100), default="")            # where to search, e.g. "Dwarka, Delhi"
    place_id: Mapped[Optional[str]] = mapped_column(String(150))          # Google's id for this listing, once matched
    rating: Mapped[Optional[float]] = mapped_column(Float)
    review_count: Mapped[Optional[int]] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    # The snapshot from before the latest check, so we can tell what moved
    previous_rating: Mapped[Optional[float]] = mapped_column(Float)
    previous_review_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    problem: Mapped[str] = mapped_column(Text, default="")                # e.g. "not found on Google Maps"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CompetitorAlert(Base):
    """One "a competitor moved" note (Task 35): a new batch of reviews, or their rating
    shifting enough to matter. Shown on Competitor watch and on the live feed."""

    __tablename__ = "competitor_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))                         # new_reviews / rating_up / rating_down
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


BOOKING_STATUSES = ("pending", "confirmed", "cancelled")


class Booking(Base):
    """A booking slot inside WhatsApp (Task 37): the owner sends a link, the customer
    picks a free time from the business's own working hours, no back-and-forth needed.

    Same shape as Due/payments: a shareable page at /book/<token> is the only key.
    Status flow: pending (link sent, no slot chosen yet) → confirmed (customer picked
    a time) or cancelled (owner cancelled it, or the customer never picked one)."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    # The enquiry it belongs to, if any (a walk-in booking may have none)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    service: Mapped[str] = mapped_column(String(150))                     # "Personal training session"
    # pending → confirmed / cancelled
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    # The secret part of the booking page address: /book/<token>
    token: Mapped[str] = mapped_column(String(32), unique=True)
    slot_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)  # set once chosen
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")    # a snapshot at creation
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TrackingNumber(Base):
    """One phone number per business (Task 38): customers call it instead of the owner's
    real number; the provider forwards it straight through, and every call shows up here."""

    __tablename__ = "tracking_numbers"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), unique=True, index=True)
    number: Mapped[str] = mapped_column(String(20))
    provider_sid: Mapped[str] = mapped_column(String(60), default="")      # the provider's own id for this number
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


CALL_STATUSES = ("ringing", "completed", "missed", "failed")


class Call(Base):
    """One phone call through the business's tracking number (Task 38). Missed calls are
    flagged for a call-back; completed calls get a short AI note on what the caller asked
    about, when a transcript is available (not every provider/plan includes one)."""

    __tablename__ = "calls"
    __table_args__ = (UniqueConstraint("business_id", "external_id", name="uq_call_business_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))                  # the provider's own call id
    from_number: Mapped[str] = mapped_column(String(20), default="")
    # ringing → completed / missed / failed
    status: Mapped[str] = mapped_column(String(12), default="ringing", index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    recording_url: Mapped[str] = mapped_column(String(500), default="")
    transcript: Mapped[str] = mapped_column(Text, default="")              # raw, when the provider sends one
    note: Mapped[str] = mapped_column(Text, default="")                    # the AI's one-line "what they asked"
    called_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base):
    """Someone who can log in."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)   # always stored in lowercase
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(300))                     # never the password itself
    role: Mapped[str] = mapped_column(String(10), default="owner")
    # Which business they belong to (empty for the platform admin)
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """One active login (e.g. the owner's phone, or their laptop)."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # fingerprint of the token
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="sessions")


SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "cancelled")


class Subscription(Base):
    """A business's plan. Created with a free trial when the business signs up.

    status:  trialing  → free trial (until trial_ends_at)
             active    → paid (until current_period_end, then Razorpay charges again)
             past_due  → the last charge failed; Razorpay keeps retrying
             cancelled → the owner cancelled; works until current_period_end
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(20))                         # starter / growth / pro
    status: Mapped[str] = mapped_column(String(10), default="trialing", index=True)
    trial_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))   # paid until
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    # Razorpay's id for the PAID subscription that renews every month
    gateway_subscription_id: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    # A checkout in progress (new plan or upgrade). Kept apart, so closing the
    # payment window halfway never breaks the plan that's already paid.
    pending_plan: Mapped[Optional[str]] = mapped_column(String(20))
    pending_gateway_subscription_id: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    payments: Mapped[list["Payment"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")


class Payment(Base):
    """One payment from a business to you."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    gateway_payment_id: Mapped[str] = mapped_column(String(60), unique=True)   # Razorpay's pay_... id (no doubles)
    plan: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)                              # ₹, whole rupees
    status: Mapped[str] = mapped_column(String(10), default="paid")           # paid / failed
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    subscription: Mapped["Subscription"] = relationship(back_populates="payments")


CONNECTION_PLATFORMS = ("whatsapp", "instagram", "facebook", "google")


class Connection(Base):
    """A business's live link to one platform account.

    external_id is how the platform names that account, and how an incoming
    webhook finds the right business:
        whatsapp  → phone_number_id        instagram → IG professional account id
        facebook  → Page id                google    → "accounts/123/locations/456"
    status:  connected / needs_reconnect (the key stopped working) / disconnected
    mode:    "real" (actual API) or "mock" (pretend, while app keys aren't set)
    """

    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), index=True)
    external_id: Mapped[str] = mapped_column(String(150), index=True)
    display_name: Mapped[str] = mapped_column(String(150), default="")   # "+91 98110 00000" / "@ironpulse"
    mode: Mapped[str] = mapped_column(String(10), default="mock")
    status: Mapped[str] = mapped_column(String(20), default="connected", index=True)
    problem: Mapped[str] = mapped_column(Text, default="")                # why it needs a reconnect
    # Locked (encrypted) keys: never stored as plain text
    access_token_locked: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token_locked: Mapped[Optional[str]] = mapped_column(Text)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict] = mapped_column(JSON, default=dict)                # e.g. {"waba_id": ...}
    social_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("social_accounts.id", ondelete="SET NULL"))
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Media(Base):
    """One photo or video in a business's media library.

    The file itself lives in storage (data/media/ for now) under an
    unguessable name, e.g. "1/9f2c...e1.jpg", and is served at /files/<key>.
    Photos are cleaned on upload: turned into JPEG (Instagram's only photo
    format), rotated the right way up, hidden location data removed.
    """

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))                          # photo / video
    key: Mapped[str] = mapped_column(String(120), unique=True)             # where the file is stored
    thumb_key: Mapped[Optional[str]] = mapped_column(String(120))          # small preview (photos)
    instagram_key: Mapped[Optional[str]] = mapped_column(String(120))      # a 4:5 / 1.91:1 crop, if the photo needs one
    content_type: Mapped[str] = mapped_column(String(40))
    original_name: Mapped[str] = mapped_column(String(200), default="")
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    warnings: Mapped[list] = mapped_column(JSON, default=list)            # e.g. "too wide for an Instagram post"
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Email(Base):
    """One email: written here first ("queued"), then sent by the mailer.

    status: queued → sending → sent   (or failed: tried again later, up to 3 times)
    dedupe_key stops doubles, e.g. "trial_ending:5:2026-11-01" can exist only once.
    """

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[Optional[int]] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    to: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), index=True)              # welcome / password_reset / receipt...
    subject: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    html: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    """A one-time 'set a new password' link (forgot password, or a new staff member).
    Like logins, only a fingerprint of the secret is stored."""

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(10), default="reset")      # reset / invite
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class InboundEmail(Base):
    """One email that arrived at a business's lead address, and what we did with it.

    status:  lead          → a new enquiry was created
             added         → added to an existing customer's conversation
             duplicate     → the same email came twice (ignored)
             unparsed      → no name/phone found: the owner should look at it
             confirmation  → Gmail's "confirm forwarding" email (code shown in Settings)
    """

    __tablename__ = "inbound_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    from_addr: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300), default="")
    platform: Mapped[str] = mapped_column(String(20), default="email")
    status: Mapped[str] = mapped_column(String(15), index=True)
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, default="")
    preview: Mapped[str] = mapped_column(Text, default="")                # the first part of the email text
    message_id: Mapped[str] = mapped_column(String(300), default="", index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ContactMessage(Base):
    """Someone wrote to you through the website's contact form."""

    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30), default="")
    business: Mapped[str] = mapped_column(String(150), default="")
    topic: Mapped[str] = mapped_column(String(20), default="question")       # question / support / privacy / billing
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class DeletedAccount(Base):
    """When an owner deletes their account, all their data goes, except this note:
    who/when, and their payment records, which Indian tax law says to keep for 8 years."""

    __tablename__ = "deleted_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(150))
    owner_email: Mapped[str] = mapped_column(String(200))
    payments: Mapped[list] = mapped_column(JSON, default=list)               # [{date, amount, plan, payment_id}]
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)



class RoiReport(Base):
    """The monthly "what Lead Intel did for you" report: one per business per month.

    The numbers are saved as they were on the day the report was made, so the
    owner always sees exactly what we told them, even if a lead changes later.
    """

    __tablename__ = "roi_reports"
    __table_args__ = (UniqueConstraint("business_id", "month", name="uq_roi_business_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)                # "2026-10"
    stats: Mapped[dict] = mapped_column(JSON, default=dict)                 # every number in the report
    message: Mapped[str] = mapped_column(Text, default="")                  # the WhatsApp-ready text
    emailed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OwnerAlert(Base):
    """One WhatsApp alert to the owner's own phone, e.g. "🔥 Hot lead: call Rahul now".

    status: pending → sent, or failed (tried 3 times) / skipped (alerts turned off, no phone, plan ended)
    """

    __tablename__ = "owner_alerts"
    __table_args__ = (UniqueConstraint("business_id", "kind", "lead_id", name="uq_alert_once_per_lead"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="hot_lead")      # hot_lead / test
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    phone: Mapped[str] = mapped_column(String(20), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[list] = mapped_column(JSON, default=list)                # the template's blanks: business, what, link
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    sent_by: Mapped[str] = mapped_column(String(20), default="")            # lead_intel / business / practice
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
