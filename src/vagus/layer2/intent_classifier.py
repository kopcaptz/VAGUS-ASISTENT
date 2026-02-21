"""
IntentClassifier — анализ намерений пользователя с помощью LLM.
Few-shot prompting для высокой точности классификации.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from .agents.protocols import LLMRouterProtocol
from ..layer0.logging import get_logger

VALID_PRIMARY_INTENTS = ("research", "code", "analysis", "design", "mixed")
VALID_COMPLEXITY = ("simple", "moderate", "complex")

DEFAULT_FEW_SHOT_EXAMPLES: List[Tuple[str, Dict[str, Any]]] = [
    (
        "Найди информацию про FastAPI и создай пример кода",
        {
            "primary_intent": "mixed",
            "sub_intents": ["search_web", "generate_code"],
            "entities": {"topic": "FastAPI"},
            "complexity": "moderate",
            "confidence": 0.95,
        },
    ),
    (
        "Проанализируй этот CSV файл и создай график",
        {
            "primary_intent": "analysis",
            "sub_intents": ["data_analysis", "visualization"],
            "entities": {"file_type": "CSV"},
            "complexity": "moderate",
            "confidence": 0.9,
        },
    ),
]


class IntentResult(TypedDict):
    """Структурированный результат классификации намерений."""

    primary_intent: str
    sub_intents: List[str]
    entities: Dict[str, Any]
    complexity: str
    confidence: float


FALLBACK_RESULT: IntentResult = {
    "primary_intent": "mixed",
    "sub_intents": [],
    "entities": {},
    "complexity": "moderate",
    "confidence": 0.5,
}


class IntentClassifier:
    """Классификатор намерений пользователя на основе LLM с few-shot prompting."""

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        *,
        few_shot_examples: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        self.llm_router = llm_router
        self.few_shot_examples = few_shot_examples if few_shot_examples is not None else list(DEFAULT_FEW_SHOT_EXAMPLES)
        self.confidence_threshold = max(0.0, min(1.0, confidence_threshold))
        self.logger = get_logger("layer2.intent_classifier")

    async def classify(self, user_input: str) -> IntentResult:
        """Классифицирует намерение пользователя по тексту запроса."""
        if not (user_input or "").strip():
            self.logger.debug("Empty user input, returning fallback")
            return dict(FALLBACK_RESULT)

        prompt = self._build_prompt(user_input.strip())
        try:
            llm_response = await self._call_llm(prompt)
            parsed = self._parse_llm_json(llm_response)
            return self._normalize_result(parsed)
        except Exception as exc:
            self.logger.warning("Intent classification failed, fallback to mixed: %s", exc)
            return dict(FALLBACK_RESULT)

    def _build_prompt(self, user_input: str) -> str:
        schema = (
            "{\n"
            '  "primary_intent": "research"|"code"|"analysis"|"design"|"mixed",\n'
            '  "sub_intents": ["string"],\n'
            '  "entities": {"key": "value"},\n'
            '  "complexity": "simple"|"moderate"|"complex",\n'
            '  "confidence": 0.0-1.0\n'
            "}"
        )
        examples_text = ""
        for inp, out in self.few_shot_examples:
            examples_text += f'\nInput: "{inp}"\nOutput: {json.dumps(out, ensure_ascii=False)}\n'
        return (
            "You are an intent classifier. Analyze user input and return STRICT JSON only.\n"
            "Output schema:\n"
            f"{schema}\n\n"
            "Few-shot examples:"
            f"{examples_text}\n"
            f"User input to classify: {user_input}\n\n"
            "Return valid JSON only, no markdown, no explanations."
        )

    async def _call_llm(self, prompt: str) -> str:
        content_parts: List[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts).strip()

    def _parse_llm_json(self, llm_text: str) -> Dict[str, Any]:
        if not llm_text:
            raise ValueError("Empty LLM response")
        candidate = llm_text.strip()
        if "```" in candidate:
            candidate = candidate.replace("```json", "").replace("```", "").strip()
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response JSON must be an object")
        return parsed

    def _normalize_result(self, parsed: Dict[str, Any]) -> IntentResult:
        primary = str(parsed.get("primary_intent", "mixed")).strip().lower()
        if primary not in VALID_PRIMARY_INTENTS:
            primary = "mixed"

        complexity = str(parsed.get("complexity", "moderate")).strip().lower()
        if complexity not in VALID_COMPLEXITY:
            complexity = "moderate"

        try:
            confidence = float(parsed.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        sub_raw = parsed.get("sub_intents", [])
        sub_intents = [str(item).strip() for item in sub_raw if str(item).strip()] if isinstance(sub_raw, list) else []

        entities_raw = parsed.get("entities", {})
        entities = dict(entities_raw) if isinstance(entities_raw, dict) else {}

        return IntentResult(
            primary_intent=primary,
            sub_intents=sub_intents,
            entities=entities,
            complexity=complexity,
            confidence=confidence,
        )


def create_intent_classifier(
    llm_router: LLMRouterProtocol,
    config: Optional[Dict[str, Any]] = None,
) -> IntentClassifier:
    """Создаёт IntentClassifier из конфигурации layer2.intent_classifier."""
    cfg = config or {}
    confidence_threshold = float(cfg.get("confidence_threshold", 0.5))
    few_shot = cfg.get("few_shot_examples")
    return IntentClassifier(
        llm_router,
        confidence_threshold=confidence_threshold,
        few_shot_examples=few_shot,
    )


__all__ = ["IntentClassifier", "IntentResult", "create_intent_classifier"]
