"""
Configuration for review-system.
Load from environment variables or .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Gmail (same Google Cloud project — enable Gmail API, add scope, get refresh token)
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")

# Claude / Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Google Review link — just the Place ID, no API needed
# Find it at: https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder
GOOGLE_PLACE_ID = os.getenv("GOOGLE_PLACE_ID", "")
GOOGLE_REVIEW_URL = f"https://search.google.com/local/writereview?placeid={GOOGLE_PLACE_ID}" if GOOGLE_PLACE_ID else ""

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = ENVIRONMENT == "development"

# Validate required vars on startup
REQUIRED = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY",
]

missing = [var for var in REQUIRED if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
