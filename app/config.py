

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

    # ── 591 搜尋條件 ───────────────────────────────────────────────────
    REGION: int = 1              # 1 = 台北市
    SECTION: str = ""            # 行政區代碼，逗號分隔，空字串=全部
    PRICE_MIN: int = 0
    PRICE_MAX: int = 0           # 0 = 不限
    LAYOUT: str = ""             # 格局：1=1房, 2=2房, 逗號分隔
    OTHER: str = ""              # 其他：lift=電梯, balcony_1=陽台, 逗號分隔
    SHAPE: str = ""              # 房型：1=獨立套房, 2=整層住家, 3=分租套房
    BATHROOM: str = ""           # 衛浴：1=獨立, 2=共用
    NOTICE: str = ""             # 費用：not_cover=未含, cover=含
    MAX_PAGES: int = 5

    # ── 服務設定 ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


settings = Settings()
