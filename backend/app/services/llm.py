"""Local LLM access. Ollama is the only implementation; no cloud service is called."""

import logging
import time
from typing import Protocol, TypeVar

import httpx
import ollama
from pydantic import BaseModel, ValidationError

from app.config import Settings

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)
MAX_RETRIES = 2


class LLMError(RuntimeError):
    """A local LLM failure with a message that can be shown to the dentist."""


class LLMClient(Protocol):
    """Anything able to return JSON validated against a Pydantic schema."""

    def generate_json(self, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        """Generate and validate one structured response."""
        ...


class OllamaClient:
    """LLMClient backed by a local Ollama server."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ollama.Client(host=settings.ollama_host, timeout=settings.llm_timeout_s)

    def generate_json(self, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        """Call the model with a JSON schema, retrying when validation fails."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            content = self._chat(messages, schema)
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                error = exc
                logger.warning("Invalid LLM output (attempt %d)", attempt + 1)
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"Invalid JSON for the schema: {exc}. Fix it.",
                    },
                ]
        raise LLMError(f"The local model returned an invalid answer: {error}")

    def _chat(self, messages: list[dict], schema: type[BaseModel]) -> str:
        started = time.perf_counter()
        try:
            response = self.client.chat(
                model=self.settings.llm_model,
                messages=messages,
                format=schema.model_json_schema(),
                think=self.settings.llm_think,
                keep_alive="30m",
                options={
                    "temperature": self.settings.llm_temperature,
                    "num_ctx": self.settings.llm_num_ctx,
                },
            )
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                model = self.settings.llm_model
                raise LLMError(f"Model not found. Run: ollama pull {model}") from exc
            raise LLMError(f"Ollama error: {exc.error}") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("The local model timed out.") from exc
        except (ConnectionError, httpx.ConnectError) as exc:
            raise LLMError("Ollama is not running. Start the Ollama app.") from exc
        logger.info(
            "LLM call: %.1fs, prompt_tokens=%s, output_tokens=%s",
            time.perf_counter() - started,
            response.get("prompt_eval_count"),
            response.get("eval_count"),
        )
        return response["message"]["content"]

    def health(self) -> str:
        """Return 'ok' or a short description of the problem."""
        try:
            client = ollama.Client(host=self.settings.ollama_host, timeout=3)
            names = [model.model for model in client.list().models]
        except Exception:  # noqa: BLE001 - health must never raise
            return "ollama not running"
        return "ok" if self.settings.llm_model in names else "model not pulled"
