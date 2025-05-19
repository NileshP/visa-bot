from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse

app = FastAPI()

# Temporary in-memory user state
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

    state = user_states.get(user_id, "start")

    if state == "start":
        resp.message("Hi! Which country would you like to visit?")
        user_states[user_id] = "waiting_for_country"

    elif state == "waiting_for_country":
        resp.message("Great choice! Please upload a clear photo of your passport.")
        user_states[user_id] = "waiting_for_passport"

    elif state == "waiting_for_passport":
        if num_media > 0:
            passport_url = (await request.form())["MediaUrl0"]
            # TODO: Save/download passport_url
            resp.message("Thanks! Now upload your supporting documents.")
            user_states[user_id] = "waiting_for_documents"
        else:
            resp.message("Please upload your passport as an image.")

    elif state == "waiting_for_documents":
        if num_media > 0:
            doc_url = (await request.form())["MediaUrl0"]
            # TODO: Save/download doc_url
            resp.message("Thank you! We’ll review and get back to you soon.")
            user_states[user_id] = "done"
        else:
            resp.message("Please upload your supporting documents.")

    else:
        resp.message("You're all set. We'll contact you shortly.")

    return PlainTextResponse(str(resp), media_type="application/xml")
