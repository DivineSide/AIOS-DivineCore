"""Constants for the Upwork integration. Single place to change template/sheet IDs."""

from settings import settings

PROPOSAL_TEMPLATE_ID = settings.UPWORK_PROPOSAL_TEMPLATE_ID
TRACKING_SHEET_ID = settings.UPWORK_TRACKING_SHEET_ID

PROPOSAL_PLACEHOLDERS = (
    "titleOfSystem",
    "briefExplanationOfSystem",
    "stepByStepBulletPoints",
    "leftToRightFlowWithArrows",
    "aboutMeBulletPoints",
)

TRACKING_SHEET_NAME = "Sheet1"
TRACKING_SHEET_RANGE = f"{TRACKING_SHEET_NAME}!A:Z"
TRACKING_SHEET_CONNECTS_COLUMN = "E"
TRACKING_SHEET_LOOM_COLUMN = "I"
