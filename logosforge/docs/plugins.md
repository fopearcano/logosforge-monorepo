# Logosforge Plugin Development Guide

## Plugin Folder Structure

Each plugin lives in its own folder inside `plugins/` at the project root:

```
plugins/
  my_plugin/
    plugin.json
    plugin.py
```

A plugin is valid when both `plugin.json` and `plugin.py` exist.

## Manifest (`plugin.json`)

Required fields:

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "What this plugin does."
}
```

Optional fields:

| Field | Default | Description |
|---|---|---|
| `entry_point` | `"plugin.py"` | Python file to load |
| `enabled_by_default` | `true` | Whether the plugin starts enabled |

## Entry Point (`plugin.py`)

Your plugin module must define a `register(api)` function:

```python
def register(api):
    api.log("My plugin loaded.")

    def my_action():
        api.show_message("Hello", "Plugin action triggered.")

    api.register_menu_action("My Action", my_action)
```

The `api` object is a `PluginAPI` instance with the methods listed below.

## Plugin API Reference

### `api.register_menu_action(name, callback)`
Adds an item to the **Plugins** menu in the menu bar. `callback` is called when the user clicks it.

### `api.log(message)`
Records a log line visible in the Plugins view details panel.

### `api.show_message(title, message)`
Shows a simple information dialog.

### `api.get_project_title() -> str`
Returns the current project title (read-only).

### `api.get_scene_titles() -> list[str]`
Returns a list of all scene titles in the current project (read-only).

### `api.get_scene_count() -> int`
Returns the number of scenes in the current project.

## Minimal Example

`plugins/example_plugin/plugin.json`:
```json
{
  "id": "example_plugin",
  "name": "Example Plugin",
  "version": "1.0.0",
  "author": "Logosforge",
  "description": "A minimal example plugin."
}
```

`plugins/example_plugin/plugin.py`:
```python
def register(api):
    api.log("Example plugin loaded.")

    def greet():
        title = api.get_project_title()
        count = api.get_scene_count()
        api.show_message(
            "Hello from Plugin",
            f"Project: {title}\nScenes: {count}",
        )

    api.register_menu_action("Hello from Plugin", greet)
```

## Enable / Disable

Plugins can be enabled or disabled from the **Plugins** view in the sidebar. State changes take effect on next launch.

Enabled state is stored in `~/.logosforge/settings.json` under `"plugin_states"`.

## Limitations

- Plugins run in the same process as the app (no sandboxing).
- The API is read-only — plugins cannot modify project data directly.
- No dependency resolution between plugins.
- No hot reloading — restart the app after adding or modifying plugins.
- A broken plugin is caught at load time and marked as errored without crashing the app.
