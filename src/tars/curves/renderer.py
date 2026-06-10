from __future__ import annotations

import json
from pathlib import Path

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 20) -> str:
    if not values:
        return ""
    mn, mx = min(values), max(values)
    span = mx - mn if mx != mn else 1.0
    chars = []
    step = max(len(values) // width, 1)
    sampled = values[::step][:width]
    for v in sampled:
        idx = int((v - mn) / span * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    return "".join(chars)


def trend_arrow(delta: float | None) -> str:
    if delta is None:
        return ""
    if delta > 0.01:
        return "↑"
    if delta < -0.01:
        return "↓"
    return "→"


class CurveRenderer:
    def __init__(self, snapshots: list[dict]) -> None:
        self.snapshots = sorted(snapshots, key=lambda s: s.get("period_label", ""))

    def to_terminal(self) -> str:
        if not self.snapshots:
            return "No improvement data yet. Complete some tasks first."

        rates = [s.get("success_rate", 0) for s in self.snapshots]
        scores = [s.get("growth_score", 0) for s in self.snapshots]
        latest = self.snapshots[-1]
        delta = latest.get("delta_success_rate")
        arrow = trend_arrow(delta)

        lines = [
            "TARS Improvement Curves",
            "",
            f"  Success Rate: {sparkline(rates)}  {rates[-1]:.0%} {arrow}",
            f"  Growth Score: {sparkline(scores)}  {scores[-1]:.0f}/100",
            "",
            f"  Episodes: {latest.get('total_episodes', 0)}",
            f"  Active Lessons: {latest.get('active_lessons', 0)}",
            f"  Avg Confidence: {latest.get('avg_confidence', 0):.0%}",
            f"  Cost/Task: ₹{latest.get('cost_per_task', 0):.2f}",
        ]

        if delta is not None:
            pct = delta * 100
            sign = "+" if pct >= 0 else ""
            lines.append(f"  Trend: {sign}{pct:.1f}pp {arrow}")

        return "\n".join(lines)

    def to_svg(self, width: int = 480, height: int = 120) -> str:
        rates = [s.get("success_rate", 0) for s in self.snapshots]
        latest = self.snapshots[-1] if self.snapshots else {}
        delta = latest.get("delta_success_rate")
        delta_pct = (delta * 100) if delta else 0
        arrow = trend_arrow(delta)
        sign = "+" if delta_pct >= 0 else ""

        spark = sparkline(rates, width=30)
        first_rate = rates[0] if rates else 0
        last_rate = rates[-1] if rates else 0

        bg = "#1a1b2e"
        accent = "#22d3ee"
        text_color = "#e2e8f0"
        dim_color = "#94a3b8"

        lessons = latest.get("total_lessons", 0)
        active = latest.get("active_lessons", 0)
        font = "monospace"
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg"'
            f' width="{width}" height="{height}"'
            f' viewBox="0 0 {width} {height}">',
            f'  <rect width="{width}" height="{height}" rx="8" fill="{bg}"/>',
            f'  <text x="20" y="30" fill="{accent}"'
            f' font-family="{font}" font-size="16"'
            f' font-weight="bold">TARS</text>',
            f'  <text x="70" y="30" fill="{text_color}"'
            f' font-family="{font}" font-size="14">'
            f'{sign}{delta_pct:.0f}% {arrow} improvement</text>',
            f'  <text x="20" y="60" fill="{accent}"'
            f' font-family="{font}" font-size="24">'
            f'{spark}</text>',
            f'  <text x="20" y="85" fill="{dim_color}"'
            f' font-family="{font}" font-size="12">'
            f'Start: {first_rate:.0%} → Now: {last_rate:.0%}</text>',
            f'  <text x="20" y="105" fill="{dim_color}"'
            f' font-family="{font}" font-size="12">'
            f'{lessons} lessons | {active} active</text>',
            "</svg>",
        ]
        return "\n".join(lines)

    def to_badge(self) -> str:
        latest = self.snapshots[-1] if self.snapshots else {}
        score = latest.get("growth_score", 0)
        if score >= 80:
            color = "brightgreen"
        elif score >= 60:
            color = "green"
        elif score >= 40:
            color = "yellow"
        else:
            color = "red"

        label = "TARS+growth"
        value = f"{score:.0f}%2F100"
        return f"https://img.shields.io/badge/{label}-{value}-{color}"

    def to_json(self) -> str:
        return json.dumps(
            {
                "snapshots": self.snapshots,
                "latest": self.snapshots[-1] if self.snapshots else None,
                "sparkline_success": sparkline(
                    [s.get("success_rate", 0) for s in self.snapshots]
                ),
                "sparkline_growth": sparkline(
                    [s.get("growth_score", 0) for s in self.snapshots]
                ),
            },
            indent=2,
            default=str,
        )

    def save_svg(self, output_dir: Path, filename: str = "tars-improvement.svg") -> Path:
        path = output_dir / filename
        path.write_text(self.to_svg(), encoding="utf-8")
        return path
