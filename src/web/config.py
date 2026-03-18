from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    output_dir: Path = Path("output")
    queue_poll_seconds: int = 30
    host: str = "0.0.0.0"
    port: int = 8000

    batch_email_template: Path = Path("templates/sharegradeasy.html")
    batch_email_csv: Path = Path("vault/teachers.csv")
    batch_email_size: int = 100

    model_config = {"env_prefix": "MMN_WEB_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
