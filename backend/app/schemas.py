"""
Data rules ("schemas") - the security guard at the door.

models.py describes how data is STORED. This file describes what data is
ALLOWED IN and what we SEND OUT through the API.

Every class here is a Pydantic "model": a checklist. When data arrives,
Pydantic ticks through the checklist:
    - Is every required field there?
    - Is each value the right type (number, text, list...)?
    - Is it on the allowed list (e.g. industry must be "gym", "salon"...)?
    - Do our custom rules pass (e.g. phone number looks real)?
If anything fails, FastAPI automatically replies with a clear error
(status 422) and NOTHING is saved. Bad data never reaches the database.

Naming pattern used below:
    XxxCreate  - what you must send to CREATE something
    XxxUpdate  - what you MAY send to CHANGE something (all fields optional)
    XxxOut     - what the API SENDS BACK to the dashboard
"""

import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import (
    CONTENT_PILLARS,
    REVIEW_PLATFORMS,
    INDUSTRIES,
    LEAD_SOURCES,
    LEAD_STATUSES,
    MESSAGE_DIRECTIONS,
    POST_KINDS,
    POST_STATUSES,
    PRIORITIES,
    RUN_STATUSES,
    SENTIMENTS,
    SOCIAL_PLATFORMS,
    WORKFLOWS,
)

# ---------------------------------------------------------------------------
# "Literal" = only these exact words are accepted. We reuse the lists from
# models.py so the allowed values are written in ONE place only.
# ---------------------------------------------------------------------------
Industry = Literal[INDUSTRIES]
LeadSource = Literal[LEAD_SOURCES]
LeadStatus = Literal[LEAD_STATUSES]
Direction = Literal[MESSAGE_DIRECTIONS]
Sentiment = Literal[SENTIMENTS]
Priority = Literal[PRIORITIES]
Workflow = Literal[WORKFLOWS]
RunStatus = Literal[RUN_STATUSES]
SocialPlatform = Literal[SOCIAL_PLATFORMS]
PostKind = Literal[POST_KINDS]
PostStatus = Literal[POST_STATUSES]
Pillar = Literal[CONTENT_PILLARS]
ReviewPlatform = Literal[REVIEW_PLATFORMS]


def _as_utc(value: datetime) -> datetime:
    """SQLite forgets the timezone when it stores a time. All our times are
    UTC, so we label them as UTC again before sending them out. The dashboard
    can then show them in India time (IST) correctly."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# Use this instead of plain `datetime` for every time we SEND OUT
UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def clean_phone(value: Optional[str]) -> Optional[str]:
    """Turn the many ways people write Indian numbers into ONE format.

        "98110 00000"      → "+919811000000"
        "098110-00000"     → "+919811000000"
        "+91 98110 00000"  → "+919811000000"
        "+1 415 555 0100"  → "+14155550100"   (foreign numbers are kept)
        "12345"            → error
    """
    if value is None or value.strip() == "":
        return None
    digits = re.sub(r"[^\d+]", "", value)        # keep only digits and "+"
    if digits.startswith("+"):
        if 8 <= len(digits) - 1 <= 15:
            return digits                           # already international
    else:
        digits = digits.lstrip("0")                 # "0981..." → "981..."
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]                     # "91981..." → "981..."
        if len(digits) == 10 and digits[0] in "6789":
            return "+91" + digits                   # Indian mobile number
    raise ValueError("doesn't look like a phone number (use 10 digits, e.g. 9811000000)")


def lowercase(value):
    """'WhatsApp' and ' whatsapp ' should both count as 'whatsapp'."""
    return value.strip().lower() if isinstance(value, str) else value


class Schema(BaseModel):
    """Common settings for every schema below."""

    model_config = ConfigDict(
        str_strip_whitespace=True,  # "  Priya  " → "Priya"
        from_attributes=True,       # can be built straight from a database row
        extra="forbid",             # unknown fields are rejected, not silently ignored
    )


# ---------------------------------------------------------------------------
# Businesses
# ---------------------------------------------------------------------------
class BusinessCreate(Schema):
    name: str = Field(min_length=2, max_length=150, examples=["Redox Gym"])
    industry: Industry
    city: str = Field(default="Delhi", max_length=100)
    area: Optional[str] = Field(default=None, max_length=100)
    description: str = Field(default="", max_length=2000)
    services: list[str] = Field(default_factory=list, max_length=50, examples=[["Zumba", "Aerobics"]])
    brand_voice: str = Field(default="", max_length=500, examples=["energetic, Hinglish, friendly"])
    target_audience: str = Field(default="", max_length=500)
    phone: Optional[str] = None
    website: Optional[str] = Field(default=None, max_length=200)
    google_review_link: Optional[str] = Field(default=None, max_length=300, pattern=r"^https://")

    _lower = field_validator("industry", mode="before")(lowercase)
    _phone = field_validator("phone")(clean_phone)

    @field_validator("services")
    @classmethod
    def no_blank_services(cls, services: list[str]) -> list[str]:
        """Drop empty entries and duplicates: ["Zumba", "", "Zumba"] → ["Zumba"]."""
        cleaned = []
        for s in services:
            s = s.strip()
            if s and s not in cleaned:
                cleaned.append(s)
        return cleaned


class BusinessUpdate(Schema):
    """Every field is optional: send only what you want to change."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    industry: Optional[Industry] = None
    city: Optional[str] = Field(default=None, max_length=100)
    area: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    services: Optional[list[str]] = Field(default=None, max_length=50)
    brand_voice: Optional[str] = Field(default=None, max_length=500)
    target_audience: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = None
    website: Optional[str] = Field(default=None, max_length=200)
    google_review_link: Optional[str] = Field(default=None, max_length=300, pattern=r"^https://")

    _lower = field_validator("industry", mode="before")(lowercase)
    _phone = field_validator("phone")(clean_phone)


