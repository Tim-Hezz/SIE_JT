#!/usr/bin/env bash
# 调用 saprfc.sh 并把 SOAP 响应反转义后打印, 省得每次肉眼解 &#60; 之类实体。
#
# 用法:
#   rfcshow.sh <FM> '<INNER_XML>'           打印整段响应(已反转义)
#   rfcshow.sh <FM> '<INNER_XML>' LOG       只打印 EV_LOG 内容
#   rfcshow.sh <FM> '<INNER_XML>' <字段名>  只打印指定字段, 如 EV_MSG / EV_RC
#
# 例:
#   rfcshow.sh ZRUN_TEST_RUN '<IV_INPUT>SURFACE=ANOD</IV_INPUT>' LOG
#
# 注意: 本脚本必须由 Git Bash 直接执行。Windows 下不要用 python subprocess
# 去调 "bash", 本机 PATH 上的 bash 会解析到 wsl.exe, 会被安全策略拦截。

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAPRFC="$HERE/saprfc.sh"

FM="${1:-}"
XML="${2:-}"
FIELD="${3:-}"

if [ -z "$FM" ]; then
  sed -n '2,20p' "${BASH_SOURCE[0]}"
  exit 1
fi

OUT="$("$SAPRFC" "$FM" "$XML")"

if ! printf '%s' "$OUT" | grep -q "HTTP 200"; then
  printf '%s\n' "$OUT"
  exit 2
fi

BODY="$(printf '%s\n' "$OUT" \
  | sed -e 's/&#60;/</g' -e 's/&#62;/>/g' -e "s/&#39;/'/g" -e 's/&quot;/"/g' -e 's/&amp;/\&/g')"

if [ -n "$FIELD" ]; then
  printf '%s\n' "$BODY" | awk -v f="$FIELD" '
    $0 ~ "<"f">"      { on=1 }
    on                { print }
    $0 ~ "</"f">"    { on=0 }
  ' | sed -e "s|<$FIELD>||" -e "s|</$FIELD>||"
else
  printf '%s\n' "$BODY"
fi
