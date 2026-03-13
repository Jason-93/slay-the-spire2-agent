# sts2-agent

`sts2-agent` 是一个面向《Slay the Spire 2》的 Agent/Mod 原型仓库，目标是把游戏内状态抽取、动作接口、自动决策和调试工具串起来，为后续接入大模型自动打牌提供稳定基础。

## 当前能力

- 提供 Python 侧的 Agent 协议模型、bridge 抽象、启发式策略和 orchestrator
- 提供 C# in-game mod，可在游戏进程内暴露本地 HTTP bridge
- 已支持读取真实运行时状态，并提供 `/health`、`/snapshot`、`/actions`、`/apply`
- 已提供 `.pck` 打包、安装、启动和联调脚本

## 仓库结构

- `src/sts2_agent/`：Python 侧核心逻辑，包括 bridge、policy、orchestrator、trace
- `tests/`：Python 单元测试
- `mod/Sts2Mod.StateBridge/`：STS2 in-game bridge mod
- `mod/Sts2Mod.StateBridge.Host/`：本地宿主程序，用于 fixture 或 runtime-host 联调
- `tools/`：构建 `.pck`、安装 mod、启动调试、校验产物的脚本
- `docs/`：补充开发文档，重点参考 `docs/sts2-mod-local-development.md`
- `openspec/`：需求、设计和变更记录

## 环境要求

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1（用于生成与游戏兼容的 `.pck`）
- 已安装的《Slay the Spire 2》Windows 版

## 常用命令

### Python 侧

```bash
python -m pytest
```

运行 Python 单元测试。

### 构建 STS2 mod

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

### 一键构建 / 安装 / 调试 mod

```bash
python tools/debug_sts2_mod.py build
python tools/debug_sts2_mod.py install
python tools/debug_sts2_mod.py debug --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

## Bridge 接口

mod 成功注入后，会在本地暴露以下接口：

- `GET /health`：健康状态与 provider 模式
- `GET /snapshot`：当前局面快照
- `GET /actions`：当前合法动作列表
- `POST /apply`：提交动作

默认以只读模式启动；如需真实执行动作，需显式开启写入能力。

## 当前进度

目前仓库已经能够：

- 在真实 STS2 进程中挂载 bridge
- 获取地图、战斗、奖励等窗口阶段的状态
- 为后续 Agent 或大模型接入提供标准化的状态和动作数据

后续会继续补齐更多游戏字段、扩大动作执行覆盖率，并把大模型决策接到现有 bridge 之上。
