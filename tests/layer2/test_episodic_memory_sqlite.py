"""Тесты SQLite-бэкенда EpisodicMemory."""

from vagus.layer2.memory import EpisodicMemory


def test_sqlite_write_and_read(tmp_path):
    """Шаги записываются и читаются из SQLite файла."""
    db_path = tmp_path / "episodic.db"
    memory = EpisodicMemory(db_path=str(db_path))

    step_id = memory.add_step("task_sqlite", "coder", "execute_code", {"ok": True}, {"line": 1})
    history = memory.get_history("task_sqlite")
    last = memory.get_last_step("task_sqlite")
    summary = memory.get_task_summary("task_sqlite")
    memory.close()

    assert step_id
    assert len(step_id) == 32  # uuid4().hex
    assert len(history) == 1
    assert history[0]["action"] == "execute_code"
    assert history[0]["result"] == {"ok": True}
    assert history[0]["metadata"] == {"line": 1}
    assert last is not None
    assert last["step_id"] == step_id
    assert summary["step_count"] == 1
    assert summary["last_step"]["step_id"] == step_id


def test_sqlite_persistence_after_restart(tmp_path):
    """Данные сохраняются между инстансами при file-based SQLite."""
    db_path = tmp_path / "episodic_persistent.db"

    memory1 = EpisodicMemory(db_path=str(db_path))
    memory1.add_step("task_persist", "researcher", "search_web", {"items": 3})
    memory1.close()

    memory2 = EpisodicMemory(db_path=str(db_path))
    history = memory2.get_history("task_persist")
    summary = memory2.get_task_summary("task_persist")
    memory2.close()

    assert len(history) == 1
    assert history[0]["agent_type"] == "researcher"
    assert history[0]["action"] == "search_web"
    assert history[0]["result"] == {"items": 3}
    assert summary["step_count"] == 1
    assert summary["last_step"]["action"] == "search_web"


def test_add_step_dict_and_batch_task_format(tmp_path):
    """Поддерживается формат add_step(task_id, step_dict) и add_steps_batch(task_id, steps)."""
    db_path = tmp_path / "episodic_compat.db"
    memory = EpisodicMemory(db_path=str(db_path))

    sid = memory.add_step(
        "task_dict",
        {
            "agent_type": "analyst",
            "action": "analyze_data",
            "result": {"score": 0.95},
            "metadata": {"source": "test"},
        },
    )
    batch_ids = memory.add_steps_batch(
        "task_dict",
        [
            {"agent_type": "coder", "action": "execute_code", "result": "ok"},
            {"agent_type": "researcher", "action": "search_web", "result": ["a", "b"]},
        ],
    )
    history = memory.get_history("task_dict")
    memory.close()

    assert sid
    assert len(batch_ids) == 2
    assert len(history) == 3
    assert history[0]["agent_type"] == "analyst"
    assert history[-1]["agent_type"] == "researcher"
