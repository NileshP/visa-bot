from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
import httpx
import os
import psycopg2
import base64

app = FastAPI()

# Temporary in-memory user state
user_states = {}
user_data = {}

# PostgreSQL connection
conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
    port=os.getenv("POSTGRES_PORT", "5432")
)
cursor = conn.cursor()

# Make sure the table exists
cursor.execute("""
    CREATE TABLE IF NOT EXISTS visa_applications (
        id SERIAL PRIMARY KEY,
        user_id TEXT,
        country TEXT,
        first_name TEXT,
        last_name TEXT,
        validity DATE
    );
""")
conn.commit()

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
            print("inside num media")
            passport_url = form["MediaUrl0"]
            print(passport_url)
            resp.message("Thanks! Processing your passport details...")

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
            # You can also store supporting docs if needed
            resp.message("Thank you! We’ll review and get back to you soon.")
            user_states[user_id] = "done"
        else:
            resp.message("Please upload your supporting documents.")

    else:
        resp.message("You're all set. We'll contact you shortly.")

    return PlainTextResponse(str(resp), media_type="application/xml")


async def extract_passport_info(image_url: str) -> dict:
    async with httpx.AsyncClient() as client:
        image_response = await client.get(image_url)
        image_bytes = image_response.content
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Extract the following passport details from this image:\n"
                                "- First Name\n"
                                "- Last Name\n"
                                "- Validity Date (passport expiry)"
                            )
                        },
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": image_base64
                            }
                        }
                    ]
                }
            ]
        }

        gemini_url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"
        response = await client.post(gemini_url, params={"key": os.getenv("GEMINI_API_KEY")}, json=payload)

        if response.status_code == 200:
            try:
                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]

                # Basic parsing example - improve with regex or parsing logic
                lines = text.splitlines()
                parsed = {
                    "first_name": lines[0].split(":")[-1].strip() if len(lines) > 0 else "Unknown",
                    "last_name": lines[1].split(":")[-1].strip() if len(lines) > 1 else "Unknown",
                    "validity": lines[2].split(":")[-1].strip() if len(lines) > 2 else "2030-01-01"
                }
                return parsed
            except Exception as e:
                print("Parsing error:", e)
                return {}
        else:
            print("Gemini API error:", response.text)
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
