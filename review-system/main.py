"""
Review System FastAPI app. Main entry point.
Exposes endpoints for GBP OAuth, SMS/email webhooks, trigger ingestion, and health checks.
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from config import ENVIRONMENT, DEBUG
from gbp_verification_flow import gbp_verification
from webhook_router import webhook_router
from trigger_detector import manual_detector

# Setup logging
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

# ==================== Health & Status ====================

@app.get("/")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "review-system",
        "environment": ENVIRONMENT
    }

# ==================== GBP OAuth Flow ====================

@app.get("/gbp/auth/start")
async def gbp_auth_start(sharon_id: str, state: str = None):
    """
    Initiate GBP OAuth flow. Redirect Sharon to Google sign-in.

    Args:
        sharon_id: Sharon's ID in our system
        state: Optional CSRF token

    Returns:
        Redirect to Google OAuth consent screen
    """
    auth_url = gbp_verification.generate_auth_url(state=state or sharon_id)
    logger.info(f"Starting GBP auth for sharon_id: {sharon_id}")
    return RedirectResponse(url=auth_url)

@app.get("/gbp/auth/callback")
async def gbp_auth_callback(code: str, state: str):
    """
    Handle OAuth callback from Google.

    Args:
        code: Authorization code from Google
        state: State parameter (should match sharon_id)

    Returns:
        {
            "success": True|False,
            "message": "...",
            "gbp_profile_id": "..." (if success)
        }
    """
    sharon_id = state  # In production, validate this

    result = gbp_verification.handle_callback(code, sharon_id)

    if result["success"]:
        return {
            "success": True,
            "message": result["message"],
            "gbp_profile_id": result["gbp_profile_id"],
            "gbp_name": result["gbp_name"]
        }
    else:
        raise HTTPException(status_code=400, detail=result["error"])

@app.get("/gbp/status")
async def gbp_status(sharon_id: str):
    """Check if Sharon's GBP is already linked."""
    refresh_token = gbp_verification.get_refresh_token(sharon_id)
    return {
        "sharon_id": sharon_id,
        "gbp_linked": refresh_token is not None
    }

# ==================== SMS Webhooks ====================

@app.post("/webhooks/sms")
async def handle_sms_webhook(request: Request):
    """
    Receive SMS reply from Twilio.

    Twilio sends:
    - POST data with MessageSid, From, Body, etc.
    - X-Twilio-Signature header for validation
    """
    try:
        # Get request data
        form_data = await request.form()
        payload = dict(form_data)

        # Get signature header
        signature = request.headers.get("X-Twilio-Signature", "")

        # Get full request URL
        request_url = str(request.url)

        # Route to handler
        result = webhook_router.handle_sms_reply(payload, request_url, signature)

        logger.info(f"SMS webhook processed: {result['status']}")
        return JSONResponse(result)

    except Exception as e:
        logger.error(f"SMS webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ==================== Email Webhooks ====================

@app.post("/webhooks/email")
async def handle_email_webhook(request: Request):
    """
    Receive email reply from Brevo (placeholder).

    Note: Actual email reply handling depends on Brevo inbound email setup.
    This is a stub for future implementation.
    """
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
    Manually enqueue a course-end trigger (for manual integration or testing).

    Request body:
    {
        "student_id": "...",
        "student_name": "...",
        "student_email": "...",
        "student_phone": "+1xxx",
        "course_id": "...",
        "course_name": "...",
        "course_result": "pass" | "completed"
    }

    Returns:
    {
        "success": True|False,
        "trigger_id": "...",
        "message": "..."
    }
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
    """Get all pending triggers (for polling-based processing)."""
    triggers = manual_detector.detect_triggers()
    return {
        "count": len(triggers),
        "triggers": triggers
    }

# ==================== Startup & Shutdown ====================

@app.on_event("startup")
async def startup():
    logger.info(f"Review System starting (environment: {ENVIRONMENT})")

@app.on_event("shutdown")
async def shutdown():
    logger.info("Review System shutting down")

# ==================== Run ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG
    )
