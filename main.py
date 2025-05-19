from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
import uvicorn

app = FastAPI()

@app.post("/webhook")
async def webhook_debug(request: Request):
    form = await request.form()
    print("🔍 Incoming Twilio Webhook:")
    for key, value in form.items():
        print(f"{key}: {value}")
    return PlainTextResponse("Logged data")


# For local testing
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
