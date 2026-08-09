#!/usr/bin/env python3
"""Render the four frozen Competition RAG SVG figures.

The renderer is intentionally dependency-free.  It keeps labels as SVG text and
assigns stable IDs to figure groups, nodes, and paths for later manual editing.
Technical claims come only from the frozen specs and VISUAL_EVIDENCE_LEDGER.md.
"""

from __future__ import annotations

import math
import re
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "competition" / "visuals" / "rendered"

W, H = 1600, 900
# A single family keeps librsvg/ImageMagick and PowerPoint imports deterministic;
# Hiragino Sans ships with macOS and provides complete Simplified Chinese glyphs.
FONT = "Hiragino Sans"

COLORS = {
    "bg": "#F4F7FB",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFD",
    "ink": "#102A43",
    "muted": "#5D6B7E",
    "line": "#D8E1EC",
    "primary": "#2F6BFF",
    "primary_soft": "#EAF0FF",
    "cyan": "#158A9B",
    "cyan_soft": "#E6F7F8",
    "success": "#168B5B",
    "success_soft": "#E8F7F0",
    "audit": "#7456D8",
    "audit_soft": "#F0ECFF",
    "danger": "#C83E4D",
    "danger_soft": "#FCECEF",
    "warn": "#B56808",
    "warn_soft": "#FFF3DC",
    "dark": "#173B57",
}


