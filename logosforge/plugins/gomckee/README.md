# Go McKee plugin for Logosforge

This plugin adapts the Go McKee runtime layer to the current Logosforge plugin format found in `plugins/example_plugin`.

## What it does

- Loads the canonical McKee JSON systems unchanged:
  - `story_system.json`
  - `character_system.json`
  - `dialogue_system.json`
- Validates trigger and conflict references at load time
- Classifies requests into `story`, `character`, and `dialogue`
- Preserves domain purity and domain nesting order:
  1. `story`
  2. `character`
  3. `dialogue`
- Applies methods as invisible constraints, not quoted advice
- Runs checks in revision/diagnosis mode
- Uses PSYKE-aware state when the host exposes it
- Exposes menu controls through the current Logosforge plugin API

## Current Logosforge-compatible controls

The repository example only confirms menu actions via `api.register_menu_action(...)`, plus a few project getters. So this plugin currently wires:

- `Go McKee: Enable`
- `Go McKee: Disable`
- `Go McKee: Explain Current Project`
- `Go McKee: Run Checks on Current Project`
- `Go McKee: Story Focus`
- `Go McKee: Character Focus`
- `Go McKee: Dialogue Focus`
- `Go McKee: All Domains`

## Command support

The engine itself supports these commands internally:

- `/gomckee on`
- `/gomckee off`
- `/gomckee story`
- `/gomckee character`
- `/gomckee dialogue`
- `/gomckee all`
- `/gomckee check`
- `/gomckee explain`

In the current repo, these are parsed by the service layer but are **not yet wired to a chat input hook**, because the example plugin API does not show such a hook.

## PSYKE integration

If the host later adds these optional API methods, the plugin will use them automatically:

- `get_current_scene()`
- `get_nearby_scenes()`
- `get_psyke_entries()`
- `get_character_states()`
- `get_relations()`
- `get_story_memory()`

If they are missing, the plugin degrades safely.

## Install

Copy `plugins/gomckee_plugin` into the repository's `plugins/` directory.

## Future extension point

`GoMcKeePlugin.evaluate_prompt(prompt, forced_domains=None)` is the clean handoff point for a future assistant hook. Once Logosforge exposes assistant interception or prompt middleware, call that method and merge `result.constraints` plus `result.checks` into the assistant runtime.
