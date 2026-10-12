import base64
import logging
import re

import httpx
from openai import APIStatusError, AsyncOpenAI, BadRequestError

from .config import BASE_DIR, Settings, get_llm_profile

log = logging.getLogger(__name__)
_SECRETISH = re.compile(r"\b(sk|gsk|xai|AIza|pk|rk)[-_A-Za-z0-9]{8,}\b")
OPTIONAL_PARAMS = ("parallel_tool_calls", "stream_options", "reasoning_effort")


class LLMNotConfigured(RuntimeError):
    pass


def _timeout(total: float) -> httpx.Timeout:
    # Fail fast on connect; allow `total` seconds between streamed chunks.
    return httpx.Timeout(total, connect=5.0)


class LLM:
    """OpenAI-compatible chat client (OpenAI, Gemini, Groq, OpenRouter, Anthropic, Mistral, Ollama, vLLM...)."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.profile = get_llm_profile()
        self.client = AsyncOpenAI(base_url=self.profile.base_url or None,
                                  api_key=settings.llm_api_key or "local-no-key",
                                  timeout=_timeout(settings.llm_timeout_seconds),
                                  max_retries=settings.llm_max_retries)
        self._unsupported: set[str] = set()
        if self.profile.key_missing:
            env = BASE_DIR / ".env"
            log.error("LLM_API_KEY is empty (expected in %s%s). Chat will not work until it is set.",
                      env, "" if env.exists() else " - file does not exist; copy .env.example to .env")
        log.info("LLM provider=%s model=%s base_url=%s context_window=%d", self.profile.provider,
                 self.profile.model, self.profile.base_url or "(default)", self.profile.context_window)

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        if self.profile.key_missing:
            raise LLMNotConfigured("LLM_API_KEY is not set")
        kwargs = dict(model=self.profile.model, messages=messages, temperature=self.s.llm_temperature,
                      max_tokens=self.s.llm_max_tokens, stream=True, stream_options={"include_usage": True})
        if self.s.llm_reasoning_effort:
            kwargs["reasoning_effort"] = self.s.llm_reasoning_effort
            kwargs.pop("temperature")
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = True
        for p in self._unsupported:
            kwargs.pop(p, None)
        try:
            return await self.client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            dropped = [p for p in OPTIONAL_PARAMS if p in kwargs]
            if not dropped:
                raise
            log.info("Provider rejected optional params %s (%s); retrying without them", dropped, describe_error(exc))
            self._unsupported.update(dropped)
            for p in dropped:
                kwargs.pop(p)
            return await self.client.chat.completions.create(**kwargs)

    async def complete(self, messages: list[dict], max_tokens: int = 800, model: str | None = None,
                       client: AsyncOpenAI | None = None) -> str:
        resp = await (client or self.client).chat.completions.create(
            model=model or self.profile.model, messages=messages, max_tokens=max_tokens, temperature=0)
        return resp.choices[0].message.content or ""

    async def check(self) -> dict:
        """Tiny round-trip used by Settings → About to verify the key/model."""
        if self.profile.key_missing:
            return {"ok": False, "error": "LLM_API_KEY is not set in .env"}
        try:
            await self.client.chat.completions.create(model=self.profile.model, max_tokens=1,
                                                      messages=[{"role": "user", "content": "ping"}])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": friendly_error(exc)}


class VisionReader:
    """Transcribes text from images with a vision-capable model (used for OCR when Tesseract is unavailable)."""

    PROMPT = ("Transcribe ALL text in this image exactly as written, preserving reading order, line breaks, "
              "headings, lists and table structure (use Markdown tables for tables). If the image has no text, "
              "describe its content in 2-3 sentences instead. Output only the transcription.")

    def __init__(self, settings: Settings, llm: LLM):
        self.s = settings
        self.llm = llm
        self.model = settings.ocr_model or llm.profile.model
        self.client = llm.client
        if settings.ocr_base_url or settings.ocr_api_key:
            self.client = AsyncOpenAI(base_url=settings.ocr_base_url or llm.profile.base_url or None,
                                      api_key=settings.ocr_api_key or settings.llm_api_key or "local-no-key",
                                      timeout=_timeout(60), max_retries=1)

    @property
    def available(self) -> bool:
        return (self.s.llm_supports_vision or bool(self.s.ocr_model)) and not (
            self.llm.profile.key_missing and not self.s.ocr_api_key)

    async def read(self, data: bytes, mime: str) -> str:
        url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        return await self.llm.complete(
            [{"role": "user", "content": [{"type": "text", "text": self.PROMPT},
                                          {"type": "image_url", "image_url": {"url": url}}]}],
            max_tokens=3000, model=self.model, client=self.client)


def describe_error(exc: Exception) -> str:
    msg = ""
    if isinstance(exc, APIStatusError):
        body = exc.body
        if isinstance(body, dict):
            err = body.get("error", body)
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
        msg = msg or exc.message
        msg = f"HTTP {exc.status_code}: {msg}"
    else:
        msg = str(exc)
    return _SECRETISH.sub("[key]", msg)[:300]


def friendly_error(exc: Exception) -> str:
    p = get_llm_profile()
    name = type(exc).__name__
    detail = describe_error(exc)
    where = f"provider '{p.provider}', model '{p.model}'"
    if isinstance(exc, LLMNotConfigured):
        return "The AI model is not configured: set LLM_API_KEY in the .env file and restart the server."
    if name == "AuthenticationError":
        return (f"The AI provider rejected the API key ({where}). Check that LLM_API_KEY is valid and belongs to "
                f"this provider; set LLM_PROVIDER or LLM_BASE_URL if you use a non-OpenAI key. Details: {detail}")
    if name == "PermissionDeniedError":
        return f"The API key has no access to this model ({where}). Details: {detail}"
    if name == "RateLimitError":
        return f"The AI provider is rate-limiting or the account has no credit ({where}). Details: {detail}"
    if name in ("APIConnectionError", "APITimeoutError"):
        return f"The AI provider at {p.base_url or 'api.openai.com'} did not respond in time. Check network / LLM_BASE_URL."
    if name == "NotFoundError":
        return f"Model '{p.model}' was not found at this provider. Set LLM_MODEL to a model your key can use."
    if name == "BadRequestError":
        return f"The AI provider rejected the request ({where}). Make sure the model supports tool calling. {detail}"
    return "Something went wrong while generating the answer. Please try again."
