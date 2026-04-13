"""
Orbi — application settings (via environment variables or .env file).
When runnig  via Docker, set env vars in docker-compose.yml.
docker-compose.yml override this file's defaults.

OCS_MODE controls which charging system handles rating and balance management:

  orbi-native  — Orbi's built-in rater. Handles bundle deduction and OOB
                 charging using its own DB tables. No external dependencies.
                 Use this for: development, demos, operators without CGRateS.

  cgrates      — Delegates balance management and CDR rating to CGRateS.
                 Orbi handles provisioning, invoicing, and customer management.
                 CGRateS handles real-time charging and balance deduction.
                 Use this for: production MVNOs with CGRateS already deployed.

Switching between modes requires only changing OCS_MODE in .env and restarting.
No code changes needed.

"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./orbi.db" # Default to SQLite for easy local dev, switch to PostgreSQL in production via env var or docker-compose.yml
    DB_ECHO: bool = False

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    API_KEY_HEADER: str = "X-API-Key"

    # Mediation
    SFTP_HOST: str = ""
    SFTP_PORT: int = 22
    SFTP_USER: str = ""
    SFTP_PASSWORD: str = ""
    SFTP_DROP_PATH: str = "/drop"
    SFTP_ARCHIVE_PATH: str = "/archive"
    SFTP_POLL_INTERVAL_SECONDS: int = 300  # 5 minutes

    # App
    APP_NAME: str = "Orbi Billing"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # ── OCS Mode — which charging system to use ───────────────────────────
    OCS_MODE: Literal["orbi-native", "cgrates"] = "cgrates" #"orbi-native"

    # ── CGRateS (required when OCS_MODE=cgrates) ──────────────────────────
    CGRATES_API_URL:          str = "http://cgrates:2080"             # e.g. http://cgrates:2080
    CGRATES_TENANT:           str  = "cgrates.org"
    CGRATES_VERIFY_SSL:       bool = False
    CGRATES_CURRENCY_MULT:    int  = 100            # CGRateS cost unit → pence
    CGRATES_TIMEOUT_SECONDS:  int  = 10
    CGRATES_CDR_PULL_HOURS:   int  = 24             # how far back to pull CDRs per billing run

    # ── Provisioning (OmniHSS + CGRateS account management) ──────────────
    HSS_API_URL:      str = "http://omnihss:8080/api/v1"
    CGRATES_API_URL_PROV: str = ""                  # can differ from rating URL
    PROVISIONING_ENABLED: bool = False              # its getting set via property below i.e. provisioning_configured

    # ── Mediation ─────────────────────────────────────────────────────────
    SFTP_HOST:                str = ""
    SFTP_PORT:                int = 22
    SFTP_USER:                str = ""
    SFTP_PASSWORD:            str = ""
    SFTP_DROP_PATH:           str = "/drop"
    SFTP_ARCHIVE_PATH:        str = "/archive"
    SFTP_POLL_INTERVAL_SECONDS: int = 300
    
    # Self-care + alerts
    ORBI_PUBLIC_URL: str = "http://localhost:5173/"   # used in CGRateS webhook URL
    BALANCE_POLL_INTERVAL_MINUTES: int = 15           # how often to poll CGRateS balances
    LOW_BALANCE_THRESHOLD_PENCE: int = 500            # £5.00 — alert threshold

    @property
    def using_cgrates(self) -> bool:
        return self.OCS_MODE == "cgrates"

    @property
    def cgrates_configured(self) -> bool:
        return bool(self.CGRATES_API_URL)

    @property
    def provisioning_configured(self) -> bool:
        return bool(self.HSS_API_URL and (self.CGRATES_API_URL or self.CGRATES_API_URL_PROV))
        
settings = Settings()