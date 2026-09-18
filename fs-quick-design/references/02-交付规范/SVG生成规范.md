# SAP 图形 SVG 规范（界面图 + 框架图）

> **为什么用 SVG**：一段文本，直接内联进产出 MD，顾问打开 Markdown 就能看到图——
> 没有 JS、没有 CSS 冲突、没有附件。顾问说"这里不对"，改配置重出即可。
> **快，是这个环节唯一的目标。**

---

## 一、生成方式：一律走脚本，不手排坐标

坐标由 `scripts/gen_ui_svg.py` 按 SAP 实测比例计算。**手写 SVG 的坐标必然出错**
（实测：手写两张框架图，一处标签栏盖住标题、一处来源标记标错行，返工 6 轮），
**除非脚本覆盖不了，否则不要手写**。

```bash
PY="py -3"        # Windows 官方启动器最可靠；macOS/Linux 用 python3（脚本纯标准库）
                  # ⚠️ Windows 直接写 `python` 可能命中 Store 占位 exe（exit 9009）
cd <skill>/scripts

"$PY" gen_ui_svg.py --demo --json > figs.json    # 拿 7 种图的填好示例（最快上手）
#   ↓ 改 figs.json 的字段与数据
"$PY" gen_ui_svg.py figs.json --inject <产出MD>   # ★ 一步到位：生成 + 注入 MD
"$PY" gen_ui_svg.py figs.json -o out/             # 每个图落一个 .svg（需单独打开时用）
"$PY" gen_ui_svg.py --demo                        # 看示例 SVG
"$PY" gen_ui_svg.py --schema                      # 看完整 JSON 结构
```

**推荐流程（三步，MD 一次成型）**：
① 写产出 MD 时，图的位置留 `{{SVG:名称}}` 占位；
② 写 `figs.json`（照 `--demo --json` 改）；
③ `--inject` 一步注入 → 完成。**不再需要手工提取、拼接、逐张验证。**

---

## 二、七种图（kind）

| kind | 图 | 用在产出 MD 的哪一节 |
|---|---|---|
| `biz_swimlane` | **业务框架图**（泳道） | 4 业务框架图 |
| `tech_layers` | **技术框架图**（四层数据流） | 5 技术框架图 |
| `select_alv` | 选择屏 + ALV 列表 | 6 界面 |
| `batch_upload` | 批导 · 上载屏 | 6 界面 |
| `batch_result` | 批导 · 结果 ALV（带状态图标列） | 6 界面 |
| `batch_log` | 批导 · 执行日志 | 6 界面 |
| `dynpro` | 功能开发屏（Tab + 抬头 + 行项目 + 消息区） | 6 界面 |

**图的语义规则**（泳道为什么这么画、四层各放什么、形状代表什么）
见 `框架图规范.md`；本节只说怎么生成。

---

## 三、配置速查

### 3.1 biz_swimlane（业务框架图）

```json
{
  "name": "业务框架图",
  "kind": "biz_swimlane",
  "title": "业务流程 · 批量创建交货单",
  "lanes": ["计划员", "系统 · Z 程序", "仓库 / 装运"],
  "steps": ["准备导入", "校验", "分组", "创建交货单", "核对 / 打印"],
  "nodes": [
    {"lane": 0, "step": 0, "text": "准备导入 Excel", "sub": "订单号/行项/数量", "shape": "person"},
    {"lane": 1, "step": 1, "text": "7 项校验", "sub": "逐行标错、不中断", "shape": "system", "tone": "sys"},
    {"lane": 1, "step": 3, "text": "创建交货单", "sub": "BAPI + 逐单提交", "shape": "doc", "tone": "sys"},
    {"lane": 0, "step": 4, "text": "核对失败行并修正", "sub": "按行号定位", "shape": "person", "tone": "err"},
    {"lane": 2, "step": 4, "text": "打印送货单 / 拣配", "sub": "复用 ZSDR002", "shape": "person", "tone": "ok"}
  ],
  "edges": [{"from": 0, "to": 1}, {"from": 1, "to": 3}, {"from": 3, "to": 4}],
  "feedback": {"from": 4, "to": 1, "label": "修正后重新上载（仅跑失败行）"}
}
```

