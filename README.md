# sts2-agent

English | [简体中文](README.zh.md)

`sts2-agent` is an agent/mod prototype for *Slay the Spire 2*. The repository focuses on exposing structured in-game state, safe action execution, and local tooling so external policies or LLMs can drive live gameplay.

## What Works Today

- Python-side bridge abstractions, policies, orchestrator, and trace pipeline
- C# in-game mod exposing a local HTTP bridge
- Live runtime endpoints: `GET /health`, `GET /snapshot`, `GET /actions`, `POST /apply`
- Menu/start-run export with `phase="menu"` for reproducible automation entry points
- Packaging, install, launch, and validation scripts for the STS2 mod

## Repository Layout

- `src/sts2_agent/` - Python agent, bridge client, policies, orchestrator, traces
- `tests/` - Python unit tests
- `mod/Sts2Mod.StateBridge/` - in-game STS2 bridge mod
- `mod/Sts2Mod.StateBridge.Host/` - local host for fixture/runtime validation
- `tools/` - build, install, launch, and validation scripts
- `docs/` - local development and integration notes
- `openspec/` - proposals, designs, specs, tasks, and archived changes

## Requirements

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1 for `.pck` packaging
- Windows install of *Slay the Spire 2*

## Encoding Notes

- Chinese docs and OpenSpec artifacts use UTF-8 without BOM.
- Avoid writing Chinese files through PowerShell text pipes; it may corrupt text into `???`.

## Common Commands

### Python tests

```bash
python -m pytest
```

### Build the STS2 mod

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

### Build / install / debug

```bash
python tools/debug_sts2_mod.py build
python tools/debug_sts2_mod.py install
python tools/debug_sts2_mod.py debug --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

### Live apply validation

```bash
python tools/validate_live_apply.py
python tools/validate_live_apply.py --launch --enable-writes --apply --allow-write --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

### LLM autoplay

```bash
python tools/run_llm_autoplay.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --battle-mode
```

`chat/completions` is expected to return strict JSON with:

- `action_id`
- `target_id`
- `reason`
- `halt`
- `confidence`

### Full-battle smoke validation

```bash
python tools/validate_full_battle_llm.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --allow-write
```

Artifacts are written under `tmp/full-battle-llm-validation/<timestamp>/`.

## Bridge API

- `GET /health`
- `GET /snapshot`
- `GET /actions`
- `POST /apply`

Writes are disabled by default. Enable them explicitly before running live action tests.

## More Documentation

- Chinese guide: [README.zh.md](README.zh.md)
- Mod local development: `docs/sts2-mod-local-development.md`
- Validation notes: `docs/prototype-validation.md`
