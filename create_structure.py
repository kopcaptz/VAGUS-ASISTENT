import os
import sys

base_path = r"C:\Users\kopca\OneDrive\Desktop\Cursor Ai\Vagus_Asistent"

# Структура Слоя 0
structure = [
    "src/vagus/layer0/config",
    "src/vagus/layer0/logging", 
    "src/vagus/layer0/security",
    "src/tests/layer0",
    "configs/backups",
    "docs",
    "scripts"
]

print("Создаю структуру Vagus Asistent...")

for folder in structure:
    full_path = os.path.join(base_path, folder)
    os.makedirs(full_path, exist_ok=True)
    print(f"✅ Создано: {folder}")

print("\nСтруктура создана!")
print("Теперь создаю основные файлы...")