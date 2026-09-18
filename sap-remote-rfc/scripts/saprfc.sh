#!/usr/bin/env bash
# saprfc.sh — 通过直连 HTTP SOAP 调用 SAP RFC 函数模块（无需 SAP GUI）
#
# 用法:
#   saprfc.sh <FM_NAME> '<INNER_XML>'            # 自定义参数 XML
#   saprfc.sh RFC_PING ''                        # 只验通道
#   saprfc.sh ZGUI_COPY '<IV_SRC>ZTMPL_SRC</IV_SRC><IV_DST>ZTMPL_OLD</IV_DST>'
#
# 连接参数来源（优先级从高到低）:
#   1) 环境变量 SAP_URL / SAP_USER / SAP_PASS / SAP_CLIENT（推荐，跨平台通用）
#   2) mcp.json 里的 SAP 连接配置（自动探测 ~/.dsh-beta、~/.dsh、~/.workbuddy，
#      可用 SAP_MCP_JSON 显式指定路径；不硬编码密码）
#
# 可选依赖:
#   - python3 / py  仅用于解析 mcp.json。只用环境变量时可完全不装。
#   - cygpath        仅 Git Bash 下用于路径转换。非 Git Bash 走降级分支。
#
# 注意:
#   - 必须【直连】，不要走 http 代理（走本地代理会返回 HTTP 000）
#   - 只能调用 remote-enabled 的函数模块（TFDIR-FMODE='R'）

set -u

FM="${1:-}"
INNER="${2:-}"

if [ -z "$FM" ]; then
  echo "usage: $0 <FM_NAME> ['<INNER_XML>']" >&2
  exit 2
fi

# ---- 定位配置与 Python ----------------------------------------------------
# $HOME 在 Git Bash 下是 /c/Users/x，原生 Windows 程序不认，需要转成 C:\Users\x。
# 没有 cygpath（非 Git Bash 环境）时退回原样，此时请用环境变量提供凭据。
_HOME_WIN="${HOME}"
if command -v cygpath >/dev/null 2>&1; then
  _HOME_WIN="$(cygpath -w "$HOME")"
fi
# 配置文件位置可覆盖；默认依次尝试 DSH / WorkBuddy 两处常见路径。
if [ -n "${SAP_MCP_JSON:-}" ]; then
  CFG="$SAP_MCP_JSON"
else
  CFG=""
  for _c in "${_HOME_WIN}\\.dsh-beta\\mcp.json" \
            "${_HOME_WIN}\\.dsh\\mcp.json" \
            "${_HOME_WIN}\\.workbuddy\\mcp.json"; do
    if [ -f "$_c" ]; then CFG="$_c"; break; fi
  done
  [ -n "$CFG" ] || CFG="${_HOME_WIN}\\.workbuddy\\mcp.json"   # 找不到也不报错，交由下面判断
fi

# Python 只用于解析 mcp.json（可选）。找不到也不影响用环境变量提供凭据。
# ⚠️ Windows 上直接写 `python` 可能命中 Microsoft Store 占位 exe，故优先 py -3。
if [ -n "${SAP_PY:-}" ]; then
  PY="$SAP_PY"
elif command -v py >/dev/null 2>&1; then
  PY="py -3"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

read_cfg() {
  # $1 = key (url|user|password|client|language)
  [ -f "$CFG" ] || return 0
  # 注意 $PY 可能带参数（如 "py -3"），必须不加引号以便分词
  # shellcheck disable=SC2086
  $PY - "$CFG" "$1" <<'PYEOF' 2>/dev/null
import json, sys, pathlib
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
key = sys.argv[2]
alias = {'url':      ('SAP_URL', 'url', 'baseUrl', 'host'),
         'user':     ('SAP_USER', 'user', 'username'),
         'password': ('SAP_PASSWORD', 'password', 'pass'),
         'client':   ('SAP_CLIENT', 'client'),
         'language': ('SAP_LANGUAGE', 'language', 'lang')}
want = tuple(a.lower() for a in alias[key])

def collect(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and k.lower() in want:
                out.append(v)
            else:
                collect(v, out)
    elif isinstance(node, list):
        for i in node:
            collect(i, out)

servers = cfg.get('mcpServers', {})
# 1) 优先 sap-vsp / 任何带 SAP_* 环境变量的 SAP server；2) 再退化为全文件扫描
named = []
for name in ['sap-vsp', 'mcp-abap-adt']:
    if name in servers:
        collect(servers[name], named)
if named:
    print(named[0])
    sys.exit(0)
allv = []
collect(cfg, allv)
if allv:
    print(allv[0])
PYEOF
}

SAP_URL="${SAP_URL:-$(read_cfg url)}"
SAP_USER="${SAP_USER:-$(read_cfg user)}"
SAP_PASS="${SAP_PASS:-$(read_cfg password)}"
SAP_CLIENT="${SAP_CLIENT:-$(read_cfg client)}"
SAP_LANG="${SAP_LANG:-${SAP_LANGUAGE:-}}"
[ -n "$SAP_LANG" ] || SAP_LANG="$(read_cfg language)"
[ -n "$SAP_LANG" ] || SAP_LANG="ZH"

if [ -z "${SAP_URL:-}" ] || [ -z "${SAP_USER:-}" ]; then
  echo "ERROR: 无法解析 SAP 连接参数，请设置 SAP_URL / SAP_USER / SAP_PASS 环境变量" >&2
  exit 3
fi

# 剥掉末尾斜杠
SAP_URL="${SAP_URL%/}"

TMPDIR_WIN="${TEMP:-/tmp}"
# curl 是原生 Windows 程序，认不出 Git Bash 的 POSIX 路径。若 TEMP=/tmp（沙箱常见），
# curl --data-binary "@/tmp/xxx" 会报 "error encountered when reading a file"。
# 用 cygpath -m 统一转成 C:/... 混合路径，bash 和 curl 都认。
if command -v cygpath >/dev/null 2>&1; then
  TMPDIR_WIN="$(cygpath -m "$TMPDIR_WIN" 2>/dev/null || echo "$TMPDIR_WIN")"
fi
OUT="$TMPDIR_WIN/saprfc_out_$$.xml"

SOAP_ACTION="urn:sap-com:document:sap:rfc:functions:$FM"

cat > "$TMPDIR_WIN/saprfc_req_$$.xml" <<XEOF
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:sap-com:document:sap:rfc:functions">
  <soapenv:Header/>
  <soapenv:Body>
    <urn:${FM}>${INNER}</urn:${FM}>
  </soapenv:Body>
</soapenv:Envelope>
XEOF

echo "FM=$FM  LANG=$SAP_LANG  USER=$SAP_USER@${SAP_URL#*//}"
HTTP_CODE=$(curl -s -o "$OUT" -w "%{http_code}" \
  --noproxy '*' \
  -u "${SAP_USER}:${SAP_PASS}" \
  -X POST \
  -H "Content-Type: text/xml; charset=UTF-8" \
  -H "SOAPAction: ${SOAP_ACTION}" \
  --data-binary "@$TMPDIR_WIN/saprfc_req_$$.xml" \
  "${SAP_URL}/sap/bc/soap/rfc?sap-language=${SAP_LANG}")

echo "HTTP $HTTP_CODE"
echo "--- response ---"
cat "$OUT"
echo
# 临时请求文件保留在 %TEMP%，不删（避免 safe-delete 拦截 rm 报噪音）

[ "$HTTP_CODE" = "200" ] || exit 1
exit 0
