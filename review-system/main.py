"""
Review System FastAPI app.
Endpoints: SMS/email webhooks, trigger ingestion, health check.
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from config import ENVIRONMENT, DEBUG
from webhook_router import webhook_router
from trigger_detector import manual_detector

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Review System",
    description="AI-powered review & referral system for coaching institutes",
    version="0.1.0"
)

# ==================== Health ====================

@app.get("/")
async def health():
    return {"status": "ok", "service": "review-system", "environment": ENVIRONMENT}

# ==================== SMS Webhooks ====================

@app.post("/webhooks/sms")
async def handle_sms_webhook(request: Request):
    """Receive SMS reply from Twilio."""
    try:
        form_data = await request.form()
        payload = dict(form_data)
        signature = request.headers.get("X-Twilio-Signature", "")
        request_url = str(request.url)
        result = webhook_router.handle_sms_reply(payload, request_url, signature)
        logger.info(f"SMS webhook processed: {result['status']}")
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"SMS webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ==================== Email Webhooks ====================

@app.post("/webhooks/email")
async def handle_email_webhook(request: Request):
    """Receive email reply from Brevo."""
    try:
        payload = await request.json()
        result = webhook_router.handle_email_reply(payload)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Email webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ==================== Trigger Ingestion ====================

@app.post("/triggers/enqueue")
async def enqueue_trigger(request: Request):
    """
    Enqueue a course-end trigger. Body:
    { student_id, student_name, student_email, student_phone,
      course_id, course_name, course_result, trigger_source }
    """
    try:
        payload = await request.json()
        result = manual_detector.enqueue_trigger(payload)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Trigger ingestion error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/triggers/pending")
async def get_pending_triggers():
    """List pending triggers."""
    triggers = manual_detector.detect_triggers()
    return {"count": len(triggers), "triggers": triggers}

# ==================== Startup & Shutdown ====================

@app.on_event("startup")
async def startup():
    logger.info(f"Review System starting (environment: {ENVIRONMENT})")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Review System shutting down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=DEBUG)