- `lanes` = **角色**（水平泳道）· `steps` = **业务步骤**（垂直列）
- `nodes[].lane/step` = 该节点落在第几条泳道、第几列（**从 0 起**）
- `edges` = 连线的节点**下标**；同泳道自动走水平直线，跨泳道自动走「水平→垂直」折线
- `feedback` = 异常回流虚线（可选），从某节点顶部绕回另一节点
- **每条泳道标签写具体角色名**（不要"用户"），**不要出现技术对象名**——技术对象归 `tech_layers`

### 3.2 tech_layers（技术框架图）

```json
{
  "name": "技术框架图",
  "kind": "tech_layers",
  "title": "技术实现 · 分层与数据流",
  "layers": ["L1 触发层", "L2 逻辑层", "L3 数据层", "L4 输出层"],
  "nodes": [
    {"layer": 0, "col": 0, "text": "事务码 ZSD_DLV_BATCH", "sub": "选择屏 · 文件 / 模式"},
    {"layer": 1, "col": 0, "text": "7 项校验", "sub": "订单 / 冻结 / 状态 / 未清数量"},
    {"layer": 2, "col": 0, "text": "VBAK / VBAP / VBUP", "sub": "读订单与交货状态（只读）", "lv": "[L2]"},
    {"layer": 2, "col": 1, "text": "BAPI_DELIVERY_CREATEFROMDAT", "sub": "逐单创建", "lv": "[L3]"},
    {"layer": 3, "col": 0, "text": "结果 ALV", "sub": "行级明细 · 失败标黄", "tone": "ok"}
  ],
  "edges": null
}
```

- `nodes[].layer/col` = 第几层、第几列（**从 0 起**）
- **`lv` 是数据层（L3）节点的来源级别**，渲染在节点右上角——**数据层每个节点必填**
- `edges` 为 `null` 时，**按同 col 的相邻层自动连线**（一般不用手写）
- 节点文字两行：`text` 加粗为主对象名，`sub` 为小字说明

### 3.3 五种界面图

| kind | 关键字段 |
|---|---|
| `select_alv` | `select.fields[]`（`required` 黄底+四角角标 / `f4` / `dd` 下拉 / `range`+`value2` 区间）、`alv.columns/rows/total/warn_cells` |
| `batch_upload` | `fields[]` + `checks[]`（复选框） |
| `batch_result` | `stat[]` 统计条（`cls`: ok/er/wn）+ `rows[].status`(s/e/w/i) + `columns[].icon` 图标列 + `rows[].warn[]` 标黄列索引 |
| `batch_log` | `messages[]`（`t`/`no`/`text`/`pos`） |
| `dynpro` | `tabs[]`+`active_tab`、`fields[][]`（二维=多行）、`items{columns,rows,edit_cols,total,selected_row}`、`buttons[]`、`messages[]` |

> ⚠️ **列配置的位置不统一**（写"批量改列"的脚本时要同时兼顾三处，实测踩过）：
> - `select_alv` 的列在 **`alv.columns`**
> - `batch_result` 的列在**顶层 `columns`**（不嵌套在 `alv` 下）
> - `dynpro` 的列在 **`items.columns`**
>
> `batch_upload` / `batch_log` 没有表格列。

**通用选项**：`toolbar` 数组（`"|"` 表示分隔线）· `status` 状态栏文字。

**列宽与对齐**：
- 列配置写 `"align": "end"` → **数值列右对齐**（SAP ALV 惯例，金额/数量/比例列必加，否则一眼不专业）
- 生成时自动做**列宽自检**，装不下就向 stderr 报：
  `⚠ 列宽不足（加宽列或缩短文本）: <图名> 第N列「列名」: 需 Xpx，实配 Ypx`
  —— **看到就先加宽列或缩短文本，不要靠截图去发现**
  （实测教训：靠截图才发现"采购期间"列 130px 装不下 200px 的文本，白验一轮）

---

## 四、MD 注入（`--inject`）

产出 MD 里图的位置写占位符，脚本一次替换：

| 占位符 | 含义 |
|---|---|
| `{{SVG:名称}}` | 按 `name` 精确匹配（**推荐**，位置明确） |
| `{{SVG}}` | 按 `screens` 数组顺序依次替换 |

```bash
"$PY" gen_ui_svg.py figs.json --inject "30-FS-批量创建交货单.md"
# 输出：injected 7 svg -> ... (未替换占位符: 0)
```

**「未替换占位符」必须是 0**——不为 0 说明命名对不上，或占位符数量多过图，要查。

