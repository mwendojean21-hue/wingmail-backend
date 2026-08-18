from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------- Auth / Users ----------

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: Optional[str] = None
    referral_code: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: Optional[str]
    avatar_key: str
    feathers_balance: int
    is_admin: bool
    referral_code: str
    referral_count: int
    shared_facebook: bool
    shared_instagram: bool
    shared_tiktok: bool
    shared_x: bool
    github_star_claimed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_key: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LocationUpdate(BaseModel):
    lat: float
    lng: float


# ---------- Bird types ----------

class BirdTypeOut(BaseModel):
    id: str
    code: str
    display_name: str
    base_speed_mph: float
    max_range_miles: float
    loss_risk_multiplier: float
    unlock_cost_feathers: int
    description: str
    sprite_key: str

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_id(cls, v):
        return str(v)

    class Config:
        from_attributes = True


# ---------- Pigeons ----------

class PigeonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    bird_type_id: str
    color: Optional[str] = "#e8e2d6"
    accessory: Optional[str] = None


class PigeonUpgrade(BaseModel):
    bird_type_id: str


class PigeonOut(BaseModel):
    id: str
    owner_id: str
    name: str
    color: str
    accessory: Optional[str]
    status: str
    energy: float
    total_deliveries: int
    total_losses: int
    is_wild: bool
    bird_type: BirdTypeOut

    class Config:
        from_attributes = True


# ---------- Messages ----------

class MessageCreate(BaseModel):
    pigeon_id: str
    content: str = Field(min_length=1, max_length=2000)
    recipient_id: Optional[str] = None
    recipient_username: Optional[str] = None
    dest_lat: Optional[float] = None
    dest_lng: Optional[float] = None
    is_anonymous: bool = False
    is_open_release: bool = False  # message lâché "dans la nature", capturable par n'importe qui


class MessageOut(BaseModel):
    id: str
    sender_id: Optional[str]
    recipient_id: Optional[str]
    pigeon_id: str
    content: Optional[str]  # masqué (None) tant que non livré au destinataire si souhaité côté frontend
    is_anonymous: bool
    is_open_release: bool
    is_return_leg: bool
    outbound_message_id: Optional[str]
    origin_lat: float
    origin_lng: float
    dest_lat: Optional[float]
    dest_lng: Optional[float]
    path: Optional[List[List[float]]] = None  # trajet en plusieurs segments pour les lâchers dans la nature
    distance_miles: float
    effective_speed_mph: float
    energy_cost_fraction: float
    out_of_energy_at_fraction: Optional[float]
    status: str
    departure_time: datetime
    eta: datetime
    delivered_at: Optional[datetime]

    class Config:
        from_attributes = True


class MessageTrackOut(BaseModel):
    id: str
    status: str
    current_lat: float
    current_lng: float
    progress_fraction: float
    distance_miles: float
    effective_speed_mph: float
    eta: datetime
    time_remaining_seconds: float


# ---------- Capture / catch nearby pigeons ----------

class NearbyQuery(BaseModel):
    lat: float
    lng: float
    radius_miles: float = 2.0  # aligné sur pigeon_logic.CAPTURE_RADIUS_MILES : pas la peine de montrer un pigeon qu'on ne peut pas capturer


class CatchablePigeonOut(BaseModel):
    message_id: str
    pigeon_id: str
    pigeon_name: str
    sprite_key: str
    distance_to_you_miles: float
    current_lat: float
    current_lng: float
    is_anonymous: bool
    is_open_release: bool


class CaptureRequest(BaseModel):
    message_id: str
    lat: float
    lng: float
    send_friend_request: bool = False


# ---------- Oiseaux tombes (secours / vol) ----------

class FallenPigeonOut(BaseModel):
    message_id: str
    pigeon_id: str
    pigeon_name: str
    sprite_key: str
    owner_username: Optional[str]
    distance_to_you_miles: float
    current_lat: float
    current_lng: float
    energy: float


class RescueRequest(BaseModel):
    message_id: str
    lat: float
    lng: float
    action: str = Field(pattern="^(release|steal)$")
    energy_boost_feathers: int = 0  # plumes depensees par le sauveteur pour recharger l'oiseau (uniquement pour "release")


# ---------- Friends ----------

class FriendshipOut(BaseModel):
    id: str
    requester_id: str
    addressee_id: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class FriendRequestCreate(BaseModel):
    addressee_username: str


# ---------- Recompenses (plumes) ----------

class ReferralLinkOut(BaseModel):
    referral_code: str
    referral_link: str
    referral_count: int
    feathers_earned_from_referrals: int


class ShareClaim(BaseModel):
    platform: str = Field(pattern="^(facebook|instagram|tiktok|x)$")


class ShareClaimOut(BaseModel):
    platform: str
    feathers_awarded: int
    new_balance: int
    share_confirmed_count: int


class GithubStarClaim(BaseModel):
    github_username: str = Field(min_length=1, max_length=64)


class GithubStarClaimOut(BaseModel):
    starred: bool
    feathers_awarded: int
    new_balance: int
    message: str


# ---------- Carte mondiale ----------

class WorldPigeonOut(BaseModel):
    message_id: str
    current_lat: float
    current_lng: float
    sprite_key: str
    progress_fraction: float


# ---------- Admin ----------

class AdminStatsOut(BaseModel):
    total_users: int
    total_pigeons: int
    total_messages: int
    messages_in_flight: int
    messages_delivered: int
    messages_lost: int
    messages_captured: int
    total_feathers_in_circulation: int
    signups_last_7_days: int


class AdminUserOut(BaseModel):
    id: str
    username: str
    display_name: Optional[str]
    email: str
    feathers_balance: int
    is_admin: bool
    referral_count: int
    ip_country: Optional[str]
    ip_region: Optional[str]
    pigeon_count: int
    message_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserDetailOut(AdminUserOut):
    ip_lat: Optional[float]
    ip_lng: Optional[float]
    pigeons: List["AdminPigeonOut"]


class AdminPigeonOut(BaseModel):
    id: str
    name: str
    status: str
    bird_type_display_name: str
    total_deliveries: int
    total_losses: int

    class Config:
        from_attributes = True


class AdminUserMapPoint(BaseModel):
    user_id: str
    username: str
    lat: float
    lng: float
    country: Optional[str]


class FeathersAdjust(BaseModel):
    delta: int  # positif pour ajouter, negatif pour retirer


class AdminPigeonGrant(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    bird_type_id: str


# ---------- Avis / demandes (feedback) ----------

class FeedbackCreate(BaseModel):
    category: str = Field(pattern="^(avis|demande|bug|autre)$")
    content: str = Field(min_length=3, max_length=2000)


class FeedbackOut(BaseModel):
    id: str
    user_id: str
    category: str
    content: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackAdminOut(FeedbackOut):
    username: str


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(pattern="^(nouveau|lu|traite)$")
