"""Vector figures and LaTeX inserts for the FSO confirmation study."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from capme.pdf_fonts import PDF_FONT_BOLD, PDF_FONT_REGULAR, register_pdf_fonts


register_pdf_fonts()


CANONICAL_FSO = "fso_no_feedback"
FEEDBACK_ENABLED_FSO = "fso"

STRATEGY_LABELS = {
    "direct_only": "Direct only",
    "fixed_only": "Fixed proxy only",
    "generated_only": "Generated only",
    "ephemeral_only": "Ephemeral only",
    "random_failover": "Random failover",
    "performance_only": "Performance only",
    "session_failover": "Session failover",
    "deadline_cost_failover": "Deadline/cost baseline",
    "fso": "Feedback enabled",
    "fso_fixed_code": "FSO fixed code",
    "fso_no_semantics": "No semantics",
    "fso_no_diversity": "No diversity",
    "fso_no_feedback": "FSO",
    "fso_no_redundancy": "No redundancy",
}

FUNCTION_LABELS = {
    "text": "Text",
    "presence": "Presence",
    "media": "Media",
    "file": "File",
    "realtime": "Real-time",
}

BLUE = colors.HexColor("#087DBB")
GREEN = colors.HexColor("#009E73")
ORANGE = colors.HexColor("#E69F00")
MAGENTA = colors.HexColor("#CC79A7")
GREY = colors.HexColor("#6C757D")
DARK = colors.HexColor("#252525")
GRID = colors.HexColor("#D8D8D8")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _linear(value: float, low: float, high: float, start: float, span: float) -> float:
    return start + span * (value - low) / (high - low)


def _base(c: canvas.Canvas, title: str, subtitle: str) -> None:
    c.setTitle(title)
    c.setFillColor(DARK)
    c.setFont(PDF_FONT_BOLD, 11)
    c.drawString(52, 286, title)
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont(PDF_FONT_REGULAR, 7.5)
    c.drawString(52, 274, subtitle)


def tradeoff_figure(rows: list[dict[str, str]], output: Path) -> None:
    """Plot availability against bytes sent per payload byte."""

    output.parent.mkdir(parents=True, exist_ok=True)
    selected = {
        "generated_only",
        "ephemeral_only",
        "random_failover",
        "session_failover",
        "deadline_cost_failover",
        CANONICAL_FSO,
        "fso_fixed_code",
        "fso_no_semantics",
        "fso_no_redundancy",
    }
    points = [row for row in rows if row["strategy"] in selected]
    width, height = 540, 310
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    _base(
        c,
        "Availability--overhead trade-off on the independent confirmation seeds",
        "Adaptive mobile trace replay; means across 20 disjoint synthetic seeds; lower overhead and higher AUAC are preferable",
    )
    left, bottom, plot_width, plot_height = 58, 50, 448, 194
    x_low, x_high = 0.95, 2.06
    y_low, y_high = 0.68, 0.945

    c.setStrokeColor(DARK)
    c.setLineWidth(0.8)
    c.line(left, bottom, left + plot_width, bottom)
    c.line(left, bottom, left, bottom + plot_height)
    c.setFont(PDF_FONT_REGULAR, 7.5)
    for tick in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0):
        x = _linear(tick, x_low, x_high, left, plot_width)
        c.setStrokeColor(GRID)
        c.setLineWidth(0.35)
        c.line(x, bottom, x, bottom + plot_height)
        c.setFillColor(DARK)
        c.drawCentredString(x, bottom - 13, f"{tick:.1f}")
    for tick in (0.70, 0.75, 0.80, 0.85, 0.90, 0.94):
        y = _linear(tick, y_low, y_high, bottom, plot_height)
        c.setStrokeColor(GRID)
        c.setLineWidth(0.35)
        c.line(left, y, left + plot_width, y)
        c.setFillColor(DARK)
        c.drawRightString(left - 5, y - 2.5, f"{tick:.2f}")

    c.setFont(PDF_FONT_REGULAR, 7.2)
    label_offsets = {
        CANONICAL_FSO: (8, 6),
        "deadline_cost_failover": (-105, -12),
        "session_failover": (8, -11),
        "fso_no_semantics": (-84, 7),
        "fso_fixed_code": (8, 6),
        "fso_no_redundancy": (8, -12),
        "generated_only": (8, 5),
        "ephemeral_only": (8, -11),
        "random_failover": (8, 5),
    }
    for row in points:
        strategy = row["strategy"]
        overhead = float(row["byte_overhead"])
        auac = float(row["auac"])
        x = _linear(overhead, x_low, x_high, left, plot_width)
        y = _linear(auac, y_low, y_high, bottom, plot_height)
        fill = BLUE if strategy == CANONICAL_FSO else (ORANGE if strategy == "fso_no_semantics" else GREY)
        radius = 5.4 if strategy == CANONICAL_FSO else 3.8
        c.setFillColor(fill)
        c.setStrokeColor(DARK)
        c.circle(x, y, radius, fill=1, stroke=1)
        dx, dy = label_offsets[strategy]
        c.setFillColor(DARK)
        c.drawString(x + dx, y + dy, STRATEGY_LABELS[strategy])

    c.setFillColor(DARK)
    c.setFont(PDF_FONT_REGULAR, 8)
    c.drawCentredString(left + plot_width / 2, 18, "Bytes transmitted per payload byte")
    c.saveState()
    c.translate(15, bottom + plot_height / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "Area under availability curve (AUAC)")
    c.restoreState()
    c.showPage()
    c.save()


def function_figure(rows: list[dict[str, str]], output: Path) -> None:
    """Compare the full mechanism with the strongest and simplest baselines."""

    output.parent.mkdir(parents=True, exist_ok=True)
    by_strategy = {row["strategy"]: row for row in rows}
    width, height = 540, 310
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    _base(
        c,
        "Function-specific survival reveals where FSO changes delivery",
        "Adaptive mobile trace replay; AUAC means across 20 independent confirmation seeds",
    )
    left, bottom, plot_width, plot_height = 55, 62, 455, 190
    c.setStrokeColor(DARK)
    c.line(left, bottom, left, bottom + plot_height)
    c.line(left, bottom, left + plot_width, bottom)
    for tick in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        y = bottom + plot_height * tick
        c.setStrokeColor(GRID)
        c.setLineWidth(0.35)
        c.line(left, y, left + plot_width, y)
        c.setFillColor(DARK)
        c.setFont(PDF_FONT_REGULAR, 7.5)
        c.drawRightString(left - 5, y - 2.5, f"{tick:.1f}")

    strategies = (
        CANONICAL_FSO,
        "deadline_cost_failover",
        "session_failover",
        "generated_only",
    )
    fills = (BLUE, MAGENTA, GREEN, GREY)
    functions = tuple(FUNCTION_LABELS)
    group_width = plot_width / len(functions)
    bar_width = 18
    for function_index, function in enumerate(functions):
        center = left + group_width * (function_index + 0.5)
        for strategy_index, (strategy, fill) in enumerate(zip(strategies, fills, strict=True)):
            value = float(by_strategy[strategy][f"auac_{function}"])
            x = center + (strategy_index - 1.5) * (bar_width + 1) - bar_width / 2
            c.setFillColor(fill)
            c.setStrokeColor(DARK)
            c.setLineWidth(0.35)
            c.rect(x, bottom, bar_width, plot_height * value, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont(PDF_FONT_REGULAR, 7.5)
        c.drawCentredString(center, bottom - 14, FUNCTION_LABELS[function])

    legend_x = 64
    for strategy, fill in zip(strategies, fills, strict=True):
        c.setFillColor(fill)
        c.rect(legend_x, 266, 10, 7, fill=1, stroke=0)
        c.setFillColor(DARK)
        c.setFont(PDF_FONT_REGULAR, 7.4)
        c.drawString(legend_x + 14, 265, STRATEGY_LABELS[strategy])
        legend_x += 112
    c.saveState()
    c.translate(15, bottom + plot_height / 2)
    c.rotate(90)
    c.setFillColor(DARK)
    c.setFont(PDF_FONT_REGULAR, 8)
    c.drawCentredString(0, 0, "Function AUAC")
    c.restoreState()
    c.showPage()
    c.save()


def ablation_figure(rows: list[dict[str, str]], output: Path) -> None:
    """Show availability and overhead together for the mechanism ablations."""

    output.parent.mkdir(parents=True, exist_ok=True)
    by_strategy = {row["strategy"]: row for row in rows}
    order = (
        CANONICAL_FSO,
        FEEDBACK_ENABLED_FSO,
        "fso_fixed_code",
        "fso_no_diversity",
        "fso_no_redundancy",
        "fso_no_semantics",
    )
    width, height = 540, 315
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    _base(
        c,
        "Ablations expose gains, costs, and a negative feedback result",
        "Bars: AUAC (left axis); points: bytes per payload byte (right axis); 20 independent confirmation seeds",
    )
    left, bottom, plot_width, plot_height = 62, 76, 434, 172
    c.setStrokeColor(DARK)
    c.line(left, bottom, left, bottom + plot_height)
    c.line(left + plot_width, bottom, left + plot_width, bottom + plot_height)
    c.line(left, bottom, left + plot_width, bottom)
    for tick in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        y = bottom + plot_height * tick
        c.setStrokeColor(GRID)
        c.setLineWidth(0.35)
        c.line(left, y, left + plot_width, y)
        c.setFillColor(DARK)
        c.setFont(PDF_FONT_REGULAR, 7.2)
        c.drawRightString(left - 5, y - 2.5, f"{tick:.1f}")
        c.drawString(left + plot_width + 5, y - 2.5, f"{1.0 + tick:.1f}")

    group_width = plot_width / len(order)
    for index, strategy in enumerate(order):
        row = by_strategy[strategy]
        center = left + group_width * (index + 0.5)
        auac = float(row["auac"])
        overhead = float(row["byte_overhead"])
        fill = BLUE if strategy == CANONICAL_FSO else GREY
        c.setFillColor(fill)
        c.setStrokeColor(DARK)
        c.setLineWidth(0.35)
        c.rect(center - 13, bottom, 26, plot_height * auac, fill=1, stroke=1)
        overhead_y = bottom + plot_height * (overhead - 1.0)
        c.setFillColor(ORANGE)
        c.circle(center, overhead_y, 3.6, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont(PDF_FONT_REGULAR, 6.4)
        short_label = {
            CANONICAL_FSO: "FSO",
            FEEDBACK_ENABLED_FSO: "Feedback on",
            "fso_fixed_code": "Fixed code",
            "fso_no_diversity": "No diversity",
            "fso_no_redundancy": "No redundancy",
            "fso_no_semantics": "No semantics",
        }[strategy]
        c.drawCentredString(center, bottom - 13, short_label)

    c.saveState()
    c.translate(16, bottom + plot_height / 2)
    c.rotate(90)
    c.setFillColor(DARK)
    c.setFont(PDF_FONT_REGULAR, 7.6)
    c.drawCentredString(0, 0, "AUAC")
    c.restoreState()
    c.saveState()
    c.translate(530, bottom + plot_height / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "Byte overhead")
    c.restoreState()
    c.showPage()
    c.save()


def _ci(row: dict[str, str], key: str, digits: int = 3) -> str:
    value = float(row[key])
    low = float(row[f"{key}_ci_low"])
    high = float(row[f"{key}_ci_high"])
    return f"{value:.{digits}f} [{low:.{digits}f}, {high:.{digits}f}]"


def _tex_label(value: str) -> str:
    return value.replace("--", "-").replace("%", r"\%")


def write_tables(rows: list[dict[str, str]], contrasts: list[dict[str, str]], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    by_strategy = {row["strategy"]: row for row in rows}
    by_baseline = {row["baseline"]: row for row in contrasts}

    main_order = (
        CANONICAL_FSO,
        "deadline_cost_failover",
        "session_failover",
        "generated_only",
        "ephemeral_only",
        "random_failover",
    )
    main_lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Strategy & AUAC [95\% CI] & Byte overhead & Mean ms & $T_{50}$ \\",
        r"\midrule",
    ]
    for strategy in main_order:
        row = by_strategy[strategy]
        main_lines.append(
            f"{_tex_label(STRATEGY_LABELS[strategy])} & {_ci(row, 'auac')} & "
            f"{float(row['byte_overhead']):.3f} & {float(row['mean_completion_ms']):.0f} & "
            f"{float(row['t50']):.1f} \\\\"
        )
    main_lines.extend((r"\bottomrule", r"\end{tabular}", ""))
    (output / "fso_main_results.tex").write_text("\n".join(main_lines), encoding="utf-8")

    function_lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Function & FSO & Deadline/cost & Session failover & Generated only \\",
        r"\midrule",
    ]
    for function, label in FUNCTION_LABELS.items():
        function_lines.append(
            f"{label} & {float(by_strategy[CANONICAL_FSO][f'auac_{function}']):.3f} & "
            f"{float(by_strategy['deadline_cost_failover'][f'auac_{function}']):.3f} & "
            f"{float(by_strategy['session_failover'][f'auac_{function}']):.3f} & "
            f"{float(by_strategy['generated_only'][f'auac_{function}']):.3f} \\\\"
        )
    function_lines.extend((r"\bottomrule", r"\end{tabular}", ""))
    (output / "fso_function_results.tex").write_text(
        "\n".join(function_lines), encoding="utf-8"
    )

    ablation_order = (
        CANONICAL_FSO,
        FEEDBACK_ENABLED_FSO,
        "fso_fixed_code",
        "fso_no_diversity",
        "fso_no_redundancy",
        "fso_no_semantics",
    )
    ablation_lines = [
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Variant & AUAC [95\% CI] & FSO minus variant & Byte overhead \\",
        r"\midrule",
    ]
    for strategy in ablation_order:
        row = by_strategy[strategy]
        difference = (
            0.0
            if strategy == CANONICAL_FSO
            else float(by_baseline[strategy]["mean_difference"])
        )
        ablation_lines.append(
            f"{_tex_label(STRATEGY_LABELS[strategy])} & {_ci(row, 'auac')} & "
            f"{difference:+.3f} & {float(row['byte_overhead']):.3f} \\\\"
        )
    ablation_lines.extend((r"\bottomrule", r"\end{tabular}", ""))
    (output / "fso_ablation_results.tex").write_text(
        "\n".join(ablation_lines), encoding="utf-8"
    )


def write_lab_table(lab: dict[str, object], output: Path) -> None:
    lines = [
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Failure-injection phase & Operation availability \\",
        r"\midrule",
    ]
    for phase in lab["phases"]:
        availability = lab["phase_availability"][phase]
        label = str(phase).replace("-", " ").title().replace("Ack", "ACK")
        lines.append(f"{label} & {float(availability):.3f} \\\\")
    lines.extend(
        (
            r"\midrule",
            f"Overall & {float(lab['availability']):.3f} \\\\",
            r"\bottomrule",
            r"\end{tabular}",
            "",
        )
    )
    (output / "fso_lab_results.tex").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def generate(
    processed: Path, loopback: Path, lab: Path, output: Path
) -> dict[str, object]:
    rows = read_rows(processed / "aggregate_metrics.csv")
    contrasts = read_rows(processed / "paired_contrasts.csv")
    loopback_manifest = json.loads(loopback.read_text(encoding="utf-8"))
    lab_manifest = json.loads(lab.read_text(encoding="utf-8"))
    figures = output / "figures"
    tradeoff_figure(rows, figures / "fso_tradeoff.pdf")
    function_figure(rows, figures / "fso_function_comparison.pdf")
    ablation_figure(rows, figures / "fso_ablation.pdf")
    write_tables(rows, contrasts, output)
    write_lab_table(lab_manifest, output)

    by_strategy = {row["strategy"]: row for row in rows}
    by_baseline = {row["baseline"]: row for row in contrasts}
    fso = by_strategy[CANONICAL_FSO]
    headline = {
        "schema_version": 1,
        "scope": (
            "synthetic CAP-ME adaptive-mobile trace replay, deterministic "
            "closed-world carrier lab, and loopback-only packet testbed"
        ),
        "confirmation_seeds": int(fso["replicates"]),
        "fso_auac": float(fso["auac"]),
        "fso_auac_ci": [float(fso["auac_ci_low"]), float(fso["auac_ci_high"])],
        "fso_byte_overhead": float(fso["byte_overhead"]),
        "fso_minus_deadline_cost_failover": float(
            by_baseline["deadline_cost_failover"]["mean_difference"]
        ),
        "fso_minus_deadline_cost_failover_ci": [
            float(by_baseline["deadline_cost_failover"]["ci_low"]),
            float(by_baseline["deadline_cost_failover"]["ci_high"]),
        ],
        "fso_minus_session_failover": float(
            by_baseline["session_failover"]["mean_difference"]
        ),
        "fso_minus_session_failover_ci": [
            float(by_baseline["session_failover"]["ci_low"]),
            float(by_baseline["session_failover"]["ci_high"]),
        ],
        "fso_minus_generated_only": float(
            by_baseline["generated_only"]["mean_difference"]
        ),
        "no_semantics_auac": float(by_strategy["fso_no_semantics"]["auac"]),
        "no_semantics_byte_overhead": float(
            by_strategy["fso_no_semantics"]["byte_overhead"]
        ),
        "fso_minus_feedback_enabled": float(
            by_baseline[FEEDBACK_ENABLED_FSO]["mean_difference"]
        ),
        "fso_minus_no_diversity": float(
            by_baseline["fso_no_diversity"]["mean_difference"]
        ),
        "fso_minus_no_diversity_ci": [
            float(by_baseline["fso_no_diversity"]["ci_low"]),
            float(by_baseline["fso_no_diversity"]["ci_high"]),
        ],
        "provider_controlled_attempts": 0,
        "loopback": {
            "operations": loopback_manifest["operations"],
            "successful_operations": loopback_manifest["successful_operations"],
            "availability": loopback_manifest["availability"],
            "byte_overhead": loopback_manifest["byte_overhead"],
            "external_destinations": loopback_manifest["external_destinations"],
        },
        "deterministic_lab": {
            "operations": lab_manifest["operations"],
            "successful_operations": lab_manifest["successful_operations"],
            "availability": lab_manifest["availability"],
            "byte_overhead": lab_manifest["byte_overhead"],
            "phase_availability": lab_manifest["phase_availability"],
            "failure_injection": lab_manifest["failure_injection"],
            "external_destinations": lab_manifest["external_destinations"],
            "provider_controlled_attempts": lab_manifest[
                "provider_controlled_attempts"
            ],
        },
        "interpretation": "Intervals quantify variation across synthetic seeds, not a deployed censor, network, or population.",
    }
    headline_path = output / "fso_headline_results.json"
    headline_path.write_text(json.dumps(headline, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    generated_names = (
        "fso_main_results.tex",
        "fso_function_results.tex",
        "fso_ablation_results.tex",
        "fso_lab_results.tex",
        "fso_headline_results.json",
        "figures/fso_tradeoff.pdf",
        "figures/fso_function_comparison.pdf",
        "figures/fso_ablation.pdf",
    )
    manifest = {
        "schema_version": 1,
        "inputs": {
            str(processed / "aggregate_metrics.csv"): sha256(processed / "aggregate_metrics.csv"),
            str(processed / "paired_contrasts.csv"): sha256(processed / "paired_contrasts.csv"),
            str(loopback): sha256(loopback),
            str(lab): sha256(lab),
        },
        "outputs": {name: sha256(output / name) for name in generated_names},
    }
    (output / "fso_generation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return headline