---

## 五、手工兜底（脚本覆盖不了时才用）

**画布与坐标**：`viewBox="0 0 1200 <高>"`；左侧竖线 x=13；面板 x=19 宽 1071；
标题栏 y=17 高 32；工具栏 y=49 高 39；内容起点 x=42；行高 26（字段）/ 20（ALV 行）/ 24（列头）。
**图的标题带是 y=0~48，左侧标签栏必须从 y=48 起**（从 0 起会盖住标题——实测踩过）。

**色板（锁定）**

| 用途 | 值 | 用途 | 值 |
|---|---|---|---|
| 页面底 | `#eaf1f6` | ALV 列头 | `#d8dde2` / 边框 `#b8c8d0` |
| 面板 | `#deebf4` / 边框 `#93b2d0` | ALV 数据行 | `#dfebf5` / 行线 `#e3ecf4` |
| 标题栏 | `#cbdcea→#bcd1e3→#adc5db` | 合计行 | `#fdf2d0` |
| 工具栏 | `#cfdde8` | 选中行 | `#bcd8f0` |
| 输入框 | `#ffffff` / 边框 `#b5b7b7` | 必输 | `#fef09e` + 四角红角标 `#ab0000` |
| 只读框 | `#eef2f6` | F4 按钮 | `#ffefa7` |

**图形语义色**：系统浅蓝 `#e8f1fb`/`#93b2d0` · 成功浅绿 `#e8f5e9`/`#81c784` ·
异常浅橙 `#fff3e0`/`#ffb74d` · 中性白 `#ffffff`/`#b0bec5`。

**文字**：`font-family="'Microsoft YaHei','Segoe UI',Arial,sans-serif"`（**多词字体名必须加引号**，
否则整条声明被 CSS 丢弃、回退成衬线体）。字号 12px、标题 16px 加粗；基线 y ≈ 行顶 + 行高/2 + 4.3。

**状态图标**：S 绿圆白勾 `#2e7d32` · E 红圆白叉 `#ab0000` · W 黄三角 `#f2b705` · I 蓝圆白 i `#0d47a1`。

**多图内联**：每个 SVG 的渐变 `id` 必须唯一（脚本按 `name` 自动生成前缀；手写时自己加序号）。

---

## 六、检查（只靠脚本的自动检查，不做人工验图）

**脚本会自动报，出现就必须处理**：

- `⚠ 列宽不足（加宽列或缩短文本）: <图名> 第N列「列名」: 需 Xpx，实配 Ypx`
- `--inject` 输出的「未替换占位符」**必须是 0**

**内容正确性靠三条原则把握，不靠自检清单**：

- 泳道图：泳道 = **角色**、列 = **步骤**（最容易画反，出图前先想清楚）
- 分层图：数据层节点都填 `lv`；节点写真实 SAP 对象名
- 敏感值用占位符 `{工厂}` `{客户}`，不留具体值

> **不截图验图、不打自检清单**——图发出去让顾问看，
> **顾问的反馈才是最有效的校验**（而且本来就是多轮迭代，第一轮不必完美）。
> 只有**改过脚本 / 色板**时才目测一次（命令见 `SKILL.md` 维护说明）。

---

## 七、常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 文字变成宋体/衬线 | 字体名没加引号 → `font-family="'Microsoft YaHei',Arial,sans-serif"` |
| 渐变失效、颜色错乱 | 多个 SVG 的 gradient id 重复 → 脚本已按 name 生成前缀；手写时注意 |
| **图标题只剩后半截** | 左侧标签栏 `rect y=0` 盖住了标题 → **必须从 y=48 起**（脚本已正确） |
| 来源级别标记位置不对 | `lv` 只对 `tech_layers` 有效，渲染在节点右上角；别写进 `sub` |
| 状态列一片蓝点 | `status` 用了大写或拼错 → 只认 `s`/`e`/`w`/`i`（脚本自动转大写） |
| 统计条看不见 | 画面板背景的 `<rect>` 在统计条之后 → 先画背景再画内容（脚本已正确） |
| 注入后占位符还在 | `{{SVG:名称}}` 的 `name` 与 JSON 里的 `name` 不一致 |
| 顾问要改某处 | 改 JSON 对应字段 → 重跑 `--inject` → 完成（**不要手工编辑 MD 里的 SVG**） |
