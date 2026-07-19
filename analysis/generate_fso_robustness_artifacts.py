#!/usr/bin/env python3
"""Generate a compact FSO robustness figure and LaTeX tables."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from capme.pdf_fonts import PDF_FONT_BOLD, PDF_FONT_REGULAR, register_pdf_fonts


register_pdf_fonts()


ROOT = Path(__file__).resolve().parents[1]
SENSITIVITY = ROOT / "results" / "processed" / "fso" / "sensitivity"
INDEPENDENT = ROOT / "results" / "processed" / "fso" / "independent-replay"
STRUCTURES = ROOT / "results" / "processed" / "fso" / "structure-replay"
OUTPUT = ROOT / "artifacts" / "generated"

STRUCTURE_LABELS = (
    ("classifier_dominant", "Classifier-dominant"),
    ("endpoint_discovery_dominant", "Endpoint-discovery"),
    ("resource_bounded_composed", "Resource-bounded"),
    ("adaptive_composed", "Adaptive-composed"),
)

DARK = colors.HexColor("#252525")
GRID = colors.HexColor("#D8D8D8")
BLUE = colors.HexColor("#087DBB")
ORANGE = colors.HexColor("#E69F00")
GREY = colors.HexColor("#6C757D")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _x(value: float, left: float, width: float, low: float, high: float) -> float:
    return left + width * (value - low) / (high - low)


def _sensitivity_figure(rows: list[dict[str, str]], path: Path) -> None:
    """Plot paired intervals for all declared sensitivity design points."""

    ordered = sorted(rows, key=lambda row: float(row["mean_difference"]))
    width, height = 540, 315
    c = canvas.Canvas(str(path), pagesize=(width, height), invariant=1)
    c.setTitle("FSO versus the deadline-and-cost-matched baseline")
    c.setFillColor(DARK)
    c.setFont(PDF_FONT_BOLD, 11)
    c.drawString(48, 291, "FSO does not have a robust advantage over the matched baseline")
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont(PDF_FONT_REGULAR, 7.4)
    c.drawString(
        48,
        279,
        "Paired AUAC differences across the declared base point and 24 Latin-hypercube designs; bars are seed-bootstrap 95% intervals",
    )

    left, bottom, plot_width, plot_height = 58, 49, 448, 210
    low, high = -0.012, 0.044
    zero = _x(0.0, left, plot_width, low, high)
    c.setStrokeColor(DARK)
    c.setLineWidth(0.8)
    c.line(left, bottom, left + plot_width, bottom)
    c.setStrokeColor(colors.HexColor("#444444"))
    c.setLineWidth(0.7)
    c.line(zero, bottom, zero, bottom + plot_height)

    for tick in (-0.01, 0.00, 0.01, 0.02, 0.03, 0.04):
        xpos = _x(tick, left, plot_width, low, high)
        c.setStrokeColor(GRID)
        c.setLineWidth(0.3)
        c.line(xpos, bottom, xpos, bottom + plot_height)
        c.setFillColor(DARK)
        c.setFont(PDF_FONT_REGULAR, 7)
        c.drawCentredString(xpos, bottom - 12, f"{tick:+.2f}")

    spacing = plot_height / len(ordered)
    for index, row in enumerate(ordered):
        ypos = bottom + spacing * (index + 0.5)
        mean = float(row["mean_difference"])
        ci_low = float(row["difference_ci_low"])
        ci_high = float(row["difference_ci_high"])
        is_base = bool(int(row["is_declared_base"]))
        fill = ORANGE if is_base else (BLUE if ci_low > 0.0 else (GREY if ci_high >= 0.0 else colors.HexColor("#CC79A7")))
        c.setStrokeColor(fill)
        c.setLineWidth(1.0 if is_base else 0.65)
        c.line(_x(ci_low, left, plot_width, low, high), ypos, _x(ci_high, left, plot_width, low, high), ypos)
        c.setFillColor(fill)
        c.circle(_x(mean, left, plot_width, low, high), ypos, 2.7 if is_base else 1.8, fill=1, stroke=0)

    c.setFillColor(DARK)
    c.setFont(PDF_FONT_REGULAR, 7.5)
    c.drawCentredString(left + plot_width / 2, 18, "FSO minus deadline/cost baseline AUAC")
    c.setFont(PDF_FONT_REGULAR, 6.7)
    c.drawString(58, 266, "negative favors baseline")
    c.drawRightString(506, 266, "positive favors FSO")
    c.setFillColor(ORANGE)
    c.circle(390, 291, 2.7, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.drawString(397, 288.5, "declared base")
    c.showPage()
    c.save()


def _contrast(path: Path) -> dict[str, str]:
    rows = _read_csv(path)
    return next(row for row in rows if row["baseline"] == "deadline_cost_failover")


def _write_tables(
    sensitivity_rows: list[dict[str, str]],
    sensitivity_summary: dict[str, object],
    independent_summary: dict[str, object],
) -> None:
    row_end = r"\\"
    base = next(row for row in sensitivity_rows if int(row["is_declared_base"]))
    lines = [
        r"\begin{tabular}{lrr}",
        r"\toprule",
        "Trace/model & FSO minus matched baseline [95\\% CI] & Interpretation " + row_end,
        r"\midrule",
        f"Adaptive base & {float(base['mean_difference']):+.4f} "
        f"[{float(base['difference_ci_low']):+.4f}, {float(base['difference_ci_high']):+.4f}] & Inconclusive " + row_end,
    ]
    for directory, label in STRUCTURE_LABELS:
        row = _contrast(STRUCTURES / directory / "paired_contrasts.csv")
        lines.append(
            f"{label} & {float(row['mean_difference']):+.4f} "
            f"[{float(row['ci_low']):+.4f}, {float(row['ci_high']):+.4f}] & Inconclusive " + row_end
        )
    independent_ci = independent_summary["fso_minus_deadline_cost_failover_ci"]
    lines.append(
        f"Separately coded trace & {float(independent_summary['fso_minus_deadline_cost_failover']):+.4f} "
        f"[{float(independent_ci[0]):+.4f}, {float(independent_ci[1]):+.4f}] & Small positive " + row_end
    )
    lines.extend((r"\bottomrule", r"\end{tabular}", ""))
    (OUTPUT / "fso_matched_baseline_results.tex").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    summary_lines = [
        r"\begin{tabular}{lr}",
        r"\toprule",
        "Sensitivity diagnostic & Result " + row_end,
        r"\midrule",
        f"Design points (base + LHS) & {int(sensitivity_summary['design_points_including_base'])} " + row_end,
        f"Mean difference range & [{float(sensitivity_summary['mean_difference_min']):+.4f}, {float(sensitivity_summary['mean_difference_max']):+.4f}] " + row_end,
        f"Median mean difference & {float(sensitivity_summary['mean_difference_median']):+.4f} " + row_end,
        f"Point estimates favoring FSO & {100.0 * float(sensitivity_summary['fraction_mean_difference_positive']):.0f}\\% " + row_end,
        f"Intervals wholly above zero & {100.0 * float(sensitivity_summary['fraction_ci_excludes_zero_positive']):.0f}\\% " + row_end,
        f"Intervals wholly below zero & {100.0 * float(sensitivity_summary['fraction_ci_excludes_zero_negative']):.0f}\\% " + row_end,
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]
    (OUTPUT / "fso_sensitivity_results.tex").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )


def main() -> int:
    sensitivity_results = SENSITIVITY / "sensitivity_results.csv"
    sensitivity_summary_path = SENSITIVITY / "summary.json"
    independent_summary_path = INDEPENDENT / "summary.json"
    rows = _read_csv(sensitivity_results)
    summary = json.loads(sensitivity_summary_path.read_text(encoding="utf-8"))
    independent = json.loads(independent_summary_path.read_text(encoding="utf-8"))
    figures = OUTPUT / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    figure = figures / "fso_sensitivity.pdf"
    _sensitivity_figure(rows, figure)
    _write_tables(rows, summary, independent)

    inputs = [sensitivity_results, sensitivity_summary_path, independent_summary_path]
    inputs.extend(
        STRUCTURES / directory / "paired_contrasts.csv"
        for directory, _ in STRUCTURE_LABELS
    )
    outputs = [
        figure,
        OUTPUT / "fso_matched_baseline_results.tex",
        OUTPUT / "fso_sensitivity_results.tex",
    ]
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "inputs": {
            str(path.relative_to(ROOT)): _sha256(path) for path in inputs
        },
        "outputs": {
            str(path.relative_to(OUTPUT)): _sha256(path) for path in outputs
        },
    }
    manifest_path = OUTPUT / "fso_robustness_generation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
