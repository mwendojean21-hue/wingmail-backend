from datetime import datetime
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, pigeon_logic
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


def _spawn_return_leg(db: Session, outbound: models.Message, pigeon: models.Pigeon):
    """Cree le vol retour automatique du pigeon vers son point de depart d'origine, une fois la livraison faite."""
    distance = outbound.distance_miles  # trajet retour symetrique
    plan = pigeon_logic.compute_flight_plan_with_energy(
        distance, pigeon.bird_type.base_speed_mph, pigeon.bird_type.max_range_miles,
        pigeon.energy, pigeon.bird_type.loss_risk_multiplier,
    )
    return_msg = models.Message(
        sender_id=None,
        recipient_id=outbound.sender_id,  # revient "chez" l'expediteur d'origine
        pigeon_id=pigeon.id,
        content="",
        is_anonymous=False,
        is_open_release=False,
        is_return_leg=True,
        outbound_message_id=outbound.id,
        origin_lat=outbound.dest_lat,
        origin_lng=outbound.dest_lng,
        dest_lat=outbound.origin_lat,
        dest_lng=outbound.origin_lng,
        distance_miles=plan["distance_miles"],
        effective_speed_mph=plan["effective_speed_mph"],
        will_be_lost=plan["will_be_lost"],
        lost_at_fraction=plan["lost_at_fraction"],
        energy_cost_fraction=plan["energy_cost_fraction"],
        out_of_energy_at_fraction=plan["out_of_energy_at_fraction"],
        remaining_energy_percent=plan["remaining_energy_percent"],
        departure_time=plan["departure_time"],
        eta=plan["eta"],
        status=models.MessageStatus.in_flight,
    )
    db.add(return_msg)


