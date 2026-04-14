# STS2 Mod 升级注意事项

本文记录近期 *Slay the Spire 2* 更新后，仓库内 bridge mod 需要同步调整的关键点，方便后续游戏再次更新时快速排查。

## 版本说明

- 本文基于当前已验证的游戏版本：`v0.99.1 (7ac1f450)`
- 当前 bridge `/health` 中已观测到：
  - `protocol_version="0.1.0"`
  - `mod_version="0.1.0.0"`
  - `provider_mode="in-game-runtime"`
- 这里的升级注意事项主要针对“游戏内置 mod loader 结构变化”，不等同于 bridge 协议版本变化

建议每次游戏更新后先记录两组版本：

- 游戏版本：从 `/health.game_version` 或游戏日志中确认
- bridge 版本：从 `/health.protocol_version` 与 `/health.mod_version` 确认

如果后续再次出现 mod 无法加载、文件名规则变化、manifest 字段变化，先把新游戏版本补到本文，再更新对应迁移步骤。

## 本次更新的核心变化

- mod manifest 不再放在 `.pck` 内部单独作为唯一入口，mod 目录下必须提供外置的 `<mod_id>.json`
- manifest 需要显式声明是否带有 `.dll` / `.pck`
- 游戏会按 `mod_id` 推导资源文件名，因此 `dll` / `pck` 文件名也要与 `mod_id` 对齐
- `settings.save` 现在会记录上次运行的 mod 加载顺序
- manifest 支持 `dependencies`
- manifest 新增 `affects_gameplay`

## 当前 bridge mod 的对应约定

当前仓库采用以下产物命名：

- `sts2-agent-bridge.json`
- `sts2-agent-bridge.dll`
- `sts2-agent-bridge.pck`

其中 `sts2-agent-bridge` 同时是：

- manifest 的 `id`
- `.dll` 文件名基座
- `.pck` 文件名基座

如果只改 json 文件名而没有同步改 `.dll` / `.pck`，游戏日志通常会出现：

- 找到 manifest
- 但找不到 `sts2-agent-bridge.dll`
- 或找不到 `sts2-agent-bridge.pck`

## 新版 manifest 字段

当前 mod 至少需要包含这些字段：

```json
{
  "id": "sts2-agent-bridge",
  "name": "STS2 Agent Bridge",
  "author": "netcan",
  "description": "Loopback bridge for exporting and controlling Slay the Spire 2 runtime state.",
  "version": "0.1.0",
  "has_pck": true,
  "has_dll": true,
  "dependencies": [],
  "affects_gameplay": true
}
```

说明：

- `has_dll=true`：告诉 loader 需要加载程序集
- `has_pck=true`：告诉 loader 需要加载 Godot 资源包
- `dependencies=[]`：当前 bridge 没有额外 mod 依赖
- `affects_gameplay=true`：bridge 会读写局面状态，不应标记为纯 UI mod

## 升级排查清单

游戏更新后，如 bridge 无法加载，优先按下面顺序检查：

1. manifest 文件名是否为 `<mod_id>.json`
2. `id`、`.dll`、`.pck` 是否同名基座
3. manifest 是否包含 `has_dll` / `has_pck`
4. 游戏日志是否出现 `Loading assembly DLL ...` 与 `Loading Godot PCK ...`
5. `settings.save` 中的 mod 顺序是否被旧配置干扰
6. 如后续增加依赖，检查 `dependencies` 是否与实际 load order 一致

## 推荐验证方式

构建并安装：

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"

python tools/debug_sts2_mod.py install --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2"
python tools/debug_sts2_mod.py debug --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2"
```

启动成功后，日志中应至少看到：

- `Found mod manifest file ...\\sts2-agent-bridge.json`
- `Loading assembly DLL ...\\sts2-agent-bridge.dll`
- `Loading Godot PCK ...\\sts2-agent-bridge.pck`

并且 `GET /health` 应返回 `provider_mode="in-game-runtime"`。
