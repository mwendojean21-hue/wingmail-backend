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
CAPTURE_RADIUS_MILES = 2.0                # distance max pour capturer un pigeon de passage


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_MILES * c


def destination_point(lat: float, lng: float, bearing_deg: float, distance_miles: float) -> Tuple[float, float]:
    """Calcule le point atteint en partant de (lat, lng), avec un cap et une distance donnes."""
    R = EARTH_RADIUS_MILES
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    brng = math.radians(bearing_deg)
    d_r = distance_miles / R

    lat2 = math.asin(math.sin(lat1) * math.cos(d_r) + math.cos(lat1) * math.sin(d_r) * math.cos(brng))
    lng2 = lng1 + math.atan2(
        math.sin(brng) * math.sin(d_r) * math.cos(lat1),
        math.cos(d_r) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lng2)


def generate_wander_path(origin_lat: float, origin_lng: float,
                          min_segments: int = 4, max_segments: int = 7,
                          min_leg_miles: float = 0.4, max_leg_miles: float = 2.5,
                          max_turn_deg: float = 75.0) -> list:
    """
    Genere un trajet en plusieurs segments avec des virages aleatoires bornes,
    pour simuler un pigeon lache dans la nature qui erre plutot qu'il ne vole
    en ligne droite. Retourne une liste de points [(lat, lng), ...].
    """
    points = [(origin_lat, origin_lng)]
    heading = random.uniform(0, 360)
    num_segments = random.randint(min_segments, max_segments)

    for _ in range(num_segments):
        turn = random.uniform(-max_turn_deg, max_turn_deg)
        heading = (heading + turn) % 360
        leg_distance = random.uniform(min_leg_miles, max_leg_miles)
        new_point = destination_point(points[-1][0], points[-1][1], heading, leg_distance)
        points.append(new_point)

    return points


