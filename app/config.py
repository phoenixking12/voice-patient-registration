from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Real secrets stay in the environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./harbor.db"
    public_base_url: str = "http://127.0.0.1:8000"
    seed: bool = True
    llm_enabled: bool = True

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    def llm_target(self) -> tuple[str, str, str] | None:
        """Prefer the free Groq key. Fall back to OpenAI only when Groq is empty."""
        if not self.llm_enabled:
            return None
        if self.groq_api_key.strip():
            return (self.groq_base_url, self.groq_api_key.strip(), self.groq_model)
        if self.openai_api_key.strip():
            return (self.openai_base_url, self.openai_api_key.strip(), self.openai_model)
        return None

    @property
    def voice_mode(self) -> str:
        target = self.llm_target()
        if target is None:
            return "script"
        if "groq" in target[0]:
            return "groq"
        return "openai"
