from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user, get_current_admin

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=schemas.FeedbackOut)
def submit_feedback(payload: schemas.FeedbackCreate,
                     current_user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    fb = models.Feedback(
        user_id=current_user.id,
        category=models.FeedbackCategory(payload.category),
        content=payload.content,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


@router.get("/mine", response_model=List[schemas.FeedbackOut])
def my_feedback(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Feedback).filter(
        models.Feedback.user_id == current_user.id
    ).order_by(models.Feedback.created_at.desc()).all()
