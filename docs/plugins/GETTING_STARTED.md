# Plugins: Getting Started

## 1) Create plugin directory

```text
my_plugin/
├── manifest.json
└── plugin.py
```

## 2) Add `manifest.json`

```json
{
  "name": "hello_world_plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Minimal Vagus plugin",
  "dependencies": [],
  "python_version": ">=3.10",
  "vagus_version": ">=0.1.0",
  "entry_point": "plugin:HelloWorldPlugin",
  "hooks": [
    {
      "name": "on_message_received",
      "priority": 80,
      "callback": "HelloWorldPlugin.on_message_received",
      "is_async": false
    }
  ],
  "permissions": ["messages:read"]
}
```

## 3) Implement plugin code (`plugin.py`)

```python
class HelloWorldPlugin:
    def on_message_received(self, message: dict) -> dict:
        updated = dict(message)
        updated["text"] = f"Hello from plugin! {updated.get('text', '')}".strip()
        return updated
```

## 4) Load plugin

```python
from vagus.plugins.loader import LocalLoader
from vagus.plugins.registry import PluginRegistry

loader = LocalLoader()
registry = PluginRegistry()

plugin = loader.load("./my_plugin")
registry.register(plugin)
```

## 5) Enable hook execution

```python
from vagus.plugins.hooks import HookSystem

hook_system = HookSystem()
instance = plugin.entry_point() if callable(plugin.entry_point) else plugin.entry_point
hook_system.register_manifest_hooks(instance, plugin.manifest.hooks)
```

## 6) Configure plugin subsystem

In `configs/vagus.yaml`:

```yaml
plugins:
  enabled: true
  auto_discover: true
  scan_directories:
    - "./plugins"
    - "~/.vagus/plugins"
  sandbox:
    enabled: true
    memory_limit_mb: 512
    timeout_seconds: 30
  marketplace:
    url: "https://plugins.vagus.ai"
    cache_ttl_hours: 24
```