class SVG:
    def __init__(self, figure_id: str, title: str, description: str):
        self.parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc" id="{figure_id}">',
            f"<title id=\"title\">{escape(title)}</title>",
            f"<desc id=\"desc\">{escape(description)}</desc>",
            "<defs>",
            "  <filter id=\"shadow\" x=\"-10%\" y=\"-10%\" width=\"120%\" height=\"130%\">",
            "    <feDropShadow dx=\"0\" dy=\"5\" stdDeviation=\"8\" flood-color=\"#102A43\" flood-opacity=\"0.08\"/>",
            "  </filter>",
            "</defs>",
            f'<rect id="canvas" width="{W}" height="{H}" fill="{COLORS["bg"]}"/>',
        ]

    def add(self, raw: str) -> None:
        self.parts.append(raw)

    def start(self, element_id: str, label: str | None = None) -> None:
        aria = f' aria-label="{escape(label)}"' if label else ""
        self.add(f'<g id="{element_id}"{aria}>')

    def end(self) -> None:
        self.add("</g>")

    def rect(
        self,
        element_id: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = COLORS["surface"],
        stroke: str = COLORS["line"],
        sw: float = 1.5,
        radius: float = 18,
        shadow: bool = False,
        dash: str | None = None,
    ) -> None:
        attrs = [
            f'id="{element_id}"',
            f'x="{x}"',
            f'y="{y}"',
            f'width="{w}"',
            f'height="{h}"',
            f'rx="{radius}"',
            f'fill="{fill}"',
            f'stroke="{stroke}"',
            f'stroke-width="{sw}"',
        ]
        if shadow:
            attrs.append('filter="url(#shadow)"')
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
        self.add(f"<rect {' '.join(attrs)}/>")

    def diamond(
        self,
        element_id: str,
        cx: float,
        cy: float,
        w: float,
        h: float,
        *,
        fill: str = COLORS["surface"],
        stroke: str = COLORS["primary"],
    ) -> None:
        pts = f"{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}"
        self.add(
            f'<polygon id="{element_id}" points="{pts}" fill="{fill}" stroke="{stroke}" '
            'stroke-width="2" filter="url(#shadow)"/>'
        )

    def circle(self, element_id: str, cx: float, cy: float, r: float, fill: str, stroke: str = "none") -> None:
        self.add(
            f'<circle id="{element_id}" cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}"/>'
        )

    def text(
        self,
        element_id: str,
        x: float,
        y: float,
        lines: str | list[str],
        *,
        size: int = 18,
        weight: int = 500,
        fill: str = COLORS["ink"],
        anchor: str = "start",
        line_height: int | None = None,
        letter_spacing: float | None = None,
    ) -> None:
        if isinstance(lines, str):
            lines = [lines]
        lh = line_height or round(size * 1.35)
        ls = f' letter-spacing="{letter_spacing}"' if letter_spacing is not None else ""
        self.add(
            f'<text id="{element_id}" x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{ls}>'
        )
        for idx, line in enumerate(lines):
            dy = 0 if idx == 0 else lh
            self.add(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
        self.add("</text>")

    def path(
        self,
        element_id: str,
        d: str,
        *,
        color: str = COLORS["primary"],
        sw: float = 2.5,
        marker: str | None = "arrow-primary",
        dash: str | None = None,
        opacity: float = 1,
    ) -> None:
        attrs = [
            f'id="{element_id}"',
            f'd="{d}"',
            'fill="none"',
            f'stroke="{color}"',
            f'stroke-width="{sw}"',
            'stroke-linecap="round"',
            'stroke-linejoin="round"',
            f'opacity="{opacity}"',
        ]
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
        self.add(f"<path {' '.join(attrs)}/>")
        if marker:
            segment = self._final_segment(d)
            if segment is not None:
                (x1, y1), (x2, y2) = segment
                dx, dy = x2 - x1, y2 - y1
                length = math.hypot(dx, dy)
                if length:
                    ux, uy = dx / length, dy / length
                    bx, by = x2 - ux * 10, y2 - uy * 10
                    px, py = -uy * 4.5, ux * 4.5
                    points = f"{x2},{y2} {bx + px},{by + py} {bx - px},{by - py}"
                    self.add(f'<polygon id="{element_id}-arrowhead" points="{points}" fill="{color}" opacity="{opacity}"/>')

    @staticmethod
    def _final_segment(d: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """Return the last segment for the renderer's absolute M/L/H/V paths."""
        tokens = re.findall(r"[MLHV]|-?\d+(?:\.\d+)?", d)
        x = y = 0.0
        points: list[tuple[float, float]] = []
        i = 0
        command = ""
        while i < len(tokens):
            token = tokens[i]
            if token in {"M", "L", "H", "V"}:
                command = token
                i += 1
                continue
            if command in {"M", "L"}:
                if i + 1 >= len(tokens):
                    break
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
            elif command == "H":
                x = float(tokens[i])
                i += 1
            elif command == "V":
                y = float(tokens[i])
                i += 1
            else:
                i += 1
                continue
            points.append((x, y))
        if len(points) < 2:
            return None
        return points[-2], points[-1]

    def line(
        self,
        element_id: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        **kwargs,
    ) -> None:
        self.path(element_id, f"M {x1} {y1} L {x2} {y2}", **kwargs)

    def finish(self, metadata: str) -> str:
        self.add(f"<metadata>{escape(metadata)}</metadata>")
        self.add("</svg>")
        return "\n".join(self.parts) + "\n"


def figure_header(svg: SVG, number: str, title: str, subtitle: str, badge: str = "RAG COMPETITION · FROZEN") -> None:
    svg.text("figure-number", 60, 42, number, size=14, weight=600, fill=COLORS["primary"], letter_spacing=1.8)
    svg.text("figure-title", 60, 78, title, size=30, weight=650)
    svg.text("figure-subtitle", 60, 103, subtitle, size=15, weight=400, fill=COLORS["muted"])
    svg.rect("baseline-badge-bg", 1250, 35, 290, 38, fill=COLORS["dark"], stroke=COLORS["dark"], radius=19)
    svg.text("baseline-badge", 1395, 60, badge, size=13, weight=600, fill="#FFFFFF", anchor="middle", letter_spacing=0.7)


def group_panel(svg: SVG, group_id: str, x: float, y: float, w: float, h: float, label: str, accent: str) -> None:
    svg.start(group_id, label)
    svg.rect(f"{group_id}-panel", x, y, w, h, fill=COLORS["surface_alt"], stroke=COLORS["line"], sw=1.2, radius=22)
    svg.rect(f"{group_id}-accent", x, y, 7, h, fill=accent, stroke=accent, sw=0, radius=3)
    svg.text(f"{group_id}-label", x + 24, y + 33, label, size=16, weight=650, fill=accent)
    svg.end()


def card(
    svg: SVG,
    node_id: str,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    detail: str | list[str] | None = None,
    *,
    accent: str = COLORS["primary"],
    fill: str = COLORS["surface"],
    title_size: int = 17,
    detail_size: int = 13,
    shadow: bool = True,
    center: bool = False,
) -> None:
    svg.start(node_id, title)
    svg.rect(f"{node_id}-bg", x, y, w, h, fill=fill, stroke=COLORS["line"], sw=1.2, radius=15, shadow=shadow)
    svg.rect(f"{node_id}-accent", x, y, 6, h, fill=accent, stroke=accent, sw=0, radius=3)
    tx = x + w / 2 if center else x + 18
    anchor = "middle" if center else "start"
    svg.text(f"{node_id}-title", tx, y + 31, title, size=title_size, weight=650, anchor=anchor)
    if detail:
        svg.text(
            f"{node_id}-detail",
            tx,
            y + 55,
            detail,
            size=detail_size,
            weight=430,
            fill=COLORS["muted"],
            anchor=anchor,
            line_height=detail_size + 7,
        )
    svg.end()


def pill(svg: SVG, element_id: str, x: float, y: float, w: float, text: str, fill: str, color: str) -> None:
    svg.rect(f"{element_id}-bg", x, y, w, 34, fill=fill, stroke=fill, sw=0, radius=17)
    svg.text(element_id, x + w / 2, y + 22, text, size=13, weight=650, fill=color, anchor="middle")


def render_01() -> str:
    svg = SVG(
        "figure-01-system-architecture",
        "冻结 RAG 核心架构",
        "可信版本、授权双路检索、默认 RRF、证据约束生成、Citation 审计和生命周期失败关闭。",
    )
    figure_header(svg, "FIGURE 01", "冻结 RAG 核心架构", "可信版本进入授权检索；模型只消费可追溯 Evidence")

    group_panel(svg, "group-trusted-knowledge", 60, 125, 1480, 135, "可信知识与版本", COLORS["cyan"])
    group_panel(svg, "group-authorized-retrieval", 60, 280, 1040, 235, "授权混合检索", COLORS["primary"])
    group_panel(svg, "group-grounded-generation", 1120, 280, 420, 235, "证据约束生成", COLORS["success"])
    group_panel(svg, "group-citation-audit", 60, 535, 1480, 140, "引用与多证据审计", COLORS["audit"])
    group_panel(svg, "group-lifecycle", 60, 695, 1480, 130, "生命周期与安全护栏", COLORS["danger"])

    # Trusted knowledge and version layer.
    card(svg, "node-approved-source", 95, 170, 235, 66, "获准 PDF / 文献来源", "OCR 未完成", accent=COLORS["cyan"])
    card(svg, "node-chunk-identity", 390, 170, 245, 66, "Chunk + 页码 / 邻接身份", accent=COLORS["cyan"])
    card(svg, "node-postgres-truth", 695, 160, 320, 82, "PostgreSQL owner / 版本 / 快照", "生命周期与不可变 Chunk 事实源", accent=COLORS["cyan"])
    card(svg, "node-ready-version", 1120, 160, 245, 82, "READY 版本", "解析 · Chunk · ES · Milvus 就绪", accent=COLORS["success"], fill=COLORS["success_soft"])
    svg.line("edge-source-chunk", 330, 203, 390, 203, color=COLORS["cyan"], marker="arrow-muted")
    svg.line("edge-chunk-postgres", 635, 203, 695, 203, color=COLORS["cyan"], marker="arrow-muted")
    svg.line("edge-postgres-ready", 1015, 203, 1120, 203, color=COLORS["success"], marker="arrow-primary")

    # Online retrieval primary path.
    card(svg, "node-question", 95, 355, 165, 78, "用户问题", "Question", accent=COLORS["primary"], center=True)
    card(svg, "node-elasticsearch", 330, 316, 190, 74, "Elasticsearch", "BM25 词项检索", accent=COLORS["primary"])
    card(svg, "node-milvus", 330, 414, 190, 74, "Milvus", "BGE-M3 向量检索", accent=COLORS["primary"])
    card(svg, "node-top20", 565, 365, 170, 76, "双路候选 Top-20", accent=COLORS["primary"], center=True)
    card(svg, "node-rrf", 775, 365, 160, 76, "RRF 融合 · k=60", "按名次融合", accent=COLORS["primary"], center=True)
    card(svg, "node-evidence-top3", 955, 365, 145, 76, "Evidence Top-3", accent=COLORS["success"], fill=COLORS["success_soft"], center=True, title_size=15)
    svg.path("edge-question-es", "M 260 384 H 290 V 353 H 330")
    svg.path("edge-question-milvus", "M 260 404 H 290 V 451 H 330")
    svg.path("edge-es-top20", "M 520 353 H 545 V 393 H 565")
    svg.path("edge-milvus-top20", "M 520 451 H 545 V 413 H 565")
    svg.line("edge-top20-rrf", 735, 403, 775, 403)
    svg.line("edge-rrf-top3", 935, 403, 955, 403)
    svg.path("edge-ready-es", "M 1190 242 V 275 H 425 V 316", color=COLORS["success"], sw=1.8, marker="arrow-muted", opacity=0.8)
    svg.path("edge-ready-milvus", "M 1255 242 V 266 H 535 V 451 H 520", color=COLORS["success"], sw=1.8, marker="arrow-muted", opacity=0.8)
    pill(svg, "default-ranking", 770, 470, 255, "默认 RRF · Reranker OFF", COLORS["primary_soft"], COLORS["primary"])

    # Grounded generation.
    card(svg, "node-qwen", 1145, 335, 150, 70, "Qwen3 14B", "think=false", accent=COLORS["success"])
    card(svg, "node-prompt", 1145, 424, 210, 70, "academic-evidence-answer-v1", "Question + Evidence", accent=COLORS["success"], title_size=12)
    card(svg, "node-answer", 1380, 375, 130, 78, "Answer + Citation", accent=COLORS["success"], fill=COLORS["success_soft"], center=True, title_size=14)
    svg.path("edge-top3-prompt", "M 1100 403 H 1125 V 459 H 1145", color=COLORS["success"], marker="arrow-primary")
    svg.line("edge-qwen-prompt", 1220, 405, 1220, 424, color=COLORS["success"], marker="arrow-primary")
    svg.path("edge-question-prompt", "M 177 433 V 500 H 1125 V 470 H 1145", sw=1.8, marker="arrow-muted", opacity=0.65)
    svg.path("edge-prompt-answer", "M 1355 459 H 1365 V 414 H 1380", color=COLORS["success"], marker="arrow-primary")

    # Citation and EvidenceSet audit path.
    card(svg, "node-citation", 120, 575, 170, 66, "Citation", "请求内 Evidence ID", accent=COLORS["audit"], fill=COLORS["audit_soft"])
    card(svg, "node-evidence-lineage", 350, 575, 315, 66, "Evidence 身份链", "document · page · chunk · version", accent=COLORS["audit"])
    card(svg, "node-claim-set", 790, 575, 250, 66, "Claim → EvidenceSet", accent=COLORS["audit"], fill=COLORS["audit_soft"], center=True)
    card(svg, "node-audit-only", 1110, 565, 340, 82, "AUDIT_ONLY", ["审计，不自动裁决", "非语义 Judge"], accent=COLORS["audit"], fill=COLORS["audit_soft"], center=True)
    svg.line("edge-citation-lineage", 290, 608, 350, 608, color=COLORS["audit"], marker="arrow-audit")
    svg.line("edge-claim-audit", 1040, 608, 1110, 608, color=COLORS["audit"], marker="arrow-audit")
    svg.path("edge-answer-citation", "M 1420 453 V 530 H 205 V 575", color=COLORS["audit"], sw=1.8, marker="arrow-audit", dash="6 6")
    svg.path("edge-answer-claim", "M 1460 453 V 545 H 915 V 575", color=COLORS["audit"], sw=1.8, marker="arrow-audit", dash="6 6")

    # Lifecycle and fail-closed rail.
    card(svg, "node-acl", 95, 738, 245, 58, "owner ACL + READY 可见性", accent=COLORS["danger"], shadow=False, center=True)
    card(svg, "node-inactive", 495, 738, 190, 58, "DELETE / INACTIVE", accent=COLORS["danger"], fill=COLORS["danger_soft"], shadow=False, center=True)
    card(svg, "node-cleanup", 815, 728, 310, 78, "三路 cleanup", "PostgreSQL · ES · Milvus / snapshot", accent=COLORS["danger"], shadow=False, center=True)
    card(svg, "node-403", 1260, 728, 245, 78, "403 RAG_FORBIDDEN_SCOPE", "不复用 stale Evidence", accent=COLORS["danger"], fill=COLORS["danger_soft"], shadow=False, center=True, title_size=15)
    svg.line("edge-acl-inactive", 340, 767, 495, 767, color=COLORS["muted"], marker="arrow-muted", dash="6 6")
    svg.line("edge-inactive-cleanup", 685, 767, 815, 767, color=COLORS["danger"], marker="arrow-danger")
    svg.line("edge-cleanup-403", 1125, 767, 1260, 767, color=COLORS["danger"], marker="arrow-danger")
    svg.path("edge-acl-ready", "M 218 738 V 690 H 1080 V 220 H 1120", color=COLORS["muted"], sw=1.6, marker="arrow-muted", dash="5 7", opacity=0.7)
    svg.path("edge-ready-inactive", "M 1240 242 V 270 H 590 V 738", color=COLORS["danger"], sw=1.5, marker="arrow-danger", dash="5 7", opacity=0.55)

    svg.text("footer-boundary", 800, 866, "冻结边界：默认 RRF · Reranker OFF · EvidenceSet AUDIT_ONLY · 非 production-ready", size=14, weight=550, fill=COLORS["muted"], anchor="middle")
    return svg.finish("Spec: 01-system-architecture.spec.md; Evidence: VISUAL_EVIDENCE_LEDGER.md 01-E01..01-E18")


def render_03() -> str:
    svg = SVG(
        "figure-03-online-rag-pipeline",
        "单次在线 RAG 请求流程",
        "请求从 owner 和 READY 校验进入并行检索、RRF、Evidence、Qwen 和 Citation 验证，并以三类独立路径失败关闭。",
    )
    figure_header(svg, "FIGURE 03", "单次在线 RAG 请求流程", "只有授权且 READY 的 Evidence 能进入 grounded generation")
    pill(svg, "success-chain-label", 60, 122, 150, "成功证据链", COLORS["success_soft"], COLORS["success"])
    pill(svg, "default-path-label", 1325, 122, 215, "frozen default · RRF", COLORS["primary_soft"], COLORS["primary"])

    group_panel(svg, "group-request-gate", 60, 170, 385, 355, "请求与授权门禁", COLORS["cyan"])
    group_panel(svg, "group-retrieval-fusion", 465, 170, 630, 355, "并行召回与融合", COLORS["primary"])
    group_panel(svg, "group-generation-gate", 1115, 170, 425, 355, "生成与引用门禁", COLORS["success"])

    card(svg, "pipeline-question", 90, 250, 130, 72, "用户问题", accent=COLORS["cyan"], center=True)
    card(svg, "pipeline-scope", 255, 250, 160, 72, "owner / scope 校验", accent=COLORS["cyan"], center=True, title_size=15)
    svg.diamond("pipeline-ready-diamond", 338, 415, 130, 86, fill=COLORS["surface"], stroke=COLORS["cyan"])
    svg.text("pipeline-ready-label", 338, 408, ["READY", "可见？"], size=16, weight=650, anchor="middle", line_height=20)
    svg.line("pipeline-edge-question-scope", 220, 286, 255, 286, color=COLORS["cyan"], marker="arrow-primary")
    svg.line("pipeline-edge-scope-ready", 338, 322, 338, 372, color=COLORS["cyan"], marker="arrow-primary")
    svg.text("pipeline-ready-yes", 410, 403, "是", size=12, weight=650, fill=COLORS["success"])

    card(svg, "pipeline-snapshot", 495, 352, 150, 76, "READY Chunk", "身份快照", accent=COLORS["primary"], center=True)
    card(svg, "pipeline-es", 680, 238, 145, 72, "Elasticsearch", "BM25 · Top-20", accent=COLORS["primary"])
    card(svg, "pipeline-milvus", 680, 408, 145, 72, "BGE-M3 → Milvus", "vector · Top-20", accent=COLORS["primary"], title_size=14)
    svg.diamond("pipeline-identity-diamond", 880, 360, 120, 84, fill=COLORS["surface"], stroke=COLORS["primary"])
    svg.text("pipeline-identity-label", 880, 354, ["候选身份", "重验"], size=15, weight=650, anchor="middle", line_height=19)
    card(svg, "pipeline-rrf", 945, 238, 120, 72, "RRF · k=60", "按名次融合", accent=COLORS["primary"], center=True, title_size=15)
    svg.diamond("pipeline-evidence-diamond", 1005, 435, 120, 84, fill=COLORS["success_soft"], stroke=COLORS["success"])
    svg.text("pipeline-evidence-label", 1005, 428, ["有效 Evidence", "Top-3？"], size=14, weight=650, anchor="middle", line_height=19)
    svg.line("pipeline-edge-ready-snapshot", 403, 415, 495, 390, color=COLORS["primary"], marker="arrow-primary")
    svg.path("pipeline-edge-snapshot-es", "M 645 376 H 660 V 274 H 680")
    svg.path("pipeline-edge-snapshot-milvus", "M 645 404 H 660 V 444 H 680")
    svg.path("pipeline-edge-es-identity", "M 825 274 H 850 V 338 H 860")
    svg.path("pipeline-edge-milvus-identity", "M 825 444 H 850 V 382 H 860")
    svg.path("pipeline-edge-identity-rrf", "M 930 344 H 940 V 274 H 945")
    svg.line("pipeline-edge-rrf-evidence", 1005, 310, 1005, 393)

    card(svg, "pipeline-qwen", 1145, 238, 150, 82, "Qwen3 14B", "grounded generation", accent=COLORS["success"], title_size=16)
    svg.diamond("pipeline-citation-diamond", 1218, 430, 135, 90, fill=COLORS["surface"], stroke=COLORS["success"])
    svg.text("pipeline-citation-label", 1218, 424, ["Citation", "验证"], size=16, weight=650, anchor="middle", line_height=20)
    card(svg, "pipeline-answer", 1350, 280, 160, 110, "Answer + Citation", ["+ Evidence", "document · page", "chunk · version"], accent=COLORS["success"], fill=COLORS["success_soft"], center=True, title_size=15)
    svg.path("pipeline-edge-evidence-qwen", "M 1065 435 H 1105 V 279 H 1145", color=COLORS["success"], marker="arrow-primary")
    svg.line("pipeline-edge-qwen-citation", 1218, 320, 1218, 385, color=COLORS["success"], marker="arrow-primary")
    svg.path("pipeline-edge-citation-answer", "M 1285 430 H 1325 V 335 H 1350", color=COLORS["success"], marker="arrow-primary")
    svg.text("pipeline-citation-pass", 1295, 416, "通过", size=12, weight=650, fill=COLORS["success"])
    pill(svg, "performance-boundary", 1315, 455, 195, "性能边界 · deferred", COLORS["warn_soft"], COLORS["warn"])
    svg.text("performance-value", 1412, 505, ["combined P95 ≈ 504.7 ms", "300 ms 未达成"], size=13, weight=550, fill=COLORS["warn"], anchor="middle", line_height=19)

    # Fail-closed output rail: three semantically distinct terminal states.
    pill(svg, "fail-closed-label", 60, 555, 165, "Fail-Closed 输出", COLORS["danger_soft"], COLORS["danger"])
    card(svg, "failure-403", 90, 620, 390, 130, "403 RAG_FORBIDDEN_SCOPE", ["未授权 / 未就绪 / 已失活", "不返回 stale Evidence"], accent=COLORS["danger"], fill=COLORS["danger_soft"], center=True, title_size=18)
    card(svg, "failure-no-evidence", 605, 620, 390, 130, "NO_EVIDENCE / 拒答", ["当前授权范围内证据不足", "不调用生成模型"], accent=COLORS["warn"], fill=COLORS["warn_soft"], center=True, title_size=19)
    card(svg, "failure-degraded", 1120, 620, 390, 130, "DEGRADED / 保留证据卡", ["生成或引用门禁失败", "只保留已授权 Evidence"], accent=COLORS["danger"], fill=COLORS["danger_soft"], center=True, title_size=18)
    svg.path("failure-edge-ready-403", "M 338 458 V 560 H 285 V 620", color=COLORS["danger"], marker="arrow-danger", dash="7 6")
    svg.text("failure-ready-no", 350, 492, "否", size=12, weight=650, fill=COLORS["danger"])
    svg.path("failure-edge-identity-403", "M 880 402 V 590 H 430 V 620", color=COLORS["danger"], marker="arrow-danger", dash="7 6")
    svg.path("failure-edge-no-evidence", "M 1005 477 V 570 H 800 V 620", color=COLORS["warn"], marker="arrow-danger", dash="7 6")
    svg.text("failure-evidence-no", 1018, 505, "0 条", size=12, weight=650, fill=COLORS["warn"])
    svg.path("failure-edge-degraded", "M 1218 475 V 570 H 1315 V 620", color=COLORS["danger"], marker="arrow-danger", dash="7 6")
    svg.text("failure-citation-no", 1230, 505, "失败", size=12, weight=650, fill=COLORS["danger"])

    svg.text("pipeline-footer", 800, 815, "403 ≠ NO_EVIDENCE ≠ DEGRADED · 成功与失败终点不合并 · 默认路径无 Reranker", size=15, weight=550, fill=COLORS["muted"], anchor="middle")
    svg.text("pipeline-caption", 800, 857, "owner / READY 前置约束，候选身份后置重验；Citation 合法不等于语义判真", size=13, weight=430, fill=COLORS["muted"], anchor="middle")
    return svg.finish("Spec: 03-online-rag-pipeline.spec.md; Evidence: VISUAL_EVIDENCE_LEDGER.md 03-E01..03-E15")


def render_06() -> str:
    svg = SVG(
        "figure-06-multi-evidence",
        "多证据 Claim–Evidence 审计",
        "脱敏结构展示 Answer 到 Claim、Citation、Evidence 和确定性 EvidenceSet 审计的绑定关系。",
    )
    figure_header(svg, "FIGURE 06", "多证据 Claim–Evidence 审计", "回答可拆、引用可回溯、审计可记录；不自动语义裁决")
    pill(svg, "redacted-example", 60, 122, 460, "冻结 Competition 场景的脱敏结构示意 · 非逐字回答 · 非原文引文", COLORS["primary_soft"], COLORS["primary"])
    pill(svg, "windows-proof", 1100, 122, 440, "Windows Gate 已观测 · 1 Claim → 2 Citations → 2 Chunks", COLORS["success_soft"], COLORS["success"])

    group_panel(svg, "group-answer-claims", 60, 170, 480, 465, "Answer 与结构化 Claims", COLORS["primary"])
    group_panel(svg, "group-citations", 560, 170, 300, 465, "Citation 绑定", COLORS["audit"])
    group_panel(svg, "group-evidence-units", 880, 170, 660, 465, "已授权 Evidence units", COLORS["cyan"])

    card(svg, "multi-answer", 95, 220, 150, 64, "Answer", "结构化 Claims", accent=COLORS["primary"], center=True)
    card(svg, "claim-a", 95, 320, 330, 74, "Claim A", "内容感知 token surprisal", accent=COLORS["primary"], shadow=False)
    card(svg, "claim-b", 95, 425, 400, 96, "Claim B · 多证据", "内容感知 + 态势感知 + 尾部聚合", accent=COLORS["success"], fill=COLORS["success_soft"], title_size=20)
    card(svg, "claim-c", 95, 552, 330, 64, "Claim C", "重复 / 连贯性缺口", accent=COLORS["primary"], shadow=False)
    svg.path("contains-claim-a", "M 170 284 V 300 H 260 V 320", color=COLORS["muted"], marker="arrow-muted", sw=1.8)
    svg.path("contains-claim-b", "M 200 284 V 414 H 295 V 425", color=COLORS["primary"], marker="arrow-primary")
    svg.path("contains-claim-c", "M 230 284 V 542 H 260 V 552", color=COLORS["muted"], marker="arrow-muted", sw=1.8)

    card(svg, "citation-1", 610, 288, 200, 76, "Citation 1", "请求内 Evidence 位置 1", accent=COLORS["audit"], fill=COLORS["audit_soft"], center=True)
    card(svg, "citation-2", 610, 474, 200, 76, "Citation 2", "请求内 Evidence 位置 2", accent=COLORS["audit"], fill=COLORS["audit_soft"], center=True)
    svg.path("claim-a-citation-1", "M 425 357 H 610", color=COLORS["audit"], marker="arrow-audit", sw=1.7, opacity=0.55)
    svg.path("claim-b-citation-1", "M 495 453 H 550 V 326 H 610", color=COLORS["audit"], marker="arrow-audit", sw=3.2)
    svg.path("claim-b-citation-2", "M 495 489 H 550 V 512 H 610", color=COLORS["audit"], marker="arrow-audit", sw=3.2)
    svg.path("claim-c-citation-2", "M 425 584 H 565 V 530 H 610", color=COLORS["audit"], marker="arrow-audit", sw=1.7, opacity=0.55)

    card(svg, "evidence-1", 930, 250, 530, 110, "Evidence 1 · Chunk α", ["概念摘录：token surprisal / repetition", "已授权 · 请求内 Evidence"], accent=COLORS["cyan"], fill=COLORS["cyan_soft"], title_size=19)
    card(svg, "evidence-2", 930, 440, 530, 110, "Evidence 2 · Chunk β", ["概念摘录：coherence gaps / tail-focused aggregation", "已授权 · 请求内 Evidence"], accent=COLORS["cyan"], fill=COLORS["cyan_soft"], title_size=19)
    card(svg, "evidence-identity", 1000, 575, 390, 46, "document · page · chunk · version", accent=COLORS["cyan"], shadow=False, center=True, title_size=14)
    svg.line("citation-1-evidence-1", 810, 326, 930, 305, color=COLORS["audit"], marker="arrow-audit", sw=3)
    svg.line("citation-2-evidence-2", 810, 512, 930, 495, color=COLORS["audit"], marker="arrow-audit", sw=3)
    svg.path("evidence-1-identity", "M 1195 360 V 575", color=COLORS["cyan"], marker="arrow-muted", sw=1.5, dash="5 6", opacity=0.7)
    svg.path("evidence-2-identity", "M 1285 550 V 565 H 1285 V 575", color=COLORS["cyan"], marker="arrow-muted", sw=1.5, dash="5 6", opacity=0.7)

    # Deterministic audit rail.
    svg.start("group-evidence-audit", "EvidenceSet deterministic audit")
    svg.rect("audit-rail-bg", 60, 660, 1480, 175, fill=COLORS["surface"], stroke=COLORS["audit"], sw=1.5, radius=22, shadow=True)
    svg.text("audit-rail-title", 90, 695, "EvidenceSet deterministic audit", size=17, weight=650, fill=COLORS["audit"])
    card(svg, "audit-identity", 90, 720, 285, 80, "① 身份检查", "owner · active version · chunk · citation", accent=COLORS["audit"], fill=COLORS["audit_soft"], shadow=False)
    card(svg, "audit-support", 420, 720, 380, 80, "② 确定性支持检查", "数字 / 单位 · 比较 · 限定 · 冲突 · 核心重合", accent=COLORS["audit"], fill=COLORS["audit_soft"], shadow=False)
    card(svg, "audit-state", 845, 720, 285, 80, "③ 状态记录", "支持 · 部分支持 · 冲突 · 证据不足", accent=COLORS["audit"], fill=COLORS["audit_soft"], shadow=False)
    card(svg, "audit-boundary", 1175, 704, 330, 112, "EvidenceSet = AUDIT_ONLY", ["审计，不自动裁决", "非人工语义 Gold · 无新 Judge", "不自动删 Claim"], accent=COLORS["audit"], fill=COLORS["audit_soft"], shadow=False, center=True, title_size=18)
    svg.line("audit-edge-1-2", 375, 760, 420, 760, color=COLORS["audit"], marker="arrow-audit")
    svg.line("audit-edge-2-3", 800, 760, 845, 760, color=COLORS["audit"], marker="arrow-audit")
    svg.line("audit-edge-3-4", 1130, 760, 1175, 760, color=COLORS["audit"], marker="arrow-audit")
    svg.end()
    svg.path("binding-to-audit", "M 295 521 V 645 H 232 V 720", color=COLORS["audit"], marker="arrow-audit", dash="6 6", sw=1.7)
    svg.path("identity-to-audit", "M 1195 621 V 645 H 300 V 720", color=COLORS["audit"], marker="arrow-audit", dash="6 6", sw=1.7)
    svg.text("multi-footer", 800, 867, "2 + 2 表示已观测的脱敏绑定结构；Chunk α/β 不是私有 ID，也不是原文摘录", size=13, weight=450, fill=COLORS["muted"], anchor="middle")
    return svg.finish("Spec: 06-multi-evidence.spec.md; Evidence: VISUAL_EVIDENCE_LEDGER.md 06-E01..06-E13")


def result_card_title(svg: SVG, element_id: str, x: float, y: float, title: str, accent: str) -> None:
    svg.text(element_id, x, y, title, size=17, weight=650, fill=accent)


def render_08() -> str:
    svg = SVG(
        "figure-08-key-evaluation-results",
        "冻结 baseline 的关键验证与负向决策",
        "四个证据块呈现真实复现、Citation 可靠性、负向排序实验和 clean-checkout 可复现性，并公开性能债。",
    )
    figure_header(svg, "FIGURE 08", "关键验证、证伪与已知限制", "真实复现 + 独立回放 + 负向决策 + clean-checkout CI")

    # 2x2 proof cards.
    svg.rect("result-card-a", 60, 130, 720, 245, fill=COLORS["surface"], stroke=COLORS["line"], radius=22, shadow=True)
    svg.rect("result-card-a-accent", 60, 130, 8, 245, fill=COLORS["success"], stroke=COLORS["success"], sw=0, radius=4)
    result_card_title(svg, "result-title-a", 90, 168, "A · Windows 真实复现", COLORS["success"])
    svg.text("result-a-metric", 100, 245, "3 / 3", size=58, weight=700, fill=COLORS["success"])
    svg.text("result-a-pass", 280, 242, "PASS", size=24, weight=700, fill=COLORS["success"])
    svg.text("result-a-scope", 100, 274, "仅限冻结 Competition 三场景", size=13, weight=500, fill=COLORS["muted"])
    pill(svg, "scenario-evidence-qa", 395, 190, 320, "Evidence QA · PASS", COLORS["success_soft"], COLORS["success"])
    pill(svg, "scenario-multi-evidence", 395, 238, 320, "Multi-Evidence Audit · PASS · AUDIT_ONLY", COLORS["audit_soft"], COLORS["audit"])
    pill(svg, "scenario-fail-closed", 395, 286, 320, "Fail-Closed · PASS", COLORS["success_soft"], COLORS["success"])
    svg.text("result-a-cleanup", 395, 346, "cleanup 3/3 · 403 · no stale Evidence", size=14, weight=550, fill=COLORS["ink"])

    svg.rect("result-card-b", 820, 130, 720, 245, fill=COLORS["surface"], stroke=COLORS["line"], radius=22, shadow=True)
    svg.rect("result-card-b-accent", 820, 130, 8, 245, fill=COLORS["primary"], stroke=COLORS["primary"], sw=0, radius=4)
    result_card_title(svg, "result-title-b", 850, 168, "B · Citation / Evidence 可靠性", COLORS["primary"])
    svg.text("result-b-metric", 860, 230, "2", size=54, weight=700, fill=COLORS["primary"])
    svg.text("result-b-label", 915, 220, ["个真实问题", "COMPLETED"], size=19, weight=650, fill=COLORS["ink"], line_height=25)
    svg.text("result-b-evidence", 860, 275, "每题 3 条 Evidence", size=15, weight=550, fill=COLORS["muted"])
    pill(svg, "citation-id-pass", 1120, 190, 355, "Citation / Evidence / 页码身份 · PASS", COLORS["primary_soft"], COLORS["primary"])
    pill(svg, "generation-replay-pass", 1120, 238, 355, "generation replay · PASS", COLORS["success_soft"], COLORS["success"])
    pill(svg, "byte-replay-pass", 1120, 286, 355, "byte-stable replay · PASS", COLORS["success_soft"], COLORS["success"])
    svg.text("result-b-boundary", 860, 346, "本次两个真实问题的观测结果，不外推永久保证", size=13, weight=450, fill=COLORS["muted"])

    svg.rect("result-card-c", 60, 395, 720, 245, fill=COLORS["surface"], stroke=COLORS["line"], radius=22, shadow=True)
    svg.rect("result-card-c-accent", 60, 395, 8, 245, fill=COLORS["warn"], stroke=COLORS["warn"], sw=0, radius=4)
    result_card_title(svg, "result-title-c", 90, 433, "C · 排序实验：证伪后停止", COLORS["warn"])
    card(svg, "top20-result", 90, 460, 235, 105, "Fixed BGE · Top-20", "0 / 3 bilateral Top-3 recovery", accent=COLORS["warn"], fill=COLORS["warn_soft"], shadow=False, center=True, title_size=15)
    card(svg, "top50-result", 350, 460, 235, 105, "Fixed BGE · Top-50", "0 / 3 bilateral Top-3 recovery", accent=COLORS["warn"], fill=COLORS["warn_soft"], shadow=False, center=True, title_size=15)
    card(svg, "screening-decision", 610, 452, 140, 121, "SCREENING_", ["WEAKENED", "冻结失败集"], accent=COLORS["danger"], fill=COLORS["danger_soft"], shadow=False, center=True, title_size=13)
    svg.path("result-edge-top20-decision", "M 325 565 V 580 H 600 V 490 H 610", color=COLORS["warn"], marker="arrow-danger", sw=1.8)
    svg.path("result-edge-top50-decision", "M 585 565 V 580 H 600 V 545 H 610", color=COLORS["warn"], marker="arrow-danger", sw=1.8)
    svg.text("result-c-decision", 90, 607, "保留默认 RRF · Phase 3 optimization STOP", size=17, weight=650, fill=COLORS["ink"])

    svg.rect("result-card-d", 820, 395, 720, 245, fill=COLORS["surface"], stroke=COLORS["line"], radius=22, shadow=True)
    svg.rect("result-card-d-accent", 820, 395, 8, 245, fill=COLORS["audit"], stroke=COLORS["audit"], sw=0, radius=4)
    result_card_title(svg, "result-title-d", 850, 433, "D · Clean-checkout 可复现性", COLORS["audit"])
    svg.text("result-d-ci", 860, 505, "make test", size=34, weight=700, fill=COLORS["ink"])
    pill(svg, "result-d-pass", 860, 530, 190, "PASS", COLORS["success_soft"], COLORS["success"])
    svg.text("result-d-errors", 1120, 515, "14 → 0", size=42, weight=700, fill=COLORS["audit"])
    svg.text("result-d-errors-label", 1120, 547, "clean-checkout runtime/path errors", size=13, weight=500, fill=COLORS["muted"])
    svg.text("result-d-env", 860, 592, "GitHub clean checkout · Ubuntu 24.04 · CPython 3.11.15", size=14, weight=550, fill=COLORS["ink"])
    svg.text("result-d-head", 860, 616, "exact submission head · fd5a517", size=13, weight=500, fill=COLORS["muted"])

    # Known limitation rail.
    svg.start("known-limitation", "Known limitation")
    svg.rect("known-limitation-bg", 60, 665, 1480, 105, fill=COLORS["warn_soft"], stroke=COLORS["warn"], sw=1.5, radius=20)
    svg.text("known-limitation-title", 90, 698, "E · Known limitation", size=16, weight=700, fill=COLORS["warn"])
    svg.text("known-limitation-actual", 90, 744, "combined P95 ≈ 504.7 ms", size=27, weight=700, fill=COLORS["ink"])
    svg.text("known-limitation-compare", 460, 741, ">", size=30, weight=700, fill=COLORS["danger"])
    svg.text("known-limitation-target", 510, 744, "目标 300 ms · 未达成 / deferred", size=22, weight=700, fill=COLORS["danger"])
    svg.text("known-limitation-phases", 950, 711, "Phase 3 · PARTIAL / NO_PROMOTION", size=14, weight=600, fill=COLORS["ink"])
    svg.text("known-limitation-phase4", 950, 738, "Phase 4 · PARTIAL / AUDIT_ONLY", size=14, weight=600, fill=COLORS["ink"])
    svg.text("known-limitation-production", 950, 762, "800–1500 Acceptance 未完成 · 不声称 production ready", size=13, weight=550, fill=COLORS["danger"])
    svg.end()

    # Provenance rail keeps the three identities separate.
    svg.start("evidence-provenance", "证据谱系")
    svg.text("provenance-title", 60, 812, "证据谱系", size=14, weight=700, fill=COLORS["muted"])
    pill(svg, "provenance-windows", 175, 790, 270, "Windows source · d775dab", COLORS["cyan_soft"], COLORS["cyan"])
    pill(svg, "provenance-equivalence", 500, 790, 255, "runtime equivalence · PASS", COLORS["success_soft"], COLORS["success"])
    pill(svg, "provenance-submission", 810, 790, 270, "submission head · fd5a517", COLORS["primary_soft"], COLORS["primary"])
    pill(svg, "provenance-authority", 1135, 790, 270, "frozen authority · 038df52", COLORS["audit_soft"], COLORS["audit"])
    svg.line("provenance-edge-1", 445, 807, 500, 807, color=COLORS["muted"], marker="arrow-muted", sw=1.5)
    svg.line("provenance-edge-2", 755, 807, 810, 807, color=COLORS["muted"], marker="arrow-muted", sw=1.5)
    svg.line("provenance-edge-3", 1080, 807, 1135, 807, color=COLORS["muted"], marker="arrow-muted", sw=1.5)
    svg.end()
    svg.text("results-footer", 800, 866, "3/3 仅指冻结三场景 · 两个 0/3 仅指现有 fixed reranker family 与冻结失败集", size=13, weight=500, fill=COLORS["muted"], anchor="middle")
    return svg.finish("Spec: 08-key-evaluation-results.spec.md; Evidence: VISUAL_EVIDENCE_LEDGER.md 08-E01..08-E16")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figures = {
        "01-system-architecture.svg": render_01(),
        "03-online-rag-pipeline.svg": render_03(),
        "06-multi-evidence.svg": render_06(),
        "08-key-evaluation-results.svg": render_08(),
    }
    for filename, content in figures.items():
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8", newline="\n")
        print(f"rendered {OUTPUT_DIR / filename}")


if __name__ == "__main__":
    main()
