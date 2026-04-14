# sts2-agent

English | [简体中文](README.zh.md)

`sts2-agent` is an Agent/Mod prototype for *Slay the Spire 2*. It combines an in-game C# bridge mod, Python-side policies and orchestrator code, and local debugging tools for future LLM-driven autoplay.

## What This Repo Includes

- `src/sts2_agent/`: Python bridge client, policies, orchestrator, traces
- `mod/Sts2Mod.StateBridge/`: in-game STS2 bridge mod
- `mod/Sts2Mod.StateBridge.Host/`: local host for fixture/runtime-host validation
- `tests/`: Python tests
- `tools/`: build, install, validate, and live-debug scripts
- `docs/`: detailed setup, validation, compatibility, and upgrade notes

## Requirements

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1
- Windows install of *Slay the Spire 2*

## Quick Start

Build the mod against a real STS2 install:

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

Install and launch the bridge mod:

```bash
python tools/debug_sts2_mod.py install --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2"
python tools/debug_sts2_mod.py debug --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2"  --enable-writes
```

Run Python tests:

```bash
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

## Autoplay (Automatic Gaming)

The agent can automatically play the game using either an LLM (via Ollama/OpenAI) or MCTS policy.

### Full Autoplay (Recommended for testing)

To run the agent in full autoplay mode (handling combat, rewards, map, and events automatically):

**LLM Mode (Requires Ollama):**
```bash
$env:PYTHONPATH='src'; python tools/run_llm_autoplay.py --full-auto --model llama3
```

**MCTS Mode (Heuristic/Search):**
```bash
$env:PYTHONPATH='src'; python tools/run_mcts_autoplay.py --full-auto
```

*Note: Make sure the game is running with the Bridge Mod installed and writes enabled if you want the agent to actually perform actions in-game.*

## MCTS Self-Learning & AlphaZero

The agent supports MCTS with a Policy-Value neural network for self-learning. This mode doesn't rely on external LLMs and can be trained on your own gameplay traces.

### How to Train

1. **Collect Data**: Run the agent with MCTS (heuristic mode) to collect gameplay traces.
   ```powershell
   $env:PYTHONPATH='src'; python tools/run_mcts_autoplay.py --full-auto --trace-dir traces/collection
   ```
2. **Train Model**: Use the collected traces to train the Policy-Value network.
   ```powershell
   $env:PYTHONPATH='src'; python tools/train_mcts_model.py --trace-dir traces/collection --output-model models/sts2_mcts_v1.pth
   ```
3. **Use Model**: Run the agent using the trained model.
   ```powershell
   $env:PYTHONPATH='src'; python tools/run_mcts_autoplay.py --full-auto --model-path models/sts2_mcts_v1.pth
   ```

## Bridge API

Once loaded in-game, the bridge exposes:

- `GET /health`
- `GET /snapshot`
- `GET /actions`
- `POST /apply`
- `GET/POST/DELETE /agent-status`

Writes are disabled by default. Enable them explicitly before live action testing.

## Key Docs

- `docs/sts2-mod-local-development.md`: build, install, live debugging, and validation
- `docs/sts2-mod-upgrade-notes.md`: mod migration notes after game updates
- `docs/sts2-mod-agent-compatibility.md`: current bridge/runtime compatibility notes
- `docs/local-development.md`: local Python-side workflow notes
- `docs/prototype-validation.md`: fixture/prototype validation details

## Encoding Note

- Chinese docs and OpenSpec artifacts use UTF-8 without BOM.
- Avoid writing Chinese files through PowerShell text pipes; that may produce `???`.