class BusinessOut(Schema):
    id: int
    name: str
    industry: str
    city: str
    area: Optional[str]
    description: str
    services: list[str]
    brand_voice: str
    target_audience: str
    phone: Optional[str]
    website: Optional[str]
    google_review_link: Optional[str] = None
    created_at: UTCDateTime


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
class MessageCreate(Schema):
    direction: Direction = "inbound"
    text: str = Field(min_length=1, max_length=4000)
    # Replies only: actually send it through the connected WhatsApp/Instagram/Facebook?
    # False = just note down a reply you already sent from your phone.
    send: bool = True

    _lower = field_validator("direction", mode="before")(lowercase)


class MessageOut(Schema):
    id: int
    direction: str
    text: str
    sent_at: UTCDateTime
    delivery: str = ""           # replies: sent / failed / logged
    delivery_error: str = ""
    auto_reply: bool = False     # True = the AI's instant first reply (Task 29), not typed by the owner
    followup: bool = False       # True = a follow-up sent from a reminder (Task 30)


# ---------------------------------------------------------------------------
# AI analysis of a lead (only ever SENT OUT; the AI writes it, not users)
# ---------------------------------------------------------------------------
class LeadAnalysisOut(Schema):
    sentiment: str
    sentiment_reason: str
    score: int = Field(ge=1, le=100)
    score_reason: str
    score_breakdown: dict
    priority: str
    analyzed_at: UTCDateTime


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
class LeadCreate(Schema):
    business_id: int = Field(gt=0, description="Which business this enquiry is for")
    source: LeadSource
    external_id: Optional[str] = Field(default=None, max_length=100)
    campaign: Optional[str] = Field(default=None, max_length=100)

    name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = None
    handle: Optional[str] = Field(default=None, max_length=100)
    area: Optional[str] = Field(default=None, max_length=100)

    service: Optional[str] = Field(default=None, max_length=100)
    details: dict = Field(default_factory=dict, examples=[{"batch": "evening"}])
    first_message: str = Field(default="", max_length=4000)

    _lower = field_validator("source", mode="before")(lowercase)
    _phone = field_validator("phone")(clean_phone)

    @field_validator("handle")
    @classmethod
    def strip_at_sign(cls, handle: Optional[str]) -> Optional[str]:
        """'@priya.fit' → 'priya.fit' (Instagram usernames are stored without @)."""
        return handle.lstrip("@") if handle else handle

    @model_validator(mode="after")
    def must_be_reachable(self):
        """A lead nobody can contact is useless, so we need at least a name,
        phone number or social media handle."""
        if not (self.name or self.phone or self.handle):
            raise ValueError("a lead needs at least a name, phone or handle")
        return self


