# Vagus Asistent — Security Guide

## Содержание

1. [Архитектура хранения ключей](#архитектура-хранения-ключей)
2. [Master Key Strategy](#master-key-strategy)
3. [Audit Logging](#audit-logging)
4. [Защита репозитория](#защита-репозитория)
5. [Security Best Practices](#security-best-practices)
6. [Ротация ключей](#ротация-ключей)
7. [Что делать если ключ скомпрометирован](#что-делать-если-ключ-скомпрометирован)
8. [CI/CD Secret Scanning](#cicd-secret-scanning)

---

## Архитектура хранения ключей

API-ключи **никогда не хранятся в открытом виде** на диске.

### Цепочка шифрования

```
Plaintext API key
      │
      ▼
  AES-256-GCM encrypt
  ┌─────────────────────────────────────┐
  │  Data Key  = PBKDF2-SHA256(         │
  │               master_key,           │
  │               random_salt_16_bytes, │
  │               390 000 iterations    │
  │             )                       │
  │  Nonce     = random 12 bytes        │
  │  AAD       = b"vagus.keys.v1"       │
  └─────────────────────────────────────┘
      │
      ▼
  ~/.vagus/keys.enc   (JSON envelope: version/salt/nonce/ciphertext)
```

- Каждая запись генерирует новые `salt` и `nonce` — rainbow-table атаки невозможны.
- `AAD` (Additional Authenticated Data) защищает от подмены envelope.
- Файл имеет права `0600` (только владелец).

### Windows: DPAPI

На Windows master key дополнительно защищается через **Windows Data Protection API (DPAPI)**:

- Расшифровать master key может только текущий Windows-пользователь на том же компьютере.
- При первом запуске происходит автоматическая миграция legacy-ключа в DPAPI-envelope.
- Plaintext backup сохраняется в `~/.vagus/.keys_master.plain.bak` (права `0600`) для экстренного восстановления.

---

## Master Key Strategy

Приоритет источников master key (от высшего к низшему):

| Приоритет | Источник | Описание |
|-----------|----------|----------|
| 1 | `VAGUS_KEYS_MASTER_KEY` (env) | Явно заданный ключ — для CI/staging |
| 2 | `~/.vagus/.keys_master` | Сохранённый ключ (DPAPI на Windows) |
| 3 | Автогенерация | `secrets.token_bytes(32)` при первом запуске |

**Рекомендации:**

- В production/staging задавайте `VAGUS_KEYS_MASTER_KEY` через secrets manager (GitHub Secrets, Vault, etc.).
- Никогда не коммитьте `VAGUS_KEYS_MASTER_KEY` в код или `.env`.
- Делайте резервную копию `~/.vagus/.keys_master` в надёжном месте (зашифрованное хранилище).

---

## Audit Logging

`KeyManager` поддерживает audit hooks для всех операций с ключами.

### Подключение hook

```python
from vagus.security import KeyManager

def my_audit_hook(*, action: str, details: dict) -> None:
    # action: "key.create" | "key.update" | "key.delete" | "key.validate"
    # details: {"name": "...", "type": "...", "valid": True/False, ...}
    # ВАЖНО: details НЕ содержит реальное значение ключа — только метаданные
    logger.info("AUDIT %s %s", action, details)

km = KeyManager()
km.set_audit_hook(my_audit_hook)
```

### Что логируется

| Событие | Поля в details |
|---------|---------------|
| `key.create` | `name`, `type` |
| `key.update` | `name`, `has_value_update` |
| `key.delete` | `name` |
| `key.validate` | `name`, `type`, `valid`, `error`, `mode` |

**Гарантии:** реальные значения ключей и master key **никогда** не попадают в audit log.

---

## Защита репозитория

### .gitignore

Следующие файлы исключены из git:

```
.env                        # реальные API ключи
.env.local / .env.production
configs/vagus.yaml          # локальная конфигурация
configs/windows.yaml
configs/telegram_test.yaml
*.enc                       # зашифрованные хранилища
.vagus/                     # директория с ключами
*.bak / *.legacy.*          # резервные копии
```

В git хранятся **только шаблоны**:
- `.env.example` — шаблон переменных окружения
- `configs/vagus.example.yaml` — шаблон конфигурации

### Pre-commit Hook

Установлен хук `.git/hooks/pre-commit`, который при каждом коммите:

1. Блокирует добавление файлов из `FORBIDDEN_FILES` (`.env`, `configs/vagus.yaml`, etc.)
2. Сканирует staged-контент по паттернам:
   - OpenAI API keys (`sk-proj-...`, `sk-...`)
   - Anthropic API keys (`sk-ant-api03-...`)
   - Google API keys (`AIza...`)
   - Generic secret assignments
   - Private key blocks (PEM)

При обнаружении — **коммит блокируется** с указанием файла, строки и типа нарушения.

---

## Security Best Practices

### Локальная разработка

```bash
# 1. Скопируйте шаблон
copy .env.example .env

# 2. Заполните реальными ключами (только в .env, никогда в коде)
# Откройте .env в редакторе и вставьте ключи

# 3. Генерация SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# 4. Проверьте что .env НЕ в git
git status  # .env не должен появляться
```

### Хранение ключей

- Используйте **KeyManager** для хранения ключей в шифрованном хранилище вместо plain `.env` в production.
- Для production рекомендуется: **HashiCorp Vault**, **AWS Secrets Manager**, **Azure Key Vault**.
- Разграничивайте ключи по окружениям: `dev`, `staging`, `production` — разные ключи с разными правами.

### Минимальные права

- Давайте API ключам минимально необходимые права (principle of least privilege).
- OpenAI: создавайте ключи с ограниченными правами в [API Keys dashboard](https://platform.openai.com/api-keys).
- Anthropic: используйте отдельные ключи для разных сервисов.

### Мониторинг использования

- Периодически проверяйте статистику использования ключей на дашборде провайдера.
- Настройте алерты на аномальное использование (расходы выше нормы, необычная геолокация).
- Используйте встроенный health-check: `GET /api/v1/keys/health`.

---

## Ротация ключей

### Плановая ротация (рекомендуется каждые 90 дней)

```bash
# 1. Сгенерируйте новый ключ на сайте провайдера
# 2. Добавьте новый ключ в систему (не удаляя старый)
vagus keys update --name openai --value sk-proj-NEW-KEY

# 3. Убедитесь что новый ключ работает
vagus keys validate --name openai

# 4. Обновите .env файл
# Замените значение OPENAI_API_KEY в .env

# 5. Деактивируйте старый ключ на сайте провайдера
```

### Через API

```bash
# Обновить значение ключа
curl -X PUT http://localhost:8000/api/v1/keys/openai \
  -H "Authorization: Bearer $SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"value": "sk-proj-NEW-KEY"}'

# Проверить статус
curl http://localhost:8000/api/v1/keys/health \
  -H "Authorization: Bearer $SECRET_KEY"
```

---

## Что делать если ключ скомпрометирован

### Немедленные действия (первые 5 минут)

1. **Отозвать ключ** на сайте провайдера:
   - OpenAI: [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Delete
   - Anthropic: [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → Deactivate
   - Google: [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) → Delete

2. **Проверить git историю** на наличие ключа:
   ```bash
   git log --all -p | grep "sk-proj\|sk-ant"
   ```

3. **Если ключ попал в git** — история считается скомпрометированной:
   ```bash
   # Установить BFG Repo Cleaner или git-filter-repo
   pip install git-filter-repo
   git filter-repo --replace-text <(echo "COMPROMISED_KEY==>REDACTED")
   # После этого ОБЯЗАТЕЛЬНО force-push и уведомить всех участников
   ```

4. **Сгенерировать новый ключ** и обновить `.env`.

### Последующие действия (первые 24 часа)

- Проверить логи использования скомпрометированного ключа (dashboard провайдера).
- Оценить возможный ущерб (несанкционированные запросы, расходы).
- Если использовался `SECRET_KEY` — пересоздать все JWT-токены пользователей.
- Обновить ключ во всех окружениях (dev, staging, production).
- Сообщить команде о инциденте.

### Checklist восстановления

- [ ] Ключ отозван у провайдера
- [ ] Новый ключ сгенерирован
- [ ] `.env` обновлён
- [ ] Сервис перезапущен и проверен
- [ ] Git история проверена / очищена
- [ ] Мониторинг логов активирован
- [ ] Команда уведомлена

---

## CI/CD Secret Scanning

### GitHub Actions

Добавьте в `.github/workflows/ci.yml`:

```yaml
- name: Secret Scan
  uses: trufflesecurity/trufflehog@main
  with:
    path: ./
    base: ${{ github.event.repository.default_branch }}
    head: HEAD
```

### Pre-commit (локально)

Хук уже установлен в `.git/hooks/pre-commit`. Для команды — добавьте в `pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

Установка:
```bash
pip install pre-commit detect-secrets
pre-commit install
detect-secrets scan > .secrets.baseline
```

### Переменные окружения в CI

Никогда не передавайте ключи через аргументы командной строки — они видны в логах:

```yaml
# ПЛОХО — ключ виден в логах
- run: python script.py --api-key sk-proj-...

# ХОРОШО — через секреты репозитория
- run: python script.py
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

---

*Последнее обновление: 2026-02-20*
