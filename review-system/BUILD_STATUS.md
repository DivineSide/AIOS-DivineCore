# Review System — Build Status

## ✅ Completed Components (Phase 1)

### Core Modules
1. **config.py** — Configuration & environment variables
   - Loads from .env file
   - Validates required variables on startup

2. **twilio_handler.py** — SMS handler
   - `send_sms()` — Send SMS via Twilio
   - `validate_twilio_webhook()` — Validate webhook signature
   - `parse_sms_reply()` — Parse incoming SMS reply

3. **brevo_handler.py** — Email handler
   - `send_email()` — Send email via Brevo
   - `parse_email_reply()` — Parse email reply (placeholder for future)

4. **claude_conversation.py** — Claude conversation engine
   - `process_reply()` — Classify sentiment + generate response
   - Parses Claude's structured output (sentiment, confidence, action, response)

5. **gbp_verification_flow.py** — GBP OAuth setup
   - `generate_auth_url()` — Redirect Sharon to Google sign-in
   - `handle_callback()` — Exchange auth code for refresh token
   - `get_refresh_token()` — Retrieve encrypted refresh token from DB

6. **gbp_oauth.py** — GBP review operations
   - `get_recent_reviews()` — Fetch reviews from GBP location
   - `post_review_reply_to_gbp()` — Reply to an existing review
   - Token refresh logic

7. **webhook_router.py** — Webhook routing & processing
   - `handle_sms_reply()` — Route SMS replies to Claude
   - `handle_email_reply()` — Route email replies (placeholder)
   - `send_claude_reply()` — Send Claude's response back to student
   - Reply processing pipeline

8. **trigger_detector.py** — Course-end trigger detection
   - `BaseTriggerDetector` — Base class for platform-specific detectors
   - `ManualTriggerDetector` — Manual webhook-based trigger ingestion
   - `enqueue_trigger()` — Webhook endpoint to manually enqueue triggers

9. **main.py** — FastAPI application
   - Endpoints for GBP OAuth (start, callback, status)
   - Endpoints for webhooks (SMS, email, triggers)
   - Health check endpoint

### Supporting Files
- **requirements.txt** — Python dependencies
- **.env.example** — Environment variable template
- **__init__.py** — Package initialization
- **BUILD_STATUS.md** — This file

---

## ⏳ Next Steps (Post-Discovery)

### After Sharon Call & Discovery Questions:

1. **Trigger Detector for Sharon's Platform**
   - If Kajabi: implement `KajabiTriggerDetector` (poll Kajabi API for completed courses)
   - If Teachable: implement `TeachableTriggerDetector`
   - If Google Classroom: implement `GoogleClassroomDetector`
   - If Manual: use `ManualTriggerDetector` as-is

2. **Message Templates**
   - SMS template for review request (different based on course result)
   - Email template for review request
   - SMS template for referral ask (after positive sentiment)

3. **n8n Workflow**
   - Trigger listener → message composition → Twilio/Brevo send
   - Webhook receiver for SMS/email replies
   - Route to Claude, get response, send back

4. **Database Schema (Supabase)**
   - `sharon_gbp_auth` — OAuth refresh tokens (encrypted)
   - `sharon_gbp_profiles` — GBP profile info
   - `review_system_triggers` — Course-end events
   - `review_system_messages` — Sent SMS/emails
   - `review_system_replies` — Student replies + Claude processing
   - `review_system_gbp_posts` — Reviews replied to on GBP
   - `review_system_referrals` — Referral asks + responses

5. **Testing**
   - Unit tests for each handler
   - Integration tests for full flow (trigger → SMS → reply → Claude → GBP)
   - Mock Twilio/Brevo/Claude for local testing

---

## 🔧 Quick Start (Local Development)

1. **Install dependencies:**
   ```bash
   cd review-system
   pip install -r requirements.txt
   ```

2. **Set up .env file:**
   ```bash
   cp .env.example .env
   # Fill in your API keys
   ```

3. **Run locally:**
   ```bash
   python -m uvicorn main:app --reload
   ```

4. **Access:**
   - Health check: http://localhost:8000/
   - GBP OAuth start: http://localhost:8000/gbp/auth/start?sharon_id=test-sharon
   - Swagger docs: http://localhost:8000/docs

---

## 📋 Pre-Build Checklist (Your End)

- [ ] Google Cloud project created
- [ ] Google My Business Business Information API enabled
- [ ] Google My Business Account Management API enabled
- [ ] OAuth 2.0 credentials created (Client ID + Secret)
- [ ] Redirect URI added: http://localhost:8000/gbp/auth/callback
- [ ] OAuth consent screen configured (External audience)
- [ ] Twilio account created, API keys retrieved
- [ ] Brevo account created, API key retrieved
- [ ] Anthropic API key (Claude) obtained
- [ ] Supabase project created, URL + key retrieved
- [ ] Encryption key generated (Python: `from cryptography.fernet import Fernet; Fernet.generate_key()`)

---

## 🚀 Architecture Summary

```
Trigger (course ends)
    ↓
Manual Webhook / Platform API
    ↓
FastAPI Trigger Endpoint
    ↓
Message Composition (SMS/Email templates)
    ↓
Twilio SMS + Brevo Email
    ↓
[Student receives message]
    ↓
[Student replies: SMS or Email]
    ↓
Twilio/Brevo Webhook
    ↓
FastAPI Webhook Endpoint
    ↓
Claude Processing (sentiment + response)
    ↓
Send Claude's Reply (SMS/Email)
    ↓
[Optional] Positive review → GBP Reply
    ↓
[Optional] Ask for Referral
```

---

## 🔐 Security Notes

- Refresh tokens are encrypted in Supabase (Fernet cipher)
- Twilio & Brevo webhook signatures are validated
- OAuth state parameter used to prevent CSRF (currently simple, can be enhanced)
- Never log sensitive data (API keys, tokens, phone numbers)

---

## 📞 Support

- All handlers have logging built-in (DEBUG level)
- FastAPI Swagger docs at `/docs` for endpoint testing
- Error responses include helpful messages

---

**Last Updated:** 2026-06-10
**Status:** Phase 1 Complete — Ready for Discovery & Platform Integration