class IncomingMessage(LeadCreate):
    """One customer message arriving through a webhook, after the normalizer
    has translated it from WhatsApp/Instagram/website format into ours.

    It's a LeadCreate (so all the same rules apply: phone cleaning, allowed
    sources...) plus two extras: the message's own ID and when it was sent.
    """

    external_id: str = Field(min_length=1, max_length=150)           # required here
    first_message: str = Field(min_length=1, max_length=4000)        # the text they sent
    sent_at: Optional[datetime] = None


class WebhookResult(Schema):
    """The quick 'got it' reply a webhook sends back."""

    received: int = 0            # customer messages found in the delivery
    new_leads: int = 0           # brand-new enquiries
    added_to_existing: int = 0   # follow-up messages from someone already in the system
    duplicates: int = 0          # the same message delivered twice (ignored)
    ignored: int = 0             # things that weren't customer messages, or broke the rules
    ai_analysis_queued: int = 0  # leads handed to the AI workflow (runs right after this reply)
    lead_ids: list[int] = []
    notes: list[str] = []        # plain-English reasons for anything ignored


class LeadUpdate(Schema):
    """Used by the dashboard, e.g. moving a lead from 'quoted' to 'won'."""

    status: Optional[LeadStatus] = None
    job_value: Optional[int] = Field(default=None, ge=0, le=100_000_000, description="₹ earned")
    name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = None
    area: Optional[str] = Field(default=None, max_length=100)
    service: Optional[str] = Field(default=None, max_length=100)
    details: Optional[dict] = None
    post_id: Optional[int] = Field(default=None, gt=0, description="The post that brought this customer")

    _lower = field_validator("status", mode="before")(lowercase)
    _phone = field_validator("phone")(clean_phone)

    @model_validator(mode="after")
    def money_only_when_won(self):
        """You only earn money from a lead you won. So a job value sent
        together with any other status is a mistake."""
        if self.job_value is not None and self.status is not None and self.status != "won":
            raise ValueError("job_value can only be set when status is 'won'")
        return self


class LeadOut(Schema):
    """One row in the leads table on the dashboard."""

    id: int
    business_id: int
    source: str
    campaign: Optional[str]
    name: Optional[str]
    phone: Optional[str]
    handle: Optional[str]
    area: Optional[str]
    service: Optional[str]
    details: dict
    first_message: str
    status: str
    job_value: Optional[int]
    post_id: Optional[int] = None
    created_at: UTCDateTime
    first_response_at: Optional[UTCDateTime]
    analysis: Optional[LeadAnalysisOut] = None   # empty until the AI has looked at it


class LeadDetailOut(LeadOut):
    """Everything about one lead, including the whole conversation."""

    messages: list[MessageOut] = []


class LeadPage(Schema):
    """One 'page' of leads, plus how many there are in total
    (so the dashboard can show 'Showing 1-50 of 300')."""

    items: list[LeadOut]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# AI runs and growth reports (only ever SENT OUT)
# ---------------------------------------------------------------------------
class AgentRunOut(Schema):
    id: int
    business_id: int
    workflow: str
    lead_id: Optional[int]
    status: str
    steps: list
    ai_mode: str
    error: Optional[str]
    started_at: UTCDateTime
    finished_at: Optional[UTCDateTime]


class GrowthReportOut(Schema):
    id: int
    business_id: int
    week_start: date
    agent_run_id: Optional[int]
    summary: str
    stats: dict
    weak_platforms: list
    presence_audit: list
    top_actions: list
    content_plan: list
    created_at: UTCDateTime


# ---------------------------------------------------------------------------
# Social media: accounts and posts
# ---------------------------------------------------------------------------
# How long a caption may be on each platform (the platforms' own limits)
CAPTION_LIMITS = {"instagram": 2200, "facebook": 63206, "google": 1500, "youtube": 5000, "linkedin": 3000}
MAX_HASHTAGS = {"instagram": 30}


