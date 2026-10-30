"""Application settings, read only from the environment (or a local .env file)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class AppEnv(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class StorageBackend(StrEnum):
    LOCAL = "local"
    SUPABASE = "supabase"


class AIMode(StrEnum):
    MOCK = "mock"
    LIVE = "live"


class MediaForModels(StrEnum):
    """How media reaches a model: inline as a data URL, or as a signed HTTPS link."""

    DATA_URL = "data_url"
    SIGNED_URL = "signed_url"


class Settings(BaseSettings):
    # The repo-root .env (when run from api/) and a local api/.env; the later file wins.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: AppEnv = AppEnv.LOCAL
    web_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5432/reel2play"

    secret_key: SecretStr = SecretStr("dev-only-change-me")
    cron_secret: SecretStr = SecretStr("dev-only-cron-secret")

    storage_backend: StorageBackend = StorageBackend.LOCAL
    local_media_dir: Path = Path("var/media")
    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")
    supabase_private_bucket: str = "reel2play-private"
    supabase_public_bucket: str = "reel2play-public"
    signed_url_ttl_seconds: int = 3600

    ai_mode: AIMode = AIMode.MOCK
    media_for_models: MediaForModels = MediaForModels.DATA_URL
    baseten_api_key: SecretStr = SecretStr("")
    baseten_base_url: str = "https://inference.baseten.co/v1"
    spark_model_baseten: str = "meta-models/muse-spark-open"
    fireworks_api_key: SecretStr = SecretStr("")
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    spark_model_fireworks: str = "accounts/fireworks/models/muse-spark-open"
    glimmer_base_url: str = ""
    glimmer_api_key: SecretStr = SecretStr("")
    glimmer_model: str = "meta-models/Muse-Glimmer-30B"
    # SAM 3.1 web endpoint printed by `modal deploy workers/modal/sam.py`
    sam_url: str = ""
    # SAM 3.1 tracking endpoint (feature 7); empty means the same app's "track" endpoint
    sam_track_url: str = ""
    # Modal proxy auth token for our Modal endpoints, written as "<token id>.<token secret>"
    modal_proxy_token: SecretStr = SecretStr("")
    # Modal API token (modal token new), for play-test Sandboxes
    modal_token_id: SecretStr = SecretStr("")
    modal_token_secret: SecretStr = SecretStr("")
    playtest_app: str = "reel2play-playtest"
    # Play-tests: runs per round, and the most fix rounds before a person is asked to look
    tester_runs: int = 3
    max_fix_rounds: int = 3
    usd_to_pkr: float = 280.0

    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    job_stale_after_seconds: int = 900

    max_upload_mb: int = 100
    max_video_seconds: int = 180
    max_photos: int = 6
    # Feature 46: products in one batch upload, one file each
    max_batch_items: int = 12
    # Feature 52: ads an AI assistant may order over MCP per hour, from one address
    mcp_ads_per_hour: int = 10
    # Feature 49: the Reel2Play team's key for reviewing marketplace templates (empty: off)
    admin_key: SecretStr = SecretStr("")

    engine_dist_dir: Path = REPO_ROOT / "engine" / "dist"
    templates_dir: Path = REPO_ROOT / "templates"
    samples_dir: Path = REPO_ROOT / "samples"
    # Try-it runs allowed at once, so a busy demo cannot run up model bills
    max_try_running: int = 3
    max_game_bytes: int = 2 * 1024 * 1024

    # Publishing (features 32 to 35). Game links are <share_base_url>/g/<code>; empty means
    # the API's own address.
    share_base_url: str = ""
    reel_fps: int = 20
    reel_scale: float = 2.0
    # Feature 40: unique win codes. A cap per game per day, and per phone per ten minutes.
    unique_coupons: bool = True
    coupons_per_ad_per_day: int = 2000
    coupons_per_visitor: int = 5
    # Feature 44: after this many plays, too few finishing or winning starts an easier version.
    easier_versions: bool = True
    easier_after_plays: int = 30
    easier_below_completion: float = 0.5
    easier_below_wins: float = 0.4

    # WhatsApp Cloud API (feature 2): Meta for Developers → your app → WhatsApp → API Setup
    whatsapp_token: SecretStr = SecretStr("")
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: SecretStr = SecretStr("")
    whatsapp_verify_token: SecretStr = SecretStr("")
    # Feature 43: the business number players write to (international format, digits only)
    whatsapp_business_number: str = ""
    graph_base_url: str = "https://graph.facebook.com"
    graph_api_version: str = "v26.0"
    # Instagram and Facebook import (feature 3): a Meta app with Facebook Login for Business
    meta_app_id: str = ""
    meta_app_secret: SecretStr = SecretStr("")
    # Optional: a Facebook Login for Business configuration; when set it replaces the scopes.
    meta_login_config_id: str = ""

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    log_level: str = Field(default="INFO")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def share_base(self) -> str:
        return (self.share_base_url or self.api_base_url).rstrip("/")

    @property
    def sam_track_endpoint(self) -> str:
        """The tracking endpoint: set on its own, or next to the segment endpoint."""
        if self.sam_track_url:
            return self.sam_track_url
        return self.sam_url.replace("-segment.", "-track.") if "-segment." in self.sam_url else ""

    @property
    def meta_import_ready(self) -> bool:
        return bool(self.meta_app_id and self.meta_app_secret.get_secret_value())

    @property
    def leads_ready(self) -> bool:
        """Feature 43 needs the WhatsApp keys and the number players write to."""
        return self.whatsapp_ready and bool(self.whatsapp_business_number)

    @property
    def whatsapp_ready(self) -> bool:
        return bool(
            self.whatsapp_token.get_secret_value()
            and self.whatsapp_phone_number_id
            and self.whatsapp_app_secret.get_secret_value()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
