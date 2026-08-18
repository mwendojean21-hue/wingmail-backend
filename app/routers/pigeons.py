from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/pigeons", tags=["pigeons"])


@router.get("/bird-types", response_model=List[schemas.BirdTypeOut])
def list_bird_types(db: Session = Depends(get_db)):
    return db.query(models.BirdType).order_by(models.BirdType.base_speed_mph).all()


@router.post("", response_model=schemas.PigeonOut)
def create_pigeon(payload: schemas.PigeonCreate,
                   current_user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    bird_type = db.query(models.BirdType).get(payload.bird_type_id)
    if not bird_type:
        raise HTTPException(status_code=404, detail="Espèce d'oiseau introuvable")

    if bird_type.unlock_cost_feathers > 0:
        if current_user.feathers_balance < bird_type.unlock_cost_feathers:
            raise HTTPException(
                status_code=402,
                detail=f"Il te faut {bird_type.unlock_cost_feathers} plumes pour débloquer {bird_type.display_name}"
            )
        current_user.feathers_balance -= bird_type.unlock_cost_feathers

    pigeon = models.Pigeon(
        owner_id=current_user.id,
        bird_type_id=bird_type.id,
        name=payload.name,
        color=payload.color or "#e8e2d6",
        accessory=payload.accessory,
    )
    db.add(pigeon)
    db.commit()
    db.refresh(pigeon)
    return pigeon


@router.get("/mine", response_model=List[schemas.PigeonOut])
def my_pigeons(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Pigeon).filter(models.Pigeon.owner_id == current_user.id).all()


@router.post("/{pigeon_id}/upgrade", response_model=schemas.PigeonOut)
def upgrade_pigeon(pigeon_id: str, payload: schemas.PigeonUpgrade,
                    current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    pigeon = db.query(models.Pigeon).filter(
        models.Pigeon.id == pigeon_id, models.Pigeon.owner_id == current_user.id
    ).first()
    if not pigeon:
        raise HTTPException(status_code=404, detail="Pigeon introuvable")

    new_type = db.query(models.BirdType).get(payload.bird_type_id)
    if not new_type:
        raise HTTPException(status_code=404, detail="Espèce d'oiseau introuvable")

    if new_type.unlock_cost_feathers > 0:
        if current_user.feathers_balance < new_type.unlock_cost_feathers:
            raise HTTPException(
                status_code=402,
                detail=f"Il te faut {new_type.unlock_cost_feathers} plumes pour débloquer {new_type.display_name}"
            )
        current_user.feathers_balance -= new_type.unlock_cost_feathers

    pigeon.bird_type_id = new_type.id
    db.commit()
    db.refresh(pigeon)
    return pigeon


@router.post("/{pigeon_id}/boost-energy", response_model=schemas.PigeonOut)
def boost_energy(pigeon_id: str, feathers: int,
                  current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Recharge la jauge d'energie d'un pigeon avec des plumes (1 plume = 1 point d'energie)."""
    pigeon = db.query(models.Pigeon).filter(
        models.Pigeon.id == pigeon_id, models.Pigeon.owner_id == current_user.id
    ).first()
    if not pigeon:
        raise HTTPException(status_code=404, detail="Pigeon introuvable")
    if feathers <= 0:
        raise HTTPException(status_code=400, detail="Le nombre de plumes doit être positif")
    if pigeon.energy >= 100:
        raise HTTPException(status_code=400, detail="Ce pigeon est déjà à pleine énergie")
    if current_user.feathers_balance < feathers:
        raise HTTPException(status_code=402, detail="Tu n'as pas assez de plumes")

    current_user.feathers_balance -= feathers
    pigeon.energy = min(100.0, pigeon.energy + feathers)
    db.commit()
    db.refresh(pigeon)
    return pigeon


@router.delete("/{pigeon_id}")
def release_pigeon(pigeon_id: str, current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    pigeon = db.query(models.Pigeon).filter(
        models.Pigeon.id == pigeon_id, models.Pigeon.owner_id == current_user.id
    ).first()
    if not pigeon:
        raise HTTPException(status_code=404, detail="Pigeon introuvable")
    if pigeon.status.value == "in_flight":
        raise HTTPException(status_code=400, detail="Ce pigeon est en plein vol, tu ne peux pas le relâcher maintenant")
    db.delete(pigeon)
    db.commit()
    return {"ok": True}
