# 案例：DSH 上的 arc-1 连接器改造

本文件是 `mcp-connector-refactor` 的实战案例存档，执行同类任务时对照参考。
**只记录 DSH 自有设施。**

> 文中 `{SAP_HOST}` / `{client}` / `{用户}` / `{系统}` / `<选定根>` 等均为**占位示例**，
> 请替换为自己环境的实际值。

## 1. 背景与交付

- 目标：arc-1（SAP ADT MCP Server，npm 分发，stdio 传输，走 ADT REST API 连 SAP，非 GUI/COM）
- 交付：DSH 独立安装的 arc-1 + DSH 自有连接注册表 + 单连接器多系统架构
- 同时期还注册了 `mcp-sap-docs`（托管 HTTP 型），见 §6

## 2. 关键突破：找到 DSH 的 MCP 注册通道

前两轮排查方向错了——一直在翻 `~/.dsh-beta/settings.yaml` 与 `cordis.yml`，找不到 MCP 配置键。

**真相**：MCP server 由官方插件 `@deepseek-ai/dsh-mcp-client`（Cordis 插件）提供，
配置由第三方插件 `dsh-skill-mcp-panel`（随 profile 预装）通过其 CLI
写入 **profile 的 `cordis.patch.yml` 受管块**。

```bash
CLI="<DSH_HOME>/profiles/desktop/node_modules/dsh-skill-mcp-panel/lib/cli.js"
node "$CLI" mcp add --name arc-1 --stdio \
  --command "<node.exe 绝对路径>" \
  --args "<选定根>/run-conn.mjs" \
  --env SYSCONN_NAME={系统} --profile desktop
```

写入结果（受管块，勿手改）：

```yaml
# >>> dsh-skill-mcp-panel:mcp:begin
- insert:
    - id: panel-mcp-arc-1
      name: "@deepseek-ai/dsh-mcp-client"
      config:
        serverName: arc-1
        transport: stdio
        command: <node.exe 绝对路径>
        args: [<选定根>/run-conn.mjs]
        env: { SYSCONN_NAME: "{系统}" }
        toolCallTimeoutMs: 60000
        failOnStartupError: false
        reconnect: { enabled: true, initialDelayMs: 500, maxDelayMs: 30000, maxAttempts: 10 }
# <<< dsh-skill-mcp-panel:mcp:end
```

## 3. 架构决策：单连接器 + 按需调用

MCP 宿主拉起连接器时 env 是静态的：进程启动那刻绑定的系统在进程存续期不可切换。
因此"工具层面面对 N 个系统"只有两条真路：

| 路线 | 优点 | 代价 |
|------|------|------|
| 每系统一个连接器 | 常驻、零延迟、跨调用保持会话 | 每加一个系统多占一个进程、多一条注册 |
| **单连接器 + 按需调用**（本项目选定） | 加系统≠加连接器，注册表统一维护 | 非默认系统每次操作重新登录（约 1~2s），无会话缓存 |

## 4. 最终架构

```
注册表 <选定根>/sap-connections.json（唯一凭据源，N 条系统记录）
   │
   ├── 常驻：cordis.patch.yml 唯一 arc-1 条目
   │         → run-conn.mjs 启动器（默认系统，密码运行时注入，stdio inherit）
   └── 按需：conn-cli.mjs call <系统> <TOOL> '<jsonArgs>'（临时拉起→调用→退出）

conn-cli 子命令：list | show | default | add | remove | test | tools | call | sync
```

- 密码只在注册表（本机明文），`cordis.patch.yml` 与日志零凭据
- 注册表写入前自动 `.bak`
- 系统名模糊匹配（子串 + 忽略大小写）
- **安全开关由注册表驱动**（`allowWrites` / `allowedPackages` / `allowDataPreview` /
  `allowFreeSql` / `allowTransportWrites`），不在启动器里硬编码

## 5. 端到端实测记录（对应 SKILL.md §五 七级检查）

| 级别 | 实测结果 |
|------|----------|
| 握手级 | 应答含正确 serverInfo 与 protocolVersion |
| 认证级 | stderr 出现 `Startup auth preflight succeeded`（`/sap/bc/adt/core/discovery`） |
| 能力级 | tools/list 返回预期数量（写权限全开 12 个；只读默认姿态 8~9 个） |
| **业务级** | 只读工具调用返回**真实数据**（唯一可信的端到端证据） |
| 配置级 | `cordis.patch.yml` 受管块合法、条目数符合架构决策、零密码 |
| 易用性 | 模糊匹配（如口述系统名子串）能命中注册表条目 |
| 安全级 | policy 实测与注册表开关一致（`writes` / `data` / `sql` / `transports`） |

`dsh-panel mcp test arc-1` → 「连接成功，发现 N 个工具」。

## 6. 姊妹案例：mcp-sap-docs（托管 HTTP 型，装法完全不同）

`marianfoo/mcp-sap-docs` —— **虽有 package.json，但官方推荐用托管端点**，
属"托管 HTTP 型"，**不要 npm 安装**：

```bash
node "$CLI" mcp add --name sap-docs --http \
  --url "https://mcp-sap-docs.marianzeis.de/mcp" --profile desktop
```

- 变体：`sap-docs`（广，9 工具）｜`abap`（多 `abap_lint`，索引更小）
- 公开只读、无需 API key、**不涉及连接注册表**
- 验活：`GET /health` → `{"status":"healthy","version":...}`
- 握手：POST `initialize`，Header 须含 `Accept: application/json, text/event-stream`，
  响应为 SSE（`data: {...}`），需正则抽 JSON 并复用 `mcp-session-id`

**教训**：装前先读 README 的 Install 段，判定 npm stdio / 托管 HTTP / 自建索引三类，
不要见到 package.json 就 npm install。

## 7. 相关文件清单（DSH 自有）

| 文件 | 用途 |
|------|------|
| `<选定根>/sap-connections.json` | 连接注册表（凭据源） |
| `<选定根>/node_modules/arc-1` | arc-1 固定安装 |
| `<选定根>/conn-cli.mjs` | 连接管理 CLI |
| `<选定根>/run-conn.mjs` | 启动器（默认系统绑定） |
| `<DSH_HOME>/profiles/<profile>/cordis.patch.yml` | DSH MCP 注册（受管块） |
| `<DSH_HOME>/profiles/<profile>/node_modules/dsh-skill-mcp-panel/lib/cli.js` | `dsh-panel` CLI |
