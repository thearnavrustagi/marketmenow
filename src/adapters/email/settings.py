from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_application_credentials: Path = Path("vertex.json")
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"

    smtp_host: str = "smtp.mail.us-east-1.awsapps.com"
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = ""
    smtp_use_tls: bool = False
    smtp_use_ssl: bool = True
    smtp_send_delay: float = 2.0
    smtp_reconnect_every: int = 25

    # In-context learning from top-performing emails
    top_examples_path: Path = Path("output/email/.email_top_examples.json")
    max_examples_in_prompt: int = 5
    examples_max_age_hours: int = 168  # re-collect weekly

    # Epsilon-greedy exploration vs exploitation for ICL.
    epsilon: float = 0.3

    @property
    def sender_address(self) -> str:
        return self.smtp_from or self.smtp_username

    @property
    def sender_display(self) -> str:
        """Return ``"Name <addr>"`` when a display name is configured."""
        addr = self.sender_address
        if self.smtp_from_name:
            return f"{self.smtp_from_name} <{addr}>"
        return addr