class SocialAccountCreate(Schema):
    business_id: int = Field(gt=0)
    platform: SocialPlatform
    handle: str = Field(min_length=1, max_length=100, examples=["ironpulsefitness"])
    display_name: str = Field(default="", max_length=150)
    followers: int = Field(default=0, ge=0)
    external_id: Optional[str] = Field(default=None, max_length=100)

    _lower = field_validator("platform", mode="before")(lowercase)

    @field_validator("handle")
    @classmethod
    def clean_handle(cls, handle: str) -> str:
        return handle.lstrip("@").strip()


class SocialAccountUpdate(Schema):
    handle: Optional[str] = Field(default=None, min_length=1, max_length=100)
    display_name: Optional[str] = Field(default=None, max_length=150)
    followers: Optional[int] = Field(default=None, ge=0)
    external_id: Optional[str] = Field(default=None, max_length=100)


class SocialAccountOut(Schema):
    id: int
    business_id: int
    platform: str
    handle: str
    display_name: str
    followers: int
    connected: bool
    created_at: UTCDateTime


def _clean_hashtags(tags: Optional[list[str]]) -> Optional[list[str]]:
    """'#Gym', 'gym', ' #gym ' → 'gym' once. Stored without the # sign."""
    if tags is None:
        return None
    cleaned: list[str] = []
    for tag in tags:
        tag = tag.strip().lstrip("#").replace(" ", "")
        if tag and tag.lower() not in [t.lower() for t in cleaned]:
            cleaned.append(tag)
    return cleaned


class PostCreate(Schema):
    account_id: int = Field(gt=0, description="Which social account this post is for")
    kind: PostKind = "photo"
    pillar: Pillar = "tips"
    title: str = Field(default="", max_length=150)
    caption: str = Field(default="", max_length=63206)
    hashtags: list[str] = Field(default_factory=list, max_length=60)
    script: str = Field(default="", max_length=5000)
    media_note: str = Field(default="", max_length=2000)
    media_url: str = Field(default="", max_length=500, pattern=r"^(https://\S+)?$", description="Public https link to the photo (JPEG) or video")
    media_id: Optional[int] = Field(default=None, gt=0, description="A photo/video from the media library (POST /media)")
    status: Literal["idea", "draft", "scheduled"] = "draft"   # "published" is set by publishing, not by hand
    scheduled_for: Optional[datetime] = None
    campaign: Optional[str] = Field(default=None, max_length=100)
    created_by: Literal["ai", "owner"] = "owner"

    _tags = field_validator("hashtags")(_clean_hashtags)

    @model_validator(mode="after")
    def schedule_needs_a_time(self):
        if self.status == "scheduled" and self.scheduled_for is None:
            raise ValueError("a scheduled post needs scheduled_for (when to publish it)")
        return self


class PostUpdate(Schema):
    kind: Optional[PostKind] = None
    pillar: Optional[Pillar] = None
    title: Optional[str] = Field(default=None, max_length=150)
    caption: Optional[str] = Field(default=None, max_length=63206)
    hashtags: Optional[list[str]] = Field(default=None, max_length=60)
    script: Optional[str] = Field(default=None, max_length=5000)
    media_note: Optional[str] = Field(default=None, max_length=2000)
    media_url: Optional[str] = Field(default=None, max_length=500, pattern=r"^(https://\S+)?$")
    media_id: Optional[int] = Field(default=None, gt=0, description="From the media library; send null to remove")
    status: Optional[PostStatus] = None
    scheduled_for: Optional[datetime] = None

    _tags = field_validator("hashtags")(_clean_hashtags)


class PostStatsUpdate(Schema):
    """New numbers for a published post (from the platform, or typed in by hand)."""

    reach: Optional[int] = Field(default=None, ge=0)
    likes: Optional[int] = Field(default=None, ge=0)
    comments: Optional[int] = Field(default=None, ge=0)
    shares: Optional[int] = Field(default=None, ge=0)
    saves: Optional[int] = Field(default=None, ge=0)
    profile_visits: Optional[int] = Field(default=None, ge=0)
    link_clicks: Optional[int] = Field(default=None, ge=0)


