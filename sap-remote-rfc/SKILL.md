---
name: sap-remote-rfc
version: 1.0.0
description: 通过直连 HTTP 的 SOAP RFC 远程调用 SAP 标准函数模块（TFDIR-FMODE='R'），全程不进 SAP GUI。典型用途：远程维护报表程序的文本元素/TEXTPOOL（SIW_RFC_WRITE_TEXTPOOL、SIW_RFC_READ_TEXTPOOL）、生成 GUI 界面（RS_CUA_GENERATE_ALL）、跑自建 RFC 壳并取回结果（ZRUN_PROG / ZRUN_SEED_RUN / ZRUN_TEST_RUN）、对象激活后复核源码。触发词：远程调用 RFC、不进 SAP GUI、维护文本元素、TEXTPOOL、选择文本、SOAP RFC、RunReport 失败、远程执行报表程序、取回 ALV/清单结果、cl_salv_bs_runtime_info、LIST_TO_ASCI、远程查 ST22 dump、批量激活假成功、INCL 语法检查、shell 残缺替代。
agent_created: true
---

# 远程调用 SAP RFC（直连 HTTP SOAP）

> **首次使用先看这几条**（换机器 / 换人时最容易卡住的地方）：
> 1. **凭据**：优先用环境变量 `SAP_URL` / `SAP_USER` / `SAP_PASS` / `SAP_CLIENT`
>    （跨平台通用，推荐）。也可让脚本自动读 `mcp.json`
>    （探测 `~/.dsh-beta` → `~/.dsh` → `~/.workbuddy`，或用 `SAP_MCP_JSON` 指定）。
> 2. **运行环境**：脚本是 **bash**（Git Bash / WSL / Linux / macOS 均可）。
>    ⚠️ Windows 下 `bash` 可能解析到 `C:\Windows\system32\bash.exe`(wsl.exe) 而被安全策略拦截
>    ——就用 Git Bash 直接跑 `.sh`，**不要用 `python subprocess(["bash", ...])` 去调**。
> 3. **可选依赖**：`python` 仅用于解析 mcp.json（只用环境变量时可不装）；
>    `cygpath` 仅 Git Bash 下做路径转换；`curl` 必需。
> 4. **`mcp__sap-vsp__SAP`**（删对象 / 激活程序）是**另一个 MCP**，没装则相关步骤走 GUI 替代。
> 5. 文中所有 `ZRUN_*` / `ZGUI_*` / `ZTMPL_*` / `{SAP系统}` / `{TR}` 等均为**占位示例**，
>    请替换成你自己系统的对象名与连接信息。

## ⛔ 先看：能力边界

**这个技能不能直接执行 ABAP 代码。** 2026-09-02 已删除远程执行入口
`ZGUI_EXEC_ABAP`，并**永久禁用 `GENERATE SUBROUTINE POOL` 动态执行机制**（理由见「红线」）。
只能调**标准系统自带的、remote-enabled 的**函数模块。

| 能力 | 手段 | 状态 |
|---|---|---|
| 调 `FMODE='R'` 的标准 FM | `saprfc.sh <FM> '<参数XML>'` | ✅ **主干能力** |
| 读 / 写文本元素（TEXTPOOL） | `SIW_RFC_READ_/WRITE_TEXTPOOL` | ✅ 已实测，见下文 |
| 复制 + 生成 GUI 状态（激活状态栏） | `ZGUI_ACTIVATE`（自建 RFC FM） | ✅ 见下文 |
| 往已有 status 里**加单个按钮** | 无标准 API | ❌ 只能改模板后整体复制 |
| 删除仓库对象 | `RS_DELETE_PROGRAM` / `RS_FUNCTION_DELETE`（`FMODE` 空 → 远程 HTTP 500）<br>**改用 VSP `mcp__sap-vsp__SAP`（标准写/删对象）** | ⚠️ 见下节 |
| 写完后重新生成程序（`GENERATE REPORT`） | VSP `mcp__sap-vsp__SAP` 激活 | ✅（VSP 在线时）／否则进 GUI |

> ⚠️ 判断"某能力可不可用"时，**必须实测一个已知有数据的对象做对照**。
> 本技能曾因为 `RFC_READ_TABLE` 静默返回空，误判"审计没配置"，教训见「硬约束 / 坑」。

## 何时用

- 需要远程做一件**有对应 `FMODE='R'` 标准 FM** 的事（维护文本元素是最典型场景）。
- VSP 的 `RunReport` / `CallRFC` 走 WebSocket，在本环境握手失败（HTTP 500 bad handshake）。
- 用户明确要求**不进 SAP GUI**。

## 核心思路

1. 直连 `http://<host>:<port>/sap/bc/soap/rfc`，Basic auth，
   `SOAPAction: urn:sap-com:document:sap:rfc:functions:<FM>`。
2. 用 `saprfc.sh` 封装好的 curl 调用，传 FM 名 + 参数 XML。
3. 需要建**常驻** Z FM 时用 VSP `mcp__sap-vsp__SAP`（函数组用 `$TMP` 免传输）。

## 通道验证（先做这一步）

```bash
S=<skill>/scripts/saprfc.sh

# 1. 通道通不通
$S RFC_PING ''

# 2. 能不能真读到数据（这条才是关键，别只看 HTTP 200）
$S SIW_RFC_READ_TEXTPOOL '<I_PROG>ZTMPL_DST</I_PROG><I_TAB_LANGU><item><SPRAS>1</SPRAS></item></I_TAB_LANGU>'
```

第 2 条应返回 4 行（`R` / `I` / `S` / `S`）。**HTTP 200 不代表 FM 真的执行成功**——
非 RFC 的 FM、被拒的调用也可能返回 200 加一段 SOAP Fault 或空结果集。

## 调用脚本

`scripts/saprfc.sh` —— 自动从 `~/.workbuddy/mcp.json` 读 SAP_URL / SAP_USER / SAP_PASSWORD。

```bash
saprfc.sh <FM_NAME> '<INNER_XML>'
# 例
saprfc.sh SIW_RFC_READ_TEXTPOOL '<I_PROG>ZTMPL_DST</I_PROG><I_TAB_LANGU><item><SPRAS>1</SPRAS></item></I_TAB_LANGU>'
```

返回**原始 SOAP XML**，用 `grep -oE "<字段名>[^<]*"` 取值：

```bash
saprfc.sh SIW_RFC_READ_TEXTPOOL '...' | grep -oE "<(ID|KEY|ENTRY)>[^<]*"
```

### `scripts/rfcshow.sh` —— 取值小助手（推荐日常用这个）

`saprfc.sh` 返回的是原始 SOAP 信封，里面有 `&#60; &#62; &#39; &quot; &amp;` 实体转义，
直接 grep 会看到一堆 `&lt;`。`rfcshow.sh` 帮你在 bash 里做完「转义还原 + 取字段」：

```bash
rfcshow.sh <FM> '<INNER_XML>' [FIELD]
# 带 FIELD  → 只打印该字段的值
# 不带 FIELD → 打印还原转义后的完整响应

cd <skill>/scripts
./rfcshow.sh ZRUN_SEED_RUN '<IV_TEST></IV_TEST>' EV_MSG
```

**一次看多个返回字段**（`rfcshow.sh` 只能取一个 FIELD，多个就用 tr 拆标签）：

```bash
./rfcshow.sh ZRUN_SEED_RUN '<IV_TEST></IV_TEST>' 2>&1 | tr '<' '\n' | grep -E "^EV_"
# → EV_CHR>37   EV_CHV>26   EV_DRV>8   EV_PRM>31  ...
```

