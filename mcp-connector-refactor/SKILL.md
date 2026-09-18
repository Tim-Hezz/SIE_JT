---
name: mcp-connector-refactor
version: 1.0.0
description: DSH（DeepSeek Harness）自有 MCP 连接器安装与多系统连接改造方法论。当用户要求安装/注册 MCP server 到 DSH、改良或重构 MCP 连接器（arc-1 等 stdio server、HTTP server）、实现"单连接器+按需调用"多系统架构、建立 DSH 自有连接注册表与管理 CLI、修复连接器启动链（Windows 编码/spawn/沙箱管道 EPERM）时使用。触发词：改良连接器、改造 arc-1、安装 MCP、注册 MCP、多系统连接、连接注册表、MCP 启动器、connector refactor。
agent_created: true
---

# DSH MCP 连接器安装与改良方法论（mcp-connector-refactor）

本技能沉淀自 arc-1（SAP ADT MCP Server）在 **DSH** 上的连接器改造实践。
**本文档只讲 DSH 自有设施，不涉及 workbuddy 或任何其他宿主。**
完整案例细节见 `references/arc1-case-study.md`。

> **首次使用先看这几条**：
> 1. **占位符**：文中 `<选定根>` / `<DSH_HOME>` / `{系统}` / `{SAP_HOST}` 等都是占位示例，
>    请替换为自己环境的实际值。
> 2. **依赖**：Node ≥ 22.19（arc-1 要求）；`dsh-skill-mcp-panel` 插件（随 profile 预装）；
>    Windows 下用 `npm.cmd`（`.ps1` 常被执行策略禁用）。
> 3. **写 `~/.dsh-beta` 需要工作区外写权限**（danger-full-access）——
>    注册 MCP 时会写 profile 的 `cordis.patch.yml`。
> 4. **本技能讲的是"怎么装/怎么改连接器"**；具体 SAP 侧的对象读写与 ADT 细节
>    见 `sap-arc1-write`（本技能不重复那些内容）。


---

## 零、DSH 的 MCP 注册机制（先搞懂这个，否则全是白干）

### 唯一的正规注册入口：`dsh-panel mcp`

DSH 的 MCP server 由官方插件 `@deepseek-ai/dsh-mcp-client` 提供，它是 **Cordis 插件**，
配置写在 **profile 的 `cordis.patch.yml`** 里，由 DSH 的 HMR 热加载。

**不要去翻 `settings.yaml` / `cordis.yml` —— 那里没有 MCP 配置键。**
正确通道是 `dsh-skill-mcp-panel` 插件自带的 CLI（该插件通常已随 profile 安装）：

```bash
# CLI 绝对路径（profile 名按需替换 desktop / web）
CLI="C:\Users\<用户>\.dsh-beta\profiles\desktop\node_modules\dsh-skill-mcp-panel\lib\cli.js"

# stdio 型
node "$CLI" mcp add --name <名> --stdio --command <绝对路径exe> \
  --args <绝对路径脚本> --env KEY=VALUE --profile desktop

# HTTP 型（streamable-http）
node "$CLI" mcp add --name <名> --http --url <url> --profile desktop

node "$CLI" mcp list   --profile desktop     # 列出
node "$CLI" mcp test <名> --profile desktop  # 连接测试（会列工具）
node "$CLI" mcp enable|disable <名> --profile desktop
node "$CLI" mcp remove <名> --yes --profile desktop
```

它写入 `cordis.patch.yml` 的**受管块**：

```yaml
# >>> dsh-skill-mcp-panel:mcp:begin
- insert:
    - id: panel-mcp-<名>
      name: "@deepseek-ai/dsh-mcp-client"
      config:
        serverName: <名>          # ^[A-Za-z0-9_-]{1,32}$
        transport: stdio | streamable-http
        command / args / env      # stdio
        url / headers             # http
        toolCallTimeoutMs: 60000
        failOnStartupError: false
        reconnect: { enabled, initialDelayMs, maxDelayMs, maxAttempts }
# <<< dsh-skill-mcp-panel:mcp:end
```

