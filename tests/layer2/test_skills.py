"""Unit-тесты SkillSystem."""
import pytest

from vagus.layer2.skills import SkillSystem


@pytest.fixture
def skill_system():
    return SkillSystem()


@pytest.mark.asyncio
async def test_skill_system_has_default_skills(skill_system):
    """Проверка регистрации навыков по умолчанию."""
    skills = skill_system.list_skills()
    assert "search_web" in skills
    assert "execute_python_code" in skills
    assert "read_file" in skills


@pytest.mark.asyncio
async def test_use_skill_search_web(skill_system):
    """search_web возвращает заглушку с текстом запроса."""
    result = await skill_system.use_skill("search_web", query="Python")
    assert isinstance(result, str)
    assert "Python" in result
    assert "заглушка" in result or "запрос" in result.lower()


@pytest.mark.asyncio
async def test_use_skill_unknown_returns_error(skill_system):
    """Неизвестный навык возвращает dict с error."""
    result = await skill_system.use_skill("unknown_skill")
    assert isinstance(result, dict)
    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_register_custom_skill(skill_system):
    """register_skill добавляет кастомный навык."""

    async def my_skill(value: int) -> int:
        return value * 2

    skill_system.register_skill("double", my_skill)
    assert "double" in skill_system.list_skills()
    result = await skill_system.use_skill("double", value=7)
    assert result == 14


@pytest.mark.asyncio
async def test_execute_python_code_success(skill_system):
    """execute_python_code выполняет простой код."""
    result = await skill_system.use_skill(
        "execute_python_code",
        code="x = 2 + 3",
    )
    assert result["status"] == "success"
    assert result["output"]["x"] == 5


@pytest.mark.asyncio
async def test_execute_python_code_error(skill_system):
    """execute_python_code возвращает error при исключении."""
    result = await skill_system.use_skill(
        "execute_python_code",
        code="raise ValueError('test')",
    )
    assert result["status"] == "error"
    assert "test" in result["message"]


@pytest.mark.asyncio
async def test_read_file(skill_system, tmp_path):
    """read_file читает содержимое файла."""
    f = tmp_path / "test.txt"
    f.write_text("Hello, World!", encoding="utf-8")
    result = await skill_system.use_skill("read_file", path=str(f))
    assert result == "Hello, World!"


@pytest.mark.asyncio
async def test_read_file_nonexistent(skill_system):
    """read_file возвращает сообщение об ошибке для несуществующего файла."""
    result = await skill_system.use_skill("read_file", path="/nonexistent/file.txt")
    assert "Error" in result or "error" in result.lower()
