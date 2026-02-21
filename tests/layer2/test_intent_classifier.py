"""Тесты IntentClassifier."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.intent_classifier import IntentClassifier, IntentResult


def _mock_llm(json_response: str):
    """Возвращает async generator function для route_request."""

    async def _inner(prompt: str, **kwargs):
        yield {"content": json_response, "done": True}

    return _inner


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm(
        '{"primary_intent": "research", "sub_intents": ["search_web"], '
        '"entities": {"topic": "FastAPI"}, "complexity": "simple", "confidence": 0.92}'
    )
    return router


@pytest.fixture
def classifier(mock_llm_router):
    return IntentClassifier(llm_router=mock_llm_router)


@pytest.mark.asyncio
async def test_classify_research_intent(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "research", "sub_intents": ["search_docs"], '
        '"entities": {"topic": "FastAPI"}, "complexity": "simple", "confidence": 0.9}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Найди документацию по FastAPI")
    assert result["primary_intent"] == "research"
    assert "search_docs" in result["sub_intents"] or "search_web" in result["sub_intents"]


@pytest.mark.asyncio
async def test_classify_code_intent(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "code", "sub_intents": ["generate_code"], '
        '"entities": {"language": "Python", "task": "CSV parsing"}, "complexity": "moderate", "confidence": 0.88}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Напиши функцию на Python для парсинга CSV")
    assert result["primary_intent"] == "code"
    assert result["entities"].get("language") == "Python" or "Python" in str(result["entities"])


@pytest.mark.asyncio
async def test_classify_analysis_intent(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "analysis", "sub_intents": ["data_analysis"], '
        '"entities": {}, "complexity": "moderate", "confidence": 0.91}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Проанализируй эти данные и найди выбросы")
    assert result["primary_intent"] == "analysis"


@pytest.mark.asyncio
async def test_classify_design_intent(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "design", "sub_intents": ["ui_design"], '
        '"entities": {"platform": "mobile"}, "complexity": "moderate", "confidence": 0.89}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Спроектируй UI для мобильного приложения")
    assert result["primary_intent"] == "design"


@pytest.mark.asyncio
async def test_classify_mixed_intent(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "mixed", "sub_intents": ["search_web", "generate_code"], '
        '"entities": {"topic": "X"}, "complexity": "moderate", "confidence": 0.95}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Найди инфо про X и создай код")
    assert result["primary_intent"] == "mixed"
    assert len(result["sub_intents"]) >= 2


@pytest.mark.asyncio
async def test_classify_extracts_entities(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "code", "sub_intents": ["generate_code"], '
        '"entities": {"framework": "FastAPI", "type": "REST API"}, "complexity": "moderate", "confidence": 0.9}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Создай REST API на FastAPI")
    assert result["entities"]
    assert "FastAPI" in str(result["entities"].values()) or "framework" in result["entities"]


@pytest.mark.asyncio
async def test_classify_complexity_simple(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "research", "sub_intents": [], '
        '"entities": {}, "complexity": "simple", "confidence": 0.98}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Что такое HTTP?")
    assert result["complexity"] == "simple"


@pytest.mark.asyncio
async def test_classify_complexity_complex(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "mixed", "sub_intents": ["search", "analyze", "code", "visualize"], '
        '"entities": {}, "complexity": "complex", "confidence": 0.85}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Найди данные, проанализируй, напиши код и построй графики")
    assert result["complexity"] == "complex"


@pytest.mark.asyncio
async def test_classify_parse_error_fallback(mock_llm_router):
    mock_llm_router.route_request = _mock_llm("This is not valid JSON at all")
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Some user input")
    assert result["primary_intent"] == "mixed"
    assert result["confidence"] == 0.5


@pytest.mark.asyncio
async def test_classify_invalid_intent_fallback(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "unknown_type", "sub_intents": [], '
        '"entities": {}, "complexity": "weird", "confidence": 0.99}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Something obscure")
    assert result["primary_intent"] == "mixed"
    assert result["complexity"] == "moderate"


@pytest.mark.asyncio
async def test_classify_confidence_bounds(mock_llm_router):
    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "code", "sub_intents": [], '
        '"entities": {}, "complexity": "simple", "confidence": 1.5}'
    )
    classifier = IntentClassifier(llm_router=mock_llm_router)
    result = await classifier.classify("Код")
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["confidence"] == 1.0

    mock_llm_router.route_request = _mock_llm(
        '{"primary_intent": "code", "sub_intents": [], '
        '"entities": {}, "complexity": "simple", "confidence": -0.2}'
    )
    result2 = await classifier.classify("Код")
    assert result2["confidence"] == 0.0


@pytest.mark.asyncio
async def test_classify_empty_input(classifier):
    result = await classifier.classify("")
    assert result["primary_intent"] == "mixed"
    assert result["confidence"] == 0.5

    result2 = await classifier.classify("   ")
    assert result2["primary_intent"] == "mixed"


@pytest.mark.asyncio
async def test_classify_result_structure(classifier):
    result = await classifier.classify("Найди документацию")
    assert set(result.keys()) == {"primary_intent", "sub_intents", "entities", "complexity", "confidence"}
    assert isinstance(result["sub_intents"], list)
    assert isinstance(result["entities"], dict)
    assert isinstance(result["confidence"], float)
