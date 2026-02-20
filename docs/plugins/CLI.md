# Plugin CLI

Команды управления плагинами доступны через:

`python -m vagus.layer3.cli.app plugin ...`

## Команды

- `plugin create <name> --template <basic|webhook|llm|ui> --destination <path>`
  - Создаёт новый плагин по шаблону.

- `plugin install <path_or_url_or_marketplace_id> [--version <version>]`
  - Устанавливает плагин:
    - из локальной директории;
    - из git/HTTP(S) URL;
    - из marketplace ID (через marketplace API).

- `plugin list [--enabled] [--disabled] [--all]`
  - Показывает таблицу установленных плагинов (`Name`, `Version`, `Status`, `Author`, `Description`).

- `plugin enable <plugin_name>`
  - Включает плагин.

- `plugin disable <plugin_name>`
  - Отключает плагин.

- `plugin uninstall <plugin_name> [--force]`
  - Удаляет плагин из локального хранилища.

## Локальное хранилище

CLI хранит установленные плагины и метаданные в:

- `~/.vagus/plugins/`
- `~/.vagus/plugins/registry.json`

Это позволяет `list/enable/disable/uninstall` работать между отдельными CLI-запусками.

## Примеры

```bash
python -m vagus.layer3.cli.app plugin create my-plugin --template basic
python -m vagus.layer3.cli.app plugin install ./my-plugin
python -m vagus.layer3.cli.app plugin list --all
python -m vagus.layer3.cli.app plugin disable my-plugin
python -m vagus.layer3.cli.app plugin enable my-plugin
python -m vagus.layer3.cli.app plugin uninstall my-plugin
```