**查看带换行的长文本字段**（如 `EV_LOG`）：不带 FIELD，再自己还原实体 + 拆行：

```bash
./rfcshow.sh ZRUN_TEST_RUN '<IV_INPUT>SURFACE=PVDF4</IV_INPUT>' 2>&1 \
  | sed -e 's/&#60;/</g' -e 's/&#62;/>/g' -e 's/&quot;/"/g' -e "s/&#39;/'/g" -e 's/&amp;/\&/g' \
  | tr '\r' '\n' | head -80
```

⚠️ **不要用 Python `subprocess(["bash", script])` 去调它** —— 本机 `bash` 会解析到
`C:\Windows\System32\bash.exe`（wsl.exe），被安全策略拦截
（`PROGRAM BLOCKED BY SECURITY POLICY: wsl.exe`）。直接用 Bash 工具跑 `.sh` 即可。

### 传"空值"覆盖 FM 的默认值

很多自建 RFC 壳 FM 的导入参数带 `DEFAULT 'X'`（默认只试运行）。
**SOAP 里传空元素即可覆盖**为初始值：

```bash
./rfcshow.sh ZRUN_SEED_RUN '<IV_TEST></IV_TEST>' EV_MSG   # IV_TEST='' → 真正写入
./rfcshow.sh ZRUN_SEED_RUN '<IV_TEST>X</IV_TEST>'  EV_MSG # IV_TEST='X' → 试运行并回滚
```

⚠️ 注意：试运行分支里如果程序 `ROLLBACK WORK`，而 FM 又用 `SELECT COUNT(*)` 回读行数，
**读到的是旧库行数**，别拿它当"新数据写进去了"的证据。

等价裸 curl（脚本内部就是这么发的）：

```bash
curl -sS --noproxy '*' -u "$SAP_USER:$SAP_PASSWORD" \
  -H 'Content-Type: text/xml; charset=UTF-8' \
  -H "SOAPAction: urn:sap-com:document:sap:rfc:functions:$FM" \
  -d "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\"
       xmlns:urn=\"urn:sap-com:document:sap:rfc:functions\">
       <soapenv:Header/><soapenv:Body><urn:$FM>$INNER</urn:$FM></soapenv:Body></soapenv:Envelope>" \
  "$SAP_URL/sap/bc/soap/rfc?sap-language=ZH"
```

## 判据：TFDIR-FMODE

**只有 `TFDIR-FMODE='R'` 的 FM 能远程调用。** 判断办法：

- 最可靠：**直接试调**。非 R 的 FM 会返回 Server Error / SOAP Fault（`RABAX_STATE`），
  代价很低，比查表快（本系统 `RFC_READ_TABLE` 不可用，见下）。
- 若确有执行通道，可查 `SELECT fmode FROM tfdir WHERE funcname = '<FM>'`。

| FMODE | 含义 | 远程可调用 |
|---|---|---|
| `R` | remote-enabled | ✅ 直接 `saprfc.sh` |
| 空 / 其他 | 普通函数模块 | ❌ 只能进 GUI，或在自建 RFC FM 里包一层 |

已实测（{SAP系统}，SAP_BASIS 757）：

| FM | FMODE | 用途 |
|---|---|---|
| `SIW_RFC_WRITE_TEXTPOOL` | **R** | 写文本元素 |
| `SIW_RFC_READ_TEXTPOOL` | **R** | 读文本元素 |
| `RS_CUA_GENERATE_ALL` | **R** | 生成 GUI 界面 |
| `RFC_PING` | R | 通道测试 |
| `RFC_READ_TABLE` | R | **能调，但本系统恒返回空，无实用价值** |
| `RS_CUA_COPY_ALL` / `RS_CUA_EXISTENCE_CHECK` / `RS_CUA_GET_STATUS` | 空 | 复制/检查 GUI 界面 → 需 GUI |
| `RS_DELETE_PROGRAM` / `RS_FUNCTION_DELETE` | 空 | 删除对象 → 远程 **HTTP 500**；改用 VSP `mcp__sap-vsp__SAP`（标准写/删对象），见下节 |
| `RS_FUNCTION_POOL_DELETE` | 空 | 删函数组 → 需 GUI |

## 参数 XML 写法

- 标量：`<I_PROG>ZTMPL_DST</I_PROG>`
- 内表：`<I_TAB_LANGU><item><SPRAS>1</SPRAS></item></I_TAB_LANGU>`
- 用 `EXCEPTIONS` 写法时 FM 返回的是结构（如 `E_STR_EXCEPTION`），**字段全空 = 成功**，
  不是"无异常标记"。

## 登录语言

ISO `ZH` → SAP 内部语言键 **`1`**（`T002`：SPRAS='1', LAISO='ZH'）。
`saprfc.sh` 默认在 URL 上追加 `?sap-language=ZH`，可用 `SAP_LANG` 环境变量覆盖。

⚠️ **登录语言 ≠ 对象的 master language**。VSP/ADT 建的程序 `TADIR-MASTERLANG` 恒为 `E`，
即使 `mcp.json` 里配了 `SAP_LANGUAGE=ZH`。写文本元素时**中英两个语言都要写**。

## ★★ 对象激活与源码复核（2026-09-14 实测，两处高风险）

写对象走 MCP `SAPWrite` / `SAPActivate`（不是 RFC 通道），但有两条**静默失效**的坑：

### ⛔ 批量激活的「假成功」—— 一个失败连累全局

`SAPActivate(objects=[F01, F02])` 在**其中一个对象失败**时，返回值形如：

```
Batch activation failed for: ZRUN_SHELL_F01, ZRUN_SHELL_F02.
  - ZRUN_SHELL_F02 (INCL): active     ← ★ 这行是假的！
```

**它会同时报"失败"和"active"** —— 如果只看 `active` 那行就误信已激活，
后续落库/实跑会用**旧版逻辑**（本例：`EV_DRV=9`，期望 11，差 2 条新规则）。

**判据（必做）**：改完必须**逐个复核 active 版源码**：

```
SAPRead(type="INCL", name="ZRUN_SHELL_F02", version="active", grep="add_drv_geo")
  → "No matches found"                    ← 新版不在 active
SAPRead(type="INCL", name="ZRUN_SHELL_F02", version="inactive", grep="add_drv_geo")
  → 3 处匹配                              ← 新版还在草稿
```

→ **单独重跑** `SAPActivate(objects=["ZRUN_SHELL_F02"])` 才真正激活。

**元规则：批量激活中只要有一个对象失败，其余对象的激活结果一律不可信 —— 必须逐个复核。**

### ⚠️ `INCL` 单独语法检查必失败 —— 改用「激活 + 实跑」验证

- `SAPDiagnose(action="syntax", name="ZRUN_SHELL_F01")` → `Not checked — Select a master program for include`
- 改查主程序 `ZRUN_SEED` → `The REPORT/PROGRAM statement is missing, or the program type is INCLUDE`

**结论**：INCL 的语法只能靠**激活成功 + 端到端实跑**来验证，别在语法检查上耗时间。

### ⚠️ `SAPWrite` 的 `edit_unit` 只能替换已有单元，不能新建

新建 FORM / 子例程报 `Unit "add_drv_chr" not found in ZRUN_SHELL_F01. Available units: ...`
→ 改用 `action="update"` **整文件重写**。

### ⚠️ FORM 实参个数必须逐一对齐

