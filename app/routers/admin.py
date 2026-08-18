from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=schemas.AdminStatsOut)
def stats(db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    return schemas.AdminStatsOut(
        total_users=db.query(func.count(models.User.id)).scalar() or 0,
        total_pigeons=db.query(func.count(models.Pigeon.id)).scalar() or 0,
        total_messages=db.query(func.count(models.Message.id)).scalar() or 0,
        messages_in_flight=db.query(func.count(models.Message.id)).filter(
            models.Message.status == models.MessageStatus.in_flight
        ).scalar() or 0,
        messages_delivered=db.query(func.count(models.Message.id)).filter(
            models.Message.status == models.MessageStatus.delivered
        ).scalar() or 0,
        messages_lost=db.query(func.count(models.Message.id)).filter(
            models.Message.status == models.MessageStatus.lost
        ).scalar() or 0,
        messages_captured=db.query(func.count(models.Message.id)).filter(
            models.Message.status == models.MessageStatus.captured
        ).scalar() or 0,
        total_feathers_in_circulation=db.query(func.sum(models.User.feathers_balance)).scalar() or 0,
        signups_last_7_days=db.query(func.count(models.User.id)).filter(
            models.User.created_at >= seven_days_ago
        ).scalar() or 0,
    )


def _enrich_user(db: Session, user: models.User) -> schemas.AdminUserOut:
    pigeon_count = db.query(func.count(models.Pigeon.id)).filter(
        models.Pigeon.owner_id == user.id
    ).scalar() or 0
    message_count = db.query(func.count(models.Message.id)).filter(
        models.Message.sender_id == user.id
    ).scalar() or 0
    return schemas.AdminUserOut(
        id=user.id, username=user.username, display_name=user.display_name, email=user.email,
        feathers_balance=user.feathers_balance, is_admin=user.is_admin,
        referral_count=user.referral_count, ip_country=user.ip_country, ip_region=user.ip_region,
        pigeon_count=pigeon_count, message_count=message_count, created_at=user.created_at,
    )


@router.get("/users", response_model=List[schemas.AdminUserOut])
def list_users(db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).limit(500).all()
    return [_enrich_user(db, u) for u in users]


@router.get("/users-map", response_model=List[schemas.AdminUserMapPoint])
def users_map(db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    users = db.query(models.User).filter(
        models.User.ip_lat.isnot(None), models.User.ip_lng.isnot(None)
    ).all()
    return [
        schemas.AdminUserMapPoint(
            user_id=u.id, username=u.username, lat=u.ip_lat, lng=u.ip_lng, country=u.ip_country
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=schemas.AdminUserDetailOut)
def user_detail(user_id: str, db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    base = _enrich_user(db, user)
    pigeons = db.query(models.Pigeon).filter(models.Pigeon.owner_id == user_id).all()
    pigeon_list = [
        schemas.AdminPigeonOut(
            id=p.id, name=p.name, status=p.status.value,
            bird_type_display_name=p.bird_type.display_name,
            total_deliveries=p.total_deliveries, total_losses=p.total_losses,
        )
        for p in pigeons
    ]

    return schemas.AdminUserDetailOut(
        **base.model_dump(), ip_lat=user.ip_lat, ip_lng=user.ip_lng, pigeons=pigeon_list,
    )


@router.post("/users/{user_id}/feathers", response_model=schemas.AdminUserOut)
def adjust_feathers(user_id: str, payload: schemas.FeathersAdjust,
                     db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.feathers_balance = max(0, user.feathers_balance + payload.delta)
    db.commit()
    db.refresh(user)
    return _enrich_user(db, user)


@router.post("/users/{user_id}/pigeons", response_model=schemas.AdminPigeonOut)
def grant_pigeon(user_id: str, payload: schemas.AdminPigeonGrant,
                  db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    bird_type = db.query(models.BirdType).get(payload.bird_type_id)
    if not bird_type:
        raise HTTPException(status_code=404, detail="Espèce d'oiseau introuvable")

    pigeon = models.Pigeon(owner_id=user.id, bird_type_id=bird_type.id, name=payload.name)
    db.add(pigeon)
    db.commit()
    db.refresh(pigeon)
    return schemas.AdminPigeonOut(
        id=pigeon.id, name=pigeon.name, status=pigeon.status.value,
        bird_type_display_name=bird_type.display_name,
        total_deliveries=0, total_losses=0,
    )


@router.delete("/users/{user_id}/pigeons/{pigeon_id}")
def remove_pigeon(user_id: str, pigeon_id: str,
                   db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    pigeon = db.query(models.Pigeon).filter(
        models.Pigeon.id == pigeon_id, models.Pigeon.owner_id == user_id
    ).first()
    if not pigeon:
        raise HTTPException(status_code=404, detail="Pigeon introuvable")
    db.delete(pigeon)
    db.commit()
    return {"ok": True}


@router.get("/feedback", response_model=List[schemas.FeedbackAdminOut])
def list_feedback(db: Session = Depends(get_db), _admin: models.User = Depends(get_current_admin)):
    rows = db.query(models.Feedback).order_by(models.Feedback.created_at.desc()).limit(300).all()
    out = []
    for fb in rows:
        user = db.query(models.User).get(fb.user_id)
        out.append(schemas.FeedbackAdminOut(
            id=fb.id, user_id=fb.user_id, category=fb.category.value, content=fb.content,
            status=fb.status.value, created_at=fb.created_at,
            username=user.username if user else "inconnu",
        ))
    return out


@router.patch("/feedback/{feedback_id}", response_model=schemas.FeedbackOut)
def update_feedback_status(feedback_id: str, payload: schemas.FeedbackStatusUpdate,
                            db: Session = Depends(get_db),
                            _admin: models.User = Depends(get_current_admin)):
    fb = db.query(models.Feedback).get(feedback_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Avis introuvable")
    fb.status = models.FeedbackStatus(payload.status)
    db.commit()
    db.refresh(fb)
    return fb
