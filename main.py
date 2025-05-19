from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse

app = FastAPI()

# In-memory user state tracking (for demo only; consider persistent storage for prod)
user_states = {}

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

    # Fetch current state or start fresh
    state = user_states.get(user_id, "start")

    # Get form data once to avoid multiple awaits
    form_data = await request.form()

    if state == "start":
        resp.message("Hi! Which country would you like to visit?")
        user_states[user_id] = "waiting_for_country"

    elif state == "waiting_for_country":
        # Basic validation: check if message is not empty and alphabetic
        if message.isalpha():
            user_states[user_id] = "waiting_for_passport"
            user_states[user_id + "_country"] = message.capitalize()  # Save country choice
            resp.message(f"Great choice! Please upload a clear photo of your passport.")
        else:
            resp.message("Please enter a valid country name.")

    elif state == "waiting_for_passport":
        if num_media > 0 and "MediaUrl0" in form_data:
            passport_url = form_data["MediaUrl0"]
            user_states[user_id + "_passport_url"] = passport_url
            resp.message("Thanks! Now upload your supporting documents.")
            user_states[user_id] = "waiting_for_documents"
        else:
            resp.message("Please upload your passport as an image.")

    elif state == "waiting_for_documents":
        if num_media > 0 and "MediaUrl0" in form_data:
            doc_url = form_data["MediaUrl0"]
            user_states[user_id + "_documents_url"] = doc_url
            resp.message("Thank you! We’ll review and get back to you soon.")
            user_states[user_id] = "done"
        else:
            resp.message("Please upload your supporting documents as images.")

    elif state == "done":
        resp.message("You're all set! We'll contact you shortly. If you want to start over, just type 'restart'.")
        if message == "restart":
            user_states[user_id] = "start"
            resp.message("Conversation restarted. Hi! Which country would you like to visit?")

    else:
        resp.message("Sorry, I didn't understand that. Let's start over. Which country would you like to visit?")
        user_states[user_id] = "waiting_for_country"

    return PlainTextResponse(str(resp), media_type="application/xml")