`add_chr` 是 10 个形参，漏了一个写成 9 个 → 激活报
`Different number of parameters in FORM and PERFORM (routine: ADD_CHR — formal: 10, actual: 9)`。
**报错在激活期，不在语法检查期** —— 语法检查通过了也可能激活失败。

### ⚠️ RFC 网关对不存在的入参「静默忽略」（不是报错）

`SAPWrite` 的 `TABLE_QUERY` 漏传 `name` → 报 `"name": TABLE_QUERY requires a table or CDS view name.`
但**删掉某个参数后不会有明显失败信号**（HTTP 200 + 按默认值执行）。
发现结果口径不对时，**先检查调用串里有没有残留旧参数**。

---

## 硬约束 / 坑

- **必须直连，禁止代理**。走 `http://127.0.0.1:46390` → `HTTP 000`。- **被调 FM 内部不能弹屏 / `CALL SCREEN`**，RFC 上下文无 GUI 会 dump。
- **直连 RFC 网关（33xx）在本环境不通**：`{SAP_HOST}` 只开 `8000` / `8001`；
  本机也没装 SAP NW RFC SDK。所以只能用 HTTP SOAP，不能用 `pyrfc` 那套。
- ⚠️ **`RFC_READ_TABLE` 在本系统恒返回空 `ET_DATA`**，即使查 `T001`（67 行）也一样，
  且不报错。**别用它判断"表里有没有数据"** —— 本技能曾据此误判
  "`RSAUPROF` 空 = 安全审计没配置"，结论无效。
  实测同样受影响的还有 `TPFYPROPT`（0 行）。
  `USE_ET_DATA_4_RETURN` 传了也没用，OPTIONS / FIELDS 传了也不影响（FIELDS 会被正确回显，
  但 `ET_DATA` 依旧空）。
- ⛔ **传给 curl / Windows Python 的文件路径必须是 Windows 路径，不能是 POSIX 路径**
  （2026-09-03 实测，`saprfc.sh` 已修）。Git Bash 里 `/tmp` 是存在且可写的，
  但沙箱会把 `TEMP` 也设成 `/tmp`，而 `curl` 是**原生 Windows 程序**，
  `--data-binary "@/tmp/req.xml"` 会报
  `curl: option --data-binary: error encountered when reading a file`
  （紧跟着 `cat: /tmp/xxx_out.xml: No such file` —— 这组合就是本坑的指纹）。
  Git Bash 只自动转换**裸路径参数**，不转 `@` 前缀里的路径。
  修法：`TMPDIR_WIN="$(cygpath -m "$TMPDIR_WIN")"` 转成 `C:/...` 混合路径，
  bash 和 curl 都认（`-m` 用正斜杠，比 `-w` 的反斜杠省去转义麻烦）。
  同理：用 Windows 版 `python.exe` 读响应文件时也必须传 `C:/...`，
  传 `/tmp/x.xml` 会得到 `FileNotFoundError: '\\tmp\\x.xml'`。
- ⚠️ **`REPLACE ALL OCCURRENCES OF ' ' IN <string> WITH 'x'` 会 dump**（ABAP 把 `' '`
  当空搜索串 → `REPLACE_ALL_OCCURENCES_EMPTY_SEARCH`）。空格一律改用正则：
  `REPLACE ALL OCCURRENCES OF REGEX '\x20' IN lv_str WITH '#'`.
  排查"看起来是空格其实不是"时用两遍：
  `REGEX '\x20'`→`#`（真空格），再 `REGEX '[^\x20-\x7E]'`→`@`（NBSP 之类冒牌空格）。
- 脚本里 `$HOME` 是 `/c/Users/Tim`，Python(Windows) 不认，要用 `cygpath -w` 转换。

### ⚠️ 会话 shell 残缺时的替代路径（2026-09-14 实测本机）

某些会话里 Bash 工具**连基础命令都没有**：
`dirname` / `cd` / `head` / `tr` / `grep` / `ls` 全部 `command not found`，
`rfcshow.sh` / `saprfc.sh` 因依赖 bash 被安全策略拦截
（`PROGRAM BLOCKED BY SECURITY POLICY ... wsl.exe`）。

**此时改用裸 `curl` + `node -e` 解码**（这两个都在，node 用 managed 版本）：

```bash
# 1. 从 mcp.json 显式注入凭据（必须与 curl 同一条命令 —— Bash 每次调用都是新 shell）
node -e 'const fs=require("fs"),os=require("os");
const m=JSON.parse(fs.readFileSync(os.homedir()+"/.workbuddy/mcp.json","utf8"));
const e=(m.mcpServers["{SAP系统}"]||{}).env||{};
console.log(Object.entries(e).filter(([k])=>/^SAP_/.test(k)).map(([k,v])=>k+"="+v).join("\n"));'

# 2. 裸 curl 发 SOAP（输出落明确的 Windows 路径，别用 /tmp）
curl -sS --noproxy '*' -u "$SAP_USER:$SAP_PASSWORD" \
  -H 'Content-Type: text/xml; charset=UTF-8' \
  -H "SOAPAction: urn:sap-com:document:sap:rfc:functions:ZRUN_TEST_RUN" \
  -d '<soapenv:Envelope ...>...</soapenv:Envelope>' \
  "$SAP_URL/sap/bc/soap/rfc?sap-language=ZH" > C:/temp/work_xf1.xml

# 3. node 读文件 + 还原 XML 实体（curl 输出是转义过的）
node -e 'const s=require("fs").readFileSync("C:/temp/work_xf1.xml","utf8")
  .replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,"\"")
  .replace(/&#39;/g,"\x27").replace(/&amp;/g,"&");
console.log(s);'
```

⛔ **`curl -o /tmp/x.xml` 后 node 读 `%TEMP%/x.xml` 会 `ENOENT`** ——
Git Bash 的 `/tmp` 不映射到 Windows `%TEMP%`。**一律写 `C:/Users/Tim/` 明确路径。**

### 多系统凭据选择（mcp.json 里配了多个 SAP 时必看）

- `saprfc.sh` 的 read_cfg 自动解析 mcp.json 时，多个 server 配置下**可能抓到错误的那个**
  （实测抓到了 S/4HANA Cloud `{云系统主机}` 的配置 → SAP Web Dispatcher 403）。
  **症状指纹**：响应头显示 `USER={用户}@{云系统主机}`（不是你预期的内网主机）。
- **修法**：环境变量优先级最高（`SAP_URL / SAP_USER / SAP_PASS / SAP_CLIENT`），
  从 arc-1 的 env 注入目标系统凭据，密码不落命令行：

  ```bash
  eval "$(node -e 'const fs=require("fs"),os=require("os");const m=JSON.parse(fs.readFileSync(os.homedir()+"/.workbuddy/mcp.json","utf8"));const e=(m.mcpServers&&(m.mcpServers["arc-1"]||{}).env)||{};for(const k of ["SAP_URL","SAP_USER","SAP_PASSWORD","SAP_CLIENT","SAP_LANGUAGE"])if(e[k])console.log("export "+k+"="+JSON.stringify(e[k]));')" \
  && export SAP_PASS="$SAP_PASSWORD" \
  && ./rfcshow.sh <FM> '<参数XML>' EV_MSG
  ```

- ⚠️ **Bash 工具每次调用都是新 shell**，env 注入与 FM 调用必须在**同一条命令**里；
  分两条跑，第二条就回落到 mcp.json 自动解析（可能又是错的那个）。

