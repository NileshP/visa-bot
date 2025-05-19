from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()

@app.post("/webhook")
async def webhook_debug(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...)
):
    form = await request.form()
    print("🔍 Incoming Twilio Webhook:")
    for key, value in form.items():
        print(f"{key}: {value}")
    
    return PlainTextResponse("Got your message! ✅")
