from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def csv_list(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Enfactum AI Assistant"
    host: str = "0.0.0.0"
    port: int = 8080
    environment: str = "development"
    cors_origins: str = ""
    data_dir: Path = Path("data")

    llm_provider: str = "auto"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_context_window: int = 0
    llm_supports_vision: bool = True
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 30
    llm_max_retries: int = 1
    # For reasoning models (o-series, gpt-5, gemini-2.5...): minimal | low | medium | high. Empty = not sent.
    llm_reasoning_effort: str = ""

    # OCR (text from images / scanned PDFs): auto | tesseract | llm | none
    ocr_provider: str = "auto"
    ocr_model: str = ""
    ocr_base_url: str = ""
    ocr_api_key: str = ""
    ocr_max_pages: int = 30

    # Generated files and images
    file_generation_enabled: bool = True
    image_generation: str = "auto"   # auto (on for OpenAI keys) | on | off
    image_model: str = "gpt-image-1"
    image_base_url: str = ""
    image_api_key: str = ""

    # Agentic actions (write operations, always confirmed by the employee)
    ai_actions_enabled: bool = True
    action_expiry_minutes: int = 15

    # Who may open the app. Enfactum OS has two user types: employee and client.
    allowed_user_types: str = "employee"
    os_user_type_field: str = "user_type"
    client_roles: str = "client"

    embedding_provider: str = "llm"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"

    web_search_provider: str = "auto"
    tavily_api_key: str = ""
    web_search_max_results: int = 5
    web_fetch_pages: int = 1
    web_timeout_seconds: float = 6

    auth_mode: str = "demo"
    demo_users_file: Path = Path("config/demo_users.yaml")
    os_base_url: str = ""
    os_user_endpoint: str = "/api/user"
    os_user_id_field: str = "id"
    os_user_name_field: str = "name"
    os_user_email_field: str = "email"
    os_user_roles_field: str = "roles"
    os_user_permissions_field: str = "permissions"
    os_forward_cookies: bool = False
    os_verify_ssl: bool = True
    auth_cache_seconds: int = 60

    jwt_secret: str = ""
    jwt_public_key_file: str = ""
    jwt_algorithms: str = "HS256"
    jwt_audience: str = ""
    jwt_issuer: str = ""

    os_tools_file: Path = Path("config/os_tools.yaml")
    mock_os_enabled: bool = False
    seed_sample_docs: bool = False

    company_db_dsn: str = ""
    db_tools_file: Path = Path("config/db_tools.yaml")
    db_statement_timeout_ms: int = 5000

    admin_roles: str = "super_admin,admin"
    perm_chat: str = ""
    perm_web_search: str = ""
    perm_documents_manage: str = "ai.documents.manage"

    rag_chunk_size: int = 1200
    rag_chunk_overlap: int = 200
    rag_top_k: int = 6
    max_upload_mb: int = 25
    max_attachment_mb: int = 20
    attachment_context_chars: int = 48000
    max_tool_rounds: int = 4
    tool_timeout_seconds: float = 12
    history_turns: int = 12
    rate_limit_per_minute: int = 30

    @field_validator("data_dir", "demo_users_file", "os_tools_file", "db_tools_file", mode="after")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BASE_DIR / value).resolve()

    @field_validator("llm_api_key", "embedding_api_key", "tavily_api_key", "llm_base_url", "llm_model",
                     "embedding_base_url", "company_db_dsn", "ocr_api_key", "image_api_key", mode="before")
    @classmethod
    def _clean(cls, value):
        # Tolerate the most common .env mistakes: surrounding quotes, spaces, "Bearer " prefix.
        if isinstance(value, str):
            value = value.strip().strip("'\"").strip()
            if value.lower().startswith("bearer "):
                value = value[7:].strip()
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def admin_role_set(self) -> frozenset[str]:
        return frozenset(csv_list(self.admin_roles))


# provider: (base_url, default chat model, context window, default embedding model or "" if unsupported)
LLM_PRESETS: dict[str, tuple[str, str, int, str]] = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", 128_000, "text-embedding-3-small"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash", 1_000_000,
               "text-embedding-004"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", 128_000, ""),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o-mini", 128_000, ""),
    "anthropic": ("https://api.anthropic.com/v1/", "claude-3-5-haiku-latest", 200_000, ""),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest", 128_000, "mistral-embed"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat", 64_000, ""),
    "xai": ("https://api.x.ai/v1", "grok-2-latest", 131_072, ""),
    "ollama": ("http://localhost:11434/v1", "qwen2.5:14b", 32_768, "nomic-embed-text"),
}
_KEY_PREFIXES = [("sk-or-", "openrouter"), ("sk-ant-", "anthropic"), ("gsk_", "groq"), ("AIza", "gemini"),
                 ("xai-", "xai")]
_HOSTS = {"openai.com": "openai", "googleapis.com": "gemini", "groq.com": "groq", "openrouter.ai": "openrouter",
          "anthropic.com": "anthropic", "mistral.ai": "mistral", "deepseek.com": "deepseek", "x.ai": "xai",
          ":11434": "ollama"}
LOCAL_PROVIDERS = {"ollama", "custom-local"}


@dataclass(frozen=True)
class LLMProfile:
    provider: str
    base_url: str
    model: str
    context_window: int
    embedding_model: str
    key_missing: bool


def _detect_provider(s: Settings) -> str:
    if s.llm_provider and s.llm_provider.lower() != "auto":
        return s.llm_provider.lower()
    if s.llm_base_url:
        for host, name in _HOSTS.items():
            if host in s.llm_base_url:
                return name
        local = any(h in s.llm_base_url for h in ("localhost", "127.0.0.1", "host.docker.internal", "0.0.0.0"))
        return "custom-local" if local else "custom"
    for prefix, name in _KEY_PREFIXES:
        if s.llm_api_key.startswith(prefix):
            return name
    return "openai"


@lru_cache
def get_llm_profile() -> LLMProfile:
    s = get_settings()
    provider = _detect_provider(s)
    base, model, window, emb = LLM_PRESETS.get(provider, ("", "", 32_768, ""))
    return LLMProfile(
        provider=provider,
        base_url=s.llm_base_url or base,
        model=s.llm_model or model,
        context_window=s.llm_context_window or window,
        embedding_model=s.embedding_model or emb,
        key_missing=not s.llm_api_key and provider not in LOCAL_PROVIDERS,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
