"""
The AI connector - the ONE place in the app that talks to the AI model (Claude).

Every agent (tone, scoring, content planner...) asks its question through
this file, never directly. That gives us three superpowers in one place:

1. MOCK MODE (free practice mode)
   When MOCK_AI=true in .env (the default), we never call the real AI.
   Instead, each agent provides a "mock" function: simple rules that give a
   sensible fake answer. So you can build and test everything for free.

2. STRUCTURED ANSWERS
   We don't want the AI to reply with a chatty paragraph. We want a filled-in
   form, e.g. {"sentiment": "urgent", "reason": "..."}. Each agent describes
   its form as a Pydantic schema; we give the AI that form as a "tool" it must
   fill in, then check the answer against the same schema.

3. SAFETY NET
   If the real AI fails (no internet, wrong key, strange answer), we don't
   crash. We fall back to the mock answer and note what went wrong, so a
   customer's lead is never lost because the AI had a bad moment.

How an agent uses it:

    result = get_llm().ask(
        system="You are a lead tone analyst...",
        prompt="Customer message: Need ceramic coating TODAY",
        schema=ToneAnswer,                 # the form to fill in
        mock=lambda: {"sentiment": "urgent", "reason": "says today"},
    )
    result.data.sentiment   → "urgent"
    result.mode             → "mock", "real" or "fallback"
"""

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Generic, Optional, TypeVar

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("ai")

Form = TypeVar("Form", bound=BaseModel)   # "any Pydantic schema"


@dataclass
class AIResult(Generic[Form]):
    """What an agent gets back: the filled-in form plus some facts about the call."""

    data: Form                       # the answer, already checked against the schema
    mode: str                        # "mock", "real" or "fallback" (real failed → mock used)
    model: Optional[str] = None      # which AI model answered (None in mock mode)
    ms: int = 0                      # how long it took, in milliseconds
    input_tokens: int = 0            # tokens = small chunks of text; the AI is billed per token
    output_tokens: int = 0
    error: Optional[str] = None      # what went wrong, if we had to fall back

    def log_entry(self, agent: str) -> dict:
        """A small summary saved in the agent_runs table, so the dashboard
        can show what each agent did."""
        return {
            "agent": agent, "mode": self.mode, "model": self.model, "ms": self.ms,
            "tokens": self.input_tokens + self.output_tokens,
            "output": self.data.model_dump(), "error": self.error,
        }


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class LLM:
    def __init__(self, client=None, enabled: Optional[bool] = None):
        """
        enabled: use the real AI? By default this comes from settings
                 (MOCK_AI=false AND an API key is present).
        client:  normally created automatically; tests pass in a fake one.
        """
        self.enabled = settings.ai_enabled if enabled is None else enabled
        self._client = client

    @property
    def client(self):
        """The official Anthropic SDK client, created the first time it's needed."""
        if self._client is None:
            import anthropic  # imported here so mock mode never needs it

            self._client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.ai_timeout_seconds,
                max_retries=2,              # quietly retry short network hiccups
            )
        return self._client

    @property
    def mode(self) -> str:
        return "real" if self.enabled else "mock"

    def ask(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[Form],
        mock: Callable[[], dict],
        smart: bool = False,
        max_tokens: int = 1024,
    ) -> AIResult[Form]:
        """Ask the AI to fill in `schema`.

        system  - the agent's job description ("You are a ...")
        prompt  - the actual question, with the data to look at
        schema  - the form the answer must fit
        mock    - rules that produce a fake answer (used in mock mode / on failure)
        smart   - True = use the smart model, False = the fast cheap one
        """
        start = time.perf_counter()

        if not self.enabled:
            return AIResult(data=schema.model_validate(mock()), mode="mock", ms=_ms_since(start))

        model = settings.ai_model if smart else settings.ai_model_fast
        # The form, described as a "tool" the AI is required to use
        answer_tool = {
            "name": "give_answer",
            "description": "Give your final answer by filling in this structure exactly.",
            "input_schema": schema.model_json_schema(),
        }
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[answer_tool],
                tool_choice={"type": "tool", "name": "give_answer"},   # must fill the form
            )
            filled_in = next(block for block in response.content if block.type == "tool_use")
            data = schema.model_validate(filled_in.input)            # check it fits our rules
            return AIResult(
                data=data, mode="real", model=model, ms=_ms_since(start),
                input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
            )
        except Exception as error:  # noqa: BLE001 - any failure → safety net
            problem = f"{type(error).__name__}: {error}"[:300]
            logger.warning("AI call failed, using mock answer instead (%s)", problem)
            return AIResult(
                data=schema.model_validate(mock()), mode="fallback", model=model,
                ms=_ms_since(start), error=problem,
            )


@lru_cache
def get_llm() -> LLM:
    """The one shared connector used by every agent."""
    return LLM()
