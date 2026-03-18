# sts2-agent

简体中文 | [English](README.md)

`sts2-agent` 是一个面向《Slay the Spire 2》的 Agent/Mod 原型仓库，包含游戏内 C# bridge mod、Python 侧策略与 orchestrator，以及配套的构建、校验和联调脚本，为后续接入大模型自动打牌提供基础设施。

## 仓库内容

- `src/sts2_agent/`：Python 侧 bridge client、policy、orchestrator、trace
- `mod/Sts2Mod.StateBridge/`：STS2 游戏内 bridge mod
- `mod/Sts2Mod.StateBridge.Host/`：fixture / runtime-host 联调宿主
- `tests/`：Python 单元测试
- `tools/`：构建、安装、验证、live 调试脚本
- `docs/`：详细开发文档、兼容性说明与升级注意事项

## 环境要求

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1
- Windows 版《Slay the Spire 2》

## 快速开始

基于真实 STS2 安装构建 mod：

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

安装并启动 bridge mod：

```bash
python tools/debug_sts2_mod.py install --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
python tools/debug_sts2_mod.py debug --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

运行 Python 测试：

```bash
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

## Bridge 接口

mod 成功注入后，会暴露：

- `GET /health`
- `GET /snapshot`
- `GET /actions`
- `POST /apply`
- `GET/POST/DELETE /agent-status`

默认只读；如需 live 写动作，请显式开启写入。

## 重点文档

- `docs/sts2-mod-local-development.md`：构建、安装、live 联调与验证
- `docs/sts2-mod-upgrade-notes.md`：游戏更新后的 mod 升级注意事项
- `docs/sts2-mod-agent-compatibility.md`：当前 bridge/runtime 兼容性说明
- `docs/local-development.md`：本地 Python 工作流说明
- `docs/prototype-validation.md`：fixture / prototype 校验说明

## 编码说明

- 中文文档与 OpenSpec artifacts 统一使用 UTF-8 无 BOM。
- 避免通过 PowerShell 文本管道写中文文件，否则可能出现 `???`。
