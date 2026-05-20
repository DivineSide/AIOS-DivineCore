from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    REDIS_URL: str = "redis://localhost:6379/0"

    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    SUPABASE_URL: str = ""
    SUPABASE_SECRET_KEY: str = ""
    SUPABASE_DB_URL: str = ""

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    CATEGORIZER_MODEL: str = "openai/gpt-4o-mini"

    FATHOM_API_KEY: str = ""
    FATHOM_API_BASE_URL: str = "https://api.fathom.ai/external/v1"
    FATHOM_POLL_LOOKBACK_HOURS: int = 24

    # Upwork integration
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REFRESH_TOKEN: str = ""
    UPWORK_PROPOSAL_TEMPLATE_ID: str = "1BnxRE-zYcri2VuUD5g8M9dzs0sRfNgP2JGU3ek6ztlY"
    UPWORK_TRACKING_SHEET_ID: str = "1yW6xojrzpgj9fBVz3BD_d6PScVqp5XjlbxrD38iZtxU"
    UPWORK_PROPOSAL_FIELDS_MODEL: str = "openai/gpt-4o-mini"
    UPWORK_APPLICATION_MODEL: str = "openai/gpt-5.1"

    # Instantly integration
    INSTANTLY_API_KEY: str = ""
    INSTANTLY_API_BASE_URL: str = "https://api.instantly.ai"
    DISCORD_OUTREACH_WEBHOOK_URL: str = ""
    DISCORD_OUTREACH_THREAD_ID: str = ""

    # Branding OS agents
    IMAGYN_BOT_TOKEN: str = ""
    LYRA_BOT_TOKEN: str = ""

    # Upwork jobs feed (Apify-based scraper)
    APIFY_API_TOKEN: str = ""
    APIFY_UPWORK_ACTOR_ID: str = "neatrat/upwork-job-scraper"
    UPWORK_SEARCH_URL: str = ""

    # Social performance tracker (LinkedIn + X via Apify, hook/closing annotation via OpenRouter)
    # Comma-separated lists so multiple authors can be tracked without a config table.
    SOCIAL_PERF_LINKEDIN_PROFILES: str = ""  # e.g. "https://www.linkedin.com/in/foo,https://www.linkedin.com/in/bar"
    SOCIAL_PERF_X_HANDLES: str = ""          # e.g. "foo,bar" (no leading @)
    APIFY_LINKEDIN_ACTOR_ID: str = "apimaestro/linkedin-profile-posts"
    APIFY_X_ACTOR_ID: str = "apidojo/tweet-scraper"
    SOCIAL_PERF_ANNOTATOR_MODEL: str = "openai/gpt-4o-mini"


settings = WorkerSettings()
