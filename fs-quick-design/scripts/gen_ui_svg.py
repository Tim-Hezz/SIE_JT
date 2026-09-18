#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAP 界面 SVG 生成器（fs-quick-design）

配置驱动：读 JSON → 输出可直接内联进 Markdown 的 SVG 文本。
坐标由脚本按 SAP 实测比例计算，不需要手排。

支持三种界面形态（kind）：
  select_alv     选择屏 + ALV 列表
  batch_upload   批导 · 上载屏
  batch_result   批导 · 结果 ALV（含状态图标）
  batch_log      批导 · 执行日志
  dynpro         功能开发屏（Tab + 抬头字段 + 可编辑行项目 + 消息区）

用法：
  python gen_ui_svg.py cfg.json                  # 全部 screen 依次输出到 stdout
  python gen_ui_svg.py cfg.json -o out/          # 每个 screen 落一个 .svg 文件
  python gen_ui_svg.py --demo                    # 打印三种形态的示例配置与 SVG
  python gen_ui_svg.py --schema                  # 打印 JSON 结构说明

色板为 SAP GUI 经典主题（实测校准），与 fs-doc-generator / sap-report-preview 同源。
"""

import json
import sys
import os
import unicodedata

# ----------------------------------------------------------------------------
# 度量（SAP GUI 实测：高 DPI 截图 ÷1.67 后的 CSS 尺寸）
# ----------------------------------------------------------------------------
W          = 1200   # 画布宽
PAGE_X     = 13     # 左侧竖线位置
PANEL_X    = 19     # 面板左边
PANEL_W    = 1071   # 面板宽（非全宽，SAP 选择屏特征）
CONTENT_X  = 42     # 面板内内容起点
TOPBAR_H   = 17
TITLE_H    = 32
TOOLBAR_H  = 39
GAP_H      = 11
FIELD_H    = 26     # 选择屏字段行高
BOX_H      = 21     # 输入框高
HEAD_H     = 24     # ALV 列头高
ROW_H      = 20     # ALV 数据行高
TAB_H      = 24     # Tab 页签高
STATUS_H   = 20
MSG_H      = 22     # 消息行高
FONT       = "'Microsoft YaHei','Segoe UI',Arial,'SimSun',sans-serif"

# 色板（锁定，勿改）
C = {
    "bg":        "#eaf1f6",
    "panel":     "#deebf4",
    "panel_bd":  "#93b2d0",
    "strip":     "#f5f7fa",
    "strip_bd":  "#9cafc3",
    "toolbar":   "#cfdde8",
    "toolbar_bd":"#a8b8c7",
    "box":       "#ffffff",
    "box_bd":    "#b5b7b7",
    "hl":        "#fef09e",
    "hl_bd":     "#d5cc98",
    "readonly":  "#eef2f6",
    "red":       "#ab0000",
    "green":     "#2e7d32",
    "amber":     "#8a4b00",
    "blue":      "#0d47a1",
    "f4":        "#ffefa7",
    "f4_bd":     "#cbbf93",
    "head":      "#d8dde2",
    "head_bd":   "#b8c8d0",
    "head_sep":  "#9faab7",
    "row":       "#dfebf5",
    "row_bd":    "#e3ecf4",
    "row_sel":   "#bcd8f0",
    "total":     "#fdf2d0",
    "total_bd":  "#d2dce6",
    "stat":      "#eef3f8",
    "stat_bd":   "#c3d1de",
    "status":    "#e8f0f0",
    "status_bd": "#90b0d0",
    "tab_on":    "#deebf4",
    "tab_off":   "#c8d6e2",
    "tab_bd":    "#a8b8c7",
    "tx":        "#000000",
    "tx2":       "#455a64",
    "sep":       "#d6dbe6",
}

# ----------------------------------------------------------------------------
# 基础绘制原语
# ----------------------------------------------------------------------------

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def rect(x, y, w, h, fill="none", stroke=None, rx=0):
    s = '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"' % (x, y, w, h, fill)
    if stroke:
        s += ' stroke="%s" stroke-width="1"' % stroke
    if rx:
        s += ' rx="%d"' % rx
    return s + "/>"


def line(x1, y1, x2, y2, stroke, dash=None, sw=1):
    s = '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%s"' % (
        x1, y1, x2, y2, stroke, sw)
    if dash:
        s += ' stroke-dasharray="%s"' % dash
    return s + "/>"


def text(x, y, s, size=12, anchor="start", fill=None, weight="normal"):
    fill = fill or C["tx"]
    extra = ' font-weight="600"' if weight == "bold" else ""
    return ('<text x="%.1f" y="%.1f" font-size="%s" fill="%s" text-anchor="%s"%s>%s</text>'
            % (x, y, size, fill, anchor, extra, esc(s)))


def vmid(top, h, size=12):
    """行内文字基线 y（近似垂直居中）"""
    return top + h / 2.0 + size * 0.36


def tw(s, size=12):
    """文字宽度估算：中文/全角 ≈ size，ASCII ≈ size*0.58"""
    n = 0.0
    for ch in str(s):
        n += size if unicodedata.east_asian_width(ch) in ("W", "F", "A") and ord(ch) > 127 else size * 0.58
    return n


# ----------------------------------------------------------------------------
# 复合部件
# ----------------------------------------------------------------------------

def title_bar(uid, title, y=TOPBAR_H):
    """顶部浅色条 + 标题栏（渐变）"""
    out = rect(0, 0, W, TOPBAR_H, C["strip"], C["strip_bd"])
    out += rect(0, y, W, TITLE_H, "url(#%s_tg)" % uid, "#8fa5bd")
    out += text(26, vmid(y, TITLE_H, 16), title, 16, fill=C["tx"], weight="bold")
    return out, y + TITLE_H


def toolbar(y, buttons, run_icon=True):
    """工具栏：执行按钮(绿勾) + 文字按钮 + 分隔线"""
    out = rect(0, y, W, TOOLBAR_H, C["toolbar"], C["toolbar_bd"])
    cy = vmid(y, TOOLBAR_H, 12)
    x = 11
    if run_icon:
        out += rect(x, y + 10, 20, 19, "#eef5ee", "#7a8f7a")
        out += ('<polyline points="%d,%d %d,%d %d,%d" fill="none" stroke="%s" '
                'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
                % (x + 4, y + 19, x + 8, y + 23, x + 16, y + 14, C["green"]))
        x += 28
    for b in buttons:
        if b == "|":
            out += line(x + 5, y + 8, x + 5, y + 30, C["toolbar_bd"])
            x += 15
            continue
        out += text(x, cy, b, 12)
        x += tw(b, 12) + 16
    return out, y + TOOLBAR_H


def status_bar(y, msg, x_from=0):
    out = rect(x_from, y, W - x_from, STATUS_H, C["status"], C["status_bd"])
    out += text(x_from + 10, vmid(y, STATUS_H, 11), msg, 11, fill="#595e62")
    out += text(W - 10, vmid(y, STATUS_H, 11), "SAP", 11, anchor="end", fill="#595e62", weight="bold")
    return out, y + STATUS_H


def text_button(x, y, w, h, label):
    """SAP 功能按钮（浅灰渐变）"""
    out = rect(x, y, w, h, "#f2f6f9", "#9aa7b2", rx=2)
    out += text(x + w / 2.0, vmid(y, h, 12), label, 12, anchor="middle")
    return out


def input_box(x, y, w, value="", required=False, readonly=False, box_h=BOX_H):
    fill = C["hl"] if required else (C["readonly"] if readonly else C["box"])
    bd = C["hl_bd"] if required else C["box_bd"]
    out = rect(x, y, w, box_h, fill, bd)
    if value:
        out += text(x + 6, vmid(y, box_h, 12), value, 12)
    if required:
        for dx in (-4, w + 2.5):
            for dy in (-4, box_h - 3):
                out += rect(x + dx, y + dy, 1.5, 7, C["red"])
    return out


def dropdown(x, y, w, value="", required=False):
    """SAP combobox：输入框 + 右侧带下三角的小按钮"""
    out = rect(x, y, w - 18, BOX_H, C["hl"] if required else C["box"],
               C["hl_bd"] if required else C["box_bd"])
    if value:
        out += text(x + 6, vmid(y, BOX_H, 12), value, 12)
    out += rect(x + w - 18, y, 18, BOX_H, "#eeeeee", C["box_bd"])
    out += ('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="#333"/>'
            % (x + w - 14, y + 8, x + w - 4, y + 8, x + w - 9, y + 13))
    if required:
        for dx in (-4, w + 2.5):
            for dy in (-4, BOX_H - 3):
                out += rect(x + dx, y + dy, 1.5, 7, C["red"])
    return out


def f4_button(x, y):
    """值帮助按钮：黄底 + 黄圆/绿三角图标"""
    out = rect(x, y, 33, 19, C["f4"], C["f4_bd"])
    out += '<circle cx="%.1f" cy="%.1f" r="3.8" fill="#fdc411" stroke="#5d5d5d" stroke-width="0.8"/>' % (x + 14, y + 7)
    out += '<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="#79b51c" stroke="#5d5d5d" stroke-width="0.8"/>' % (
        x + 9, y + 13, x + 19, y + 13, x + 14, y + 18)
    return out


def checkbox(x, y, label, checked=False, size=12):
    out = rect(x, y, size, size, "#ffffff", "#7a848e", rx=1)
    if checked:
        out += ('<polyline points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="#1a4d1a" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
                % (x + 2.5, y + 6.5, x + 5, y + 9, x + 10, y + 3))
    out += text(x + size + 6, vmid(y - 2, size, 12), label, 12)
    return out


def col_text(x, w, y, s, col, size=12, bold=False):
    """按列的 align 设置输出单元格/列头文字（end = 数值列右对齐，SAP ALV 惯例）"""
    anc = "end" if col.get("align") == "end" else "start"
    tx = x + w - 6 if anc == "end" else x + 6
    return text(tx, y, str(s), size, anchor=anc, weight="bold" if bold else "normal")


def check_overflow(name, cols, rows):
    """生成时自检列宽——比截图验图便宜得多，能提前发现文字溢列"""
    msgs = []
    for ci, c in enumerate(cols):
        need = tw(str(c.get("t", "")), 12)
        for r in rows:
            cells = r.get("cells", r) if isinstance(r, dict) else r
            if ci < len(cells):
                need = max(need, tw(str(cells[ci]), 12))
        if need + 12 > c["w"]:
            msgs.append("    %s 第%d列「%s」: 需 %.0fpx，实配 %dpx"
                        % (name, ci, c.get("t", ""), need + 12, c["w"]))
    if msgs:
        sys.stderr.write("⚠ 列宽不足（加宽列或缩短文本）:\n" + "\n".join(msgs) + "\n")
    return bool(msgs)


def stat_bar(y, items, right="", x=PANEL_X, w=None):
    """统计条：键值对 + 右侧说明"""
    w = w or PANEL_W
    out = rect(x, y, w, 26, C["stat"], C["stat_bd"])
    cx = x + 10
    for it in items:
        col = {"ok": C["green"], "er": C["red"], "wn": C["amber"]}.get(it.get("cls"), "#1a1a1a")
        out += text(cx, vmid(y, 26, 12), it["label"], 12)
        cx += tw(it["label"], 12) + 5
        out += text(cx, vmid(y, 26, 12), str(it["value"]), 12, fill=col, weight="bold")
        cx += tw(str(it["value"]), 12) + 20
    if right:
        out += text(x + w - 10, vmid(y, 26, 12), right, 12, anchor="end", fill=C["tx2"])
    return out, y + 26


def msg_icon(x, y, kind):
    """消息图标 S/E/W/I"""
    r, cx, cy = 6.2, x + 7, y + 7
    if kind == "S":
        return ('<circle cx="%d" cy="%d" r="%.1f" fill="%s"/>'
                '<polyline points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="#fff" '
                'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
                % (cx, cy, r, C["green"], x + 3.6, cy + 0.4, x + 6, cy + 2.8, x + 10.4, cy - 2.4))
    if kind == "E":
        return ('<circle cx="%d" cy="%d" r="%.1f" fill="%s"/>'
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#fff" stroke-width="1.9" stroke-linecap="round"/>'
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#fff" stroke-width="1.9" stroke-linecap="round"/>'
                % (cx, cy, r, C["red"], x + 4.2, cy - 2.8, x + 9.8, cy + 2.8,
                   x + 9.8, cy - 2.8, x + 4.2, cy + 2.8))
    if kind == "W":
        return ('<polygon points="%d,%d %d,%d %d,%d" fill="#f2b705" stroke="#8a6400" stroke-width="0.8"/>'
                '<rect x="%.1f" y="%.1f" width="1.6" height="4.2" fill="#3d2c00"/>'
                '<rect x="%.1f" y="%.1f" width="1.6" height="1.6" fill="#3d2c00"/>'
                % (cx, y + 1, x + 13.2, y + 12.6, x + 0.8, y + 12.6,
                   cx - 0.8, y + 5, cx - 0.8, y + 10.2))
    return ('<circle cx="%d" cy="%d" r="%.1f" fill="%s"/>'
            '<rect x="%.1f" y="%.1f" width="1.4" height="4.6" fill="#fff"/>'
            '<rect x="%.1f" y="%.1f" width="1.4" height="1.4" fill="#fff"/>'
            % (cx, cy, r, C["blue"], cx - 0.7, y + 3.2, cx - 0.7, y + 9))


def svg_wrap(uid, body, height):
    """包一层 SVG 外壳（含渐变 defs、浅色底）"""
    defs = ('<defs><linearGradient id="%s_tg" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="#cbdcea"/>'
            '<stop offset="0.55" stop-color="#bcd1e3"/>'
            '<stop offset="1" stop-color="#adc5db"/></linearGradient></defs>' % uid)
    return ('<svg viewBox="0 0 %d %d" width="100%%" xmlns="http://www.w3.org/2000/svg" '
            'style="min-width:%dpx;font-family:%s">%s%s</svg>'
            % (W, height, W, FONT, defs, body))


def _uid(name):
    """生成 SVG 内唯一 id 前缀（ASCII 安全，避免中文 id 在 url(#...) 引用中出问题）"""
    keep = [ch for ch in str(name) if ch.isalnum() and ord(ch) < 128]
    base = "".join(keep) or ("n%d" % (abs(hash(str(name))) % 100000))
    return ("u" + base)[:24]


# ----------------------------------------------------------------------------
# 形态 1：选择屏 + ALV
# ----------------------------------------------------------------------------

def build_select_alv(cfg):
    uid = _uid(cfg.get("name", "sel"))
    body, y = title_bar(uid, cfg.get("title", ""))
    body += rect(0, y, W, 0)
    tb, y = toolbar(y, cfg.get("toolbar", ["|", "显示", "变式", "导出"]))
    body += tb
    y += GAP_H

    sc = cfg.get("select", {})
    fields = sc.get("fields", [])
    checks = sc.get("checks", [])
    ph = 28 + len(fields) * FIELD_H + len(checks) * 24 + 19
    px, py = PANEL_X, y
    body += rect(px, py, PANEL_W, ph, C["panel"], C["panel_bd"])
    cx = px + 22 + 1          # 内容起点
    ly = py + 28
    for f in fields:
        body += text(cx, vmid(ly, FIELD_H, 12), f.get("label", ""), 12)
        bw = f.get("box_w", 168)
        bx = cx + 285
        if f.get("dd"):
            body += dropdown(bx, ly + 2, bw, f.get("value", ""), f.get("required", False))
        elif f.get("readonly"):
            body += input_box(bx, ly + 2, bw, f.get("value", ""), readonly=True)
        else:
            body += input_box(bx, ly + 2, bw, f.get("value", ""), f.get("required", False))
        if f.get("value2") is not None and f.get("range"):
            body += text(bx + bw + 10, vmid(ly, FIELD_H, 12), "到", 12)
            body += input_box(bx + bw + 40, ly + 2, bw, f.get("value2", ""))
        if f.get("f4"):
            body += f4_button(cx + 681, ly + 3)
        ly += FIELD_H
    for i, ck in enumerate(checks):
        if isinstance(ck, str):
            ck = {"label": ck}
        body += checkbox(cx + 285, ly + 5, ck["label"], ck.get("checked", False))
        ly += 24

    y = py + ph + GAP_H

    alv = cfg.get("alv")
    if alv:
        cols = alv.get("columns", [])
        rows = alv.get("rows", [])
        check_overflow(cfg.get("name", ""), cols, rows)
        total = alv.get("total")
        warns = set(tuple(x) for x in alv.get("warn_cells", []))
        tw_sum = sum(c["w"] for c in cols)
        h = 10 + HEAD_H + len(rows) * ROW_H + (ROW_H + 2 if total else 0) + 8
        body += rect(px, y, tw_sum + 12, h, C["panel"], C["panel_bd"])
        ix, iy = px + 6, y + 10
        body += rect(ix, iy, tw_sum, HEAD_H, C["head"], C["head_bd"])
        cxp = ix
        for i, c in enumerate(cols):
            body += col_text(cxp, c["w"], vmid(iy, HEAD_H, 12), c["t"], c)
            cxp += c["w"]
            if i < len(cols) - 1:
                body += line(cxp, iy, cxp, iy + HEAD_H, C["head_sep"])
        ry = iy + HEAD_H
        for ri, r in enumerate(rows):
            body += rect(ix, ry, tw_sum, ROW_H, C["row"])
            body += line(ix, ry + ROW_H, ix + tw_sum, ry + ROW_H, C["row_bd"])
            cxp = ix
            for ci, cell in enumerate(r):
                cw = cols[ci]["w"] if ci < len(cols) else 60
                bold = False
                if (ri, ci) in warns:
                    body += rect(cxp, ry, cw, ROW_H, C["hl"])
                    body += text(cxp + 6, vmid(ry, ROW_H, 12), cell, 12, fill=C["red"])
                else:
                    body += col_text(cxp, cw, vmid(ry, ROW_H, 12), cell, cols[ci] if ci < len(cols) else {})
                cxp += cw
            ry += ROW_H
        if total:
            body += rect(ix, ry, tw_sum, ROW_H, C["total"])
            body += line(ix, ry + ROW_H, ix + tw_sum, ry + ROW_H, C["total_bd"])
            cxp = ix
            for ci, cell in enumerate(total):
                cw = cols[ci]["w"] if ci < len(cols) else 60
                body += col_text(cxp, cw, vmid(ry, ROW_H, 12), cell,
                                 cols[ci] if ci < len(cols) else {}, bold=True)
                cxp += cw
            ry += ROW_H
        y = y + h + GAP_H

    if cfg.get("status"):
        sb, y = status_bar(y, cfg["status"])
        body += sb
    return svg_wrap(uid, body, y)


# ----------------------------------------------------------------------------
# 形态 2a：批导 · 上载屏
# ----------------------------------------------------------------------------

def build_batch_upload(cfg):
    uid = _uid(cfg.get("name", "bup"))
    body, y = title_bar(uid, cfg.get("title", ""))
    tb, y = toolbar(y, cfg.get("toolbar", ["模拟运行", "|", "下载模板", "显示日志", "返回"]))
    body += tb
    y += GAP_H

    fields = cfg.get("fields", [])
    checks = cfg.get("checks", [])
    ph = 28 + len(fields) * FIELD_H + len(checks) * 24 + 19
    body += rect(PANEL_X, y, PANEL_W, ph, C["panel"], C["panel_bd"])
    cx = PANEL_X + 23
    ly = y + 28
    for f in fields:
        body += text(cx, vmid(ly, FIELD_H, 12), f.get("label", ""), 12)
        bw = f.get("box_w", 168)
        bx = cx + 285
        if f.get("dd"):
            body += dropdown(bx, ly + 2, bw, f.get("value", ""), f.get("required", False))
        else:
            body += input_box(bx, ly + 2, bw, f.get("value", ""), f.get("required", False),
                              f.get("readonly", False))
        if f.get("f4"):
            body += f4_button(bx + bw + 12, ly + 3)
        ly += FIELD_H
    for ck in checks:
        if isinstance(ck, str):
            ck = {"label": ck}
        body += checkbox(cx + 285, ly + 5, ck["label"], ck.get("checked", False))
        ly += 24
    y += ph + GAP_H

    sb, y = status_bar(y, cfg.get("status", "就绪"))
    body += sb
    return svg_wrap(uid, body, y)


# ----------------------------------------------------------------------------
# 形态 2b：批导 · 结果 ALV（带状态图标列）
# ----------------------------------------------------------------------------

def build_batch_result(cfg):
    uid = _uid(cfg.get("name", "brs"))
    body, y = title_bar(uid, cfg.get("title", ""))
    tb, y = toolbar(y, cfg.get("toolbar", ["导出结果", "|", "仅看错误", "执行日志", "返回"]))
    body += tb
    y += GAP_H

    cols = cfg.get("columns", [])
    rows = cfg.get("rows", [])
    total = cfg.get("total")
    check_overflow(cfg.get("name", ""), cols, rows)
    tw_sum = sum(c["w"] for c in cols)
    has_stat = bool(cfg.get("stat"))
    stat_h = 34 if has_stat else 0
    h = 10 + stat_h + HEAD_H + len(rows) * ROW_H + (ROW_H if total else 0) + 8
    body += rect(PANEL_X, y, tw_sum + 12, h, C["panel"], C["panel_bd"])
    ix = PANEL_X + 6
    iy = y + 10
    if has_stat:
        st, ny = stat_bar(iy, cfg.get("stat", []), cfg.get("stat_right", ""), x=ix, w=tw_sum)
        body += st
        iy = ny + 8
    body += rect(ix, iy, tw_sum, HEAD_H, C["head"], C["head_bd"])
    cxp = ix
    for i, c in enumerate(cols):
        body += col_text(cxp, c["w"], vmid(iy, HEAD_H, 12), c["t"], c)
        cxp += c["w"]
        if i < len(cols) - 1:
            body += line(cxp, iy, cxp, iy + HEAD_H, C["head_sep"])
    ry = iy + HEAD_H
    for r in rows:
        cells = r.get("cells", r) if isinstance(r, dict) else r
        st_kind = (r.get("status") or "").upper() if isinstance(r, dict) else None
        warns = set()
        if isinstance(r, dict):
            warns = set(r.get("warn", []))
        body += rect(ix, ry, tw_sum, ROW_H, C["row"])
        body += line(ix, ry + ROW_H, ix + tw_sum, ry + ROW_H, C["row_bd"])
        cxp = ix
        for ci, cell in enumerate(cells):
            cw = cols[ci]["w"] if ci < len(cols) else 60
            if cols[ci].get("icon") and st_kind:
                body += msg_icon(cxp + (cw - 14) / 2.0, ry + 3.5, st_kind)
            elif ci in warns:
                body += rect(cxp, ry, cw, ROW_H, C["hl"])
                body += text(cxp + 6, vmid(ry, ROW_H, 12), str(cell), 12, fill=C["red"])
            else:
                body += col_text(cxp, cw, vmid(ry, ROW_H, 12), cell, cols[ci] if ci < len(cols) else {})
            cxp += cw
        ry += ROW_H
    if total:
        body += rect(ix, ry, tw_sum, ROW_H, C["total"])
        body += line(ix, ry + ROW_H, ix + tw_sum, ry + ROW_H, C["total_bd"])
        cxp = ix
        for ci, cell in enumerate(total):
            cw = cols[ci]["w"] if ci < len(cols) else 60
            body += col_text(cxp, cw, vmid(ry, ROW_H, 12), cell,
                             cols[ci] if ci < len(cols) else {}, bold=True)
            cxp += cw
        ry += ROW_H
    y = y + h + GAP_H
    sb, y = status_bar(y, cfg.get("status", ""))
    body += sb
    return svg_wrap(uid, body, y)


# ----------------------------------------------------------------------------
# 形态 2c：批导 · 执行日志
# ----------------------------------------------------------------------------

def build_batch_log(cfg):
    uid = _uid(cfg.get("name", "blg"))
    body, y = title_bar(uid, cfg.get("title", ""))
    tb, y = toolbar(y, cfg.get("toolbar", ["导出日志", "|", "仅看错误", "返回结果"]), run_icon=False)
    body += tb
    y += GAP_H

    msgs = cfg.get("messages", [])
    tw_sum = PANEL_W
    has_stat = bool(cfg.get("stat"))
    stat_h = 34 if has_stat else 0
    h = 10 + stat_h + HEAD_H + len(msgs) * MSG_H + 8
    body += rect(PANEL_X, y, tw_sum, h, C["panel"], C["panel_bd"])
    ix = PANEL_X + 6
    iy = y + 10
    if has_stat:
        st, ny = stat_bar(iy, cfg.get("stat", []), cfg.get("stat_right", ""),
                          x=ix, w=tw_sum - 12)
        body += st
        iy = ny + 8
    body += rect(ix, iy, tw_sum - 12, HEAD_H, C["head"], C["head_bd"])
    body += text(ix + 8, vmid(iy, HEAD_H, 12), "类型", 12)
    body += text(ix + 40, vmid(iy, HEAD_H, 12), "消息号", 12)
    body += text(ix + 152, vmid(iy, HEAD_H, 12), "消息文本", 12)
    body += text(ix + tw_sum - 20, vmid(iy, HEAD_H, 12), "位置", 12, anchor="end")
    ry = iy + HEAD_H
    for m in msgs:
        body += rect(ix, ry, tw_sum - 12, MSG_H, "#ffffff")
        body += line(ix, ry + MSG_H, ix + tw_sum - 12, ry + MSG_H, "#eef2f6")
        body += msg_icon(ix + 8, ry + 3, m.get("t", "S"))
        col = {"S": C["green"], "E": C["red"], "W": C["amber"], "I": C["blue"]}.get(m.get("t", "S"))
        body += text(ix + 26, vmid(ry, MSG_H, 12), m.get("t", "S"), 12, fill=col, weight="bold")
        body += text(ix + 40, vmid(ry, MSG_H, 12), m.get("no", ""), 12, fill=C["tx2"])
        body += text(ix + 152, vmid(ry, MSG_H, 12), m.get("text", ""), 12)
        body += text(ix + tw_sum - 20, vmid(ry, MSG_H, 12), m.get("pos", ""), 12, anchor="end", fill=C["tx2"])
        ry += MSG_H
    y = y + h + GAP_H
    sb, y = status_bar(y, cfg.get("status", ""))
    body += sb
    return svg_wrap(uid, body, y)


# ----------------------------------------------------------------------------
# 形态 3：功能开发屏（Tab + 抬头 + 可编辑行项目）
# ----------------------------------------------------------------------------

def build_dynpro(cfg):
    uid = _uid(cfg.get("name", "dyn"))
    body, y = title_bar(uid, cfg.get("title", ""))
    tb, y = toolbar(y, cfg.get("toolbar", ["检查", "|", "新增行", "删除行", "复制行", "|", "上载 Excel", "返回"]))
    body += tb
    y += GAP_H

    # Tab 页签
    tabs = cfg.get("tabs", [])
    active = cfg.get("active_tab", 0)
    tx = PANEL_X + 6
    for i, t in enumerate(tabs):
        tw_ = tw(t, 12) + 32
        on = (i == active)
        body += rect(tx, y, tw_, TAB_H, C["tab_on"] if on else C["tab_off"], C["tab_bd"], rx=3)
        body += text(tx + tw_ / 2.0, vmid(y, TAB_H, 12), t, 12, anchor="middle",
                     weight="bold" if on else "normal")
        tx += tw_ + 2
    y += TAB_H
    body += line(PANEL_X, y, PANEL_X + PANEL_W, y, C["panel_bd"])

    # 抬头字段区
    rows = cfg.get("fields", [])
    ph = 16 + len(rows) * 27 + 18
    body += rect(PANEL_X, y, PANEL_W, ph, C["panel"])
    ly = y + 16
    for row in rows:
        fx = PANEL_X + 1 + 22
        for f in row:
            lw = f.get("label_w", 130)
            body += text(fx + lw - 9, vmid(ly, BOX_H, 12), f.get("label", ""), 12, anchor="end")
            bw = f.get("w", 96)
            bx = fx + lw
            if f.get("dd"):
                body += dropdown(bx, ly, bw, f.get("value", ""), f.get("required", False))
            else:
                body += input_box(bx, ly, bw, f.get("value", ""), f.get("required", False),
                                  f.get("readonly", False))
            if f.get("f4"):
                body += f4_button(bx + bw + 2, ly + 1)
            fx = bx + bw + (35 if f.get("f4") else 34)
        ly += 27
    y += ph

    # 行项目区
    items = cfg.get("items")
    if items:
        y += GAP_H
        body += text(PANEL_X + 12, vmid(y, 18, 12), items.get("title", "行项目"), 12,
                     weight="bold")
        y += 20
        cols = items.get("columns", [])
        irows = items.get("rows", [])
        total = items.get("total")
        edit_cols = set(items.get("edit_cols", []))
        sel_row = items.get("selected_row", -1)
        tw_sum = sum(c["w"] for c in cols)
        h = HEAD_H + len(irows) * 22 + (22 if total else 0)
        body += rect(PANEL_X, y, tw_sum, h, "#ffffff", C["panel_bd"])
        iy = y
        body += rect(PANEL_X, iy, tw_sum, HEAD_H, C["head"], C["head_bd"])
        cxp = PANEL_X
        for i, c in enumerate(cols):
            body += col_text(cxp, c["w"], vmid(iy, HEAD_H, 12), c["t"], c)
            cxp += c["w"]
            if i < len(cols) - 1:
                body += line(cxp, iy, cxp, iy + HEAD_H, C["head_sep"])
        ry = iy + HEAD_H
        for ri, r in enumerate(irows):
            cells = r.get("cells", r) if isinstance(r, dict) else r
            body += rect(PANEL_X, ry, tw_sum, 22,
                         C["row_sel"] if ri == sel_row else C["row"])
            body += line(PANEL_X, ry + 22, PANEL_X + tw_sum, ry + 22, C["row_bd"])
            cxp = PANEL_X
            for ci, cell in enumerate(cells):
                cw = cols[ci]["w"] if ci < len(cols) else 60
                if ci in edit_cols:
                    body += rect(cxp, ry, cw, 22, "#ffffff")
                    body += line(cxp + cw, ry, cxp + cw, ry + 22, "#dfe6ec")
                    if cell != "":
                        body += col_text(cxp, cw, vmid(ry, 22, 12), cell, cols[ci] if ci < len(cols) else {})
                else:
                    body += col_text(cxp, cw, vmid(ry, 22, 12), cell, cols[ci] if ci < len(cols) else {})
                cxp += cw
            ry += 22
        if total:
            body += rect(PANEL_X, ry, tw_sum, 22, C["total"])
            body += line(PANEL_X, ry + 22, PANEL_X + tw_sum, ry + 22, C["total_bd"])
            cxp = PANEL_X
            for ci, cell in enumerate(total):
                cw = cols[ci]["w"] if ci < len(cols) else 60
                body += col_text(cxp, cw, vmid(ry, 22, 12), cell, cols[ci] if ci < len(cols) else {}, bold=True)
                cxp += cw
            ry += 22
        y = ry

    # 按钮区
    btns = cfg.get("buttons", [])
    if btns:
        y += 12
        bx = PANEL_X + 12
        for i, b in enumerate(btns):
            bw_ = tw(b, 12) + 28
            body += text_button(bx, y, bw_, 24, b)
            bx += bw_ + 8
        y += 24 + 12

    # 消息区
    msgs = cfg.get("messages", [])
    if msgs:
        y += 4
        mh = len(msgs) * MSG_H + 2
        body += rect(PANEL_X, y, PANEL_W, mh, "#ffffff", C["panel_bd"])
        my = y + 1
        for m in msgs:
            body += msg_icon(PANEL_X + 8, my + 3, m.get("t", "S"))
            col = {"S": C["green"], "E": C["red"], "W": C["amber"], "I": C["blue"]}.get(m.get("t", "S"))
            body += text(PANEL_X + 26, vmid(my, MSG_H, 12), m.get("t", "S"), 12, fill=col, weight="bold")
            body += text(PANEL_X + 40, vmid(my, MSG_H, 12), m.get("no", ""), 12, fill=C["tx2"])
            body += text(PANEL_X + 152, vmid(my, MSG_H, 12), m.get("text", ""), 12)
            my += MSG_H
        y += mh

    y += GAP_H
    sb, y = status_bar(y, cfg.get("status", ""))
    body += sb
    return svg_wrap(uid, body, y)


# ----------------------------------------------------------------------------
# 形态 4：业务框架图（泳道）· 形态 5：技术框架图（分层）
# ----------------------------------------------------------------------------

LANE_LABEL_W = 130   # 左侧泳道/层标签栏宽
FIG_TITLE_H  = 48    # 图标题占用的高度带（★ 标签栏必须从这里开始，不能从 0）
LANE_H       = 96    # 泳道高
LAYER_H      = 84    # 分层高
NODE_H_SW    = 42    # 泳道节点高
NODE_H_TL    = 44    # 分层节点高

# 色调：填充 / 边框 / 文字
TONE = {
    "plain": ("#ffffff", "#b0bec5", "#1a1a1a"),
    "sys":   ("#e8f1fb", "#93b2d0", "#1a1a1a"),
    "ok":    ("#e8f5e9", "#81c784", "#1a1a1a"),
    "err":   ("#fff3e0", "#ffb74d", "#8a4b00"),
}


def _arrow(x, y, direction):
    if direction == "right":
        pts = [(x, y), (x - 8, y - 4), (x - 8, y + 4)]
    elif direction == "down":
        pts = [(x, y), (x - 4, y - 8), (x + 4, y - 8)]
    elif direction == "up":
        pts = [(x, y), (x - 4, y + 8), (x + 4, y + 8)]
    else:
        pts = [(x, y), (x + 8, y - 4), (x + 8, y + 4)]
    return '<polygon points="%s" fill="#90a4ae"/>' % " ".join("%.1f,%.1f" % p for p in pts)


def _shape_person(cx, cy, w, h, fill, stroke):
    return rect(cx - w / 2, cy - h / 2, w, h, fill, stroke, rx=5)


def _shape_system(cx, cy, w, h, fill, stroke):
    hw, hh = w / 2.0, h / 2.0
    cut = min(12.0, w * 0.09)
    pts = [(cx - hw + cut, cy - hh), (cx + hw - cut, cy - hh), (cx + hw, cy),
           (cx + hw - cut, cy + hh), (cx - hw + cut, cy + hh), (cx - hw, cy)]
    return '<polygon points="%s" fill="%s" stroke="%s"/>' % (
        " ".join("%.1f,%.1f" % p for p in pts), fill, stroke)


def _shape_doc(cx, cy, w, h, fill, stroke):
    hw, hh = w / 2.0, h / 2.0
    fold = 15.0
    x, y = cx - hw, cy - hh
    d = "M%.1f,%.1f h%.1f l%.1f,%.1f v%.1f h%.1f z" % (x, y, w - fold, fold, fold, h - fold, -w)
    return '<path d="%s" fill="%s" stroke="%s"/>' % (d, fill, stroke)


def _shape_decision(cx, cy, w, h, fill, stroke):
    hw, hh = w / 2.0, h / 2.0
    return ('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s" stroke="%s"/>'
            % (cx, cy - hh, cx + hw, cy, cx, cy + hh, cx - hw, cy, fill, stroke))


SHAPES = {"person": _shape_person, "system": _shape_system,
          "doc": _shape_doc, "decision": _shape_decision}


def build_biz_swimlane(cfg):
    """业务框架图：水平泳道 = 角色，垂直列 = 业务步骤"""
    uid = _uid(cfg.get("name", "biz"))
    lanes = cfg.get("lanes", [])
    steps = cfg.get("steps", [])
    nodes_cfg = cfg.get("nodes", [])
    edges_cfg = cfg.get("edges", [])
    n_lane = max(1, len(lanes))
    n_step = max(1, len(steps))
    cw = W - LANE_LABEL_W
    step_w = cw / float(n_step)
    height = FIG_TITLE_H + LANE_H * n_lane + 36

    body = rect(0, 0, W, height, "#ffffff")
    body += text(24, 28, cfg.get("title", ""), 14, weight="bold")

    for i in range(n_lane):
        body += rect(0, FIG_TITLE_H + i * LANE_H, W, LANE_H,
                     "#f7f9fb" if i % 2 == 0 else "#ffffff")
    for i in range(1, n_step):
        x = LANE_LABEL_W + i * step_w
        body += line(x, FIG_TITLE_H, x, FIG_TITLE_H + LANE_H * n_lane, "#e3eaf1", dash="3 3")
    body += line(0, FIG_TITLE_H + LANE_H * n_lane, W, FIG_TITLE_H + LANE_H * n_lane, "#e3eaf1")

    # ★ 标签栏从 FIG_TITLE_H 起——从 0 起会盖住图标题（实测踩过）
    body += rect(0, FIG_TITLE_H, LANE_LABEL_W, LANE_H * n_lane, "#eef3f8")
    body += line(LANE_LABEL_W, FIG_TITLE_H, LANE_LABEL_W, FIG_TITLE_H + LANE_H * n_lane, "#d6dee7")
    for i, ln in enumerate(lanes):
        lb = ln["label"] if isinstance(ln, dict) else str(ln)
        body += text(LANE_LABEL_W / 2.0, FIG_TITLE_H + i * LANE_H + LANE_H / 2.0 + 4,
                     lb, 12, anchor="middle", weight="bold")

    nw = min(150.0, step_w - 26)
    pos = []
    for nd in nodes_cfg:
        li, si = nd.get("lane", 0), nd.get("step", 0)
        cx = LANE_LABEL_W + si * step_w + step_w / 2.0
        cy = FIG_TITLE_H + li * LANE_H + LANE_H / 2.0
        f, s, tc = TONE.get(nd.get("tone", "plain"), TONE["plain"])
        shape = SHAPES.get(nd.get("shape", "person"), _shape_person)
        body += shape(cx, cy, nw, NODE_H_SW, f, s)
        sub = nd.get("sub")
        body += text(cx, cy + (-4 if sub else 0) + 4, nd.get("text", ""), 12,
                     anchor="middle", fill=tc)
        if sub:
            body += text(cx, cy + 15, sub, 10, anchor="middle", fill="#5a6b7b")
        pos.append({"cx": cx, "cy": cy, "left": cx - nw / 2, "right": cx + nw / 2,
                    "top": cy - NODE_H_SW / 2.0, "bottom": cy + NODE_H_SW / 2.0,
                    "lane": li, "step": si})

    for e in edges_cfg:
        a, b = pos[e["from"]], pos[e["to"]]
        if a["lane"] == b["lane"]:
            body += line(a["right"], a["cy"], b["left"] - 9, b["cy"], "#90a4ae", sw=1.4)
            body += _arrow(b["left"], b["cy"], "right")
        else:
            down = b["cy"] > a["cy"]
            y2 = b["top"] if down else b["bottom"]
            body += ('<polyline points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" '
                     'stroke="#90a4ae" stroke-width="1.4"/>'
                     % (a["right"], a["cy"], b["cx"], a["cy"], b["cx"], y2 + (-8 if down else 8)))
            body += _arrow(b["cx"], y2, "down" if down else "up")
        if e.get("label"):
            body += text((a["right"] + b["cx"]) / 2.0, a["cy"] - 6, e["label"], 10,
                         anchor="middle", fill="#5a6b7b")

    fb = cfg.get("feedback")
    if fb:
        a, b = pos[fb["from"]], pos[fb["to"]]
        y = FIG_TITLE_H + 12
        body += ('<polyline points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" '
                 'stroke="#90a4ae" stroke-width="1.2" stroke-dasharray="4 3"/>'
                 % (a["cx"], a["top"], a["cx"], y, b["cx"], y, b["cx"], b["top"] - 2))
        body += _arrow(b["cx"], b["top"], "down")
        if fb.get("label"):
            body += text((a["cx"] + b["cx"]) / 2.0, y - 4, fb["label"], 10,
                         anchor="middle", fill="#5a6b7b")

    return svg_wrap(uid, body, height)


def build_tech_layers(cfg):
    """技术框架图：四层数据流（触发 → 逻辑 → 数据 → 输出）"""
    uid = _uid(cfg.get("name", "tech"))
    layers = cfg.get("layers", [])
    nodes_cfg = cfg.get("nodes", [])
    n_layer = max(1, len(layers))
    cols = max([n.get("col", 0) for n in nodes_cfg] + [0]) + 1
    cols = max(cols, int(cfg.get("min_cols", 3)))
    cw = W - LANE_LABEL_W
    col_w = cw / float(cols)
    nw = col_w - 60
    height = FIG_TITLE_H + LAYER_H * n_layer + 16

    body = rect(0, 0, W, height, "#ffffff")
    body += text(24, 28, cfg.get("title", ""), 14, weight="bold")

    for i in range(n_layer):
        body += rect(0, FIG_TITLE_H + i * LAYER_H, W, LAYER_H,
                     "#f7f9fb" if i % 2 == 0 else "#ffffff")
    body += rect(0, FIG_TITLE_H, LANE_LABEL_W, LAYER_H * n_layer, "#eef3f8")
    body += line(LANE_LABEL_W, FIG_TITLE_H, LANE_LABEL_W, FIG_TITLE_H + LAYER_H * n_layer, "#d6dee7")
    for i, ly in enumerate(layers):
        lb = ly["label"] if isinstance(ly, dict) else str(ly)
        body += text(LANE_LABEL_W / 2.0, FIG_TITLE_H + i * LAYER_H + LAYER_H / 2.0 + 4,
                     lb, 12, anchor="middle", weight="bold")

    pos = []
    for nd in nodes_cfg:
        li, ci = nd.get("layer", 0), nd.get("col", 0)
        cx = LANE_LABEL_W + ci * col_w + col_w / 2.0
        cy = FIG_TITLE_H + li * LAYER_H + LAYER_H / 2.0
        f, s, tc = TONE.get(nd.get("tone", "sys"), TONE["sys"])
        body += rect(cx - nw / 2, cy - NODE_H_TL / 2, nw, NODE_H_TL, f, s, rx=4)
        sub = nd.get("sub")
        body += text(cx, cy + (-4 if sub else 0) + 4, nd.get("text", ""), 12,
                     anchor="middle", fill=tc, weight="bold")
        if sub:
            body += text(cx, cy + 15, sub, 10, anchor="middle", fill="#5a6b7b")
        # 数据层必须标来源级别
        if nd.get("lv"):
            body += text(cx + nw / 2 - 8, cy + 4, nd["lv"], 9, anchor="end", fill="#5a6b7b")
        pos.append({"cx": cx, "top": cy - NODE_H_TL / 2.0, "bottom": cy + NODE_H_TL / 2.0,
                    "layer": li, "col": ci})

    edges = cfg.get("edges")
    if edges is None:                       # 自动：同 col 的相邻层连线
        by_col = {}
        for i, nd in enumerate(nodes_cfg):
            by_col.setdefault(nd.get("col", 0), []).append(i)
        edges = []
        for _c, idxs in by_col.items():
            idxs.sort(key=lambda k: nodes_cfg[k].get("layer", 0))
            for a, b in zip(idxs, idxs[1:]):
                edges.append({"from": a, "to": b})
    for e in edges:
        a, b = pos[e["from"]], pos[e["to"]]
        body += line(a["cx"], a["bottom"], b["cx"], b["top"] - 9, "#90a4ae", sw=1.4)
        body += _arrow(b["cx"], b["top"], "down")

    return svg_wrap(uid, body, height)


# ----------------------------------------------------------------------------
# 调度
# ----------------------------------------------------------------------------

BUILDERS = {
    "select_alv":   build_select_alv,
    "batch_upload": build_batch_upload,
    "batch_result": build_batch_result,
    "batch_log":    build_batch_log,
    "dynpro":       build_dynpro,
    "biz_swimlane": build_biz_swimlane,
    "tech_layers":  build_tech_layers,
}


def render(cfg):
    kind = cfg.get("kind")
    if kind not in BUILDERS:
        raise SystemExit("未知 kind：%s（可用：%s）" % (kind, ", ".join(BUILDERS)))
    return BUILDERS[kind](cfg)


def main(argv):
    if "--schema" in argv:
        print(SCHEMA)
        return
    if "--demo" in argv:
        outdir = argv[argv.index("-o") + 1] if "-o" in argv else None
        if "--json" in argv:                     # 顺便导出示例配置，便于改着用
            print(json.dumps(DEMO_CONFIG, ensure_ascii=False, indent=2))
            return
        for cfg in DEMO_CONFIG["screens"]:
            svg = render(cfg)
            if outdir:
                os.makedirs(outdir, exist_ok=True)
                fn = os.path.join(outdir, "%s.svg" % cfg["name"])
                with open(fn, "w", encoding="utf-8") as fh:
                    fh.write(svg)
                print("written: %s" % fn, file=sys.stderr)
            else:
                print("\n<!-- ===== %s ===== -->\n" % cfg["name"])
                print(svg)
        return

    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return

    path = argv[0]
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    screens = cfg.get("screens", [cfg])

    # --inject：生成后直接注入 Markdown 占位符，MD 一次成型
    #   占位符两种写法：{{SVG:名称}}（具名）· {{SVG}}（按 screens 顺序）
    if "--inject" in argv:
        md_path = argv[argv.index("--inject") + 1]
        pairs = [(sc.get("name", "svg%d" % i), render(sc)) for i, sc in enumerate(screens)]
        with open(md_path, "r", encoding="utf-8") as fh:
            md = fh.read()
        for nm, sv in pairs:
            md = md.replace("{{SVG:%s}}" % nm, sv)
        for nm, sv in pairs:
            md = md.replace("{{SVG}}", sv, 1)
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print("injected %d svg -> %s (未替换占位符: %d)"
              % (len(pairs), md_path, md.count("{{SVG")), file=sys.stderr)
        return

    outdir = None
    if "-o" in argv:
        outdir = argv[argv.index("-o") + 1]

    for sc in screens:
        svg = render(sc)
        if outdir:
            os.makedirs(outdir, exist_ok=True)
            fn = os.path.join(outdir, "%s.svg" % sc.get("name", "ui"))
            with open(fn, "w", encoding="utf-8") as fh:
                fh.write(svg)
            print("written: %s" % fn, file=sys.stderr)
        else:
            print("<!-- ==== %s ==== -->" % sc.get("name", "ui"))
            print(svg)


SCHEMA = """
JSON 结构（顶层 screens 数组，每个元素一种界面形态）：

{
  "screens": [
    {
      "name": "选择屏-ALV",          // 用于生成唯一 SVG id 与文件名
      "kind": "select_alv",          // select_alv|batch_upload|batch_result|batch_log|dynpro
      "title": "库存报表",
      "toolbar": ["显示", "|", "导出", "返回"],
      "select": {
        "fields": [
          {"label":"物料","value":"","box_w":168,"f4":true},
          {"label":"工厂","value":"1000","required":true,"f4":true,"dd":false},
          {"label":"日期","value":"2026/09/01","value2":"2026/09/30","range":true,"box_w":96}
        ],
        "checks": [{"label":"仅显示非限制库存","checked":true}]
      },
      "alv": {
        "columns": [{"t":"物料","w":90},{"t":"数量","w":70}],
        "rows": [["MAT-001","10.000"]],
        "warn_cells": [[0,1]],
        "total": ["合计","48.000"]
      },
      "status": "就绪"
    },
    { "name":"批导-上载", "kind":"batch_upload", "title":"...",
      "fields":[{"label":"导入文件名","value":"C:\\\\temp\\\\X.XLSX","box_w":380,"required":true,"f4":true},
                {"label":"列分隔方式","value":"XLSX 单元格","dd":true,"readonly":true}],
      "checks":[{"label":"首行含列标题","checked":true}], "status":"就绪" },
    { "name":"批导-结果", "kind":"batch_result", "title":"...",
      "stat":[{"label":"读取行数","value":"120"},{"label":"成功","value":"116","cls":"ok"}],
      "stat_right":"耗时 3.2 秒",
      "columns":[{"t":"行号","w":46},{"t":"状态","w":44,"icon":true},{"t":"消息文本","w":300}],
      "rows":[{"cells":["1","","订单已创建"],"status":"s"},
              {"cells":["3","","售达方不存在"],"status":"e","warn":[2]}],
      "total":["","","共 4 行"], "status":"已处理 120 行" },
    { "name":"批导-日志", "kind":"batch_log", "title":"...",
      "stat":[{"label":"消息总数","value":"8"}], "stat_right":"11:20:03 - 11:20:06",
      "messages":[{"t":"S","no":"V1 311","text":"销售订单已创建","pos":"第 1 行"}],
      "status":"日志已生成" },
    { "name":"功能开发屏", "kind":"dynpro", "title":"维护销售订单",
      "tabs":["基本数据","组织数据","附加数据"], "active_tab":0,
      "fields":[
        [{"label":"订单类型","value":"ZOR","required":true,"dd":true,"w":96},
         {"label":"订单日期","value":"2026/09/18","required":true,"w":96},
         {"label":"货币","value":"CNY","w":78}]
      ],
      "items":{
        "title":"行项目",
        "columns":[{"t":"项目","w":50},{"t":"物料","w":100}],
        "rows":[[{"cells":["10","MAT-1001"]}]],
        "edit_cols":[1],
        "total":["合计",""],
        "selected_row":0
      },
      "buttons":["检查","模拟","保存","返回"],
      "messages":[{"t":"E","no":"V1 234","text":"第 30 行：未输入物料"}],
      "status":"订单已就绪"
    }
    { "name":"业务框架图", "kind":"biz_swimlane", "title":"业务流程 · xxx",
      "lanes":["计划员","系统 · Z 程序","仓库 / 装运"],
      "steps":["准备导入","校验","分组","创建交货单","核对 / 打印"],
      "nodes":[{"lane":0,"step":0,"text":"准备导入 Excel","sub":"订单号/行项/数量","shape":"person"},
               {"lane":1,"step":1,"text":"7 项校验","sub":"逐行标错","shape":"system","tone":"sys"}],
      "edges":[{"from":0,"to":1}],
      "feedback":{"from":4,"to":1,"label":"修正后重新上载"} },

    { "name":"技术框架图", "kind":"tech_layers", "title":"技术实现 · 分层与数据流",
      "layers":["L1 触发层","L2 逻辑层","L3 数据层","L4 输出层"],
      "nodes":[{"layer":0,"col":0,"text":"事务码 XXX_BATCH","sub":"选择屏 · 文件 / 模式"},
               {"layer":2,"col":0,"text":"VBAK / VBAP","sub":"读订单（只读）","lv":"[L2]"},
               {"layer":3,"col":0,"text":"结果 ALV","sub":"行级明细","tone":"ok"}],
      "edges": null }
  ]
}

字段速查：
  shape  person(圆角矩形·人) | system(六边形·系统) | doc(文档形·数据) | decision(菱形·判定)
  tone   plain(白) | sys(浅蓝) | ok(浅绿) | err(浅橙)
  lv     数据层节点的来源级别标记 "[L1]"/"[L2]"/"[L3]"（tech_layers 专用，必填）
  edges  biz_swimlane 必须写；tech_layers 写 null 则按同 col 相邻层自动连线
  feedback  仅 biz_swimlane：异常回流虚线 {"from":节点索引,"to":节点索引,"label":"..."}

输出：SVG 文本（可直接内联进 Markdown）。
  -o <dir>            每个 screen 落一个 .svg 文件
  --inject <md路径>   生成后直接注入 MD 占位符（{{SVG:名称}} 具名 / {{SVG}} 按顺序），MD 一次成型
"""


DEMO_CONFIG = {
    "screens": [
        {
            "name": "示例-业务框架图",
            "kind": "biz_swimlane",
            "title": "业务流程 · 批量创建交货单",
            "lanes": ["计划员", "系统 · Z 程序", "仓库 / 装运"],
            "steps": ["准备导入", "校验", "分组", "创建交货单", "核对 / 打印"],
            "nodes": [
                {"lane": 0, "step": 0, "text": "准备导入 Excel", "sub": "订单号/行项/数量", "shape": "person"},
                {"lane": 1, "step": 1, "text": "7 项校验", "sub": "逐行标错、不中断", "shape": "system", "tone": "sys"},
                {"lane": 1, "step": 2, "text": "按销售订单分组", "sub": "一单一交货单", "shape": "system", "tone": "sys"},
                {"lane": 1, "step": 3, "text": "创建交货单", "sub": "BAPI + 逐单提交", "shape": "doc", "tone": "sys"},
                {"lane": 0, "step": 4, "text": "核对失败行并修正", "sub": "按行号定位", "shape": "person", "tone": "err"},
                {"lane": 2, "step": 4, "text": "打印送货单 / 拣配", "sub": "复用 ZSDR002", "shape": "person", "tone": "ok"},
            ],
            "edges": [{"from": 0, "to": 1}, {"from": 1, "to": 2}, {"from": 2, "to": 3},
                      {"from": 3, "to": 4}, {"from": 3, "to": 5}],
            "feedback": {"from": 4, "to": 1, "label": "修正后重新上载（仅跑失败行）"},
        },
        {
            "name": "示例-技术框架图",
            "kind": "tech_layers",
            "title": "技术实现 · 分层与数据流",
            "layers": ["L1 触发层", "L2 逻辑层", "L3 数据层", "L4 输出层"],
            "nodes": [
                {"layer": 0, "col": 0, "text": "事务码 ZSD_DLV_BATCH", "sub": "选择屏 · 文件 / 模式"},
                {"layer": 0, "col": 1, "text": "Excel 导入文件", "sub": "4 列：订单 / 项目 / 数量 / 日期"},
                {"layer": 0, "col": 2, "text": "处理模式", "sub": "正式执行 / 仅模拟运行"},
                {"layer": 1, "col": 0, "text": "7 项校验", "sub": "订单 / 冻结 / 状态 / 未清数量"},
                {"layer": 1, "col": 1, "text": "按销售订单分组", "sub": "哈希归集 · 无嵌套 LOOP"},
                {"layer": 1, "col": 2, "text": "结果收集器", "sub": "成功行 / 失败行 + 原因"},
                {"layer": 2, "col": 0, "text": "VBAK / VBAP / VBUP", "sub": "读订单与交货状态（只读）", "lv": "[L2]"},
                {"layer": 2, "col": 1, "text": "BAPI_DELIVERY_CREATEFROMDAT", "sub": "逐单创建 · 返回消息收集", "lv": "[L3]"},
                {"layer": 2, "col": 2, "text": "LIKP / LIPS", "sub": "交货单落库（经 BAPI 写入）", "lv": "[L2]"},
                {"layer": 3, "col": 0, "text": "结果 ALV", "sub": "行级明细 · 失败标黄", "tone": "ok"},
                {"layer": 3, "col": 1, "text": "执行日志（消息收集器）", "sub": "S / I / W / E 分级", "tone": "ok"},
                {"layer": 3, "col": 2, "text": "Excel 回写", "sub": "另存 *_RESULT.xlsx，不覆盖原件", "tone": "ok"},
            ],
        },
        {
            "name": "示例-选择屏ALV",
            "kind": "select_alv",
            "title": "库存报表",
            "toolbar": ["执行", "|", "显示", "变式", "导出", "返回"],
            "select": {
                "fields": [
                    {"label": "物料", "value": "", "box_w": 168, "f4": True},
                    {"label": "工厂", "value": "{工厂}", "required": True, "f4": True},
                    {"label": "日期", "value": "2026/09/01", "value2": "2026/09/30",
                     "range": True, "box_w": 96, "f4": True},
                ],
                "checks": [{"label": "仅显示非限制库存", "checked": True},
                           {"label": "包含已删除物料", "checked": False}],
            },
            "alv": {
                "columns": [{"t": "物料", "w": 90}, {"t": "工厂", "w": 60},
                            {"t": "库位", "w": 60}, {"t": "批次", "w": 90},
                            {"t": "非限制库存", "w": 90}, {"t": "单位", "w": 46},
                            {"t": "状态", "w": 90}],
                "rows": [["MAT-10001", "1000", "0001", "B20260901", "1,250.000", "PC", "正常"],
                         ["MAT-10002", "1000", "0001", "B20260902", "980.000", "PC", "正常"],
                         ["MAT-10003", "1000", "0002", "B20260820", "0.000", "PC", "已冻结"]],
                "warn_cells": [[2, 6]],
                "total": ["合计", "", "", "", "2,230.000", "PC", "3 条"],
            },
            "status": "已读取 3 条记录",
        },
        {
            "name": "示例-批导上载",
            "kind": "batch_upload",
            "title": "批量创建销售订单",
            "toolbar": ["模拟运行", "|", "下载模板", "显示日志", "返回"],
            "fields": [
                {"label": "导入文件名", "value": "C:\\temp\\SO_UPLOAD.XLSX",
                 "box_w": 380, "required": True, "f4": True},
                {"label": "工作表", "value": "Sheet1", "box_w": 96},
                {"label": "列分隔方式", "value": "XLSX 单元格", "dd": True, "readonly": True},
                {"label": "处理模式", "value": "仅创建新订单", "dd": True},
                {"label": "错误消息上限", "value": "100", "box_w": 78},
            ],
            "checks": [{"label": "首行含列标题", "checked": True},
                       {"label": "仅模拟运行（不写入数据库）", "checked": False},
                       {"label": "遇到错误继续处理后续行", "checked": True}],
            "status": "就绪",
        },
        {
            "name": "示例-批导结果",
            "kind": "batch_result",
            "title": "批量创建销售订单 - 处理结果",
            "toolbar": ["导出结果", "|", "仅看错误", "执行日志", "返回"],
            "stat": [{"label": "读取行数", "value": "120"}, {"label": "成功", "value": "116", "cls": "ok"},
                     {"label": "失败", "value": "4", "cls": "er"},
                     {"label": "警告", "value": "2", "cls": "wn"}],
            "stat_right": "耗时 3.2 秒 · 订单已提交 116 笔",
            "columns": [{"t": "行号", "w": 46}, {"t": "状态", "w": 44, "icon": True},
                        {"t": "销售订单", "w": 90}, {"t": "订单类型", "w": 70},
                        {"t": "售达方", "w": 90}, {"t": "物料", "w": 90},
                        {"t": "数量", "w": 80}, {"t": "单位", "w": 46},
                        {"t": "请求交货日期", "w": 100}, {"t": "消息文本", "w": 300}],
            "rows": [
                {"cells": ["1", "", "0000004711", "ZOR", "CUST-001", "MAT-1001", "10.000", "PC", "2026/09/20", "订单已创建"], "status": "s"},
                {"cells": ["2", "", "0000004712", "ZOR", "CUST-002", "MAT-1002", "25.000", "PC", "2026/09/22", "订单已创建"], "status": "s"},
                {"cells": ["3", "", "", "ZOR", "CUST-999", "MAT-1003", "5.000", "PC", "2026/09/25", "售达方 CUST-999 不存在（V1 371）"], "status": "e", "warn": [4, 9]},
                {"cells": ["4", "", "0000004713", "ZOR", "CUST-003", "MAT-2002", "8.000", "PC", "2026/09/28", "物料 MAT-2002 已标记停用，按警告继续"], "status": "w", "warn": [9]},
            ],
            "total": ["", "", "", "", "", "", "48.000", "", "", "共 4 行"],
            "status": "已处理 120 行，成功 116，失败 4",
        },
        {
            "name": "示例-批导日志",
            "kind": "batch_log",
            "title": "批量创建销售订单 - 执行日志",
            "toolbar": ["导出日志", "|", "仅看错误", "返回结果"],
            "stat": [{"label": "消息总数", "value": "8"}, {"label": "成功", "value": "3", "cls": "ok"},
                     {"label": "错误", "value": "1", "cls": "er"},
                     {"label": "警告", "value": "1", "cls": "wn"}],
            "stat_right": "开始 11:20:03 · 结束 11:20:06",
            "messages": [
                {"t": "S", "no": "ZSD_IMP 001", "text": "导入文件读取成功，共 120 行，列标题已识别", "pos": "— · 11:20:03"},
                {"t": "I", "no": "ZSD_IMP 002", "text": "列映射：售达方 → KUNNR，物料 → MATNR，数量 → KWMENG", "pos": "— · 11:20:03"},
                {"t": "S", "no": "V1 311", "text": "销售订单 0000004711 已创建", "pos": "第 1 行 · 11:20:04"},
                {"t": "W", "no": "V1 402", "text": "物料 MAT-2002 已标记停用，仍按当前输入创建", "pos": "第 4 行 · 11:20:05"},
                {"t": "E", "no": "V1 371", "text": "售达方 CUST-999 不存在，该行已跳过", "pos": "第 3 行 · 11:20:05"},
                {"t": "S", "no": "ZSD_IMP 900", "text": "处理完成：共 120 行，成功 116，失败 4", "pos": "— · 11:20:06"},
            ],
            "status": "日志已生成",
        },
        {
            "name": "示例-功能开发屏",
            "kind": "dynpro",
            "title": "维护销售订单",
            "toolbar": ["检查", "|", "新增行", "插入行", "删除行", "复制行", "|", "上载 Excel", "返回"],
            "tabs": ["基本数据", "组织数据", "附加数据"],
            "active_tab": 0,
            "fields": [
                [{"label": "订单类型", "value": "ZOR", "required": True, "dd": True, "w": 96},
                 {"label": "订单日期", "value": "2026/09/18", "required": True, "w": 96},
                 {"label": "货币", "value": "CNY", "w": 78}],
                [{"label": "售达方", "value": "CUST-001", "required": True, "w": 96, "f4": True},
                 {"label": "客户参考", "value": "REF-2026-0918", "w": 168}],
                [{"label": "送达方", "value": "CUST-001", "w": 96, "f4": True},
                 {"label": "采购订单号", "value": "PO-88213", "w": 168}],
                [{"label": "请求交货日期", "value": "2026/09/25", "w": 96},
                 {"label": "销售员", "value": "SALES-07", "w": 114},
                 {"label": "付款条件", "value": "0001", "w": 96}],
                [{"label": "订单说明", "value": "客户加急订单，需在交付期内完成", "w": 300}],
            ],
            "items": {
                "title": "行项目",
                "columns": [{"t": "项目", "w": 50}, {"t": "物料", "w": 100},
                            {"t": "物料描述", "w": 180}, {"t": "数量", "w": 80},
                            {"t": "单位", "w": 46}, {"t": "单价", "w": 90},
                            {"t": "净价值", "w": 80}, {"t": "交货日期", "w": 100},
                            {"t": "工厂", "w": 70}, {"t": "状态", "w": 90}],
                "rows": [["10", "MAT-1001", "铝合金型材 6063-T5", "10.000", "PC", "128.50", "1,285.00", "2026/09/25", "{工厂}", "已确认"],
                         ["20", "MAT-1002", "铝合金型材 6061-T6", "25.000", "PC", "146.00", "3,650.00", "2026/09/28", "{工厂}", "已确认"],
                         ["30", "", "", "", "", "", "", "", "", ""]],
                "edit_cols": [1, 3, 5, 7],
                "total": ["", "", "合计", "35.000", "", "", "4,935.00", "", "", "3 行"],
                "selected_row": 0,
            },
            "buttons": ["检查", "模拟", "保存", "返回"],
            "messages": [{"t": "W", "no": "V1 402", "text": "第 20 行：请求交货日期早于物料可用日期，已按可用日期调整"}],
            "status": "订单已就绪，3 个行项目",
        },
    ]
}


if __name__ == "__main__":
    main(sys.argv[1:])
