

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LINE Messaging API ─────────────────────────────────────────────
    LINE_CHANNEL_ACCESS_TOKEN: str = ""
    LINE_GROUP_ID: str = ""

    # ── Google Sheets ──────────────────────────────────────────────────
    GCP_SERVICE_ACCOUNT_FILE: str = "service_account.json"
    GOOGLE_SHEET_ID: str = ""
    SHEET_NAME: str = "houses"

    # ── 591 搜尋條件（完整 query string，直接在 .env 組好）────────────
    # 範例：region=1&section=10&price=20000_30000&layout=1,2&other=lift,balcony_1&shape=2&bathroom=1&notice=not_cover
    QUERY_1: str = ""
    QUERY_2: str = ""

    # ── 服務設定 ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


settings = Settings()
