from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
import uvicorn

app = FastAPI()

@app.post("/webhook")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...)
):
    # Log incoming message
    print(f"📩 Message from {From}: {Body}")
    
    # Simple logic to reply
    if "hello" in Body.lower():
        response_text = "Hello! 👋 How can I help you with your visa application?"
    elif "visa" in Body.lower():
        response_text = "Please tell me which country you want to visit."
    else:
        response_text = f"You said: {Body}. I'm still learning 😊"

    # Twilio expects plain text response for WhatsApp
    return PlainTextResponse(content=response_text)

# For local testing
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
