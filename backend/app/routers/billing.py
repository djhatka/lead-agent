"""
Subscription and payment endpoints.

    GET  /billing/plans          the price list (open to everyone: the pricing page)
    GET  /billing/status         my plan, trial days left, limits used, what to show
    POST /billing/subscribe      owner picks a plan → details to open Razorpay checkout
    POST /billing/verify         the browser passes back what Razorpay gave it → plan active
    POST /billing/mock-pay       MOCK MODE ONLY: pretend the owner paid
    POST /billing/cancel         stop renewing (works until the paid days run out)
    GET  /billing/payments       payment history
    GET  /admin/billing          (admin) how much the website earns
    POST /webhooks/razorpay      Razorpay's doorbell: renewals / failures / cancellations

Billing is reachable even when the plan has ended: that's how they pay again.
"""

import json
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.access import get_current_user, require_admin, require_owner
from app.config import settings
from app.database import get_db
from app.models import User
from app.plans import PLAN_CODES, PLANS, TRIAL_PLAN
from app.routers.businesses import business_or_404
from app.schemas import UTCDateTime
from app.services import billing_service as billing
from app.services import email_service
from app.services import payment_gateway as gw

public = APIRouter(tags=["Billing"])
router = APIRouter(tags=["Billing"])


def _business_id(user: User, business_id: Optional[int], db: Session) -> int:
    """Owners and staff: their own business. The admin must say which (?business_id=)."""
    if user.role == "admin":
        if not business_id:
            raise HTTPException(status_code=400, detail="Admin: add ?business_id=")
        return business_or_404(business_id, db).id
    return user.business_id


def _try(action, *args):
    try:
        return action(*args)
    except billing.BillingError as problem:
        raise HTTPException(status_code=400, detail=str(problem))


# ---------------------------------------------------------------------------
# Open to everyone
# ---------------------------------------------------------------------------
class PlanOut(BaseModel):
    code: str
    name: str
    price: int
    tagline: str
    staff_seats: int
    social_accounts: int
    storage_mb: int
    weekly_review: bool
    review_requests: bool
    highlights: list[str]
    free_trial_days: int


@public.get("/billing/plans", response_model=list[PlanOut])
def plans():
    return [PlanOut(**{**p.__dict__, "highlights": list(p.highlights)},
                    free_trial_days=settings.trial_days if p.code == TRIAL_PLAN else 0) for p in PLANS.values()]


@public.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, background: BackgroundTasks, x_razorpay_signature: str = Header(default=""),
                           db: Session = Depends(get_db)):
    """Razorpay calls this by itself. We check its signature on the exact raw
    bytes it sent; anything unsigned or wrongly signed is refused."""
    raw = await request.body()
    if not gw.webhook_signature_ok(raw, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Bad signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    note = billing.handle_webhook(db, event)
    background.add_task(email_service.deliver_in_background)        # receipt / "payment failed" email
    return {"ok": True, "note": note}


# ---------------------------------------------------------------------------
# Logged in (but no paywall: this is where they pay)
# ---------------------------------------------------------------------------
class BillingStatus(billing.Access):
    limits: dict[str, int | bool]
    used: dict[str, int]
    payments_mode: str            # "mock" or "real"


@router.get("/billing/status", response_model=BillingStatus)
def status(business_id: Optional[int] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bid = _business_id(user, business_id, db)
    info = billing.access(db, bid)
    plan = PLANS[info.plan]
    return BillingStatus(**info.model_dump(), payments_mode="real" if settings.payments_enabled else "mock",
                         used=billing.usage(db, bid),
                         limits={"staff_seats": plan.staff_seats, "social_accounts": plan.social_accounts,
                                 "storage_mb": plan.storage_mb,
                                 "weekly_review": plan.weekly_review, "review_requests": plan.review_requests})


class SubscribeIn(BaseModel):
    plan: Literal[PLAN_CODES]  # type: ignore[valid-type]


@router.post("/billing/subscribe", response_model=billing.Checkout)
def subscribe(body: SubscribeIn, business_id: Optional[int] = None, owner: User = Depends(require_owner),
              db: Session = Depends(get_db)):
    """Step 1 of paying. The website then opens Razorpay checkout with
    `key_id` + `subscription_id` (in mock mode: call /billing/mock-pay instead)."""
    return _try(billing.start_checkout, db, _business_id(owner, business_id, db), body.plan)


class VerifyIn(BaseModel):
    razorpay_payment_id: str = Field(max_length=60)
    razorpay_subscription_id: str = Field(max_length=60)
    razorpay_signature: str = Field(max_length=128)


@router.post("/billing/verify", response_model=billing.Access)
def verify(body: VerifyIn, background: BackgroundTasks, business_id: Optional[int] = None,
           owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Step 2: pass back the three values Razorpay's checkout gave the browser."""
    result = _try(billing.confirm_payment, db, _business_id(owner, business_id, db),
                  body.razorpay_payment_id, body.razorpay_subscription_id, body.razorpay_signature)
    background.add_task(email_service.deliver_in_background)        # the receipt
    return result


@router.post("/billing/mock-pay", response_model=billing.Access)
def mock_pay(background: BackgroundTasks, business_id: Optional[int] = None, owner: User = Depends(require_owner),
             db: Session = Depends(get_db)):
    """Free mock mode only: acts as if the owner paid in the Razorpay window."""
    result = _try(billing.mock_pay, db, _business_id(owner, business_id, db))
    background.add_task(email_service.deliver_in_background)
    return result


@router.post("/billing/cancel", response_model=billing.Access)
def cancel(business_id: Optional[int] = None, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    return _try(billing.cancel, db, _business_id(owner, business_id, db))


class PaymentOut(BaseModel):
    id: int
    plan: str
    amount: int
    status: str
    gateway_payment_id: str
    paid_at: UTCDateTime

    model_config = {"from_attributes": True}


@router.get("/billing/payments", response_model=list[PaymentOut])
def payment_history(business_id: Optional[int] = None, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return billing.payments(db, _business_id(user, business_id, db))


@router.get("/admin/billing", response_model=billing.PlatformBilling)
def admin_billing(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Your money dashboard: monthly recurring revenue, trials, payment problems."""
    return billing.platform_overview(db)