## ★★ 远程跑程序并取回结果（自建执行壳 `ZRUN_PROG`）

**不是任意代码执行通道。** 目标程序必须先在白名单表 `ZRUN_PROG_WL` 登记
（`IV_MODE=ADD/DEL`，走 `S_DEVELOP ACTVT 02`）；RUN 时再过三关：
白名单 → `TRDIR` 存在性 → `S_DEVELOP ACTVT 16`。

- 位置：函数组 `ZRUN_TOOL`，包 `{PACKAGE}`，`processingType: rfc`（`TFDIR-FMODE='R'`），2026-09-07 建。
- 签名（**v6，2026-09-10 起**）：IMP `IV_PROG` / `IV_MODE`(RUN|ADD|DEL) / `IV_GET`(LIST|DATA) /
  `IV_MAXROWS`(5000) / `IV_DESCR` / `IV_READONLY` / `IV_SKIPCHK`(默认空)；
  EXP `EV_JSON` / `EV_COUNT` / `EV_MSG`；TABLES `IT_PARAMS LIKE rsparams`。
- ⛔ **`IV_RUNMODE` / `IV_MAXWAIT` / `IV_PDEST` 已于 v6 删除**（原 BG 后台作业模式）。
  详见本节末尾「BG 后台作业模式为何删除」。
- 用法（`saprfc.sh`，`IT_PARAMS` 一条 = 一个选择屏参数）：

```bash
./rfcshow.sh ZRUN_PROG '<IV_PROG>ZALV_TST</IV_PROG><IV_GET>DATA</IV_GET>
  <IT_PARAMS><item><SELNAME>P_TYPE</SELNAME><KIND>P</KIND><SIGN>I</SIGN>
  <OPTION>EQ</OPTION><LOW>R</LOW></item></IT_PARAMS>' EV_COUNT
```

### 两种取回口径（S4 757 实测，2026-09-07 / v6 回归 2026-09-10）

| 目标程序形态 | `IV_GET=DATA` | `IV_GET=LIST` |
|---|---|---|
| WRITE 清单型 | ✗ 无 ALV 可捕获 | ✅ 原样清单文本 |
| `CL_SALV_TABLE`（SALV OM） | ✅ 结构化 JSON | ✅ 清单文本 |
| `REUSE_ALV_GRID_DISPLAY_LVC` | ✅ **结构化 JSON** | ✅ 清单文本 |

> ✅ **纠正 2026-09-07 早前的误判**：`cl_salv_bs_runtime_info` **能**捕获
> `REUSE_ALV_GRID_DISPLAY_LVC` 的输出，不只是 `CL_SALV_TABLE`。
> 当时误判"REUSE 系只能走 BG"是因为目标程序数据全空、走了空数据短路
> （`IF gt_out IS INITIAL. MESSAGE ... RETURN.`），**根本没执行到 ALV 调用**。
> ⛔ **判据**：判定"某形态取不到"之前，先确认目标程序**真的跑到了输出语句**。
> 空数据集导致的失败，不能当作技术形态不支持的证据。
>
> 默认路径 `IV_GET=DATA`（快、结构化、能直接当数据用）；拿不到再换 `LIST`。

### 这段链路的坑

- ⛔ **FM 名是 `LIST_TO_ASCI`（只有一个 I），本系统不存在 `LIST_TO_ASCII`。**
  写错 → `CALL_FUNCTION_NOT_FOUND` → RFC 侧 **HTTP 500**，body 只有
  `Internal Server Error`，**不告诉你找不到的是哪个 FM**。
  （`LIST_FROM_MEMORY` 名字是对的，坑只在 `LIST_TO_ASCI`。）
- ⚠️ `LIST_TO_ASCI` 的 `LISTASCII`(TABLES) 是 `LIKE abaplist`；传 `char255` 会因行宽不足
  运行时越界。想省事直接要 `IMPORTING list_string_ascii TYPE list_string_table`（string 表）。
- ⚠️ **`abaplist` 不能 `CONV string( )`**（编译报 "type cannot be converted to STRING"）。
- ⚠️ **HTTP 500 ≠ 一定有 dump**：找不到 FM、越界这类会写 dump；未处理的 E 消息可能 500 但无 dump。
  **先看 ST22 再猜**，别凭 500 猜原因。
- 🔍 **远程查 dump**：`CNV_MBT_READ_ST22_DUMPS`（组 `CNV_MBT_DIAG`，`FMODE='R'`）
  → `ET_DUMPINFO`（`SYDATE`/`SYTIME`/`SYUSER`/`DUMPID`/`PROGRAMNAME`/`INCLUDENAME`）。

  ```bash
  ./rfcshow.sh CNV_MBT_READ_ST22_DUMPS \
    '<IV_FROM_DATE>2026-09-10</IV_FROM_DATE><IV_PROGRAMNAME>SAPLZRUN_TOOL</IV_PROGRAMNAME>'
  ```

  ⚠️ dump 存在**各应用服务器本地**：多实例系统要用 `IV_HOSTNAME` 指定，否则查不到。
  抽查同一天其他用户的 dump 能确认"接口本身是通的"（别把查不到当成没有）。

### BG 后台作业模式为何删除（v6，2026-09-10）

原 `IV_RUNMODE=BG` 走 `GET_PRINT_PARAMETERS` → `RS_CREATE_VARIANT` → `JOB_OPEN/SUBMIT/CLOSE`
→ 轮询 `TBTCO` → `RSPO_RETURN_SPOOLJOB`。评估后判定**收益不抵复杂度**，整段移除：

1. **产出质量更差**：spool 结果带页眉页脚 / 表格线 / 页码，同一程序 BG 取回 75 行，
   `SYNC + LIST` 只有 7 行有效内容——**结构化程度反而更低**。
2. **复杂度高**：临时变体创建与清理、作业轮询与超时、spool 设备兜底链，
   每一环都是一个独立故障面（`USR01-SPLD` 为空就静默无 spool）。
3. **原本的立论点不成立**：BG 当初是为"REUSE 系取不到"准备的兜底，
   而 2026-09-07 已实测证伪——REUSE 系 `SYNC + DATA` 直接就能拿到结构化 JSON。

> ⚠️ **遗留行为**：RFC 网关对**已不存在的入参静默忽略**（不是报错）。
> 老脚本继续传 `IV_RUNMODE=BG` 会 **HTTP 200 成功返回**，只是按默认 `IV_GET='LIST'` 执行。
> 所以删参数后**不会有明显的失败信号**——发现结果口径不对时，先检查调用串里有没有残留旧参数。
>
> 历史坑（保留备查）：后台作业跑完却没 spool，真根因常是**用户 `USR01-SPLD` 为空**；
> 排错顺序：设备存在 → 目标程序有数据 → 打印参数，别一上来怀疑 RSPARAM。

### 必填参数预校验（2026-09-10 已实现）

RUN 之前先用 `RS_SELSCREEN_INFO`（组 `SVAR`：`REPORT` + TABLES `FIELD_INFO LIKE SCR_INFO`）
读目标程序的选择屏定义，再和 `IT_PARAMS` 对一遍：

- `SCR_INFO-OBLIGATORY='X'` 的字段没传、或传了但 `LOW` 为空 → **不执行**，
  返回 `EV_COUNT=-1`，`EV_JSON` 是缺失参数名数组（如 `["S_VKORG"]`），`EV_MSG` 是中文清单。
- 传了目标程序**不存在**的选择字段 → **不阻断**，`EV_MSG` 提示"未知参数将被忽略"
  （`SUBMIT` 对未知参数静默忽略，这是最难排查的一类问题）。
