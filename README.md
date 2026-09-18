# SIE_JT

SAP 实施交付类 skill 集合（DSH / Claude Code 兼容的目录式 skill）。

## 包含的 skill

| skill | 作用 | 状态 |
|---|---|---|
| [`fs-quick-design`](fs-quick-design/) | SAP 需求「快速技术方案」生成器（多轮确认制）。第一轮只出**业务框架图 + 技术框架图 + 界面图 + 要点/待确认**，先对齐业务理解，再谈细节 | v3.0.2 |

---

## 安装

把 skill 目录拷到你的 skill 根目录即可，**DSH 会自动发现、不用重启**：

| 作用域 | 路径 |
|---|---|
| 用户级（推荐，所有工作区可用） | `<DSH_HOME>/skills/`（DSH_HOME 默认 `~/.dsh`） |
| 项目级 | `<项目根>/.dsh/skills/` |

```bash
git clone https://github.com/Tim-Hezz/SIE_JT.git
cp -r SIE_JT/fs-quick-design "<DSH_HOME>/skills/"
```

> ⚠️ **别把备份目录放进 skills 根目录**。DSH 会扫描该目录下**每个含 `SKILL.md` 的子目录**并**按 skill 名去重**；
> 如果备份里有同名 `SKILL.md`，它可能**遮蔽**正本（实测踩过：改动被旧备份盖掉，加载到的是旧版本）。
> 备份请放在 skills 根目录**之外**。

---

## 环境要求

- **Python 3**（仅 `fs-quick-design` 的 `scripts/gen_ui_svg.py` 需要）
  - **纯标准库、零第三方依赖**，任意 Python 3 均可
  - Windows 用 `py -3`；macOS / Linux 用 `python3`
  - ⚠️ Windows 上直接写 `python` 可能命中 Microsoft Store 的占位 exe（exit 9009），别默认用它
- 其余 skill 为纯 Markdown，无依赖

## 可选依赖

`fs-quick-design` 读 `.docx` 输入时，若走 `tencent-local-office-edit`（editor_sdk 通道）会更省事，
但**该依赖不是必需的**：`.md` / 口述输入，以及出图全流程都不受影响。

---

## 仓库约定

- 各 skill **自包含**：`references/` 与 `examples/` 用相对路径引用，拷走即用。
- **所有内容需脱敏**：不得包含客户名、真实账号 / 邮箱、传输请求号、内网 IP、
  生产金额等敏感值（提交前请自查）。
- 版本号唯一来源：各 skill `SKILL.md` frontmatter 的 `version:`。

## License

[MIT](LICENSE)