**块内内容勿手改**；块外的用户内容逐字节保留。

### 三种 server 类型，装法完全不同

| 类型 | 判定 | 装法 |
|------|------|------|
| **npm stdio 包** | package.json 有 `bin`，README 说 stdio | npm 安装到 DSH 自有目录 → `mcp add --stdio` |
| **托管 HTTP 端点** | README 给 `https://.../mcp`，无需 key | **不要 npm 安装**，直接 `mcp add --http --url ...` |
| **需自建索引的仓库** | 要 `npm run setup && npm run build` | 先评估代价（可能要几十 GB/数小时），再决定是否本地部署 |

> 实例：`mcp-sap-docs` 虽有 package.json，但官方推荐用托管端点 `https://mcp-sap-docs.marianzeis.de/mcp`，
> 属第二类——**硬去 npm 安装是错的**。装前务必读 README 的 Install 段。

### 路径约定（DSH 自有）

| 用途 | 路径 |
|------|------|
| 连接注册表 | `<选定根>/sap-connections.json` |
| 连接器安装目录 | `<选定根>/node_modules/<pkg>` |
| 启动器 / CLI | `<选定根>/run-conn.mjs`、`conn-cli.mjs` |
| DSH MCP 注册 | `~/.dsh-beta/profiles/<profile>/cordis.patch.yml` |

`<选定根>` 由用户指定（例：`D:\<工作区>\_install\arc-1`）。

---

## 一、适用场景

1. **新连接器安装**：从 npm/GitHub 安装 MCP server 并固化（避免 npx 按需拉取）
2. **多系统连接改造**：一个连接器面对多个后端系统（多 SAP 系统、多数据库、多环境）
3. **启动链修复**：配置存在但拉起失败（路径迁移、编码、spawn、认证注入）
4. **凭据治理**：密码从 `cordis.patch.yml` 收敛到独立注册表

## 二、核心目标与前提条件

**改造完成态（五项验收标准）**：

| # | 标准 |
|---|------|
| 1 | 注册表 `<选定根>/sap-connections.json` 是唯一凭据源（name / url / client / user / language / password / default） |
| 2 | `cordis.patch.yml` 中该连接器条目**零密码**，只留 `SYSCONN_NAME: <系统>` |
| 3 | CLI 提供九个子命令：`list / show / default / add / remove / test / tools / call / sync` |
| 4 | 非默认系统经**按需一次性调用**访问（临时拉起→调用→退出）——加系统 ≠ 加连接器 |
| 5 | "用户报系统名 → 建连 → 报告结果"由配套技能自然语言触发 |

**动手前逐项确认**：
1. 官方 README 的 **Install 段**已读——先判定属上述三类中的哪一类，**不凭猜测装**
2. Node ≥ 服务要求版本（arc-1 要 ≥22.19）；本机可用 `C:\Program Files\nodejs\node.exe`
3. 至少一套真实凭据可做只读端到端验证
4. `dsh-panel` CLI 路径与目标 profile 名已知
5. 用户已就架构做选择："每系统一个常驻连接器" vs "单连接器+按需调用"

## 三、分步操作流程

### 阶段 1：现状盘点与文档核对
- `dsh-panel mcp list --profile <名>`：看 DSH 当前有哪些 MCP server
- WebFetch 官方 README，**重点读 Install 段与 Tools 段**，判定 server 类型
- 文档 404 时回退 `raw.githubusercontent.com` 的 README 原文
- 若为 HTTP 型：先 `curl <url 同源>/health` 验活，再走协议握手