- ⚠️ SELECT-OPTIONS 在 `FIELD_INFO` 里被拆成 `XXX-LOW` / `XXX-HIGH`，
  要 `SPLIT ... AT '-'` 取前段才是 `RSPARAMS-SELNAME`。
- 读不到选择屏信息（无选择屏 / 子程序池，`NO_SELECTIONS` rc=1）→ **不拦**，
  交给目标程序自己处理，别把 rc=1 当错误。
- 确实要跳过预校验：传 `IV_SKIPCHK=X`。

> 实测（ZSDR003）：缺 `S_VKORG` 时，从"HTTP 500、body 只有 Internal Server Error"
> 变成 `EV_MSG>缺少必填参数: S_VKORG` + `EV_JSON>["S_VKORG"]`，调用方可程序化补齐后重发。
> 补齐后再次调用即真正进入执行（该例因 VBAK 空落到"未执行到 ALV 调用"消息，属数据问题）。

⚠️ 预校验只拦"必填缺失"，**不猜值、不补默认值**；目标程序内部的其它 `MESSAGE E`
仍会 RFC 500，那条路径目前无解。

### 字段/签名坑（757 实测，别靠记忆）

| 我记错的 | 系统里的真实情况 |
|---|---|
| `TRDIR-PROGNAME` | 主键列是 `TRDIR-NAME` |
| `TBTCP-LISTID` | spool 字段是 `TBTCP-LISTIDENT`（类型 `tbtcp-listident`，传给 `RSPO_RETURN_SPOOLJOB` 要 `CONV tsp01-rqident( )`） |
| `VARIT-ENQTXT` | 文本字段是 `VARIT-VTEXT` |
| `get_data_ref( ) RETURNING` | 757 上是 `EXPORTING r_data` |
| 预定义类型 `CHAR1023` | 不存在，要 `TYPES ... TYPE c LENGTH 1023` |

## VSP 建 FUNC 的坑（沿用原 ARC-1 经验）

- `parameters` 用**结构化数组**传，不要在源码里写 `*" IMPORTING ...` 注释块（会被 strip）。
- 同一参数**不要同时传 `default` 和 `optional`** → 生成非法 ABAP，激活失败。
- 建之前先确认对象是否已存在（VSP 读对象 / TADIR 查询）；已存在就更新，重复创建会 HTTP 500。
- **`FUNC update` 会替换整个 `/source/main`，必须把 `parameters` 一起重传**，否则签名被清空。
- 读对象偶尔读到旧缓存 → 加刷新参数（force_refresh 之类）。
- VSP 为当前唯一的对象管理 MCP；VSP 不可用时（断网/未启动）依赖它激活的对象只能进 GUI 处理。

## ⛔ 红线

### 1. 绝不直接 INSERT / UPDATE / MODIFY / DELETE 任何标准表

（`EUDB`、`RSMPTEXTS`、`TADIR`、`SMODILOG`、`CROSS`、`D347T` …）
只能调标准函数 / BAPI，让 SAP 自己写它自己的表。确实没有标准 API 时，**先跟用户确认**。

原因：绕过权限与一致性校验、无传输记录，且会造成静默残缺（只复制 `EUDB` 不复制
`RSMPTEXTS` → 状态能出来但按钮文本全空），比直接报错更难排查。

### 2. 禁止使用 GENERATE SUBROUTINE POOL 执行任意代码

**2026-09-02 用户决定禁用。** 理由：

- 它是完整的远程代码执行通道：拿到账号的人可从 Python 脚本 / Postman / Excel 直接调，
  不需要 SAP GUI，比在 SE38 里手工跑更隐蔽。
- **审计盲区**：代码在内存里编译执行，不落仓库对象、不进版本管理、不进传输请求。
  SAP 侧的 RFC 审计最多记到"谁、何时、调了哪个 FM"，**不记参数值**，
  即"具体执行了什么代码"永远查不到。
- 加权限检查或留痕只能缓解，不能消除这个盲区。

**已删除**：FM `ZGUI_EXEC_ABAP`（2026-09-02，用 `RS_FUNCTION_DELETE`，rc=0），
配套脚本 `sapexec.sh` / `sapexec_show.sh` 已一并删除。
函数组 `ZGUI_FG` **保留**（组内现在放着 `ZGUI_ACTIVATE`，见下文），不要删这个组。

**替代方案**：真要执行，就**为具体任务建一个具体的 FM**（用 VSP `mcp__sap-vsp__SAP`，
`processingType: rfc`），签名固定、代码进版本管理、有传输记录、可被审计。
成本高一点，但可控。

## ★★ 文本元素（TEXTPOOL）维护 —— 全远程可用

**这是本技能目前最有价值的场景。** ADT 侧两条路都堵死了：

- VSP `mcp__sap-vsp__SAP` 读文本元素（type=TEXT_ELEMENTS）→ **404**（本系统无该 ADT 服务）
- ADT 系 MCP（VSP）的写文本符号能力只支持 **CLAS**，不支持 PROG

但标准系统自带一对 `FMODE='R'` 的函数，直接 `saprfc.sh` 调：

| FM | 签名 |
|---|---|
| `SIW_RFC_WRITE_TEXTPOOL` | IMP `I_PROG`(syrepid)、`I_LANGU`(sy-langu **标量**)、`I_TAB_TEXTPOOL`(textpool_table)；EXP `E_STR_EXCEPTION` |
| `SIW_RFC_READ_TEXTPOOL` | IMP `I_PROG`、`I_TAB_LANGU`(siw_tab_t002 **内表**)；EXP `E_TAB_TEXTPOOL`、`E_STR_EXCEPTION` |

两个都带 `cl_siw_adapter_utilities=>authorization_failure( i_activity = '02'/'03' )` 权限检查，
**成功时 `E_STR_EXCEPTION` 全字段为空**（`MSGTY` 是空串，不是"无异常"标记）。

### ⚠️ 参数名不对称（静默失败，最阴的坑）

- **写**：`I_LANGU` —— 标量，`<I_LANGU>1</I_LANGU>`
- **读**：`I_TAB_LANGU` —— 内表，`<I_TAB_LANGU><item><SPRAS>1</SPRAS></item></I_TAB_LANGU>`

把 `I_LANGU` 传给读函数 → `E_TAB_TEXTPOOL` 空，**不报错、无消息**。

### ⛔ 头号大坑：选择文本（ID='S'）的 ENTRY 必须带 8 位前缀

**症状**：`text-001`（ID='I'）正常显示，**选择文本全部空白**，SE32 和运行时都一样。
数据回读"看得出有数据"、行数也对 —— **完全静默，最容易卡住**。

**原因**：`ID='S'` 的 `ENTRY` 不是纯文本，是 **8 位固定前缀 + 正文**。
SAP 取正文从**偏移 8** 开始读；只写正文（5 个字符）→ 偏移 8 之后什么都没有 → 空白。

基准对照（扫标准报表 + `REPLACE 空格→#` 实测）：

```
标准报表 RM07MLBD / MATNR : strlen=12  length=38  >>########物料编号<<
标准报表 RPR_...  / APPL  : strlen=12  length=38  >>D#######应用程序<<   ← D = 取 DDIC 文本
错误写法         S_EBELN  : strlen=5   length=5   >>采购订单号<<          ← 空白的真凶
正确写法         S_EBELN  : strlen=13  length=38  >>########采购订单号<<
```

**前缀规则**

