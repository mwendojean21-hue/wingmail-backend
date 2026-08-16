from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, pigeon_logic
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


def _sync_message(db: Session, message: models.Message) -> models.Message:
    """Met à jour le statut du message (et du pigeon associé) en fonction du temps écoulé."""
    if message.status == models.MessageStatus.in_flight:
        new_status = pigeon_logic.resolve_status(
            message.departure_time, message.eta, message.will_be_lost, message.lost_at_fraction
        )
        if new_status != "in_flight":
            message.status = models.MessageStatus(new_status)
            if new_status == "delivered":
                message.delivered_at = message.eta
            pigeon = db.query(models.Pigeon).get(message.pigeon_id)
            if pigeon:
                if new_status == "delivered":
                    pigeon.status = models.PigeonStatus.idle
                    pigeon.total_deliveries += 1
                elif new_status == "lost":
                    pigeon.status = models.PigeonStatus.lost
                    pigeon.total_losses += 1
            db.commit()
            db.refresh(message)
    return message


@router.post("", response_model=schemas.MessageOut)
def send_message(payload: schemas.MessageCreate,
                  current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    pigeon = db.query(models.Pigeon).filter(
        models.Pigeon.id == payload.pigeon_id, models.Pigeon.owner_id == current_user.id
    ).first()
    if not pigeon:
        raise HTTPException(status_code=404, detail="Pigeon introuvable")
    if pigeon.status != models.PigeonStatus.idle:
        raise HTTPException(status_code=400, detail="Ce pigeon n'est pas disponible (déjà en vol, perdu, ou capturé)")

    if current_user.last_lat is None or current_user.last_lng is None:
        raise HTTPException(status_code=400, detail="Active ta position avant d'envoyer un message")

    recipient = None
    dest_lat, dest_lng = payload.dest_lat, payload.dest_lng

    if payload.recipient_username and not payload.is_open_release:
        recipient = db.query(models.User).filter(models.User.username == payload.recipient_username).first()
        if not recipient:
            raise HTTPException(status_code=404, detail="Destinataire introuvable")
        if recipient.last_lat is None or recipient.last_lng is None:
            raise HTTPException(status_code=400, detail="Le destinataire n'a pas encore de position connue")
        dest_lat, dest_lng = recipient.last_lat, recipient.last_lng
    elif payload.recipient_id and not payload.is_open_release:
        recipient = db.query(models.User).get(payload.recipient_id)
        if not recipient:
            raise HTTPException(status_code=404, detail="Destinataire introuvable")
        dest_lat, dest_lng = recipient.last_lat, recipient.last_lng
    elif payload.is_open_release:
        # message lâché dans la nature : direction aléatoire, capturable par n'importe qui
        import random
        angle = random.uniform(0, 360)
        distance_deg = random.uniform(0.5, 3.0)  # ~ portée du lâcher
        import math
        dest_lat = current_user.last_lat + distance_deg * math.cos(math.radians(angle))
        dest_lng = current_user.last_lng + distance_deg * math.sin(math.radians(angle))
    else:
        raise HTTPException(status_code=400, detail="Précise un destinataire ou choisis un lâcher anonyme")

    plan = pigeon_logic.compute_flight_plan(
        current_user.last_lat, current_user.last_lng,
        dest_lat, dest_lng,
        pigeon.bird_type.base_speed_mph,
        pigeon.bird_type.loss_risk_multiplier,
    )

    message = models.Message(
        sender_id=None if payload.is_anonymous else current_user.id,
        recipient_id=recipient.id if recipient else None,
        pigeon_id=pigeon.id,
        content=payload.content,
        is_anonymous=payload.is_anonymous,
        is_open_release=payload.is_open_release,
        origin_lat=current_user.last_lat,
        origin_lng=current_user.last_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        distance_miles=plan["distance_miles"],
        effective_speed_mph=plan["effective_speed_mph"],
        will_be_lost=plan["will_be_lost"],
        lost_at_fraction=plan["lost_at_fraction"],
        departure_time=plan["departure_time"],
        eta=plan["eta"],
        status=models.MessageStatus.in_flight,
    )
    pigeon.status = models.PigeonStatus.in_flight

    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/inbox", response_model=List[schemas.MessageOut])
def inbox(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    messages = db.query(models.Message).filter(models.Message.recipient_id == current_user.id).all()
    out = []
    for m in messages:
        m = _sync_message(db, m)
        if m.status != models.MessageStatus.delivered:
            m.content = None  # le contenu reste secret tant que le pigeon n'est pas arrivé
        out.append(m)
    return out


@router.get("/sent", response_model=List[schemas.MessageOut])
def sent(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    messages = db.query(models.Message).filter(models.Message.sender_id == current_user.id).all()
    return [_sync_message(db, m) for m in messages]


@router.get("/{message_id}/track", response_model=schemas.MessageTrackOut)
def track(message_id: str, db: Session = Depends(get_db),
          current_user: models.User = Depends(get_current_user)):
    message = db.query(models.Message).get(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message introuvable")
    if message.sender_id != current_user.id and message.recipient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tu ne peux pas suivre ce pigeon")

    message = _sync_message(db, message)
    lat, lng, fraction = pigeon_logic.current_position(
        message.origin_lat, message.origin_lng, message.dest_lat, message.dest_lng,
        message.departure_time, message.eta
    )
    remaining = max(0.0, (message.eta - datetime.utcnow()).total_seconds())

    return schemas.MessageTrackOut(
        id=message.id,
        status=message.status.value,
        current_lat=lat,
        current_lng=lng,
        progress_fraction=fraction,
        distance_miles=message.distance_miles,
        effective_speed_mph=message.effective_speed_mph,
        eta=message.eta,
        time_remaining_seconds=remaining,
    )


@router.post("/nearby", response_model=List[schemas.CatchablePigeonOut])
def catchable_nearby(payload: schemas.NearbyQuery, db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    """Pigeons en vol (lâchers anonymes/ouverts) qui passent actuellement près de toi."""
    candidates = db.query(models.Message).filter(
        models.Message.status == models.MessageStatus.in_flight,
        models.Message.is_open_release == True,  # noqa: E712
    ).all()

    results = []
    for m in candidates:
        m = _sync_message(db, m)
        if m.status != models.MessageStatus.in_flight:
            continue
        lat, lng, _ = pigeon_logic.current_position(
            m.origin_lat, m.origin_lng, m.dest_lat, m.dest_lng, m.departure_time, m.eta
        )
        dist = pigeon_logic.haversine_miles(payload.lat, payload.lng, lat, lng)
        if dist <= payload.radius_miles:
            pigeon = db.query(models.Pigeon).get(m.pigeon_id)
            results.append(schemas.CatchablePigeonOut(
                message_id=m.id,
                pigeon_id=m.pigeon_id,
                pigeon_name=pigeon.name if pigeon else "Pigeon inconnu",
                sprite_key=pigeon.bird_type.sprite_key if pigeon else "pigeon",
                distance_to_you_miles=round(dist, 2),
                is_anonymous=m.is_anonymous,
                is_open_release=m.is_open_release,
            ))
    results.sort(key=lambda r: r.distance_to_you_miles)
    return results


@router.post("/catch", response_model=schemas.MessageOut)
def catch_pigeon(payload: schemas.CaptureRequest, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    message = db.query(models.Message).get(payload.message_id)
    if not message or not message.is_open_release:
        raise HTTPException(status_code=404, detail="Ce pigeon n'est pas capturable")
    message = _sync_message(db, message)
    if message.status != models.MessageStatus.in_flight:
        raise HTTPException(status_code=400, detail="Ce pigeon n'est plus attrapable (déjà livré, perdu, ou capturé)")

    lat, lng, _ = pigeon_logic.current_position(
        message.origin_lat, message.origin_lng, message.dest_lat, message.dest_lng,
        message.departure_time, message.eta
    )
    dist = pigeon_logic.haversine_miles(payload.lat, payload.lng, lat, lng)
    if dist > 1.0:
        raise HTTPException(status_code=400, detail="Le pigeon n'est pas assez proche pour être capturé")

    message.status = models.MessageStatus.captured
    message.recipient_id = current_user.id
    message.delivered_at = datetime.utcnow()

    pigeon = db.query(models.Pigeon).get(message.pigeon_id)
    if pigeon:
        pigeon.status = models.PigeonStatus.captured

    capture_event = models.CaptureEvent(
        pigeon_id=message.pigeon_id,
        message_id=message.id,
        catcher_id=current_user.id,
        catch_lat=payload.lat,
        catch_lng=payload.lng,
    )
    db.add(capture_event)

    if payload.send_friend_request and message.sender_id and message.sender_id != current_user.id:
        existing = db.query(models.Friendship).filter(
            models.Friendship.requester_id == current_user.id,
            models.Friendship.addressee_id == message.sender_id,
        ).first()
        if not existing:
            db.add(models.Friendship(
                requester_id=current_user.id,
                addressee_id=message.sender_id,
                via_pigeon_id=message.pigeon_id,
            ))

    db.commit()
    db.refresh(message)
    return message