class PostOut(Schema):
    id: int
    business_id: int
    account_id: int
    platform: str
    kind: str
    pillar: str
    title: str
    caption: str
    hashtags: list[str]
    script: str
    media_note: str
    media_url: str
    media_id: Optional[int] = None
    campaign: Optional[str]
    status: str
    created_by: str
    ai_reason: str = ""
    scheduled_for: Optional[UTCDateTime]
    published_at: Optional[UTCDateTime]
    publish_error: str = ""
    reach: int
    likes: int
    comments: int
    shares: int
    saves: int
    profile_visits: int
    link_clicks: int
    created_at: UTCDateTime
    # Worked out from the numbers above and the linked leads:
    engagement_rate: float = 0.0      # (likes + comments + shares + saves) / reach, in %
    enquiries: int = 0                # leads that came from this post
    sales: int = 0                    # ... of which were won
    revenue: int = 0                  # ₹ from those sales


# ---------------------------------------------------------------------------
# Reputation: reviews and review requests
# ---------------------------------------------------------------------------
class ReviewCreate(Schema):
    """A review typed in by hand, or imported from a platform."""

    business_id: int = Field(gt=0)
    platform: ReviewPlatform = "google"
    external_id: Optional[str] = Field(default=None, max_length=150, description="Platform's ID (stops duplicates)")
    author_name: str = Field(default="", max_length=100)
    rating: int = Field(ge=1, le=5)
    text: str = Field(default="", max_length=5000)
    reviewed_at: Optional[datetime] = None

    _lower = field_validator("platform", mode="before")(lowercase)


class ReviewOut(Schema):
    id: int
    business_id: int
    platform: str
    author_name: str
    rating: int
    text: str
    reviewed_at: UTCDateTime
    lead_id: Optional[int]
    sentiment: str
    topics: list[str]
    needs_attention: bool
    reply_text: str
    reply_status: str
    replied_at: Optional[UTCDateTime]


class ReplyApprove(Schema):
    """Post the reply. Leave text empty to post the AI's draft as it is."""

    text: Optional[str] = Field(default=None, min_length=2, max_length=4000)


class ReviewRequestOut(Schema):
    id: int
    business_id: int
    lead_id: int
    phone: str
    message: str
    status: str
    send_after: UTCDateTime
    sent_at: Optional[UTCDateTime]


# ---------------------------------------------------------------------------
# Accounts: sign up, log in, team
# ---------------------------------------------------------------------------
EMAIL = r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$"


def _lower_email(value):
    return value.strip().lower() if isinstance(value, str) else value


class SignupIn(Schema):
    """A new business joins: creates the business AND the owner's account."""

    name: str = Field(min_length=2, max_length=100, examples=["Anmol"])
    email: str = Field(pattern=EMAIL, max_length=200, examples=["owner@redoxgym.in"])
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(min_length=2, max_length=150, examples=["Redox Gym"])
    industry: Industry
    city: str = Field(default="Delhi", max_length=100)
    area: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = None

    _email = field_validator("email", mode="before")(_lower_email)
    _industry = field_validator("industry", mode="before")(lowercase)
    _phone = field_validator("phone")(clean_phone)


class LoginIn(Schema):
    email: str = Field(max_length=200, examples=["gym@demo.in"])
    password: str = Field(max_length=128, examples=["demo1234"])

    _email = field_validator("email", mode="before")(_lower_email)


class UserOut(Schema):
    id: int
    email: str
    name: str
    role: str
    business_id: Optional[int]
    is_active: bool
    last_login_at: Optional[UTCDateTime]


class AuthOut(Schema):
    token: str                     # send as "Authorization: Bearer <token>"
    expires_at: UTCDateTime
    user: UserOut
    business: Optional[BusinessOut]


class ChangePasswordIn(Schema):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class StaffInvite(Schema):
    """The owner adds a staff member. They get an email to choose their own password
    (or the owner can set a starting password here)."""

    name: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=EMAIL, max_length=200)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

    _email = field_validator("email", mode="before")(_lower_email)


class ForgotPasswordIn(Schema):
    email: str = Field(max_length=200)

    _email = field_validator("email", mode="before")(_lower_email)


class ResetPasswordIn(Schema):
    token: str = Field(min_length=20, max_length=200, description="From the link in the email")
    new_password: str = Field(min_length=8, max_length=128)