| 位 | 含义 |
|---|---|
| 第 1 位 | 空格 = 用下面的字面文本；**`D`** = 取 DDIC 数据元素文本（正文常写作 `.`） |
| 第 2–8 位 | 7 个空格 |

**只有 `ID='S'` 有这个前缀。** `ID='R'`（标题）和 `ID='I'`（text-符号）直接写正文。
→ **「text-001 正常、选择文本全空白」就是这坑的指纹。**

✅ **已实测：8 个前导空格在 SOAP XML 里完整保留**，不会被 trim。
可以放心在 `saprfc.sh` 的参数 XML 里直接写 `<ENTRY>        采购订单号</ENTRY>`。

### TEXTPOOL 行结构（DDIC 结构 `TEXTPOOL`）

`ID`(char1) / `KEY`(char8) / `ENTRY`(char255) / `LENGTH`(数值)

| ID | 含义 | KEY | ENTRY 格式 |
|---|---|---|---|
| `R` | 程序标题 | 空 | 直接写正文 |
| `I` | **text-符号**（`text-001`） | `001` | 直接写正文 |
| `S` | **选择文本**（PARAMETERS / SELECT-OPTIONS 标签） | 变量名，如 `S_EBELN` | **8 位前缀 + 正文**，LENGTH=38 |
| `H` | 列表表头 | `001` | 直接写正文 |

### 写入流程（三处致命细节）

```bash
S=<skill>/scripts/saprfc.sh

# 中文（LANG='1'）；英文把 I_LANGU 换成 E
$S SIW_RFC_WRITE_TEXTPOOL '<I_PROG>ZTMPL_DST</I_PROG><I_LANGU>1</I_LANGU><I_TAB_TEXTPOOL>
  <item><ID>R</ID><KEY></KEY><ENTRY>ZTMPL_DST 采购订单跟踪报表</ENTRY><LENGTH>38</LENGTH></item>
  <item><ID>I</ID><KEY>001</KEY><ENTRY>查询条件</ENTRY><LENGTH>4</LENGTH></item>
  <item><ID>S</ID><KEY>S_EBELN</KEY><ENTRY>        采购订单号</ENTRY><LENGTH>38</LENGTH></item>
  <item><ID>S</ID><KEY>S_BEDAT</KEY><ENTRY>        凭证日期</ENTRY><LENGTH>38</LENGTH></item>
</I_TAB_TEXTPOOL>'
```

1. **写入是覆盖式的** —— `SIW_RFC_WRITE_TEXTPOOL` 内部就是 `INSERT TEXTPOOL`，
   会把整个语言池替换掉。必须先 `SIW_RFC_READ_TEXTPOOL` 读出全部行，
   在已有行的基础上改，再整份写回。**实测踩过**：只写 1 行选择文本，
   把该语言下的标题和 text-符号全抹了。
2. **选择文本要 8 位前缀 + `LENGTH=38`**（见上一节）。
3. **写完必须重新生成程序** —— 选择屏幕 dynpro 是程序生成时固化的 cache，
   只改文本池不动它，前台还是旧的。远程**没有**可用的生成 FM
   （`RS_GENERATE_REPORT` 非 RFC，`RS_PROGRAM_GENERATE` 不存在），
   → 用 VSP `mcp__sap-vsp__SAP` 激活，或让用户在 SE38 里激活一次。

### ⚠️ ADT 建的程序 master language 是 E —— 文本会"写到错的语言"

| 程序 | TADIR-MASTERLANG | 怎么建的 |
|---|---|---|
| `ZTMPL_SRC` | **`1`**（中文） | 同事在 GUI 里建的 |
| `ZTMPL_OLD` / `ZTMPL_WB001` / `ZTMPL_DST` | **`E`** | VSP `mcp__sap-vsp__SAP` 建的 |

中文下运行 → 去 `LANG='1'` 找 `text-001` → 该语言没有池 → 回退到 master lang `E` → 也没有 → 空白。

**修法**：中英两语言**都写一遍**（按语言独立，互不覆盖），无论登 ZH 还是 EN 都能命中。
改 master language 要动 `TADIR` → **红线，禁止改表**；要改走 SE38/SE80 属性里的"原始语言"。

### 校验

```bash
$S SIW_RFC_READ_TEXTPOOL '<I_PROG>ZTMPL_DST</I_PROG><I_TAB_LANGU><item><SPRAS>1</SPRAS></item></I_TAB_LANGU>' \
  | grep -oE "<(ID|KEY|ENTRY)>[^<]*"
```

**要逐字节看 ENTRY**，只看行数会被"数据有、格式错"骗过去。
把空格替换成 `#` 打印更直观（`#` = 空格）：

```
[R][]            strlen=15  >>ZTMPL_DST#采购订单跟踪报表<<
[I][001]         strlen=4   >>查询条件<<
[S][S_EBELN]     strlen=13  >>########采购订单号<<
[S][S_BEDAT]     strlen=12  >>########凭证日期<<
```

判据：**`ID='S'` 行前面必须能看到 8 个 `#`**，且 `strlen = 8 + 正文长度`。

（`RS_TEXTPOOL_READ` 是 SE32 自己用的数据源，更权威，但 `FMODE` 为空 → 远程调不了，
只能进 GUI 校验。远程就用 `SIW_RFC_READ_TEXTPOOL`。）

### 排查「写成功了但用户说没看见」的顺序

1. **确认他看的是哪个程序** —— 让他念标题栏；把同批程序一起读出来对比。
   （同名报表 ZTMPL_OLD / ZTMPL_DST 混过一次。）
2. **看 ENTRY 的字节格式**，不是看行数 —— 空格替换成 `#` 打印，对照标准报表。
3. **中英两语言都写** —— 覆盖登录语言不确定的情况。
4. **重新生成/激活了吗** —— 没跑就是旧 dynpro。
5. 让用户退出 SE32 重进（`/nSE32`），或 `/nSE38` → **执行(F8)** 看选择屏幕。

⚠️ **用户若在我们写入前就开着 SE32，千万别让他点保存** ——
那个窗口的缓存还是写入前的空值，保存会覆盖掉新写的文本。必须退出（不保存）再重开。

### 方法论：拿不准格式就扫标准对象做基准对照

8 位前缀就是这么量出来的 —— 扫 20 个标准报表（RM07MLBD / RSEIDOC2 / RSNAST00 /
RMCB0300 / SAPF124 / RSPO0041 …）的 `S` 行，把空格替换成 `#` 打印 `strlen` 和 `length`，
真实格式一眼可见。**比翻文档、比读 FM 源码都快。**

## ★★ GUI 状态复制与激活 —— 用自建 FM `ZGUI_ACTIVATE`

**这是"为具体任务建具体 FM"的样板**（替代已被禁用的通用动态执行）：
签名固定、代码进版本管理、有传输记录、可审计，且**不需要**执行任意代码的能力。

- 位置：函数组 `ZGUI_FG`，包 `$TMP`，`processingType: rfc`（`TFDIR-FMODE='R'`），2026-09-02 建。
- 签名：

  | 方向 | 参数 | 类型 | 说明 |
  |---|---|---|---|
  | IMPORTING | `IV_SRC` | `TRDIR-NAME` | 源程序（提供 GUI 界面的模板） |
  | IMPORTING | `IV_DST` | `TRDIR-NAME` | 目标程序 |
  | IMPORTING | `IV_PROTECT` | `CHAR1` | 默认 `'X'`：目标已有界面则**不覆盖**；传空强制覆盖 |
  | EXPORTING | `EV_RC` | `SY-SUBRC` | 见下表 |
  | EXPORTING | `EV_MSG` | `STRING` | 人话结果 |
  | EXPORTING | `EV_COPIED` | `CHAR1` | `'X'` = 确实复制了 |

  `EV_RC`：`0` 成功 / `1` 已保护跳过 / `4` 源程序没有 GUI 界面 / `8` 生成后复核失败 /
  其他 = `RS_CUA_COPY_ALL`(1–3) 或 `RS_CUA_GENERATE_ALL`(1–4) 的返回码。

