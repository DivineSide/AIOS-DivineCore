"""
GBP OAuth handler. Posts reviews to Google Business Profile using stored refresh tokens.
"""
import logging
from datetime import datetime
import requests
from gbp_verification_flow import gbp_verification

logger = logging.getLogger(__name__)

class GBPOAuthHandler:
    def __init__(self):
        self.token_endpoint = "https://oauth2.googleapis.com/token"
        self.gbp_api_base = "https://mybusiness.googleapis.com/v4"
        self.reviews_api_base = "https://mybusiness.googleapis.com/v4/accounts"

    def get_recent_reviews(self, sharon_id: str, account_id: str, gbp_profile_id: str, limit: int = 10) -> dict:
        """
        Fetch recent reviews for Sharon's GBP location.
        Used to monitor for new reviews to reply to.

        Args:
            sharon_id: Sharon's ID in our system
            account_id: Google account ID (from OAuth setup)
            gbp_profile_id: GBP location ID
            limit: Max reviews to fetch

        Returns:
            {
                "success": True|False,
                "reviews": [
                    {
                        "review_id": "...",
                        "reviewer_name": "...",
                        "rating": 5,
                        "review_text": "...",
                        "create_time": "...",
                        "has_reply": True|False
                    }
                ],
                "error": "..." (if failed)
            }
        """
        try:
            access_token = self._refresh_access_token(sharon_id)

            if not access_token:
                return {
                    "success": False,
                    "error": "Could not refresh access token."
                }

            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.reviews_api_base}/{account_id}/locations/{gbp_profile_id}/reviews?pageSize={limit}"

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                reviews = []

                for review in data.get("reviews", []):
                    reviews.append({
                        "review_id": review.get("name", "").split("/")[-1],
                        "reviewer_name": review.get("reviewer", {}).get("displayName", "Anonymous"),
                        "rating": review.get("starRating", 0),
                        "review_text": review.get("comment", ""),
                        "create_time": review.get("createTime", ""),
                        "has_reply": bool(review.get("reply"))
                    })

                logger.info(f"Fetched {len(reviews)} reviews for Sharon {sharon_id}")
                return {
                    "success": True,
                    "reviews": reviews
                }
            else:
                logger.error(f"Failed to fetch reviews: {response.text}")
                return {
                    "success": False,
                    "error": response.text
                }

        except Exception as e:
            logger.error(f"Failed to fetch reviews: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def post_review_reply_to_gbp(self, sharon_id: str, gbp_profile_id: str,
                                  review_id: str, reply_text: str) -> dict:
        """
        Post a reply to an existing review on Google Business Profile.
        This is the actual GBP API capability (posting new reviews is handled by Google's review system).

        Args:
            sharon_id: Sharon's ID
            gbp_profile_id: GBP location ID
            review_id: The review ID to reply to
            reply_text: Sharon's reply text

        Returns:
            {
                "success": True|False,
                "reply_id": "...",
                "error": "..."
            }
        """
        try:
            access_token = self._refresh_access_token(sharon_id)

            if not access_token:
                return {
                    "success": False,
                    "error": "Could not refresh access token."
                }

            # Use My Business Business Information API to post reply
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.reviews_api_base}/{gbp_profile_id}/reviews/{review_id}/reply"

            payload = {
                "comment": reply_text
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code in [200, 201]:
                logger.info(f"Posted reply to review {review_id}")
                return {
                    "success": True,
                    "reply_id": response.json().get("name"),
                    "message": "Reply posted successfully!"
                }
            else:
                logger.error(f"Failed to post reply: {response.text}")
                return {
                    "success": False,
                    "error": response.text
                }

        except Exception as e:
            logger.error(f"Failed to post reply: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def _refresh_access_token(self, sharon_id: str) -> str:
        """Get a fresh access token using the stored refresh token."""
        refresh_token = gbp_verification.get_refresh_token(sharon_id)

        if not refresh_token:
            logger.error(f"No refresh token found for {sharon_id}")
            return None

        payload = {
            "refresh_token": refresh_token,
            "client_id": gbp_verification.client_id,
            "client_secret": gbp_verification.client_secret,
            "grant_type": "refresh_token"
        }

        try:
            response = requests.post(self.token_endpoint, data=payload)
            data = response.json()

            if "access_token" in data:
                return data["access_token"]
            else:
                logger.error(f"Failed to refresh token: {data.get('error', 'Unknown error')}")
                return None

        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return None


# Singleton instance
gbp_handler = GBPOAuthHandler()
