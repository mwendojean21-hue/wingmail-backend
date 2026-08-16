"""
Coeur de la simulation "vol de pigeon" de Wingmail.

- Calcul de distance réelle (formule de haversine)
- Vitesse effective = vitesse de base de l'espèce +/- fluctuation aléatoire
- Tirage au sort de la perte du message (probabilité configurable, 0.2% par défaut)
- Calcul de la position actuelle du pigeon en vol (pour le suivi sur la carte
  et pour la fonctionnalité "capturer un pigeon qui passe près de chez moi")
"""

import math
import random
from datetime import datetime, timedelta
from typing import Optional, Tuple

EARTH_RADIUS_MILES = 3958.8

DEFAULT_LOSS_PROBABILITY = 0.002          # 0.2% de chance de perte définitive
SPEED_FLUCTUATION = 0.25                  # +/- 25%
LOCAL_DELIVERY_THRESHOLD_MILES = 0.5      # en dessous : livraison quasi instantanée


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_MILES * c


def roll_effective_speed(base_speed_mph: float) -> float:
    fluctuation = random.uniform(-SPEED_FLUCTUATION, SPEED_FLUCTUATION)
    return max(1.0, base_speed_mph * (1 + fluctuation))


def roll_loss(base_probability: float = DEFAULT_LOSS_PROBABILITY,
              risk_multiplier: float = 1.0) -> bool:
    probability = min(0.5, base_probability * risk_multiplier)
    return random.random() < probability


def compute_flight_plan(origin_lat: float, origin_lng: float,
                         dest_lat: float, dest_lng: float,
                         base_speed_mph: float,
                         loss_risk_multiplier: float = 1.0) -> dict:
    """Retourne toutes les infos nécessaires pour créer un Message en vol."""
    distance = haversine_miles(origin_lat, origin_lng, dest_lat, dest_lng)

    if distance <= LOCAL_DELIVERY_THRESHOLD_MILES:
        # livraison locale quasi instantanée
        effective_speed = base_speed_mph
        duration_hours = max(0.001, distance / effective_speed)
    else:
        effective_speed = roll_effective_speed(base_speed_mph)
        duration_hours = distance / effective_speed

    will_be_lost = roll_loss(risk_multiplier=loss_risk_multiplier)
    lost_at_fraction = random.uniform(0.15, 0.9) if will_be_lost else None

    departure = datetime.utcnow()
    eta = departure + timedelta(hours=duration_hours)

    return {
        "distance_miles": round(distance, 2),
        "effective_speed_mph": round(effective_speed, 2),
        "duration_hours": duration_hours,
        "will_be_lost": will_be_lost,
        "lost_at_fraction": lost_at_fraction,
        "departure_time": departure,
        "eta": eta,
    }


def current_position(origin_lat: float, origin_lng: float,
                      dest_lat: float, dest_lng: float,
                      departure_time: datetime, eta: datetime,
                      now: Optional[datetime] = None) -> Tuple[float, float, float]:
    """
    Interpole la position actuelle du pigeon sur le trajet.
    Retourne (lat, lng, fraction_parcourue [0-1]).
    """
    now = now or datetime.utcnow()
    total_seconds = max(1.0, (eta - departure_time).total_seconds())
    elapsed_seconds = (now - departure_time).total_seconds()
    fraction = max(0.0, min(1.0, elapsed_seconds / total_seconds))

    lat = origin_lat + (dest_lat - origin_lat) * fraction
    lng = origin_lng + (dest_lng - origin_lng) * fraction
    return lat, lng, fraction


def resolve_status(departure_time: datetime, eta: datetime,
                    will_be_lost: bool, lost_at_fraction: Optional[float],
                    now: Optional[datetime] = None) -> str:
    """Détermine si le message est encore en vol, livré, ou perdu, à l'instant 'now'."""
    now = now or datetime.utcnow()
    total_seconds = max(1.0, (eta - departure_time).total_seconds())
    elapsed_seconds = (now - departure_time).total_seconds()
    fraction = elapsed_seconds / total_seconds

    if will_be_lost and lost_at_fraction is not None and fraction >= lost_at_fraction:
        return "lost"
    if fraction >= 1.0:
        return "delivered"
    return "in_flight"
