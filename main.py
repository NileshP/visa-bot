from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
import httpx
import os
import psycopg2
import base64
import re
import json

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
        validity DATE,
        passport_number TEXT,
        date_of_birth TEXT
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
        user_states[user_id] = "waiting_for_front_page_passport"

    elif state == "waiting_for_front_page_passport":
        form = await request.form()
        if num_media > 0:
            #print("inside num media")
            passport_url = form["MediaUrl0"]
            #print(passport_url)
            resp.message("Thanks! Processing your passport details...")

            extracted_info = await extract_passport_info(passport_url)

            print(extracted_info)

            if extracted_info:
                if(extracted_info["is_valid_passport"] and extracted_info["all_info_extracted"]):
                    user_data[user_id].update(extracted_info)
                    store_user_data(user_id, user_data[user_id])
                    resp.message(f"Hi {user_data[user_id]["first_name"]} {user_data[user_id]["last_name"]} Passport info saved! Please upload supporting documents.")
                    user_states[user_id] = "waiting_for_documents"
                else:
                    resp.message("Seems you have uploaded wrong passport, can you please upload valid passport")
                    user_states[user_id] = "waiting_for_front_page_passport"
            else:
                resp.message("Sorry, there was an error while extracting information, please retry")
                user_states[user_id] = "waiting_for_front_page_passport"
        else:
            resp.message("Please upload your passport as an image.")
            user_states[user_id] = "waiting_for_front_page_passport"

    elif state == "waiting_for_documents":
        form = await request.form()
        if num_media > 0:
            # You can also store supporting docs if needed
            resp.message("Thank you! We’ll review and get back to you soon.")
            user_states[user_id] = "done"
        else:
            resp.message("Please upload your supporting documents.")
            user_states[user_id] = "waiting_for_documents"
    else:
        resp.message("You're all set. We'll contact you shortly.")

    return PlainTextResponse(str(resp), media_type="application/xml")


async def extract_passport_info(image_url: str) -> dict:
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    print("started executing passport info")
    print("twilio sid", twilio_sid)
    print("twilio_auth_token",twilio_auth_token)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        
        # Download media with Twilio authentication
        image_response = await client.get(
            image_url,
            auth=(twilio_sid, twilio_auth_token)
        )
        print("Status Code",image_response.status_code)
        image_bytes = image_response.content
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        headers = {
            "Content-Type": "application/json"
        }

        prompt = """
            Extract the following details from the provided passport image and return the output strictly in JSON format:

            - First Name as `first_name`
            - Last Name as `last_name`
            - Passport Number as `passport_number`
            - Date of Birth as `date_of_birth` (in DD/MM/YYYY format)
            - Validity Date (passport expiry) as `validity`

            Additionally, include the following fields in the JSON:
            - `all_info_extracted`: true if all the above fields were successfully extracted, otherwise false
            - `is_valid_passport`: true if the image appears to be a valid passport, otherwise false

            Ensure the output is valid JSON with no additional text — return only the JSON object.
            """

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (prompt)
                        },
                        {
                            "inlineData": {
                                "mimeType": "image/png",
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

                print("text from gemini")

                print(text)

                parsed = parse_passport_info(text)

                return parsed
            except Exception as e:
                print("Parsing error:", e)
                return {}
        else:
            print("Gemini API error:", response.text)
            return {}

def parse_passport_info(text: str) -> dict:
    try:
        lines = text.splitlines()
        json_str = "\n".join(lines[1:-1])  # Skip first and last line
        print("Json Str", json_str)
        data = json.loads(json_str)
        print("Data", data)
        return data
    except Exception as e:
        print("Simple JSON parse error:", e)
        return {}

def store_user_data(user_id: str, data: dict):
    try:
        cursor.execute("""
            INSERT INTO visa_applications (user_id, country, first_name, last_name, validity, passport_number, date_of_birth)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, data["country"], data["first_name"], data["last_name"], data["validity"], data["passport_number"], data["date_of_birth"]))
        conn.commit()
    except Exception as e:
        print("Database error:", e)
        conn.rollback()
