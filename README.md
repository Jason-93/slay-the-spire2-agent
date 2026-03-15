# sts2-agent

English | [简体中文](README.zh.md)

`sts2-agent` is an Agent/Mod prototype for *Slay the Spire 2*. The goal of this repository is to connect in-game state extraction, action execution, automated decision making, and debugging tools into a stable foundation for future LLM-driven autoplay.

## Current Capabilities

- Python-side agent protocol models, bridge abstractions, heuristic policies, and orchestrator
- A C# in-game mod that exposes a local HTTP bridge inside the game process
- Real runtime state reading through `/health`, `/snapshot`, `/actions`, and `/apply`
- `phase="menu"` export for the main menu / run-start flow, making automation entry reproducible when no active run exists (see `docs/sts2-mod-agent-compatibility.md`)
- `.pck` packaging, install, launch, and live-debug scripts

## Repository Layout

- `src/sts2_agent/`: Python core logic, including bridge, policy, orchestrator, and trace code
- `tests/`: Python unit tests
- `mod/Sts2Mod.StateBridge/`: STS2 in-game bridge mod
- `mod/Sts2Mod.StateBridge.Host/`: local host program for fixture or runtime-host validation
- `tools/`: scripts for building `.pck`, installing the mod, launching debug sessions, and validating outputs
- `docs/`: supporting development docs, especially `docs/sts2-mod-local-development.md`
- `openspec/`: requirements, designs, and change records

## Requirements

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1, used to generate a game-compatible `.pck`
- A Windows installation of *Slay the Spire 2*

## Documentation Encoding Notes

- Chinese docs, OpenSpec artifacts, and related documentation use UTF-8 without BOM.
- Do not write Chinese files through PowerShell text pipes such as `@'...'@ | python -`; in this environment that can turn text into `???`.
- When updating Chinese docs, prefer direct file edits or `apply_patch`.

## Common Commands

### Python

```bash
python -m pytest
```

Run Python unit tests.

### Build the STS2 Mod

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

### Build / Install / Debug the Mod

```bash
python tools/debug_sts2_mod.py build
python tools/debug_sts2_mod.py install
python tools/debug_sts2_mod.py debug --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

### Live `POST /apply` Validation

Read-only discovery:

```bash
python tools/validate_live_apply.py
```

Launch the game, enable writes, and run a real autoplay validation:

```bash
python tools/validate_live_apply.py \
  --launch \
  --enable-writes \
  --apply \
  --allow-write \
  --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

Each run writes structured artifacts to `tmp/live-apply-validation/<timestamp>/`, including `health.json`, `before_snapshot.json`, `before_actions.json`, `apply_request.json`, `apply_response.json`, `after_snapshot.json`, `after_actions.json`, and `result.json`.

### Reward -> Map -> Next Battle Validation

When the game is already at a reward or map window and the bridge allows writes, you can validate the full transition with a conservative default policy:

```bash
python tools/validate_reward_map_next_battle.py \
  --apply \
  --allow-write
```

The script prefers `skip_reward`, then uses conservative default map routing until it returns to the next `combat` phase or times out. Artifacts are written to `tmp/reward-map-next-battle-validation/<timestamp>/` by default.

## Bridge API

After the mod is injected successfully, it exposes these local endpoints:

- `GET /health`: health status and provider mode
- `GET /snapshot`: current game-state snapshot
- `GET /actions`: current legal actions
- `POST /apply`: submit an action

The bridge starts in read-only mode by default. To execute real in-game actions, writes must be enabled explicitly.

`tools/validate_live_apply.py` also requires `--allow-write` as an explicit confirmation to avoid accidental live actions.

## LLM Autoplay

The repository already includes:

- `src/sts2_agent/bridge/http.py`: wraps the local STS2 HTTP bridge as `GameBridge`
- `src/sts2_agent/policy/llm.py`: OpenAI-compatible `chat/completions` policy
- `tools/run_llm_autoplay.py`: live autoplay entry point

The default local model endpoint is:

```text
http://127.0.0.1:8080/v1
```

You can inspect available models first:

```bash
curl http://127.0.0.1:8080/v1/models
```

`chat/completions` currently expects strict JSON with at least:

- `action_id`
- `target_id`: return `null` for actions with no target
- `reason`
- `halt`
- `confidence`

Actual execution still depends only on the current legal actions. `target_id` is used to align targeted actions explicitly, and `confidence` is mainly used for trace and recovery diagnostics.

### Dry Run

Read the current state and query the model without submitting actions:

```bash
python tools/run_llm_autoplay.py \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --dry-run
```

### Live Autoplay for a Full Player Turn

Once you are in a real battle and writes are enabled on the bridge, you can run continuous autoplay for one full player turn:

```bash
python tools/run_llm_autoplay.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --max-actions-per-turn 12
```

Common options:

- `--dry-run`: model decision only, no `/apply`
- `--trace-dir`: set the trace output directory
- `--max-steps`: cap total decision steps for the run
- `--max-actions-per-turn`: cap actions in the current player turn
- `--no-auto-end-turn-when-only-end-turn`: stop instead of auto-ending when only `end_turn` remains
- `--no-stop-after-player-turn`: disable the default "stop after one player turn" behavior and keep the older cross-window debug flow
- `--policy-timeout-seconds`: per-step model timeout

### Live Autoplay for a Full Battle

To play from the current player turn until the battle ends, handle reward/map transitions, and optionally reconnect to the next battle, enable battle mode:

```bash
python tools/run_llm_autoplay.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --battle-mode \
  --reward-mode safe-default \
  --map-mode safe-default \
  --stop-after-next-combat \
  --max-turns-per-battle 12 \
  --max-total-actions 48 \
  --wait-for-next-player-turn-seconds 30 \
  --transition-timeout-seconds 15
```

In battle mode, the runner keeps polling through enemy turns and animation windows until it:

- reaches cross-window states such as `reward`, `map`, or transition wait states and keeps advancing
- hits explicit stop boundaries such as `next_combat_entered`, `map_phase_reached`, or `reward_phase_reached`
- hits `max_turns_per_battle` or `max_total_actions`
- times out while waiting for the next player turn or a reward/map transition
- is interrupted by model or bridge failures

Additional common options:

- `--battle-mode`: enable full-battle mode; equivalent to disabling `stop_after_player_turn`
- `--reward-mode`: reward strategy, one of `halt`, `skip`, `skip-only`, `safe-default`, `llm`
- `--map-mode`: map strategy, one of `halt`, `safe-default`, `llm`
- `--stop-after-next-combat`: stop as soon as the next battle is entered, useful for validating cross-window flow
- `--max-turns-per-battle`: cap completed player turns for the full battle
- `--max-total-actions`: cap total submitted actions for the full battle
- `--max-consecutive-failures`: cap the consecutive failure budget
- `--max-recovery-attempts`: cap the recovery budget; once exhausted, stop with `recovery_budget_exhausted`
- `--wait-for-next-player-turn-seconds`: timeout while waiting for the next player turn
- `--transition-timeout-seconds`: timeout while waiting for reward/map/room transitions
- `--poll-interval-seconds`: polling interval during enemy turns or animation windows
- `--max-non-combat-steps`: cap reward/map/transition and other non-combat steps
- `--unknown-window-fuse`: stop after an unknown window appears this many times consecutively
- `--battle-context-recent-steps`: number of recent steps to keep in the battle summary

Each run outputs a `RunSummary` and saves a JSONL trace under `trace_dir`. Key turn-level fields:

- `turn_completed`: whether the current turn reached its stop boundary normally
- `actions_this_turn`: number of actions executed in the turn
- `ended_by`: final stop reason, such as `auto_end_turn`, `phase_changed`, or `max_actions_per_turn`

Additional full-battle fields:

- `battle_completed`: whether the current battle truly finished
- `turns_completed`: number of completed player turns
- `total_actions`: total submitted actions for the battle
- `current_turn_index`: currently observed player-turn index
- `reward_actions_taken` / `map_actions_taken`: number of actions submitted during reward and map phases
- `non_combat_steps`: total non-combat steps encountered during the run
- `next_combat_entered`: whether the runner successfully re-entered the next battle
- `recovery_attempts` / `recovery_successes`: recovery attempts and successes during the battle
- `last_recovery_reason`: the most recent recovery reason
- `battle_context`: the battle-level summary from the last trace

Each step trace includes at least:

- current `snapshot`
- current `legal_actions`
- model output `action_id` / `reason` / `halt`
- raw model response text `raw_response_text`
- bridge receipt or dry-run result

In multi-step turn mode, each trace also records:

- `step_index`
- `actions_this_turn`
- `phase_kind` / `step_kind`
- `transition_elapsed_seconds`
- `battle_context`
- `recovery_attempts` / `recovery_successes` / `recovery_streak`
- `is_final_step`
- `stop_reason`

### Full-Battle Smoke Validation

To persist battle autoplay completion, recovery counts, and final stop reason as stable artifacts:

```bash
python tools/validate_full_battle_llm.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --allow-write
```

The script writes the following files under `tmp/full-battle-llm-validation/<timestamp>/`:

- `health.json`
- `summary.json`
- `trace_tail.json`
- `result.json`

`result.json` explicitly records `battle_completed`, `turns_completed`, `total_actions`, `recovery_attempts`, `recovery_successes`, and the final `stop_reason`.

## Current Progress

At this point, the repository can already:

- inject the bridge into a real STS2 process
- read state across map, combat, reward, and related windows
- provide standardized state and action data for future agent or LLM integration

Next steps will keep expanding runtime fields, increase action coverage, and connect model decisions more deeply to the existing bridge.
