from pydantic import BaseModel
from typing import List, Optional


# ---------------- AUTH MODELS ----------------

class PhoneRequest(BaseModel):
    phone: str


class OTPVerify(BaseModel):
    phone: str
    otp: str


# ---------------- CREATE AD MODEL ----------------

class CreateAd(BaseModel):
    user_phone: str
    category: str
    title: str
    description: str
    price: Optional[str] = None

    # ✅ Live Location
    latitude: float
    longitude: float
    district: Optional[str] = None

    # Car / Bike
    brand: Optional[str] = None
    year: Optional[str] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None
    km_driven: Optional[str] = None
    no_of_owner: Optional[str] = None

    # Property
    type: Optional[str] = None
    bhk: Optional[str] = None
    bathrooms: Optional[str] = None
    furnishing: Optional[str] = None
    area_sqft: Optional[str] = None
    listing_type: Optional[str] = None

    images: Optional[List[str]] = []


# ---------------- CHAT MODEL ----------------

class MessageCreate(BaseModel):
    ad_id: str
    sender_phone: str
    receiver_phone: str
    message: str


# ---------------- FCM UPDATE MODEL ----------------

class FCMUpdate(BaseModel):
    phone: str
    fcm_token: str