### 阶段 2：环境预检与安装
- **stdio 型**：
  ```powershell
  # npm 缓存必须改到工作区内，否则 %LOCALAPPDATA%\npm-cache 被沙箱拒绝（EPERM）
  # 且必须调 npm.cmd（npm.ps1 被执行策略禁用）
  & "C:\Program Files\nodejs\npm.cmd" install <pkg> --prefix <选定根> `
      --cache "<选定根>\.npm-cache" --no-audit --no-fund
  ```
- 从 package.json 的 `bin` 解析入口**绝对路径**（`typeof p.bin === 'string' ? p.bin : Object.values(p.bin)[0]`）
- **HTTP 型**：跳过安装，仅探活

### 阶段 3：MCP 握手探针（先验证，不动配置）
- **关键**：DSH 沙箱内 **Node 不能用 `stdio:'pipe'` spawn 子进程**（EPERM，见 §四-1），
  所以**不要用 Node 写探针脚本**——改用 **PowerShell 直接驱动子进程 stdin/stdout**：

```powershell
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'C:\Program Files\nodejs\node.exe'
$psi.Arguments = '"<入口.js>" --transport stdio <参数>'
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $false      # 放行到控制台，便于看认证预检
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)
$proc.StandardInput.WriteLine('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1.0.0"}}}')
$proc.StandardInput.WriteLine('{"jsonrpc":"2.0","method":"notifications/initialized"}')
$proc.StandardInput.Flush()
# 逐行读 stdout 直到拿到 id=1 的应答；切勿用 ReadToEndAsync（会死锁）
```

- **禁止 `ReadToEndAsync()` 后再 `.Result`**——进程不退，管道不关，管道一满就死锁（实测挂在 120s）。
  必须 `ReadLine()` 逐行读到目标 id 为止。
- HTTP 型探针：POST `initialize`，Header 需 `Accept: application/json, text/event-stream`，
  响应是 SSE（`data: {...}`），用正则抽 JSON；记下响应头 `mcp-session-id` 供后续请求复用。
- 只读调用被安全策略拦截（如 `allowDataPreview=false`）属默认设计，不是故障

### 阶段 4：注册进 DSH
- 用 `dsh-panel mcp add`（见 §零），**不要手写 cordis.patch.yml**
- 写入后 `read` 回读全文校验：受管块结构完整、条目正确、**无明文密码**
- `dsh-panel mcp test <名>` 应报「连接成功，发现 N 个工具」

### 阶段 5：注册表 + 管理 CLI + 启动器（多系统改造核心）
1. **注册表**：每系统一条记录；写文件前自动 `.bak` 备份
2. **CLI**（`conn-cli.mjs` 风格）：
   - `list` / `show` / `default <名>` / `add --name --url [--client --user --lang --password --default]` / `remove`
   - `test <名>`：临时拉起服务，MCP 握手 + 解析 stderr 认证预检 → 报告成败
   - `tools <名>`：tools/list 列出工具
   - `call <名> <TOOL> [jsonArgs]`：一次性调用任意工具并回显结果
   - `sync [--dry-run]`：按注册表重写本连接器条目（**保留无关条目**）
3. **启动器**（`run-conn.mjs` 风格）：`cordis.patch.yml` 条目指向它，按 `env.SYSCONN_NAME`
   从注册表取参、**stdio inherit** 拉起服务——密码运行时注入，配置文件零凭据
4. **安全开关由注册表驱动**（`allowWrites` / `allowedPackages` / `allowDataPreview` /
   `allowFreeSql` / `allowTransportWrites`），**不要在启动器里硬编码**——
   否则每个新系统都被迫继承同一套权限

关键要点：
- 系统名支持**模糊匹配**（子串/忽略大小写），口述"`{代号}`"命中"`{代号}系统`"
- 单连接器架构下只生成 1 个条目（默认系统）

### 阶段 6：端到端实测
`list` → `test <系统>`（CONNECTION OK）→ `tools <系统>` → `call <系统> <只读工具>`
返回**真实数据** → 回读 `cordis.patch.yml` 校验 → 经启动器握手。全部通过才算完成。

### 阶段 7：技能化与记忆沉淀
- 触发技能：用户说"连接 <系统名>"→ 查注册表 → test → 报告结果
- 更新长期记忆（架构决策、路径、坑点）与当日工作日志

## 四、常见问题与解决方案

| # | 症状 | 根因 | 解法 |
|---|------|------|------|
| 1 | `spawn EPERM`（Node 起子进程时） | **DSH 沙箱禁止 Node 以 `stdio:'pipe'` spawn**（命名管道受限） | 探针改用 PowerShell 直驱子进程；`stdio:'inherit'` 的启动器不受影响。判据：对**本机**目标跑同样命令也 EPERM 即证明是沙箱 |
| 2 | 探针挂在 120s 无输出 | `ReadToEndAsync().Result` 等进程退出，但管道未关→死锁 | 改 `ReadLine()` 逐行读到目标 id；或用 `stdin` 管道喂完消息后**逐行读 stdout** |
| 3 | `EPERM: operation not permitted, open '...npm-cache...'` | npm 默认缓存在用户目录，沙箱只允许工作区内写 | `--cache "<工作区内路径>"` |
| 4 | `npm.ps1 无法加载，因为在此系统上禁止运行脚本` | PowerShell 执行策略禁 `.ps1` | 一律调 `npm.cmd`，且 `.ps1` 脚本须内联执行 |
| 5 | `dsh-panel ... EPERM ... cordis.patch.yml.panel.lock` | `~/.dsh-beta` 在工作区之外，沙箱拒绝写 | 需要工作区外写权限（danger-full-access）才能注册 |
| 6 | `spawn ... ENOENT` 或 npx 拉起失败 | Windows 不能直接 spawn npx/.cmd；托管 node 版本目录会变 | node.exe 直启 bin 入口 .js；托管运行时路径**动态扫描**，勿硬编码版本目录 |
| 7 | CLI 大量 console.log 后输出丢失/为空 | `process.exit()` 不等管道缓冲排空 | 全部改 `process.exitCode` 自然退出 |
| 8 | 机械替换 exit→exitCode 后命令行为错乱 | 原分支依赖 exit 即时终止，改后落入后续分支 | 重构为 if/else-if + return 守卫式，每分支显式 return |
| 9 | 服务报 authentication required | env 变量未传入或 wrapper 注入失败 | 列 .env 键名（隐藏值）核对变量名；wrapper 链与直启 exe 两路隔离诊断 |
| 10 | 装了才发现装错类型 | 没读 README 的 Install 段 | HTTP 托管型**不要 npm 安装**；装前先判定三类 |
| 11 | 改了 `cordis.patch.yml` 但当前会话工具没变 | 工具列表在**会话建立时**装配 | 提示用户**开新会话**；配置本身已热加载 |
| 12 | 旧条目指向已迁移路径 | 目录迁移后配置未同步 | `dsh-panel mcp remove` + `add` 重注册，再冒烟验证 |

## 五、验证改良效果（七级检查）

| 级别 | 检查项 |
|------|--------|
| 握手级 | initialize 应答含正确 serverInfo（版本号） |
| 认证级 | stderr 出现认证预检成功字样（如 `Startup auth preflight succeeded`） |
| 能力级 | tools/list 返回预期数量的工具 |
| **业务级** | **至少一次真实只读调用返回真实数据（唯一可信的端到端证据）** |
| 配置级 | 回读 `cordis.patch.yml`：受管块合法、条目数符合架构决策、块外内容未动、**无明文密码** |
| 易用性 | 模糊名称命中注册表；启动器表现与宿主实际拉起一致 |
| 安全级 | 写类操作按注册表开关正确启停；默认姿态是否符合系统性质（生产必收紧） |

## 六、执行守则

- 同一动作连续失败 2 次即停止，报告用户并请求决策（用户硬性要求）
- 改任何含格式/含凭据文件前先 `.bak` 备份（技能文件备份到 `~/.dsh-beta/skill-backups/`）
- 密码永不写入日志、探针输出与对话回显
- **装前先读 README 的 Install 段**，判定 npm stdio / 托管 HTTP / 自建索引三类
- 注册后提示用户**开新会话**才能看到新工具
- 安全开关默认保守；对**生产**系统必须与用户逐项确认写权限
