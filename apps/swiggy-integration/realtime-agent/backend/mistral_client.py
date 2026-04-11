"""Small wrapper around the Mistral SDK for strict JSON planner responses."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from mistralai import Mistral


class MistralClientError(RuntimeError):
    """Raised when Mistral returns an invalid or unexpected response."""


class MistralTextClient:
    """Adapter that constrains Mistral to return JSON for the sidecar planner."""

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-small-latest",
    ) -> None:
        """Initialize the Mistral SDK client and remember the chosen model."""
        self._client = Mistral(api_key=api_key)
        self._model = model

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        """Run the blocking Mistral SDK call off the event loop."""
        return await asyncio.to_thread(self._generate_json_sync, prompt)

    def _generate_json_sync(self, prompt: str) -> dict[str, Any]:
        """Submit the prompt and parse the first choice as a JSON object."""
        response = self._client.chat.complete(
            model=self._model,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        text = self._extract_text(response)
        return self._parse_json(text)

    def _extract_text(self, response: Any) -> str:
        """Extract plain text from the first Mistral chat choice."""
        if not getattr(response, "choices", None):
            raise MistralClientError(f"Mistral response did not include choices: {response}")

        choice = response.choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif hasattr(item, "text") and isinstance(item.text, str):
                    text_parts.append(item.text)
            text = "\n".join(text_parts).strip()
        else:
            text = str(content or "").strip()

        if not text:
            raise MistralClientError(f"Mistral choice did not include text: {response}")
        return text

    def _parse_json(self, text: str) -> dict[str, Any]:
        """Parse raw model text into a JSON object, tolerating fenced output."""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Some responses wrap the JSON object in prose or code fences; recover
        # the first object-shaped payload instead of failing immediately.
        fenced_match = re.search(r"\{.*\}", text, re.DOTALL)
        if fenced_match:
            parsed = json.loads(fenced_match.group(0))
            if isinstance(parsed, dict):
                return parsed

        raise MistralClientError(f"Mistral did not return a JSON object: {text}")
