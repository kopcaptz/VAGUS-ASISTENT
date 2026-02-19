# Hello World Plugin

Minimal plugin example for Vagus plugin subsystem.

## Files

- `manifest.json` — plugin metadata and hook declarations.
- `plugin.py` — runtime implementation (`HelloWorldPlugin`).

## Local loading example

```python
from vagus.plugins.loader import LocalLoader

plugin = LocalLoader().load("examples/plugins/hello_world_plugin")
instance = plugin.entry_point()  # HelloWorldPlugin class
print(instance.on_message_received({"text": "test"}))
```