def path_total_distance_miles(path: list) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        total += haversine_miles(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
    return total


def position_along_path(path: list, fraction: float) -> Tuple[float, float]:
    """Retourne le point (lat, lng) atteint apres avoir parcouru 'fraction' (0-1) du trajet total."""
    fraction = max(0.0, min(1.0, fraction))
    total = path_total_distance_miles(path)
    if total <= 0 or len(path) < 2:
        return path[0] if path else (0.0, 0.0)

    target_distance = fraction * total
    accumulated = 0.0

    for i in range(len(path) - 1):
        seg_len = haversine_miles(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
        if accumulated + seg_len >= target_distance or i == len(path) - 2:
            remaining = target_distance - accumulated
            seg_fraction = (remaining / seg_len) if seg_len > 0 else 0.0
            seg_fraction = max(0.0, min(1.0, seg_fraction))
            lat = path[i][0] + (path[i + 1][0] - path[i][0]) * seg_fraction
            lng = path[i][1] + (path[i + 1][1] - path[i][1]) * seg_fraction
            return lat, lng
        accumulated += seg_len

    return path[-1]


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
    """Retourne toutes les infos nécessaires pour créer un Message en vol (trajet direct en ligne droite)."""
    distance = haversine_miles(origin_lat, origin_lng, dest_lat, dest_lng)
    return compute_flight_plan_from_distance(distance, base_speed_mph, loss_risk_multiplier)


def compute_flight_plan_from_distance(distance: float, base_speed_mph: float,
                                       loss_risk_multiplier: float = 1.0) -> dict:
    """Meme logique que compute_flight_plan, mais a partir d'une distance deja connue
    (utilise pour les trajets en plusieurs segments des lachers dans la nature)."""
    if distance <= LOCAL_DELIVERY_THRESHOLD_MILES:
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


def compute_flight_plan_with_energy(distance: float, base_speed_mph: float,
                                     max_range_miles: float, current_energy_percent: float,
                                     loss_risk_multiplier: float = 1.0) -> dict:
    """
    Comme compute_flight_plan_from_distance, mais tient compte de la portee de
    l'espece et de l'energie actuelle du pigeon. Si le trajet demande plus
    d'energie que le pigeon n'en a, il tombe en route (statut "fallen") avant
    d'arriver, au lieu d'etre livre.
    """
    energy_fraction = max(0.0, min(1.0, current_energy_percent / 100.0))
    energy_cost_fraction = distance / max(1.0, max_range_miles)

    plan = compute_flight_plan_from_distance(distance, base_speed_mph, loss_risk_multiplier)
    plan["energy_cost_fraction"] = round(energy_cost_fraction, 4)

    if energy_cost_fraction > energy_fraction:
        # Le pigeon n'a pas assez d'energie pour arriver : il tombe, encore vivant,
        # a l'endroit ou sa jauge atteint zero.
        out_of_energy_at_fraction = energy_fraction / energy_cost_fraction if energy_cost_fraction > 0 else 0.0
        duration_hours = plan["duration_hours"] * out_of_energy_at_fraction
        plan["out_of_energy_at_fraction"] = round(out_of_energy_at_fraction, 4)
        plan["will_be_lost"] = False
        plan["lost_at_fraction"] = None
        plan["eta"] = plan["departure_time"] + timedelta(hours=duration_hours)
        plan["guaranteed_fallen"] = True
        plan["remaining_energy_percent"] = 0.0
    else:
        plan["out_of_energy_at_fraction"] = None
        plan["guaranteed_fallen"] = False
        plan["remaining_energy_percent"] = round((energy_fraction - energy_cost_fraction) * 100, 2)

    return plan


def current_position(origin_lat: float, origin_lng: float,
                      dest_lat: float, dest_lng: float,
                      departure_time: datetime, eta: datetime,
                      now: Optional[datetime] = None,
                      path: Optional[list] = None,
                      cap_fraction: Optional[float] = None) -> Tuple[float, float, float]:
    """
    Interpole la position actuelle du pigeon sur le trajet.
    Si 'path' est fourni (lâcher dans la nature), la position suit ce trajet
    en plusieurs segments plutôt qu'une ligne droite entre origine et destination.
    Si 'cap_fraction' est fourni (cas d'un pigeon a court d'energie : l'eta a ete
    raccourci pour representer le moment de la chute), la position spatiale
    progresse lineairement jusqu'a cap_fraction du trajet total, puis se fige
    la (le pigeon ne continue pas jusqu'a la destination complete).
    Retourne (lat, lng, fraction_parcourue [0-1]).
    """
    now = now or datetime.utcnow()
    total_seconds = max(1.0, (eta - departure_time).total_seconds())
    elapsed_seconds = (now - departure_time).total_seconds()
    time_fraction = max(0.0, min(1.0, elapsed_seconds / total_seconds))

    fraction = time_fraction * cap_fraction if cap_fraction is not None else time_fraction

    if path and len(path) >= 2:
        lat, lng = position_along_path(path, fraction)
        return lat, lng, fraction

    lat = origin_lat + (dest_lat - origin_lat) * fraction
    lng = origin_lng + (dest_lng - origin_lng) * fraction
    return lat, lng, fraction


def resolve_status(departure_time: datetime, eta: datetime,
                    will_be_lost: bool, lost_at_fraction: Optional[float],
                    now: Optional[datetime] = None,
                    guaranteed_fallen: bool = False) -> str:
    """Détermine si le message est encore en vol, livré, perdu ou tombé (à court d'énergie), à l'instant 'now'."""
    now = now or datetime.utcnow()
    total_seconds = max(1.0, (eta - departure_time).total_seconds())
    elapsed_seconds = (now - departure_time).total_seconds()
    fraction = elapsed_seconds / total_seconds

    if guaranteed_fallen and fraction >= 1.0:
        # eta a ete raccourci pour correspondre au point ou l'energie tombe a zero
        return "fallen"
    if will_be_lost and lost_at_fraction is not None and fraction >= lost_at_fraction:
        return "lost"
    if fraction >= 1.0:
        return "delivered"
    return "in_flight"
