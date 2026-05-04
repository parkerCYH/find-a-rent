

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Discord Webhook ────────────────────────────────────────────────
    DISCORD_WEBHOOK_URL: str = ""

    # ── Google Sheets ──────────────────────────────────────────────────
    GCP_SERVICE_ACCOUNT_FILE: str = "service_account.json"
    GOOGLE_SHEET_ID: str = ""
    SHEET_NAME: str = "houses"
    BLACKLIST_SHEET_NAME: str = "black_list"
    BLACKLIST_ADDR_SHEET_NAME: str = "black_addr_list"

    BASE_URL: str = ""

    
    QUERY_1: str = ""
    QUERY_2: str = ""

    # ── 服務設定 ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


settings = Settings()
