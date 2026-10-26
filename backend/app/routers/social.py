"""
Social media endpoints - accounts and posts.

    GET    /social/accounts?business_id=1     a business's social profiles
    POST   /social/accounts                   add a profile (e.g. their Instagram)
    PATCH  /social/accounts/{id}              change it (e.g. new follower count)

    GET    /posts?business_id=1&...           posts, newest first, with leads + ₹ per post
    POST   /posts                             create an idea / draft / scheduled post
    GET    /posts/{id}                        one post
    PATCH  /posts/{id}                        edit it, or change its status
    POST   /posts/{id}/stats                  save new numbers (reach, likes...) for a published post
    DELETE /posts/{id}                        delete an idea/draft/scheduled post
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.access import can_access
from app.routers.businesses import business_or_404
from app.services import billing_service
from app.schemas import (
    Pillar, PostCreate, PostKind, PostOut, PostStatsUpdate, PostStatus, PostUpdate,
    SocialAccountCreate, SocialAccountOut, SocialAccountUpdate, SocialPlatform,
)
from app.services import social_service as social

router = APIRouter(tags=["Social media"])


def _rule_broken(problem: ValueError):
    return HTTPException(status_code=400, detail=str(problem))


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def account_or_404(account_id: int, db: Session):
    account = social.get_account(db, account_id)
    if account is None or not can_access(account.business_id):
        raise HTTPException(status_code=404, detail=f"Social account {account_id} not found")
    return account


@router.get("/social/accounts", response_model=list[SocialAccountOut])
def list_accounts(business_id: int, db: Session = Depends(get_db)):
    business_or_404(business_id, db)
    return social.list_accounts(db, business_id)


@router.post("/social/accounts", response_model=SocialAccountOut, status_code=status.HTTP_201_CREATED)
def create_account(data: SocialAccountCreate, db: Session = Depends(get_db)):
    business_or_404(data.business_id, db)
    try:
        billing_service.check_room(db, data.business_id, "social_accounts")    # plan limit
    except billing_service.PlanLimit as problem:
        raise HTTPException(status_code=403, detail=str(problem))
    try:
        return social.create_account(db, data)
    except ValueError as problem:
        raise _rule_broken(problem)


@router.patch("/social/accounts/{account_id}", response_model=SocialAccountOut)
def update_account(account_id: int, data: SocialAccountUpdate, db: Session = Depends(get_db)):
    return social.update_account(db, account_or_404(account_id, db), data)


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
class PostPage(BaseModel):
    items: list[PostOut]
    total: int
    limit: int
    offset: int


def post_or_404(post_id: int, db: Session):
    post = social.get_post(db, post_id)
    if post is None or not can_access(post.business_id):
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    return post


@router.get("/posts", response_model=PostPage)
def list_posts(
    business_id: int,
    platform: Optional[SocialPlatform] = None,
    status: Optional[PostStatus] = None,
    pillar: Optional[Pillar] = None,
    kind: Optional[PostKind] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    business_or_404(business_id, db)
    posts, total = social.list_posts(db, business_id, platform, status, pillar, kind, limit, offset)
    return PostPage(items=social.posts_out(db, posts), total=total, limit=limit, offset=offset)


@router.post("/posts", response_model=PostOut, status_code=201)
def create_post(data: PostCreate, db: Session = Depends(get_db)):
    account = account_or_404(data.account_id, db)
    try:
        post = social.create_post(db, account, data)
    except ValueError as problem:
        raise _rule_broken(problem)
    return social.to_out(post)


@router.get("/posts/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    return social.posts_out(db, [post_or_404(post_id, db)])[0]


@router.patch("/posts/{post_id}", response_model=PostOut)
def update_post(post_id: int, data: PostUpdate, db: Session = Depends(get_db)):
    post = post_or_404(post_id, db)
    try:
        social.update_post(db, post, data)
    except ValueError as problem:
        raise _rule_broken(problem)
    return social.posts_out(db, [post])[0]


@router.post("/posts/{post_id}/stats", response_model=PostOut)
def update_stats(post_id: int, data: PostStatsUpdate, db: Session = Depends(get_db)):
    post = post_or_404(post_id, db)
    try:
        social.update_stats(db, post, data)
    except ValueError as problem:
        raise _rule_broken(problem)
    return social.posts_out(db, [post])[0]


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db)):
    try:
        social.delete_post(db, post_or_404(post_id, db))
    except ValueError as problem:
        raise _rule_broken(problem)
    return Response(status_code=204)
