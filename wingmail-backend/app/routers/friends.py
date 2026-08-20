from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/friends", tags=["friends"])


@router.post("/request", response_model=schemas.FriendshipOut)
def request_friend(payload: schemas.FriendRequestCreate,
                    current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    addressee = db.query(models.User).filter(models.User.username == payload.addressee_username).first()
    if not addressee:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if addressee.id == current_user.id:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'ajouter toi-même")

    existing = db.query(models.Friendship).filter(
        models.Friendship.requester_id == current_user.id,
        models.Friendship.addressee_id == addressee.id,
    ).first()
    if existing:
        return existing

    friendship = models.Friendship(requester_id=current_user.id, addressee_id=addressee.id)
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    return friendship


@router.post("/{friendship_id}/accept", response_model=schemas.FriendshipOut)
def accept_friend(friendship_id: str, current_user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    friendship = db.query(models.Friendship).filter(
        models.Friendship.id == friendship_id, models.Friendship.addressee_id == current_user.id
    ).first()
    if not friendship:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    friendship.status = models.FriendshipStatus.accepted
    db.commit()
    db.refresh(friendship)
    return friendship


@router.get("/mine", response_model=List[schemas.FriendshipOut])
def my_friendships(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Friendship).filter(
        (models.Friendship.requester_id == current_user.id)
        | (models.Friendship.addressee_id == current_user.id)
    ).all()
