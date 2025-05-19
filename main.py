from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
import httpx
import os
import psycopg2

app = FastAPI()

# Temporary in-memory user state
user_states = {}
user_data = {}

# PostgreSQL connection (update with Railway credentials or env variables)
conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
    port=os.getenv("POSTGRES_PORT", "5432")
)
cursor = conn.cursor()

@app.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    NumMedia: str = Form(default="0")
):
    user_id = From
    message = Body.strip().lower()
    num_media = int(NumMedia)
    resp = MessagingResponse()

    state = user_states.get(user_id, "start")

    if state == "start":
        resp.message("Hi! Which country would you like to visit?")
        user_states[user_id] = "waiting_for_country"

    elif state == "waiting_for_country":
        user_data[user_id] = {"country": message}
        resp.message("Great! Please upload a clear photo of your passport.")
        user_states[user_id] = "waiting_for_passport"

    elif state == "waiting_for_passport":
        form = await request.form()
        if num_media > 0:
            passport_url = form["MediaUrl0"]
            resp.message("Thanks! Processing your passport details...")

            # Call Gemini API to extract data
            extracted_info = await extract_passport_info(passport_url)

            if extracted_info:
                user_data[user_id].update(extracted_info)
                store_user_data(user_id, user_data[user_id])
                resp.message("Passport info saved! Please upload supporting documents.")
                user_states[user_id] = "waiting_for_documents"
            else:
                resp.message("Sorry, couldn't extract info. Please try again.")
        else:
            resp.message("Please upload your passport as an image.")

    elif state == "waiting_for_documents":
        form = await request.form()
        if num_media > 0:
            doc_url = form["MediaUrl0"]
            # You can choose to store it too
            resp.message("Thank you! We’ll review and get back to you soon.")
            user_states[user_id] = "done"
        else:
            resp.message("Please upload your supporting documents.")

    else:
        resp.message("You're all set. We'll contact you shortly.")

    return PlainTextResponse(str(resp), media_type="application/xml")


async def extract_passport_info(image_url: str) -> dict:
    # Download image content
    async with httpx.AsyncClient() as client:
        image_response = await client.get(image_url)
        image_bytes = image_response.content

        # Send to Gemini API (replace with real API call)
        headers = {
            "Authorization": f"Bearer {os.getenv('GEMINI_API_KEY')}",
            "Content-Type": "application/json"
        }
        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_bytes.decode("latin1")  # For raw bytes, better to use base64
                            }
                        }
                    ]
                }
            ]
        }

        response = await client.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent", headers=headers, json=data)
        if response.status_code == 200:
            # Extract and return relevant fields
            result = response.json()
            # TODO: Replace with actual parsing logic
            return {
                "first_name": "Sample",
                "last_name": "Name",
                "validity": "2030-01-01"
            }
        else:
            print("Gemini error:", response.text)
            return {}


def store_user_data(user_id: str, data: dict):
    try:
        cursor.execute("""
            INSERT INTO visa_applications (user_id, country, first_name, last_name, validity)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, data["country"], data["first_name"], data["last_name"], data["validity"]))
        conn.commit()
    except Exception as e:
        print("Database error:", e)
        conn.rollback()