- 用法：

  ```bash
  S=<skill>/scripts/saprfc.sh

  # 常规（保护已有界面）
  $S ZGUI_ACTIVATE '<IV_SRC>ZGUI_TMPL</IV_SRC><IV_DST>ZTMPL_DST</IV_DST>'

  # 强制覆盖
  $S ZGUI_ACTIVATE '<IV_SRC>ZGUI_TMPL</IV_SRC><IV_DST>ZTMPL_DST</IV_DST><IV_PROTECT></IV_PROTECT>'
  ```

  实测三条分支都通：`rc=1` 保护跳过 / `rc=0` 复制+生成成功 / `rc=4` 源无界面。

### 内部流程（全走标准 API，零表写操作）

1. `RS_CUA_EXISTENCE_CHECK( program = 源 )` → 源无界面则退出
2. `IV_PROTECT='X'` 时再检查目标 → 已有则跳过
3. `RS_CUA_COPY_ALL( cobjectname = 目标, objectname = 源, language = 'D' )` → 复制设计 + 文本
4. `RS_CUA_GENERATE_ALL( objectname = 目标 )` → 生成（等价 SE41 激活）
5. `RS_CUA_EXISTENCE_CHECK( program = 目标 )` → 复核

### ⚠️ 三个标准 FM 的真实签名（读源码确认，别靠猜）

| FM | FMODE | 参数 |
|---|---|---|
| `RS_CUA_EXISTENCE_CHECK` | 空 | IMP **`PROGRAM`**(TRDIR-NAME) ← **不是 OBJECTNAME**；EXP `RCODE`(SY-SUBRC)；**无 EXCEPTIONS** |
| `RS_CUA_COPY_ALL` | 空 | IMP **`COBJECTNAME`=目标**、**`OBJECTNAME`=源**、`LANGUAGE`(opt，空则内部置 `'D'`)、`COMPARE`(any，默认 space)、`ACTIVE_ONLY`(opt)、`P_ACTIVE_TO_INACTIVE`(默认 space)；EXC `NO_ACTION_TAKEN` / `OBJECT_NOT_FOUND` |
| `RS_CUA_GENERATE_ALL` | **R** | IMP `OBJECTNAME`(目标)、`LANGUAGE`(opt，**死参数，体里没用**)、`STATUS`(opt)；EXC `NOT_EXCECUTED` / `OBJECT_NOT_FOUND` / `STATUS_NOT_FOUND` |

目标/源的方向从源码一眼看出：`PERFORM copy_frame USING objectname cobjectname ...`
（第一个是源，第二个是目标）。

**为什么是 `RS_CUA_COPY_ALL` 而不是 `RS_CUA_COPY`**：

| FM | 内部行为 |
|---|---|
| `RS_CUA_COPY` | 走 `RS_CORR_CHECK` + **`RS_CORR_INSERT`**（弹传输请求框 → `CALL SCREEN`），RFC 下 dump |
| `RS_CUA_COPY_ALL` | 只 `copy_frame`，无修正系统、无屏幕 |
| `RS_CUA_DELETE_ALL` | `DELETE FROM EUDB/RSMPTEXTS/...` + `CALL 'DBCUADEL'` |

选 FM 的判据：**读源码，确认里面没有 `RS_CORR_INSERT`、没有 `CALL SCREEN`。**

### ⛔ 想"加一个按钮"？没有这个 API

用 `FUNCTION_EXISTS` 把菜单绘制器的 API 扫了一遍，结果是：

| 存在 | 不存在（逐个验证过） |
|---|---|
| `RS_CUA_EXISTENCE_CHECK` / `RS_CUA_GET_STATUS` | `RS_CUA_ADD_FUNCTION` |
| `RS_CUA_COPY_ALL` / `RS_CUA_COPY_STATUS` | `RS_CUA_ADD_BUTTON` |
| `RS_CUA_GENERATE_ALL` / `RS_CUA_DELETE_ALL` | `RS_CUA_ADD_FUNCTIONCODE` |
| `RS_CUA_ADD` / `RS_CUA_TITLE_ADD` / `RS_CUA_SINGLE_TITLE_COPY` | `RS_CUA_INSERT_FUNCTION` / `MENU_ADD_FUNCTION` |

**SAP 没有提供"往已有 status 加一个 function code"的标准函数**，
只有整体复制 / 生成 / 删除。直接写 `EUDB`/`RSMPTEXTS` 加按钮违反红线，不要做。

### ✅ 解法：维护自己的模板程序 `ZGUI_TMPL`

- 位置：PROG，`$TMP`，2026-09-02 建（源就是 `ZTMPL_SRC`，只搬了一次）。
- 它**不是业务程序**，只用来集中维护一套标准 GUI 状态 / 标题。
- **加按钮的正确姿势**：SE41 打开 `ZGUI_TMPL` 改 `STATUS01`
  → 对每个目标程序跑一次 `ZGUI_ACTIVATE`（源填 `ZGUI_TMPL`）。
  一处改，多处同步。

为什么不用 `ZTMPL_SRC` 当长期源：那是同事的程序，你改它会影响对方。
**复制本身是物理独立的**（复制后目标程序不依赖源程序）—— 但**源必须是自己的**。

> 补充：`SET PF-STATUS 'X' OF PROGRAM 'Y'` 那种"运行时借用"才是真依赖，
> 会随源程序变化而变化，不适合长期方案。这里用的是物理复制，不存在这个问题。

### GUI 界面数据分布（别只搬一半）

| 表 | 内容 | 语言 |
|---|---|---|
| `EUDB`（RELID='CU'） | Menu Painter **设计**数据（簇表） | **SPRSL='D'**（SAP 内部硬编码，见 `RS_CUA_GENERATE_ALL`） |
| `RSMPTEXTS` | **GUI 文本**（按钮/菜单/标题文字） | `SPRSL='1'` = 中文 |
| `D347T` | 标题 load | — |

`RS_CUA_COPY_ALL` 会一起处理；手写 SQL 只搬 EUDB → **文本全丢**。

## 清理 / 删除仓库对象 —— 远程走不通，改用 ADT

删除**只能**走标准 FM（`RS_DELETE_PROGRAM` / `RS_FUNCTION_DELETE`），它们内部会自己处理
`TADIR`、`TRDIR`、include、文本池、传输登记。**不要手写 DELETE。**

### ✅ 首选：VSP `mcp__sap-vsp__SAP`（写/删对象，2026-09-03 原 ARC-1 实测，VSP 同理）

删除 `ZRUN_DYNP_GEN`（PROG，包 `{PACKAGE}`，请求 `{TR}`）一次成功：

```
mcp__sap-vsp__SAP（删除动作）{ action: "delete", type: "PROG", name: "ZRUN_DYNP_GEN", transport: "{TR}" }
→ "Deleted PROG ZRUN_DYNP_GEN."
```

