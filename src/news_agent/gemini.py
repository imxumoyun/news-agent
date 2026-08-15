"""Gemini API ustidagi yupqa qatlam.

Barcha agentlar shu yerdan o'tadi: strukturali JSON chiqish, qayta urinish va
token sarfini hisoblash bir joyda turadi.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import Any, TypeVar

from google import genai
from google.genai import errors
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Vaqtinchalik xatolar — qayta urinishga arziydi.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

# Gemini 429 javobida "Please retry in 28.46s" deb aniq vaqt beradi — taxmin
# qilgandan ko'ra o'shanga quloq solgan afzal.
_RETRY_AFTER = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)
MAX_RETRY_WAIT = 70.0


def _retry_after(exc: Exception) -> float | None:
    match = _RETRY_AFTER.search(str(exc))
    if not match:
        return None
    return min(float(match.group(1)) + 1.0, MAX_RETRY_WAIT)


class UsageTracker:
    """Yugurish davomidagi token sarfini yig'ib boradi."""

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def record(self, usage: Any) -> None:
        self.calls += 1
        if usage is None:
            return
        self.input_tokens += getattr(usage, "total_input_tokens", None) or 0
        # Thinking token'lar ham chiqish sifatida hisoblanadi.
        self.output_tokens += (getattr(usage, "total_output_tokens", None) or 0) + (
            getattr(usage, "total_thought_tokens", None) or 0
        )

    def summary(self) -> str:
        return (
            f"{self.calls} chaqiruv, "
            f"{self.input_tokens:,} kirish + {self.output_tokens:,} chiqish token"
        )


class GeminiClient:
    def __init__(self, api_key: str, max_retries: int = 4, rpm_limit: int = 5) -> None:
        self._client = genai.Client(api_key=api_key)
        self.max_retries = max_retries
        self.usage = UsageTracker()

        # Bepul tarifda daqiqasiga bir necha chaqiruvga ruxsat beriladi. Chaqiruvlar
        # orasida majburiy pauza qo'ymasak, yarmi 429 bilan qaytadi.
        self._min_interval = 60.0 / rpm_limit if rpm_limit > 0 else 0.0
        self._gate = asyncio.Lock()
        self._next_slot = 0.0

    async def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._gate:
            now = time.monotonic()
            wait = self._next_slot - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_slot = now + self._min_interval

    async def structured(
        self,
        *,
        model: str,
        prompt: str,
        schema: type[T],
        tools: list[dict] | None = None,
        system: str | None = None,
        timeout: float = 180.0,
    ) -> T:
        """Modelni chaqirib, javobni `schema` bo'yicha tekshirilgan obyekt qilib qaytaradi."""
        body: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
        }
        if tools:
            body["tools"] = tools
        if system:
            body["system_instruction"] = system

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                await self._throttle()
                interaction = await self._client.aio.interactions.create(
                    timeout=timeout, **body
                )
                self.usage.record(interaction.usage)
                text = interaction.output_text
                if not text:
                    raise ValueError("model bo'sh javob qaytardi")
                return schema.model_validate_json(text)

            except errors.APIError as exc:
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if status not in _RETRYABLE_STATUS or attempt == self.max_retries:
                    raise
                last_error = exc

            except (ValidationError, ValueError) as exc:
                # Model sxemaga tushmaydigan javob berdi — qayta urinish odatda yordam beradi.
                if attempt == self.max_retries:
                    raise
                last_error = exc

            delay = _retry_after(last_error) or min(2**attempt, 20) + random.uniform(0, 1)
            log.warning(
                "Gemini (%s) urinish %d/%d muvaffaqiyatsiz: %s — %.1fs kutamiz",
                model,
                attempt,
                self.max_retries,
                last_error,
                delay,
            )
            await asyncio.sleep(delay)

        raise RuntimeError(f"Gemini chaqiruvi muvaffaqiyatsiz: {last_error}")
