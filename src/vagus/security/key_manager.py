"""Secure API key manager with encrypted local storage and monitoring helpers."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import shutil
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .dpapi_wrapper import is_dpapi_available, protect_data, unprotect_data

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]

KeyChangeListener = Callable[[dict[str, Any]], None]
logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64e(value: bytes) -> str:
    return base64.b64encode(value).decode("utf-8")


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("utf-8"))


def _looks_like_key_env(name: str) -> bool:
    return name.endswith("_API_KEY")


def _safe_iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except Exception:
        return None


def _safe_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


class KeyManager:
    """Singleton API key manager."""

    _instance: Optional["KeyManager"] = None
    _instance_lock = threading.Lock()
    _aad = b"vagus.keys.v1"

    def __new__(cls, *args, **kwargs):  # noqa: D401 - singleton constructor
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._lock = threading.RLock()
        self._audit_hook: Optional[Callable[..., None]] = None
        self._listeners: list[KeyChangeListener] = []

        # Validation controls.
        self._validation_cache_ttl_seconds = 900
        self._validation_cache_maxsize = 100
        self._validation_min_interval_seconds = 2.0
        self._validation_cache: OrderedDict[str, tuple[float, bool, Optional[str], str]] = OrderedDict()
        self._validation_last_attempt: dict[str, float] = {}
        self._env_validation_meta: dict[str, dict[str, Any]] = {}

        # Watcher state.
        self._watchdog_observer = None
        self._watch_poll_thread: Optional[threading.Thread] = None
        self._watch_stop_event = threading.Event()
        self._watch_interval_seconds = 5.0
        self._watch_last_mtime: Optional[float] = None
        self._watch_mode = "stopped"

        home = Path.home()
        self._base_dir = home / ".vagus"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._keys_file = self._base_dir / "keys.enc"
        self._master_file = self._base_dir / ".keys_master"

    @classmethod
    def reset_instance_for_tests(cls) -> None:
        with cls._instance_lock:
            if cls._instance is not None:
                try:
                    cls._instance.stop_watching()
                except Exception:
                    pass
            cls._instance = None

    def set_audit_hook(self, hook: Optional[Callable[..., None]]) -> None:
        self._audit_hook = hook

    def add_listener(self, listener: KeyChangeListener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: KeyChangeListener) -> None:
        with self._lock:
            self._listeners = [item for item in self._listeners if item is not listener]

    def _emit_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(dict(event))
            except Exception:
                continue

    def _notify_change(
        self,
        *,
        action: str,
        key_name: Optional[str] = None,
        key_type: Optional[str] = None,
        source: str = "store",
    ) -> None:
        self._emit_event(
            {
                "action": action,
                "key_name": key_name,
                "key_type": key_type,
                "source": source,
                "timestamp": _utc_now(),
            }
        )

    @property
    def keys_file(self) -> Path:
        return self._keys_file

    @property
    def is_watching(self) -> bool:
        with self._lock:
            return self._watch_mode != "stopped"

    @property
    def watch_mode(self) -> str:
        with self._lock:
            return self._watch_mode

    def watch_for_changes(self, *, interval_seconds: float = 5.0) -> bool:
        with self._lock:
            if self._watch_mode != "stopped":
                return True
            self._watch_interval_seconds = max(1.0, float(interval_seconds))
            self._watch_stop_event.clear()
            self._watch_last_mtime = self._read_keys_mtime()

        if WATCHDOG_AVAILABLE:
            try:
                observer = Observer()
                observer.schedule(_KeyFileWatcher(self), str(self._base_dir), recursive=False)
                observer.start()
                with self._lock:
                    self._watchdog_observer = observer
                    self._watch_mode = "watchdog"
                return True
            except Exception:
                with self._lock:
                    self._watchdog_observer = None

        thread = threading.Thread(target=self._poll_watch_loop, name="vagus-key-watch", daemon=True)
        thread.start()
        with self._lock:
            self._watch_poll_thread = thread
            self._watch_mode = "polling"
        return True

    def stop_watching(self) -> None:
        with self._lock:
            observer = self._watchdog_observer
            poll_thread = self._watch_poll_thread
            self._watch_stop_event.set()
            self._watch_mode = "stopped"
            self._watchdog_observer = None
            self._watch_poll_thread = None
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception:
                pass
        if poll_thread is not None and poll_thread.is_alive():
            poll_thread.join(timeout=5)

    def _read_keys_mtime(self) -> Optional[float]:
        try:
            return self._keys_file.stat().st_mtime
        except Exception:
            return None

    def _poll_watch_loop(self) -> None:
        while not self._watch_stop_event.is_set():
            current = self._read_keys_mtime()
            changed = False
            with self._lock:
                if current != self._watch_last_mtime:
                    self._watch_last_mtime = current
                    changed = True
            if changed:
                self._notify_change(action="external_change", source="watcher")
            self._watch_stop_event.wait(self._watch_interval_seconds)

    def _on_keys_file_changed(self) -> None:
        with self._lock:
            current = self._read_keys_mtime()
            if current == self._watch_last_mtime:
                return
            self._watch_last_mtime = current
        self._notify_change(action="external_change", source="watcher")

    def _audit(self, action: str, details: dict[str, Any]) -> None:
        hook = self._audit_hook
        if hook is None:
            return
        try:
            hook(action=action, details=details)
        except Exception:
            return

    def _get_master_key(self) -> bytes:
        env_value = os.getenv("VAGUS_KEYS_MASTER_KEY", "").strip()
        if env_value:
            return self._normalize_master_key(env_value.encode("utf-8"))

        stored = self._load_master_key()
        if stored is not None:
            return stored

        generated = secrets.token_bytes(32)
        self._save_master_key(generated)
        return generated

    @staticmethod
    def _normalize_master_key(raw: bytes) -> bytes:
        if len(raw) == 32:
            return raw
        return sha256(raw).digest()

    def _load_master_key(self) -> Optional[bytes]:
        if not self._master_file.exists():
            return None
        try:
            raw_bytes = self._master_file.read_bytes()
        except Exception:
            return None
        if not raw_bytes:
            return None

        running_on_windows = sys.platform == "win32"
        dpapi_ready = running_on_windows and is_dpapi_available()
        is_dpapi_envelope = raw_bytes.startswith(b"DPAPIv1")

        if dpapi_ready and is_dpapi_envelope:
            try:
                plain = unprotect_data(raw_bytes)
                return self._normalize_master_key(plain)
            except Exception as exc:
                logger.warning("Failed to unprotect DPAPI master key, trying fallback format: %s", exc)

        try:
            raw_text = raw_bytes.decode("utf-8").strip()
        except Exception:
            raw_text = ""

        if raw_text:
            try:
                parsed = base64.b64decode(raw_text.encode("utf-8"))
                plain = self._normalize_master_key(parsed)
            except Exception:
                plain = self._normalize_master_key(raw_text.encode("utf-8"))
        else:
            plain = self._normalize_master_key(raw_bytes)

        # One-time Windows migration to DPAPI envelope with backup of legacy file.
        if dpapi_ready and not is_dpapi_envelope:
            try:
                if self._master_file.exists():
                    timestamp = str(int(time.time()))
                    legacy_backup = self._base_dir / f".keys_master.legacy.{timestamp}.bak"
                    shutil.copy2(self._master_file, legacy_backup)
                self._save_master_key(plain)
            except Exception as exc:
                logger.warning("Failed to migrate legacy master key to DPAPI: %s", exc)
        return plain

    def _save_master_key(self, key: bytes) -> None:
        normalized = self._normalize_master_key(key)
        encoded = base64.b64encode(normalized).decode("utf-8")
        running_on_windows = sys.platform == "win32"
        dpapi_ready = running_on_windows and is_dpapi_available()

        if dpapi_ready:
            try:
                protected = protect_data(normalized)
                self._master_file.write_bytes(protected)
                return
            except Exception as exc:
                logger.warning("DPAPI protect failed, falling back to file key storage: %s", exc)

        self._master_file.write_text(encoded, encoding="utf-8")
        try:
            os.chmod(self._master_file, 0o600)
        except Exception:
            pass

    def _derive_data_key(self, master_key: bytes, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=390_000,
        )
        return kdf.derive(master_key)

    def _encrypt_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        master = self._get_master_key()
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        key = self._derive_data_key(master, salt)
        aesgcm = AESGCM(key)
        plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, self._aad)
        return {
            "version": 1,
            "kdf": "pbkdf2-sha256",
            "salt": _b64e(salt),
            "nonce": _b64e(nonce),
            "ciphertext": _b64e(ciphertext),
            "updated_at": _utc_now(),
        }

    def _decrypt_payload(self, envelope: dict[str, Any]) -> dict[str, Any]:
        master = self._get_master_key()
        salt = _b64d(str(envelope.get("salt", "")))
        nonce = _b64d(str(envelope.get("nonce", "")))
        ciphertext = _b64d(str(envelope.get("ciphertext", "")))
        key = self._derive_data_key(master, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, self._aad)
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            return {"version": 1, "keys": {}}
        return payload

    def _load_store(self) -> dict[str, Any]:
        if not self._keys_file.exists():
            return {"version": 1, "keys": {}}
        try:
            envelope = json.loads(self._keys_file.read_text(encoding="utf-8"))
            if not isinstance(envelope, dict):
                return {"version": 1, "keys": {}}
            payload = self._decrypt_payload(envelope)
            if "keys" not in payload or not isinstance(payload.get("keys"), dict):
                payload["keys"] = {}
            return payload
        except Exception:
            return {"version": 1, "keys": {}}

    def _save_store(self, payload: dict[str, Any]) -> None:
        envelope = self._encrypt_payload(payload)
        self._keys_file.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(self._keys_file, 0o600)
        except Exception:
            pass

    @staticmethod
    def _mask(value: str) -> str:
        if not value or len(value) <= 8:
            return "***"
        return f"***{value[-8:]}"

    @staticmethod
    def _env_name(name: str, key_type: Optional[str] = None) -> str:
        normalized = (key_type or name).upper().replace("-", "_").replace(" ", "_")
        return f"{normalized}_API_KEY"

    def _touch_validation_cache(self, cache_key: str) -> None:
        if cache_key in self._validation_cache:
            self._validation_cache.move_to_end(cache_key)
        while len(self._validation_cache) > self._validation_cache_maxsize:
            self._validation_cache.popitem(last=False)

    def _get_validation_cached(self, cache_key: str) -> Optional[tuple[bool, Optional[str], str]]:
        now = time.monotonic()
        data = self._validation_cache.get(cache_key)
        if data is None:
            return None
        cached_at, valid, error, checked_at = data
        if now - cached_at > self._validation_cache_ttl_seconds:
            self._validation_cache.pop(cache_key, None)
            return None
        self._validation_cache.move_to_end(cache_key)
        return valid, error, checked_at

    def _set_validation_cached(self, cache_key: str, valid: bool, error: Optional[str], checked_at: str) -> None:
        self._validation_cache[cache_key] = (time.monotonic(), valid, error, checked_at)
        self._touch_validation_cache(cache_key)

    def _store_validation_metadata(
        self,
        *,
        key_name: str,
        valid: bool,
        error: Optional[str],
        checked_at: str,
    ) -> None:
        with self._lock:
            store = self._load_store()
            keys = store.setdefault("keys", {})
            entry = keys.get(key_name)
            if isinstance(entry, dict):
                entry["last_validation"] = {
                    "valid": bool(valid),
                    "error": error,
                    "checked_at": checked_at,
                }
                entry["updated_at"] = _utc_now()
                keys[key_name] = entry
                self._save_store(store)
            else:
                self._env_validation_meta[key_name] = {
                    "valid": bool(valid),
                    "error": error,
                    "checked_at": checked_at,
                }

    def add_key(
        self,
        *,
        name: str,
        key_type: str,
        value: str,
        expires_at: Optional[str] = None,
    ) -> dict[str, Any]:
        key_name = name.strip()
        if not key_name:
            raise ValueError("key name is required")
        if not value.strip():
            raise ValueError("key value is required")
        now = _utc_now()
        normalized_type = key_type.strip().lower() or "custom"
        with self._lock:
            store = self._load_store()
            keys = store.setdefault("keys", {})
            if key_name in keys:
                raise ValueError(f"key '{key_name}' already exists")
            keys[key_name] = {
                "name": key_name,
                "type": normalized_type,
                "value": value.strip(),
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "last_used_at": None,
                "last_validation": None,
                "expires_at": _safe_iso(expires_at),
            }
            self._save_store(store)

        self._audit("key.create", {"name": key_name, "type": normalized_type})
        self._notify_change(action="add", key_name=key_name, key_type=normalized_type)
        return self.list_keys().get(key_name, {})

    def update_key(
        self,
        *,
        name: str,
        value: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> dict[str, Any]:
        key_name = name.strip()
        if not key_name:
            raise ValueError("key name is required")
        key_type = None
        with self._lock:
            store = self._load_store()
            keys = store.setdefault("keys", {})
            if key_name not in keys:
                raise KeyError(key_name)
            current = keys[key_name]
            if value is not None:
                if not value.strip():
                    raise ValueError("key value cannot be empty")
                current["value"] = value.strip()
            if expires_at is not None:
                current["expires_at"] = _safe_iso(expires_at)
            current["updated_at"] = _utc_now()
            key_type = str(current.get("type", "custom"))
            keys[key_name] = current
            self._save_store(store)

        self._audit("key.update", {"name": key_name, "has_value_update": value is not None})
        self._notify_change(action="update", key_name=key_name, key_type=key_type)
        return self.list_keys().get(key_name, {})

    def delete_key(self, name: str) -> bool:
        key_name = name.strip()
        if not key_name:
            return False
        key_type = None
        with self._lock:
            store = self._load_store()
            keys = store.setdefault("keys", {})
            existed = key_name in keys
            if existed:
                key_type = str(keys[key_name].get("type", "custom"))
                del keys[key_name]
                self._save_store(store)
        if existed:
            self._audit("key.delete", {"name": key_name})
            self._notify_change(action="delete", key_name=key_name, key_type=key_type)
        return existed

    def get_key(self, name: str) -> Optional[str]:
        key_name = name.strip()
        if not key_name:
            return None
        with self._lock:
            store = self._load_store()
            keys = store.get("keys", {})
            entry = keys.get(key_name)
            env_name = self._env_name(key_name, str(entry.get("type")) if isinstance(entry, dict) else None)
            env_value = os.getenv(env_name)
            if env_value:
                return env_value
            if isinstance(entry, dict):
                return str(entry.get("value", "")) or None
        return None

    def mark_used(self, name: str) -> None:
        key_name = name.strip()
        if not key_name:
            return
        with self._lock:
            store = self._load_store()
            keys = store.setdefault("keys", {})
            entry = keys.get(key_name)
            if not isinstance(entry, dict):
                return
            entry["last_used_at"] = _utc_now()
            keys[key_name] = entry
            self._save_store(store)

    def list_keys(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        with self._lock:
            store = self._load_store()
            for name, entry in store.get("keys", {}).items():
                if not isinstance(entry, dict):
                    continue
                key_type = str(entry.get("type", "custom"))
                env_name = self._env_name(name, key_type)
                env_value = os.getenv(env_name)
                source = "env" if env_value else "store"
                result[name] = {
                    "name": name,
                    "type": key_type,
                    "status": str(entry.get("status", "active")),
                    "last_used_at": entry.get("last_used_at"),
                    "last_validation": entry.get("last_validation"),
                    "created_at": entry.get("created_at"),
                    "updated_at": entry.get("updated_at"),
                    "expires_at": entry.get("expires_at"),
                    "source": source,
                    "masked_value": self._mask(env_value if env_value else str(entry.get("value", ""))),
                }

        for env_name, env_value in os.environ.items():
            if not env_value or not _looks_like_key_env(env_name):
                continue
            inferred_name = env_name[: -len("_API_KEY")].lower()
            if inferred_name in result:
                continue
            result[inferred_name] = {
                "name": inferred_name,
                "type": inferred_name,
                "status": "active",
                "last_used_at": None,
                "last_validation": self._env_validation_meta.get(inferred_name),
                "created_at": None,
                "updated_at": None,
                "expires_at": None,
                "source": "env",
                "masked_value": self._mask(env_value),
            }
        return result

    def get_health_stats(self, *, days_ahead: int = 7) -> dict[str, Any]:
        keys = list(self.list_keys().values())
        total = len(keys)
        now = datetime.now(timezone.utc)
        expiring_soon = 0
        valid_keys = 0
        invalid_keys = 0
        items: list[dict[str, Any]] = []

        for item in keys:
            expires_dt = _safe_dt(item.get("expires_at"))
            expires_in_days: Optional[int] = None
            if expires_dt is not None:
                expires_in_days = int((expires_dt - now).total_seconds() // 86400)
                if expires_in_days <= int(days_ahead):
                    expiring_soon += 1

            validation = item.get("last_validation")
            valid_status = None
            last_validation = None
            if isinstance(validation, dict):
                valid_status = validation.get("valid")
                last_validation = validation.get("checked_at")
            if valid_status is True:
                valid_keys += 1
                status = "valid"
            elif valid_status is False:
                invalid_keys += 1
                status = "invalid"
            elif expires_in_days is not None and expires_in_days < 0:
                status = "expired"
                invalid_keys += 1
            elif expires_in_days is not None and expires_in_days <= int(days_ahead):
                status = "expiring_soon"
            else:
                status = str(item.get("status", "unknown"))

            items.append(
                {
                    "name": str(item.get("name", "")),
                    "type": str(item.get("type", "custom")),
                    "status": status,
                    "last_validation": last_validation,
                    "expires_in_days": expires_in_days,
                }
            )

        rotation_required = invalid_keys > 0 or expiring_soon > 0
        return {
            "total_keys": total,
            "valid_keys": valid_keys,
            "invalid_keys": invalid_keys,
            "expiring_soon": expiring_soon,
            "rotation_required": rotation_required,
            "keys": sorted(items, key=lambda x: (x.get("expires_in_days") is None, x.get("expires_in_days") or 999999)),
        }

    def validate_key(self, name: str, *, online: bool = True) -> tuple[bool, Optional[str]]:
        key_name = name.strip()
        if not key_name:
            return False, "Key name is required"

        key_meta = self.list_keys().get(key_name, {})
        key_type = str(key_meta.get("type", key_name)).lower()
        value = self.get_key(key_name)
        if not value:
            return False, "Key not found"
        if len(value) < 12:
            return False, "Key value looks invalid (too short)"

        value_hash = sha256(value.encode("utf-8")).hexdigest()[:12]
        cache_key = f"{key_name}:{key_type}:{int(bool(online))}:{value_hash}"
        with self._lock:
            cached = self._get_validation_cached(cache_key)
        if cached is not None:
            valid, error, _checked_at = cached
            return valid, error

        checked_at = _utc_now()
        if not online:
            valid, error = True, None
        else:
            rate_key = f"{key_name}:{key_type}"
            now_mono = time.monotonic()
            with self._lock:
                last_attempt = self._validation_last_attempt.get(rate_key, 0.0)
                self._validation_last_attempt[rate_key] = now_mono
            if now_mono - last_attempt < self._validation_min_interval_seconds:
                return False, "Validation rate limit reached. Retry later."
            valid, error = self._validate_online(key_type=key_type, value=value)

        with self._lock:
            self._set_validation_cached(cache_key, valid, error, checked_at)
        self._store_validation_metadata(key_name=key_name, valid=valid, error=error, checked_at=checked_at)
        self._audit(
            "key.validate",
            {"name": key_name, "type": key_type, "valid": valid, "error": error, "mode": "online" if online else "format"},
        )
        return valid, error

    def _validate_online(self, *, key_type: str, value: str) -> tuple[bool, Optional[str]]:
        try:
            import httpx
        except Exception:
            return True, None

        probes = {
            "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {value}"}),
            "anthropic": (
                "https://api.anthropic.com/v1/models",
                {"x-api-key": value, "anthropic-version": "2023-06-01"},
            ),
            "google": ("https://generativelanguage.googleapis.com/v1beta/models?key=" + value, {}),
            "deepseek": ("https://api.deepseek.com/v1/models", {"Authorization": f"Bearer {value}"}),
            "openrouter": ("https://openrouter.ai/api/v1/models", {"Authorization": f"Bearer {value}"}),
        }
        probe = probes.get(key_type)
        if probe is None:
            return True, None
        url, headers = probe
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(url, headers=headers)
            if 200 <= response.status_code < 300:
                return True, None
            return False, f"Provider responded with status {response.status_code}"
        except Exception as exc:
            return False, str(exc)


class _KeyFileWatcher(FileSystemEventHandler):
    """Watchdog handler for KeyManager keys file updates."""

    def __init__(self, manager: KeyManager) -> None:
        self.manager = manager

    def on_modified(self, event):  # noqa: ANN001 - watchdog callback signature
        if getattr(event, "is_directory", False):
            return
        path = Path(getattr(event, "src_path", "")).resolve()
        if path == self.manager.keys_file.resolve():
            self.manager._on_keys_file_changed()

    def on_created(self, event):  # noqa: ANN001 - watchdog callback signature
        if getattr(event, "is_directory", False):
            return
        path = Path(getattr(event, "src_path", "")).resolve()
        if path == self.manager.keys_file.resolve():
            self.manager._on_keys_file_changed()
