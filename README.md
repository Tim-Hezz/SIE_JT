# SIE_JT

SAP 实施交付类 skill 集合（DSH / Claude Code 兼容的目录式 skill）。

> ⚠️ **本仓库为公开仓库**。所有内容必须**已脱敏**：不含客户名、内网 IP / 端口、
> 传输请求号、系统代号、账号口令，以及**客户私有的自开发对象名**。
> 文中的 `{SAP_HOST}` / `{TR}` / `{SAP系统}` / `ZRUN_*` / `ZGUI_*` 等**均为占位示例**，
> 使用时请替换为自己系统的实际值。

## 包含的 skill

每个 skill 一个顶层目录，目录内自带 `SKILL.md`（DSH 按此识别）。

| skill | 作用 |
|---|---|
| [`fs-quick-design/`](fs-quick-design/) | SAP 需求「快速技术方案」生成器（多轮确认制）。第一轮只出**业务框架图 + 技术框架图 + 界面图 + 要点/待确认**，先对齐业务理解，再谈细节 |
| [`sap-remote-rfc/`](sap-remote-rfc/) | 通过直连 HTTP 的 **SOAP RFC** 远程调用 SAP 标准函数模块（`TFDIR-FMODE='R'`），**全程不进 SAP GUI**。文本元素/TEXTPOOL 维护、GUI 状态复制与激活、远程跑报表取结果、远程查 ST22 dump |

---

## 安装

把**整个 skill 目录**拷到你的 skill 根目录即可，**DSH 会自动发现、不用重启**：

| 作用域 | 路径 |
|---|---|
| 用户级（推荐，所有工作区可用） | `<DSH_HOME>/skills/`（DSH_HOME 默认 `~/.dsh`） |
| 项目级 | `<项目根>/.dsh/skills/` |

```bash
git clone https://github.com/Tim-Hezz/SIE_JT.git
cp -r SIE_JT/fs-quick-design       "<DSH_HOME>/skills/"
cp -r SIE_JT/sap-remote-rfc        "<DSH_HOME>/skills/"
```

> ⚠️ **别把备份目录放进 skills 根目录**。DSH 会扫描该目录下**每个含 `SKILL.md` 的子目录**并**按 skill 名去重**；
> 如果备份里有同名 `SKILL.md`，它可能**遮蔽**正本（实测踩过：改动被旧备份盖掉，加载到的是旧版本）。
> 备份请放在 skills 根目录**之外**。

---

## 各 skill 的环境要求

### fs-quick-design

- **Python 3**（仅 `scripts/gen_ui_svg.py` 需要）
  - **纯标准库、零第三方依赖**，任意 Python 3 均可
  - Windows 用 `py -3`；macOS / Linux 用 `python3`
  - ⚠️ Windows 上直接写 `python` 可能命中 Microsoft Store 的占位 exe（exit 9009），别默认用它
- 读 `.docx` 输入时若走 `tencent-local-office-edit`（editor_sdk 通道）会更省事，
  **但该依赖不是必需的**：`.md` / 口述输入与出图全流程都不受影响

### sap-remote-rfc

- **bash**（Git Bash / WSL / Linux / macOS 均可）
  - ⚠️ Windows 下 `bash` 可能解析到 `C:\Windows\system32\bash.exe`(wsl.exe)，被安全策略拦截。
    请用 Git Bash 直接跑 `.sh`，**不要用 `python subprocess(["bash", ...])` 去调**
- **curl** —— 必需（脚本内部就是发 SOAP 请求）
- **凭据**：优先环境变量 `SAP_URL` / `SAP_USER` / `SAP_PASS` / `SAP_CLIENT`（推荐）；
  也可让脚本自动读 `mcp.json`（探测 `~/.dsh-beta` → `~/.dsh` → `~/.workbuddy`，
  或用 `SAP_MCP_JSON` 显式指定路径）
- **可选依赖**：`python` 仅用于解析 mcp.json（只用环境变量时可不装）；
  `cygpath` 仅 Git Bash 下做路径转换
- **`mcp__sap-vsp__SAP`**（删对象 / 激活程序）是**另一个 MCP**，没装则相关步骤走 GUI 替代

---

## 安全红线（两个 skill 共同遵守）

1. **绝不直接 `INSERT` / `UPDATE` / `MODIFY` / `DELETE` 任何标准表**（`TADIR` / `EUDB` /
   `RSMPTEXTS` / `E070` …）。只能调标准函数 / BAPI，让 SAP 自己写它自己的表。
   确实没有标准 API 时，先与负责人确认。
2. **禁止用 `GENERATE SUBROUTINE POOL` 执行任意代码**——它是完整的远程代码执行通道，
   且代码在内存里编译执行，不落仓库对象、不进版本管理、不进传输请求，属审计盲区。
   替代做法是为具体任务建**具体的 FM**。
3. 涉及直接改标准对象 / 标准表时，**停下来报告**，不设计绕行方案。

---

## 仓库约定

- **一个 skill 一个顶层目录**，目录名 = skill 名；内容自包含，
  `references/` 与 `examples/` 用相对路径引用，拷走即用。
- 脚本以**所在 skill 根目录**为基准定位资源（文档中写作 `<skill>/scripts/...`）。
- 版本号唯一来源：各 skill `SKILL.md` frontmatter 的 `version:`。
- **提交前请自查脱敏**，见文首警示。

## License

[MIT](LICENSE)
