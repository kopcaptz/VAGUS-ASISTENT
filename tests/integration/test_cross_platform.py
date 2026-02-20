from __future__ import annotations

from vagus.security import KeyManager


def test_key_manager_falls_back_when_dpapi_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()

    import vagus.security.key_manager as km_module

    monkeypatch.setattr(km_module.sys, "platform", "win32")
    monkeypatch.setattr(km_module, "is_dpapi_available", lambda: True)
    monkeypatch.setattr(km_module, "protect_data", lambda _b: (_ for _ in ()).throw(RuntimeError("dpapi failed")))

    manager = KeyManager()
    key = manager._get_master_key()  # noqa: SLF001
    assert len(key) == 32
    assert (tmp_path / ".vagus" / ".keys_master").exists()
