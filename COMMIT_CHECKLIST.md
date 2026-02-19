# Чеклист перед первым коммитом

## Проверки

- [ ] `pip install -r requirements.txt` выполнен без ошибок
- [ ] `PYTHONPATH=src python scripts/verify.py` — все проверки [OK]
- [ ] `PYTHONPATH=src pytest tests/layer1/unit/ -v` — тесты проходят
- [ ] `PYTHONPATH=src python examples/layer1/basic_usage.py` — пример запускается
- [ ] Файл `.env` не добавлен в git (проверьте `.gitignore`)
- [ ] В коде нет захардкоженных API ключей

## Файлы для коммита

Основные файлы (около 50+):

```
src/vagus/           # исходный код
tests/               # тесты
docs/                # документация
examples/            # примеры
configs/             # пример конфига
scripts/             # скрипты проверки
README.md
SETUP.md
requirements.txt
.env.example
.gitignore
pytest.ini
TZ_LAYER1.md
```

## Команды для коммита

```bash
git init
git add .
git status   # проверьте, что .env и __pycache__ не в списке
git commit -m "Initial commit: Vagus Asistent Layer 1"
git branch -M main
git remote add origin <url>
git push -u origin main
```
