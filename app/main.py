from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from app.schemas import PhoneRequest, OTPVerify, CreateAd, MessageCreate, FCMUpdate
from app.database import supabase
from app.utils import generate_otp
from app.auth import create_token
from fastapi.middleware.cors import CORSMiddleware  
import uuid
import shutil
import os
import json
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if not os.path.exists("uploads"):
    os.makedirs("uploads")

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")

# ✅ FCM SEND FUNCTION
# ✅ FCM SEND FUNCTION
def send_fcm_notification(token: str, title: str, body: str, ad_id: str, sender_phone: str):

    SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']

    firebase_json = os.getenv("FIREBASE_CREDENTIALS")

    if not firebase_json:
        print("FIREBASE_CREDENTIALS not set!")
        return

    credentials = service_account.Credentials.from_service_info(
        json.loads(firebase_json),
        scopes=SCOPES
    )

    credentials.refresh(Request())
    access_token = credentials.token

    url = f"https://fcm.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/messages:send"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "message": {
            "token": token,
            "notification": {
                "title": title,
                "body": body
            },
            "data": {
                "ad_id": ad_id,
                "sender_phone": sender_phone
            }
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    print("FCM Response:", response.status_code, response.text)

# ---------------- ROOT ----------------

@app.get("/")
def home():
    return {"message": "TXM Backend Running ✅"}


# ---------------- AUTH ----------------
@app.post("/send-otp")
def send_otp(data: PhoneRequest):

    phone = data.phone.strip()

    if phone.startswith("+91"):
        phone = phone[3:]

    phone = phone.replace(" ", "")

    otp = generate_otp()

    supabase.table("otp_store").upsert({
        "phone": phone,
        "otp": otp
    }).execute()

    return {"message": "OTP sent successfully", "otp": otp}

@app.post("/verify-otp")
def verify_otp(data: OTPVerify):

    phone = data.phone.strip()

    if phone.startswith("+91"):
        phone = phone[3:]

    phone = phone.replace(" ", "")

    otp_record = supabase.table("otp_store") \
        .select("otp") \
        .eq("phone", phone) \
        .single() \
        .execute()

    stored_otp = otp_record.data["otp"] if otp_record.data else None

    if not stored_otp or stored_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    user = supabase.table("users") \
        .select("*") \
        .eq("phone", phone) \
        .execute()

    if not user.data:
        new_user = supabase.table("users").insert({
            "phone": phone,
            "district": None,
            "latitude": None,
            "longitude": None,
            "fcm_token": None
        }).execute()
        user_data = new_user.data[0]
    else:
        user_data = user.data[0]

    token = create_token({"phone": phone})

    return {
        "message": "Login success",
        "token": token,
        "user": user_data
    }
# ✅ Update FCM Token

@app.post("/update-fcm")
def update_fcm(data: FCMUpdate):

    supabase.table("users").update({
        "fcm_token": data.fcm_token
    }).eq("phone", data.phone).execute()

    return {"message": "FCM updated ✅"}


# ---------------- CREATE AD ----------------

@app.post("/create-ad")
def create_ad(data: CreateAd):

    ad_id = str(uuid.uuid4())

    # ✅ Update user location
    supabase.table("users").update({
        "latitude": round(data.latitude, 6),
        "longitude": round(data.longitude, 6)
    }).eq("phone", data.user_phone).execute()

    # ✅ Insert ad
    supabase.table("ads").insert({
        "id": ad_id,
        "user_phone": data.user_phone,
        "category": data.category,
        "title": data.title,
        "description": data.description,
        "price": data.price
    }).execute()

    # ✅ SAVE IMAGES PROPERLY
    if data.images:
        for img in data.images:
            supabase.table("ad_images").insert({
                "ad_id": ad_id,
                "image_url": img
            }).execute()

    return {"message": "Ad created successfully ✅"}

# ---------------- CHAT ----------------

@app.post("/send-message")
def send_message(data: MessageCreate):

    supabase.table("messages").insert({
        "ad_id": data.ad_id,
        "sender_phone": data.sender_phone,
        "receiver_phone": data.receiver_phone,
        "message": data.message
    }).execute()

    receiver = supabase.table("users") \
        .select("fcm_token") \
        .eq("phone", data.receiver_phone) \
        .single() \
        .execute()

    fcm_token = receiver.data.get("fcm_token") if receiver.data else None

    if fcm_token:
        send_fcm_notification(
            fcm_token,
            "New Message",
            data.message,
            data.ad_id,
            data.sender_phone
        )

    return {"message": "Sent ✅"}


@app.get("/messages/{phone}")
def get_all_user_messages(phone: str):

    response = supabase.table("messages") \
        .select("*") \
        .or_(f"sender_phone.eq.{phone},receiver_phone.eq.{phone}") \
        .order("created_at", desc=True) \
        .execute()

    return response.data


@app.get("/messages/{ad_id}/{phone1}/{phone2}")
def get_messages(ad_id: str, phone1: str, phone2: str):

    response = supabase.table("messages") \
        .select("*") \
        .eq("ad_id", ad_id) \
        .or_(
            f"and(sender_phone.eq.{phone1},receiver_phone.eq.{phone2}),"
            f"and(sender_phone.eq.{phone2},receiver_phone.eq.{phone1})"
        ) \
        .order("created_at") \
        .execute()

    return response.data


@app.post("/mark-read/{ad_id}/{receiver_phone}")
def mark_read(ad_id: str, receiver_phone: str):

    supabase.table("messages") \
        .update({"is_read": True}) \
        .eq("ad_id", ad_id) \
        .eq("receiver_phone", receiver_phone) \
        .execute()

    return {"message": "Marked read ✅"}


# ---------------- GET ALL ADS ----------------

@app.get("/ads")
def get_all_ads():

    ads_response = supabase.table("ads") \
        .select("*, ad_images(image_url)") \
        .order("created_at", desc=True) \
        .execute()

    ads = ads_response.data

    for ad in ads:
        ad["images"] = [img["image_url"] for img in ad.get("ad_images", [])]

    return ads


# ---------------- SINGLE AD ----------------

# ---------------- SINGLE AD ----------------

@app.get("/ad/{ad_id}")
def get_single_ad(ad_id: str):

    ad_response = supabase.table("ads") \
        .select("*, ad_images(image_url)") \
        .eq("id", ad_id) \
        .execute()

    if not ad_response.data:
        raise HTTPException(status_code=404, detail="Ad not found")

    ad = ad_response.data[0]

    # ✅ Attach images properly
    ad["images"] = [img["image_url"] for img in ad.get("ad_images", [])]

    # ✅ Attach seller details
    user_response = supabase.table("users") \
        .select("*") \
        .eq("phone", ad["user_phone"]) \
        .execute()

    if user_response.data:
        ad["seller"] = user_response.data[0]
    else:
        ad["seller"] = None

    return ad


    # ---------------- IMAGE UPLOAD ----------------

@app.post("/upload-image")
async def upload_image(image: UploadFile = File(...)):

    file_location = f"uploads/{image.filename}"

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    return {"image_url": f"/uploads/{image.filename}"}



    # ---------------- UPDATE PROFILE ----------------

@app.post("/update-profile")
def update_profile(data: dict):

    supabase.table("users").update({
        "name": data.get("name"),
        "house_no": data.get("house_no"),
        "street_name": data.get("street_name"), 
        "district": data.get("district"),
        "state": data.get("state")
    }).eq("phone", data.get("phone")).execute()

    return {"message": "Profile Updated ✅"}


@app.get("/get-profile/{phone}")
def get_profile(phone: str):

    response = supabase.table("users") \
        .select("name, house_no, street_name, district, state") \
        .eq("phone", phone) \
        .execute()

    return response.data


    # ---------------- DELETE AD ----------------

@app.delete("/ads/{ad_id}")
def delete_ad(ad_id: str):

    # ✅ Delete images first
    supabase.table("ad_images") \
        .delete() \
        .eq("ad_id", ad_id) \
        .execute()

    # ✅ Delete ad
    response = supabase.table("ads") \
        .delete() \
        .eq("id", ad_id) \
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Ad not found")

    return {"message": "Ad deleted successfully ✅"}




