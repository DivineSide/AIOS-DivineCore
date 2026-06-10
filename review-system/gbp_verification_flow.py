"""
GBP OAuth verification flow. Redirects Sharon to Google, handles callback, stores refresh token.
"""
import logging
from datetime import datetime
from urllib.parse import urlencode
from cryptography.fernet import Fernet
from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    ENCRYPTION_KEY,
    SUPABASE_URL,
    SUPABASE_KEY,
)
from supabase import create_client

logger = logging.getLogger(__name__)

class GBPVerificationFlow:
    def __init__(self):
        self.client_id = GOOGLE_CLIENT_ID
        self.client_secret = GOOGLE_CLIENT_SECRET
        self.redirect_uri = GOOGLE_REDIRECT_URI
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.cipher_suite = Fernet(ENCRYPTION_KEY)

        # OAuth endpoints
        self.auth_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_endpoint = "https://oauth2.googleapis.com/token"

    def generate_auth_url(self, state: str = None) -> str:
        """
        Generate Google OAuth authentication URL.
        Sharon will be redirected here to sign in / register.

        Args:
            state: Optional state parameter for security (CSRF token)

        Returns:
            Full auth URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/business.manage",
            "access_type": "offline",  # For refresh token
            "prompt": "consent"  # Force consent screen (gets refresh token on re-auth)
        }

        if state:
            params["state"] = state

        auth_url = f"{self.auth_endpoint}?{urlencode(params)}"
        logger.info(f"Generated auth URL for state: {state}")
        return auth_url

    def handle_callback(self, auth_code: str, sharon_id: str) -> dict:
        """
        Handle OAuth callback. Exchange auth code for refresh token.

        Args:
            auth_code: Authorization code from Google
            sharon_id: Sharon's ID in our system

        Returns:
            {
                "success": True|False,
                "refresh_token": "1//0g..." (if success),
                "gbp_profile_id": "123456789" (if success),
                "error": "..." (if failed)
            }
        """
        try:
            # Exchange code for tokens
            token_response = self._exchange_code_for_token(auth_code)

            if "error" in token_response:
                logger.error(f"Token exchange failed: {token_response['error']}")
                return {
                    "success": False,
                    "error": token_response["error"]
                }

            access_token = token_response["access_token"]
            refresh_token = token_response.get("refresh_token")

            if not refresh_token:
                logger.warning(f"No refresh token returned for {sharon_id}. Ensure 'offline' access was requested.")

            # Get GBP profiles
            gbp_profiles = self._get_gbp_profiles(access_token)

            if not gbp_profiles:
                logger.error(f"No GBP profiles found for {sharon_id}")
                return {
                    "success": False,
                    "error": "No Google Business Profile found. Please verify your account."
                }

            # Use first profile (most common case)
            gbp_profile = gbp_profiles[0]
            gbp_profile_id = gbp_profile.get("name", "").split("/")[-1]  # Extract ID from resource name

            # Store refresh token (encrypted) + profile info
            self._store_gbp_auth(sharon_id, refresh_token, gbp_profile_id, gbp_profile)

            logger.info(f"GBP auth successful for {sharon_id}, profile: {gbp_profile_id}")
            return {
                "success": True,
                "gbp_profile_id": gbp_profile_id,
                "gbp_name": gbp_profile.get("displayName", "Unknown"),
                "message": "Google Business Profile connected successfully!"
            }

        except Exception as e:
            logger.error(f"Callback handling failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def _exchange_code_for_token(self, auth_code: str) -> dict:
        """Exchange authorization code for access + refresh tokens."""
        import requests

        payload = {
            "code": auth_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code"
        }

        response = requests.post(self.token_endpoint, data=payload)
        return response.json()

    def _get_gbp_profiles(self, access_token: str) -> list:
        """Get all GBP profiles for the authenticated user."""
        import requests

        headers = {"Authorization": f"Bearer {access_token}"}
        # Simplified: use My Business Account Management API to list locations
        # Full implementation would use the Business Information API
        url = "https://mybusiness.googleapis.com/v4/accounts?pageSize=10"

        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            # Extract locations from accounts
            profiles = []
            for account in data.get("accounts", []):
                locations = self._get_locations_for_account(account["name"], access_token)
                profiles.extend(locations)
            return profiles
        except Exception as e:
            logger.error(f"Failed to fetch GBP profiles: {str(e)}")
            return []

    def _get_locations_for_account(self, account_name: str, access_token: str) -> list:
        """Get all locations for a GBP account."""
        import requests

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusiness.googleapis.com/v4/{account_name}/locations?pageSize=10"

        try:
            response = requests.get(url, headers=headers)
            return response.json().get("locations", [])
        except Exception as e:
            logger.error(f"Failed to fetch locations: {str(e)}")
            return []

    def _store_gbp_auth(self, sharon_id: str, refresh_token: str, gbp_profile_id: str, gbp_profile: dict):
        """Store encrypted refresh token + profile info in Supabase."""
        encrypted_token = self.cipher_suite.encrypt(refresh_token.encode()).decode()

        self.supabase.table("sharon_gbp_auth").insert({
            "sharon_id": sharon_id,
            "refresh_token": encrypted_token,
            "gbp_profile_id": gbp_profile_id,
            "gbp_name": gbp_profile.get("displayName", ""),
            "created_at": datetime.utcnow().isoformat()
        }).execute()

    def get_refresh_token(self, sharon_id: str) -> str:
        """Retrieve decrypted refresh token for Sharon."""
        result = self.supabase.table("sharon_gbp_auth").select("refresh_token").eq(
            "sharon_id", sharon_id
        ).execute()

        if result.data:
            encrypted_token = result.data[0]["refresh_token"]
            return self.cipher_suite.decrypt(encrypted_token.encode()).decode()

        return None


# Singleton instance
gbp_verification = GBPVerificationFlow()