- `delete` 只需 `{action, type, name}`；**非 `$TMP` 包要带 `transport`**（删除同样要登记进请求）。
- 覆盖 PROG / CLAS / INTF / FUNC / FUGR / INCL / DDLS / TABL / DTEL / DOMA / MSAG 等。
- 删完用 VSP 读对象复核（force_refresh）→ 应返回 **404 + hint "was not found"**。
- **顺手复核邻居对象没被误删**（删完读一下同包的函数组 / include 还完整）。

### ❌ 远程调 `RS_DELETE_PROGRAM` 是死路（实测）

`TFDIR-FMODE` 为空 → SOAP 直接 **HTTP 500 Internal Server Error**。
传 `SUPPRESS_POPUP=X` / `SUPPRESS_CHECKS=X` 也没用 ——
**500 卡在"是否 remote-enabled"这一层，还没进 FM 体**，抑制弹窗的参数救不了。

判据：同系统 `RFC_PING` 返回 HTTP 200，说明通道通，500 只可能是 FMODE。
→ **本技能远程删不了任何仓库对象**，别再挨个试删除类 FM。要删走 ADT，或 SE80/SE38 GUI。

### 备用：从 GUI 的 SE37 调（或包进自建 RFC FM）

| FM | 关键参数 |
|---|---|
| `RS_DELETE_PROGRAM` | I `PROGRAM`；I `SUPPRESS_POPUP` / `SUPPRESS_CHECKS`；I `WITH_INCLUDES` / `WITH_TEXTPOOL` / `WITH_DYNPRO` / `WITH_CUA` / `WITH_VARIANTS` / `WITH_DOCUMENTATION`；X `ENQUEUE_LOCK` / `OBJECT_NOT_FOUND` / `PERMISSION_FAILURE` / `REJECT_DELETION` |
| `RS_FUNCTION_DELETE` | I `FUNCNAME`；I `SUPPRESS_POPUPS` / `SUPPRESS_CHECKS`；X `CANCELLED` / `FUNCTION_RELEASED` |

`EXCEPTIONS OTHERS = 1` + `sy-subrc=0` 即成功。从 GUI 之外调用时**必须传 POPUP 抑制参数**，
否则可能 `CALL SCREEN` dump。

**⚠️ 头号风险：多个 FM 共用一个函数组**

`ZGUI_COPY`、`ZGUI_RFC_TEST`、`ZGUI_EXEC_ABAP` 三个 FM 曾同时挂在 `SAPLZGUI_FG` 下
（当时只能逐个删 FM，**绝不能用 `RS_FUNCTION_POOL_DELETE` 删整组**，会连要留的一起带走）。

现在这个组里**只剩 `ZGUI_ACTIVATE` 一个 FM**，所以：
**`ZGUI_FG` 函数组 = `ZGUI_ACTIVATE` 的载体，删组等于删 FM。** SE80 里看到它别顺手删。

删完立刻验证（`TADIR` / `TRDIR` / `TFDIR` 里应查不到）。

## 菜单绘制器 FM 真实签名（读源码确认，别靠猜）

- **`RS_CUA_GENERATE_ALL`** — `FMODE='R'`，可远程调用。
  - IMPORTING `OBJECTNAME`（必填）、`LANGUAGE`（**体里根本没用到，是死参数**）、`STATUS`
  - 存在性校验**硬编码 `SPRSL = 'D'`**：
    `SELECT SINGLE * FROM eudb WHERE relid='CU' AND name=objectname AND sprsl='D' AND srtf2=0`
    → 找不到就 `OBJECT_NOT_FOUND`。**CUA 主版本必须在 EUDB 的 D 语言行里**。
  - 核心是 `RS_CUA_INTERNAL_GENERATE`。
- **`RS_CUA_COPY`** — 非 RFC，`SUPPRESS_CHECKS='X'` 时走纯逻辑：
  `RS_CORR_CHECK(源)` → `get_master_language_trkey` → `RS_CORR_INSERT(目标, MODIFY)` →
  `copy_frame(源, 目标, ...)`。即便如此在 RFC 下仍 HTTP 500。
- 其他（包 SEUC）：`RS_CUA_EXISTENCE_CHECK`、`RS_CUA_GET_STATUS`、`RS_CUA_ADD`、
  `RS_CUA_COPY_STATUS`、`RS_CUA_SINGLE_TITLE_COPY`、`RS_CUA_TITLE_ADD`。

## 背景知识

- 目标系统：{SAP系统}（`{SAP_HOST}:{SAP_PORT}`，client {CLIENT}，HDB，SAP_BASIS 757，Linux）。
  业务数据极少（`EKKO`/`EKPO`/`LFA1` 都是 0 行，`T001`=67，`T000` 有行但读不出来）。
- GUI Status / Title 存在簇表 **`EUDB`**（`RELID='CU'`，key = NAME / SPRSL / SRTF2）。
- **VSP/ADT 官方不支持创建 GUI Status(CUAD) 和 GUI Title**，只能走 FM / 簇表。
- `SET PF-STATUS 'X' OF PROGRAM 'Y'` 可借用他程序状态（ALV 常用
  `SET PF-STATUS 'STANDARD_FULLSCREEN' OF PROGRAM 'SAPLKKBL'`），但会让目标程序依赖源程序，
  不适合长期方案。

## 本系统的对象现状（2026-09-02 清理 + 重建后）

**在用（保留）**

| 对象 | 类型 | 包 | 说明 |
|---|---|---|---|
| `ZGUI_ACTIVATE` | FUNC（rfc） | `$TMP` | **专用 FM**：复制 + 生成 GUI 界面（激活状态栏）。2026-09-02 建，三条分支实测通过 |
| `ZGUI_TMPL` | PROG | `$TMP` | **GUI 状态模板程序**，不跑业务。加按钮改这里，再传播下去 |
| `ZTMPL_SRC` | PROG | `$TMP` | 同事的模板程序（中文 master lang），**只读，不要改** |
| `ZTMPL_WB001` / `ZTMPL_OLD` / `ZTMPL_DST` | PROG | `$TMP` | 业务报表，master lang = `E` |

**已删除**

| 对象 | 类型 | 备注 |
|---|---|---|
| `ZGUI_EXEC_ABAP` | FM | 动态执行入口，**永久禁用** `GENERATE SUBROUTINE POOL` |
| `ZGUI_COPY` / `ZGUI_RFC_TEST` | FM | 一次性验证用 |
| `ZTMPL_CUACOPY` | PROG | 一次性验证用 |

**待清理**：函数组 `ZGUI_FG` 原本是空壳待删，现已存放 `ZGUI_ACTIVATE`
（`LZGUIU04` 等），**不要再删这个组**，否则会连 `ZGUI_ACTIVATE` 一起带走。

### 常用组合技：新报表落地一条龙

```bash
S=<skill>/scripts/saprfc.sh

# 1. 建程序、写代码        → VSP mcp__sap-vsp__SAP
# 2. 灌 GUI 状态栏         → 从模板复制并生成
$S ZGUI_ACTIVATE '<IV_SRC>ZGUI_TMPL</IV_SRC><IV_DST>ZTMPL_DST</IV_DST>'
# 3. 写文本元素（中英各一遍，S 行记得 8 位前缀）
$S SIW_RFC_WRITE_TEXTPOOL '<I_PROG>ZTMPL_DST</I_PROG><I_LANGU>1</I_LANGU>...'
# 4. 重新生成程序（否则选择屏幕还是旧 dynpro）→ VSP mcp__sap-vsp__SAP 激活
```
