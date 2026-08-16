from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ---------- Auth / Users ----------

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: Optional[str]
    avatar_key: str
    feathers_balance: int
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LocationUpdate(BaseModel):
    lat: float
    lng: float


# ---------- Bird types ----------

class BirdTypeOut(BaseModel):
    id: int
    code: str
    display_name: str
    base_speed_mph: float
    loss_risk_multiplier: float
    unlock_cost_feathers: int
    description: str
    sprite_key: str

    class Config:
        from_attributes = True


# ---------- Pigeons ----------

class PigeonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    bird_type_id: int
    color: Optional[str] = "#e8e2d6"
    accessory: Optional[str] = None


class PigeonUpgrade(BaseModel):
    bird_type_id: int


class PigeonOut(BaseModel):
    id: str
    owner_id: str
    name: str
    color: str
    accessory: Optional[str]
    status: str
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
    origin_lat: float
    origin_lng: float
    dest_lat: Optional[float]
    dest_lng: Optional[float]
    distance_miles: float
    effective_speed_mph: float
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
    radius_miles: float = 5.0


class CatchablePigeonOut(BaseModel):
    message_id: str
    pigeon_id: str
    pigeon_name: str
    sprite_key: str
    distance_to_you_miles: float
    is_anonymous: bool
    is_open_release: bool


class CaptureRequest(BaseModel):
    message_id: str
    lat: float
    lng: float
    send_friend_request: bool = False


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
