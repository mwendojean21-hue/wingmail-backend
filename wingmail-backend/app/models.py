import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


class BirdType(Base):
    """Espèces d'oiseaux disponibles : pigeon voyageur, faucon, hirondelle, etc."""
    __tablename__ = "bird_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False)       # "pigeon", "hawk", "falcon", "swallow"
    display_name = Column(String, nullable=False)
    base_speed_mph = Column(Float, nullable=False)
    max_range_miles = Column(Float, nullable=False, default=500.0)  # portee max sur une pleine jauge d'energie
    loss_risk_multiplier = Column(Float, default=1.0)        # >1 = plus risqué, <1 = plus sûr
    unlock_cost_feathers = Column(Integer, default=10)        # monnaie virtuelle du jeu - aucune espece n'est gratuite
    description = Column(Text, default="")
    sprite_key = Column(String, default="pigeon")             # clé utilisée par le frontend pour l'illustration/animation

    pigeons = relationship("Pigeon", back_populates="bird_type")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    avatar_key = Column(String, default="default")
    feathers_balance = Column(Integer, default=50)  # monnaie virtuelle gagnée en jouant
    is_admin = Column(Boolean, default=False)

    last_lat = Column(Float, nullable=True)
    last_lng = Column(Float, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)

    # --- Localisation approximative par adresse IP (pour la carte admin) ---
    last_ip = Column(String, nullable=True)
    ip_country = Column(String, nullable=True)
    ip_region = Column(String, nullable=True)
    ip_lat = Column(Float, nullable=True)
    ip_lng = Column(Float, nullable=True)

    # --- Parrainage ---
    referral_code = Column(String, unique=True, nullable=False, default=gen_uuid)
    referred_by_id = Column(String, ForeignKey("users.id"), nullable=True)
    referral_count = Column(Integer, default=0)  # nombre de filleuls ayant rejoint via son lien

    # --- Partage sur les reseaux ---
    shared_facebook = Column(Boolean, default=False)
    shared_instagram = Column(Boolean, default=False)
    shared_tiktok = Column(Boolean, default=False)
    shared_x = Column(Boolean, default=False)
    share_confirmed_count = Column(Integer, default=0)

    # --- Etoile GitHub ---
    github_star_claimed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    pigeons = relationship("Pigeon", back_populates="owner", foreign_keys="Pigeon.owner_id")
    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")


class PigeonStatus(str, enum.Enum):
    idle = "idle"
    in_flight = "in_flight"
    delivered = "delivered"
    lost = "lost"
    captured = "captured"
    fallen = "fallen"  # a court d'energie en plein vol, encore vivant, secourable


class Pigeon(Base):
    __tablename__ = "pigeons"

    id = Column(String, primary_key=True, default=gen_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    bird_type_id = Column(Integer, ForeignKey("bird_types.id"), nullable=False)

    name = Column(String, nullable=False, default="Pigeon")
    color = Column(String, default="#e8e2d6")            # couleur de plumage personnalisée
    accessory = Column(String, nullable=True)             # ex: "bandana_rouge", "sac_cuir"
    status = Column(Enum(PigeonStatus), default=PigeonStatus.idle)
    energy = Column(Float, default=100.0)  # 0-100, consommee au fil des vols, rechargeable avec des plumes

    total_deliveries = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    is_wild = Column(Boolean, default=False)  # pigeon "sauvage" généré par le système, capturable

    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="pigeons", foreign_keys=[owner_id])
    bird_type = relationship("BirdType", back_populates="pigeons")


class MessageStatus(str, enum.Enum):
    in_flight = "in_flight"
    delivered = "delivered"
    lost = "lost"
    captured = "captured"  # capturé par un tiers avant d'arriver (message anonyme "lâché dans la nature")
    fallen = "fallen"      # a court d'energie, encore vivant, secourable par n'importe qui


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=gen_uuid)
    sender_id = Column(String, ForeignKey("users.id"), nullable=True)  # nullable si totalement anonyme
    recipient_id = Column(String, ForeignKey("users.id"), nullable=True)
    pigeon_id = Column(String, ForeignKey("pigeons.id"), nullable=False)

    content = Column(Text, nullable=False)
    is_anonymous = Column(Boolean, default=False)
    is_open_release = Column(Boolean, default=False)  # message "lâché dans la nature", n'importe qui peut le capturer
    is_return_leg = Column(Boolean, default=False)    # vol retour automatique du pigeon vers son proprietaire apres livraison
    outbound_message_id = Column(String, ForeignKey("messages.id"), nullable=True)  # message d'origine si c'est un retour

    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    dest_lat = Column(Float, nullable=True)
    dest_lng = Column(Float, nullable=True)

    distance_miles = Column(Float, nullable=False)
    effective_speed_mph = Column(Float, nullable=False)
    will_be_lost = Column(Boolean, default=False)   # tiré au sort au départ (0.2% par défaut)
    lost_at_fraction = Column(Float, nullable=True)  # si perdu : à quelle fraction du trajet (0-1)
    path_json = Column(Text, nullable=True)  # trajet en plusieurs segments (lâchers dans la nature uniquement), JSON [[lat,lng], ...]
    energy_cost_fraction = Column(Float, default=0.0)         # fraction de la jauge d'energie consommee par ce vol
    out_of_energy_at_fraction = Column(Float, nullable=True)  # si le trajet depasse la portee : fraction ou le pigeon tombe
    remaining_energy_percent = Column(Float, default=100.0)   # energie du pigeon une fois ce vol termine (si delivre)

    status = Column(Enum(MessageStatus), default=MessageStatus.in_flight)

    departure_time = Column(DateTime, default=datetime.utcnow)
    eta = Column(DateTime, nullable=False)
    delivered_at = Column(DateTime, nullable=True)

    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    pigeon = relationship("Pigeon")

    @property
    def path(self):
        if not self.path_json:
            return None
        import json
        try:
            return json.loads(self.path_json)
        except (ValueError, TypeError):
            return None


class FriendshipStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class Friendship(Base):
    """Représente le 'flock'. Peut naître de la capture d'un pigeon porteur d'une demande d'ami."""
    __tablename__ = "friendships"

    id = Column(String, primary_key=True, default=gen_uuid)
    requester_id = Column(String, ForeignKey("users.id"), nullable=False)
    addressee_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(FriendshipStatus), default=FriendshipStatus.pending)
    via_pigeon_id = Column(String, ForeignKey("pigeons.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CaptureEvent(Base):
    """Historique des pigeons sauvages/de passage capturés par les utilisateurs."""
    __tablename__ = "capture_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    pigeon_id = Column(String, ForeignKey("pigeons.id"), nullable=False)
    message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    catcher_id = Column(String, ForeignKey("users.id"), nullable=False)
    catch_lat = Column(Float, nullable=False)
    catch_lng = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FeedbackCategory(str, enum.Enum):
    avis = "avis"
    demande = "demande"
    bug = "bug"
    autre = "autre"


class FeedbackStatus(str, enum.Enum):
    nouveau = "nouveau"
    lu = "lu"
    traite = "traite"


class Feedback(Base):
    """Avis, demandes de fonctionnalites et signalements envoyes par les utilisateurs."""
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(Enum(FeedbackCategory), default=FeedbackCategory.avis)
    content = Column(Text, nullable=False)
    status = Column(Enum(FeedbackStatus), default=FeedbackStatus.nouveau)
    created_at = Column(DateTime, default=datetime.utcnow)
