#!/usr/bin/env bash
# Проверка Redis перед запуском Redis Streams в production.
# Запустить из корня проекта после: docker compose up -d

set -e

echo "=== 1. Запуск Docker Compose ==="
docker compose up -d

echo ""
echo "=== 2. Ожидание Redis (5 sec) ==="
sleep 5

echo ""
echo "=== 3. Redis ping ==="
python -c "
import redis
r = redis.Redis(host='localhost', port=6379)
ok = r.ping()
print('PING:', ok)
if not ok:
    exit(1)
"

echo ""
echo "=== 4. Redis version (должна быть >= 7.0) ==="
docker exec vagus-redis redis-server --version

echo ""
echo "=== 5. Инфраструктурные тесты ==="
python -m pytest tests/infrastructure/test_redis_streams.py -v

echo ""
echo "=== Готово: Redis готов к Redis Streams ==="