def _sync_message(db: Session, message: models.Message) -> models.Message:
    """Met à jour le statut du message (et du pigeon associé) en fonction du temps écoulé."""
    if message.status == models.MessageStatus.in_flight:
        new_status = pigeon_logic.resolve_status(
            message.departure_time, message.eta, message.will_be_lost, message.lost_at_fraction,
            guaranteed_fallen=message.out_of_energy_at_fraction is not None,
        )
        if new_status != "in_flight":
            message.status = models.MessageStatus(new_status)
            if new_status == "delivered":
                message.delivered_at = message.eta
            pigeon = db.query(models.Pigeon).get(message.pigeon_id)
            if pigeon:
                if new_status == "delivered":
                    pigeon.energy = message.remaining_energy_percent
                    if message.is_return_leg:
                        # le pigeon est rentre chez lui : disponible a nouveau
                        pigeon.status = models.PigeonStatus.idle
                    else:
                        pigeon.total_deliveries += 1
                        # le pigeon repart aussitot pour rentrer chez son proprietaire
                        _spawn_return_leg(db, message, pigeon)
                        pigeon.status = models.PigeonStatus.in_flight
                elif new_status == "lost":
                    pigeon.status = models.PigeonStatus.lost
                    pigeon.total_losses += 1
                elif new_status == "fallen":
                    pigeon.status = models.PigeonStatus.fallen
                    pigeon.energy = 0.0
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
    wander_path = None

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
        # message lâché dans la nature : trajet errant en plusieurs segments,
        # capturable par n'importe qui se trouvant sur son passage
        wander_path = pigeon_logic.generate_wander_path(current_user.last_lat, current_user.last_lng)
        dest_lat, dest_lng = wander_path[-1]
    else:
        raise HTTPException(status_code=400, detail="Précise un destinataire ou choisis un lâcher anonyme")

    if wander_path:
        distance = pigeon_logic.path_total_distance_miles(wander_path)
    else:
        distance = pigeon_logic.haversine_miles(current_user.last_lat, current_user.last_lng, dest_lat, dest_lng)

    plan = pigeon_logic.compute_flight_plan_with_energy(
        distance, pigeon.bird_type.base_speed_mph, pigeon.bird_type.max_range_miles,
        pigeon.energy, pigeon.bird_type.loss_risk_multiplier,
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
        path_json=json.dumps(wander_path) if wander_path else None,
        distance_miles=plan["distance_miles"],
        effective_speed_mph=plan["effective_speed_mph"],
        will_be_lost=plan["will_be_lost"],
        lost_at_fraction=plan["lost_at_fraction"],
        energy_cost_fraction=plan["energy_cost_fraction"],
        out_of_energy_at_fraction=plan["out_of_energy_at_fraction"],
        remaining_energy_percent=plan["remaining_energy_percent"],
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
        message.departure_time, message.eta, path=message.path, cap_fraction=message.out_of_energy_at_fraction
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
    effective_radius = min(payload.radius_miles, pigeon_logic.CAPTURE_RADIUS_MILES)
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
        m.origin_lat, m.origin_lng, m.dest_lat, m.dest_lng,
        m.departure_time, m.eta, path=m.path, cap_fraction=m.out_of_energy_at_fraction
    )
        dist = pigeon_logic.haversine_miles(payload.lat, payload.lng, lat, lng)
        if dist <= effective_radius:
            pigeon = db.query(models.Pigeon).get(m.pigeon_id)
            results.append(schemas.CatchablePigeonOut(
                message_id=m.id,
                pigeon_id=m.pigeon_id,
                pigeon_name=pigeon.name if pigeon else "Pigeon inconnu",
                sprite_key=pigeon.bird_type.sprite_key if pigeon else "pigeon",
                distance_to_you_miles=round(dist, 2),
                current_lat=lat,
                current_lng=lng,
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
        message.departure_time, message.eta, path=message.path, cap_fraction=message.out_of_energy_at_fraction
    )
    dist = pigeon_logic.haversine_miles(payload.lat, payload.lng, lat, lng)
    if dist > pigeon_logic.CAPTURE_RADIUS_MILES:
        raise HTTPException(status_code=400, detail=f"Le pigeon n'est pas assez proche pour être capturé (moins de {pigeon_logic.CAPTURE_RADIUS_MILES} miles requis)")

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


@router.get("/world-active", response_model=List[schemas.WorldPigeonOut])
def world_active(db: Session = Depends(get_db)):
    """
    Position actuelle de TOUS les pigeons en vol, toutes personnes confondues,
    pour la carte mondiale en temps réel. Endpoint public en lecture seule :
    aucune donnée personnelle (ni expéditeur, ni destinataire, ni contenu)
    n'est renvoyée, seulement une position et une espèce.
    """
    active = db.query(models.Message).filter(
        models.Message.status == models.MessageStatus.in_flight
    ).all()

    results = []
    for m in active:
        m = _sync_message(db, m)
        if m.status != models.MessageStatus.in_flight:
            continue
        lat, lng, fraction = pigeon_logic.current_position(
        m.origin_lat, m.origin_lng, m.dest_lat, m.dest_lng,
        m.departure_time, m.eta, path=m.path, cap_fraction=m.out_of_energy_at_fraction
    )
        pigeon = db.query(models.Pigeon).get(m.pigeon_id)
        results.append(schemas.WorldPigeonOut(
            message_id=m.id,
            current_lat=lat,
            current_lng=lng,
            sprite_key=pigeon.bird_type.sprite_key if pigeon else "pigeon",
            progress_fraction=fraction,
        ))
    return results


@router.get("/fallen-nearby", response_model=List[schemas.FallenPigeonOut])
def fallen_nearby(lat: float, lng: float, radius_miles: float = pigeon_logic.CAPTURE_RADIUS_MILES,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """
    Oiseaux tombes (a court d'energie, encore vivants) detectes pres de toi,
    tous expediteurs confondus - n'importe qui peut les trouver et les aider.
    """
    fallen = db.query(models.Message).filter(models.Message.status == models.MessageStatus.fallen).all()
    results = []
    for m in fallen:
        fall_lat, fall_lng, _ = pigeon_logic.current_position(
            m.origin_lat, m.origin_lng, m.dest_lat, m.dest_lng,
            m.departure_time, m.eta, path=m.path, cap_fraction=m.out_of_energy_at_fraction,
        )
        dist = pigeon_logic.haversine_miles(lat, lng, fall_lat, fall_lng)
        if dist <= min(radius_miles, pigeon_logic.CAPTURE_RADIUS_MILES):
            pigeon = db.query(models.Pigeon).get(m.pigeon_id)
            if not pigeon:
                continue
            owner = db.query(models.User).get(pigeon.owner_id)
            results.append(schemas.FallenPigeonOut(
                message_id=m.id,
                pigeon_id=pigeon.id,
                pigeon_name=pigeon.name,
                sprite_key=pigeon.bird_type.sprite_key,
                owner_username=owner.username if owner else None,
                distance_to_you_miles=round(dist, 2),
                current_lat=fall_lat,
                current_lng=fall_lng,
                energy=pigeon.energy,
            ))
    results.sort(key=lambda r: r.distance_to_you_miles)
    return results


@router.post("/rescue", response_model=schemas.MessageOut)
def rescue_fallen(payload: schemas.RescueRequest, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Secourir un oiseau tombe : soit le relacher (avec un boost d'energie optionnel
    et une demande d'ami envoyee au proprietaire), soit se l'approprier (vol)."""
    message = db.query(models.Message).get(payload.message_id)
    if not message or message.status != models.MessageStatus.fallen:
        raise HTTPException(status_code=404, detail="Cet oiseau n'est pas (ou plus) a secourir")

    fall_lat, fall_lng, _ = pigeon_logic.current_position(
        message.origin_lat, message.origin_lng, message.dest_lat, message.dest_lng,
        message.departure_time, message.eta, path=message.path, cap_fraction=message.out_of_energy_at_fraction,
    )
    dist = pigeon_logic.haversine_miles(payload.lat, payload.lng, fall_lat, fall_lng)
    if dist > pigeon_logic.CAPTURE_RADIUS_MILES:
        raise HTTPException(status_code=400, detail="Tu n'es pas assez proche de cet oiseau")

    pigeon = db.query(models.Pigeon).get(message.pigeon_id)
    if not pigeon:
        raise HTTPException(status_code=404, detail="Pigeon introuvable")
    owner_id = pigeon.owner_id

    if payload.action == "steal":
        # Vol pur et simple : l'oiseau change de proprietaire, le message d'origine est perdu
        message.status = models.MessageStatus.lost
        pigeon.owner_id = current_user.id
        pigeon.status = models.PigeonStatus.idle
        pigeon.energy = max(pigeon.energy, 20.0)  # remis sur pattes a minima pour pouvoir revoler
        db.commit()
        db.refresh(message)
        return message

    # action == "release" : on l'aide, on le relache, il continue sa route
    if payload.energy_boost_feathers > 0:
        if current_user.feathers_balance < payload.energy_boost_feathers:
            raise HTTPException(status_code=402, detail="Tu n'as pas assez de plumes pour ce boost d'énergie")
        current_user.feathers_balance -= payload.energy_boost_feathers
        pigeon.energy = min(100.0, pigeon.energy + payload.energy_boost_feathers)  # 1 plume = 1 point d'energie

    # Demande d'ami envoyee au proprietaire, si ce n'est pas soi-meme
    if owner_id and owner_id != current_user.id:
        existing = db.query(models.Friendship).filter(
            models.Friendship.requester_id == current_user.id,
            models.Friendship.addressee_id == owner_id,
        ).first()
        if not existing:
            db.add(models.Friendship(
                requester_id=current_user.id, addressee_id=owner_id, via_pigeon_id=pigeon.id,
            ))

    # Reprise du vol depuis l'endroit ou il est tombe, avec la nouvelle energie
    remaining_distance = message.distance_miles * (1 - (message.out_of_energy_at_fraction or 0))
    plan = pigeon_logic.compute_flight_plan_with_energy(
        remaining_distance, pigeon.bird_type.base_speed_mph, pigeon.bird_type.max_range_miles,
        pigeon.energy, pigeon.bird_type.loss_risk_multiplier,
    )

    message.status = models.MessageStatus.in_flight
    message.origin_lat, message.origin_lng = fall_lat, fall_lng
    message.distance_miles = plan["distance_miles"]
    message.effective_speed_mph = plan["effective_speed_mph"]
    message.will_be_lost = plan["will_be_lost"]
    message.lost_at_fraction = plan["lost_at_fraction"]
    message.energy_cost_fraction = plan["energy_cost_fraction"]
    message.out_of_energy_at_fraction = plan["out_of_energy_at_fraction"]
    message.remaining_energy_percent = plan["remaining_energy_percent"]
    message.departure_time = plan["departure_time"]
    message.eta = plan["eta"]
    message.path_json = None  # le trajet restant repart en ligne droite vers la meme destination

    pigeon.status = models.PigeonStatus.in_flight

    db.commit()
    db.refresh(message)
    return message
