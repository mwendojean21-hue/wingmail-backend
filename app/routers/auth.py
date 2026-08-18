from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import hash_password, verify_password, create_access_token, get_current_user
from ..config import settings
from ..geo import get_client_ip, lookup_ip_geo

router = APIRouter(prefix="/auth", tags=["auth"])

REFERRAL_FEATHERS_PER_STEP = 10
SHARE_FEATHERS_PER_STEP = 5
GITHUB_STAR_FEATHERS = 30


@router.post("/register", response_model=schemas.TokenOut)
def register(payload: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        (models.User.username == payload.username) | (models.User.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur ou email déjà utilisé")

    referrer = None
    if payload.referral_code:
        referrer = db.query(models.User).filter(
            models.User.referral_code == payload.referral_code
        ).first()
        # Un code de parrainage invalide n'empêche pas l'inscription, on l'ignore simplement.

    user = models.User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        is_admin=payload.username in settings.admin_usernames_list,
        referred_by_id=referrer.id if referrer else None,
    )

    client_ip = get_client_ip(request)
    if client_ip:
        user.last_ip = client_ip
        geo = lookup_ip_geo(client_ip)
        if geo:
            user.ip_country = geo["country"]
            user.ip_region = geo["region"]
            user.ip_lat = geo["lat"]
            user.ip_lng = geo["lng"]

    db.add(user)
    db.flush()  # pour obtenir user.id avant de committer

    if referrer:
        referrer.referral_count += 1
        referrer.feathers_balance += REFERRAL_FEATHERS_PER_STEP * referrer.referral_count
        db.add(models.Friendship(
            requester_id=referrer.id,
            addressee_id=user.id,
            status=models.FriendshipStatus.accepted,
        ))

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return schemas.TokenOut(access_token=token, user=user)


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Nom d'utilisateur ou mot de passe incorrect")

    # Promotion admin retroactive si le compte existait avant l'ajout de cette regle
    should_be_admin = payload.username in settings.admin_usernames_list
    if should_be_admin and not user.is_admin:
        user.is_admin = True

    # Re-geolocalise seulement si l'IP a change, pour rester dans les limites du service gratuit
    client_ip = get_client_ip(request)
    if client_ip and client_ip != user.last_ip:
        user.last_ip = client_ip
        geo = lookup_ip_geo(client_ip)
        if geo:
            user.ip_country = geo["country"]
            user.ip_region = geo["region"]
            user.ip_lat = geo["lat"]
            user.ip_lng = geo["lng"]

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return schemas.TokenOut(access_token=token, user=user)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserOut)
def update_me(payload: schemas.UserUpdate,
              current_user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if payload.display_name is not None:
        current_user.display_name = payload.display_name
    if payload.avatar_key is not None:
        current_user.avatar_key = payload.avatar_key
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/password")
def change_password(payload: schemas.PasswordChange,
                     current_user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


@router.post("/me/location", response_model=schemas.UserOut)
def update_location(payload: schemas.LocationUpdate,
                     current_user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    current_user.last_lat = payload.lat
    current_user.last_lng = payload.lng
    current_user.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return current_user
