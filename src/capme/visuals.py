"""Vector figures and LaTeX tables generated from processed results."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from .io import read_csv, write_json
from .model import ARCHITECTURES, WORKLOADS

PALETTE = {
    "direct_e2ee": colors.HexColor("#0072B2"),
    "fixed_proxy": colors.HexColor("#D55E00"),
    "generated_transport": colors.HexColor("#009E73"),
    "ephemeral_relay": colors.HexColor("#E69F00"),
    "platform_controlled": colors.HexColor("#CC79A7"),
}
LAYER_COLORS = {
    "path": colors.HexColor("#56B4E9"),
    "endpoint": colors.HexColor("#E69F00"),
    "platform": colors.HexColor("#CC79A7"),
}


def _axis(c: canvas.Canvas, left: float, bottom: float, width: float, height: float) -> None:
    c.setStrokeColor(colors.HexColor("#333333"))
    c.setLineWidth(0.8)
    c.line(left, bottom, left, bottom + height)
    c.line(left, bottom, left + width, bottom)
    c.setFont("Helvetica", 7.5)
    for tick in range(0, 6):
        value = tick / 5
        y = bottom + height * value
        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.setLineWidth(0.35)
        c.line(left, y, left + width, y)
        c.setFillColor(colors.HexColor("#444444"))
        c.drawRightString(left - 5, y - 2.5, f"{value:.1f}")


def survival_figure(curves: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = 520, 310
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    c.setTitle("CAP-ME service availability over adaptive epochs")
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, 290, "Service availability over adaptive censor-defender epochs")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(48, 278, "Mobile-like network; mean across functions and 20 simulation seeds; bands are 95% bootstrap CIs")
    left, bottom, plot_width, plot_height = 48, 48, 448, 198
    _axis(c, left, bottom, plot_width, plot_height)
    maximum_epoch = max(int(row["epoch"]) for row in curves)
    by_architecture: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in curves:
        by_architecture[row["architecture"]].append(row)
    for architecture in ARCHITECTURES:
        rows = sorted(by_architecture[architecture], key=lambda row: int(row["epoch"]))
        color = PALETTE[architecture]
        lower = [
            (
                left + plot_width * int(row["epoch"]) / maximum_epoch,
                bottom + plot_height * float(row["ci_low"]),
            )
            for row in rows
        ]
        upper = [
            (
                left + plot_width * int(row["epoch"]) / maximum_epoch,
                bottom + plot_height * float(row["ci_high"]),
            )
            for row in reversed(rows)
        ]
        path = c.beginPath()
        first_x, first_y = lower[0]
        path.moveTo(first_x, first_y)
        for x, y in lower[1:] + upper:
            path.lineTo(x, y)
        path.close()
        c.saveState()
        c.setFillColor(color)
        if hasattr(c, "setFillAlpha"):
            c.setFillAlpha(0.13)
        c.drawPath(path, fill=1, stroke=0)
        c.restoreState()
        line = c.beginPath()
        for index, row in enumerate(rows):
            x = left + plot_width * int(row["epoch"]) / maximum_epoch
            y = bottom + plot_height * float(row["availability"])
            if index == 0:
                line.moveTo(x, y)
            else:
                line.lineTo(x, y)
        c.setStrokeColor(color)
        c.setLineWidth(1.8)
        c.drawPath(line, fill=0, stroke=1)
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica", 8)
    for epoch in range(0, maximum_epoch + 1, 5):
        x = left + plot_width * epoch / maximum_epoch
        c.drawCentredString(x, bottom - 13, str(epoch))
    c.drawCentredString(left + plot_width / 2, 20, "Adaptive epoch")
    c.saveState()
    c.translate(14, bottom + plot_height / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, "Functional availability")
    c.restoreState()
    legend_y = 263
    x_positions = (48, 218, 365)
    for index, architecture in enumerate(ARCHITECTURES):
        x = x_positions[index % 3]
        y = legend_y - 11 * (index // 3)
        c.setStrokeColor(PALETTE[architecture])
        c.setLineWidth(2)
        c.line(x, y + 2, x + 16, y + 2)
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica", 7.5)
        c.drawString(x + 21, y, ARCHITECTURES[architecture].label)
    c.showPage()
    c.save()


def auac_figure(aggregates: list[dict[str, str]], output: Path) -> None:
    rows = {
        (row["architecture"], row["censor"]): row
        for row in aggregates
        if row["network"] == "mobile" and row["censor"] in {"passive_only", "adaptive_cross_layer"}
    }
    width, height = 520, 300
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    c.setTitle("CAP-ME lifecycle availability")
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, 280, "Lifecycle availability changes when censor layers are composed")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(48, 268, "AUAC over 36 epochs; mobile-like network; error bars are 95% bootstrap CIs across 20 seeds")
    left, bottom, plot_width, plot_height = 48, 72, 448, 172
    _axis(c, left, bottom, plot_width, plot_height)
    architectures = list(ARCHITECTURES)
    group_width = plot_width / len(architectures)
    bar_width = 23
    for index, architecture in enumerate(architectures):
        center = left + group_width * (index + 0.5)
        for offset, censor_name, fill in (
            (-bar_width / 2, "passive_only", colors.HexColor("#B8C7D9")),
            (bar_width / 2, "adaptive_cross_layer", PALETTE[architecture]),
        ):
            row = rows[(architecture, censor_name)]
            value = float(row["auac"])
            low = float(row["auac_ci_low"])
            high = float(row["auac_ci_high"])
            x = center + offset - bar_width / 2
            c.setFillColor(fill)
            c.setStrokeColor(colors.HexColor("#444444"))
            c.setLineWidth(0.4)
            c.rect(x, bottom, bar_width, plot_height * value, fill=1, stroke=1)
            error_x = x + bar_width / 2
            c.setStrokeColor(colors.HexColor("#222222"))
            c.setLineWidth(0.7)
            c.line(error_x, bottom + plot_height * low, error_x, bottom + plot_height * high)
            c.line(error_x - 3, bottom + plot_height * low, error_x + 3, bottom + plot_height * low)
            c.line(error_x - 3, bottom + plot_height * high, error_x + 3, bottom + plot_height * high)
        c.saveState()
        c.translate(center + 4, bottom - 7)
        c.rotate(-28)
        c.setFont("Helvetica", 7.2)
        c.setFillColor(colors.HexColor("#333333"))
        c.drawRightString(0, 0, ARCHITECTURES[architecture].label)
        c.restoreState()
    c.saveState()
    c.translate(14, bottom + plot_height / 2)
    c.rotate(90)
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(0, 0, "Area under availability curve (AUAC)")
    c.restoreState()
    c.setFillColor(colors.HexColor("#B8C7D9"))
    c.rect(350, 259, 10, 7, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica", 7.5)
    c.drawString(364, 259, "Passive only")
    c.setFillColor(colors.HexColor("#4D4D4D"))
    c.rect(425, 259, 10, 7, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawString(439, 259, "Adaptive cross-layer")
    c.showPage()
    c.save()


def attribution_figure(shapley: list[dict[str, str]], output: Path) -> None:
    values: dict[tuple[str, str], float] = {
        (row["architecture"], row["layer"]): max(0.0, float(row["auac_loss_contribution"]))
        for row in shapley
    }
    width, height = 520, 292
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    c.setTitle("CAP-ME interventional layer attribution")
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, 272, "Endpoint control dominates lifecycle loss for stable services")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(48, 260, "Exact three-layer Shapley allocation on mobile-like conditions; means across 8 paired seeds")
    left, bottom, plot_width, plot_height = 48, 68, 448, 166
    _axis(c, left, bottom, plot_width, plot_height)
    architectures = list(ARCHITECTURES)
    group_width = plot_width / len(architectures)
    bar_width = 42
    for index, architecture in enumerate(architectures):
        x = left + group_width * (index + 0.5) - bar_width / 2
        current = bottom
        for layer in ("path", "endpoint", "platform"):
            value = values.get((architecture, layer), 0.0)
            height_value = plot_height * value
            c.setFillColor(LAYER_COLORS[layer])
            c.setStrokeColor(colors.white)
            c.setLineWidth(0.4)
            c.rect(x, current, bar_width, height_value, fill=1, stroke=1)
            current += height_value
        c.saveState()
        c.translate(x + bar_width / 2 + 7, bottom - 7)
        c.rotate(-28)
        c.setFont("Helvetica", 7.2)
        c.setFillColor(colors.HexColor("#333333"))
        c.drawRightString(0, 0, ARCHITECTURES[architecture].label)
        c.restoreState()
    c.saveState()
    c.translate(14, bottom + plot_height / 2)
    c.rotate(90)
    c.setFillColor(colors.HexColor("#333333"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(0, 0, "Attributed AUAC loss")
    c.restoreState()
    legend_x = 290
    for layer in ("path", "endpoint", "platform"):
        c.setFillColor(LAYER_COLORS[layer])
        c.rect(legend_x, 250, 10, 7, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica", 7.5)
        c.drawString(legend_x + 14, 250, layer.title())
        legend_x += 69
    c.showPage()
    c.save()


def function_heatmap(aggregates: list[dict[str, str]], output: Path) -> None:
    selected = {
        row["architecture"]: row
        for row in aggregates
        if row["network"] == "mobile" and row["censor"] == "adaptive_cross_layer"
    }
    width, height = 520, 255
    c = canvas.Canvas(str(output), pagesize=(width, height), invariant=1)
    c.setTitle("CAP-ME function-specific lifecycle availability")
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, 235, "Function-specific lifecycle availability is not a single scalar")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(48, 223, "Adaptive cross-layer censor; mobile-like network; AUAC means across 20 seeds")
    functions = ("text", "presence", "media", "file", "realtime")
    architectures = list(ARCHITECTURES)
    left, bottom = 150, 45
    cell_w, cell_h = 66, 28
    for column, function in enumerate(functions):
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(left + cell_w * (column + 0.5), bottom + cell_h * 5 + 10, function.title())
    for row_index, architecture in enumerate(architectures):
        y = bottom + cell_h * (len(architectures) - row_index - 1)
        c.setFillColor(colors.HexColor("#333333"))
        c.setFont("Helvetica", 7.5)
        c.drawRightString(left - 8, y + 9, ARCHITECTURES[architecture].label)
        for column, function in enumerate(functions):
            value = float(selected[architecture][f"auac_{function}"])
            shade = colors.Color(0.96 - 0.63 * value, 0.98 - 0.36 * value, 1.0 - 0.12 * value)
            x = left + cell_w * column
            c.setFillColor(shade)
            c.setStrokeColor(colors.white)
            c.rect(x, y, cell_w, cell_h, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#111111") if value < 0.70 else colors.white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x + cell_w / 2, y + 9, f"{value:.2f}")
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(150, 24, "Values are synthetic-model outcomes, not measurements of named services.")
    c.showPage()
    c.save()


def _latex_escape(value: str) -> str:
    return (
        value.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
        .replace("&", "\\&")
    )


def write_tables(
    aggregates: list[dict[str, str]],
    contrasts: list[dict[str, str]],
    shapley: list[dict[str, str]],
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mobile = {
        (row["architecture"], row["censor"]): row
        for row in aggregates
        if row["network"] == "mobile"
    }
    contrast_mobile = {
        row["architecture"]: row for row in contrasts if row["network"] == "mobile"
    }
    main_lines = [
        "\\begin{tabular}{lrrrr}",
        "\\toprule",
        "Architecture & Passive AUAC & Adaptive AUAC & Paired $\\Delta$ & Adaptive $T_{50}$ \\\\",
        "\\midrule",
    ]
    headline: dict[str, object] = {"mobile": {}}
    for architecture in ARCHITECTURES:
        passive = mobile[(architecture, "passive_only")]
        adaptive = mobile[(architecture, "adaptive_cross_layer")]
        contrast = contrast_mobile[architecture]
        main_lines.append(
            f"{_latex_escape(ARCHITECTURES[architecture].label)} & "
            f"{float(passive['auac']):.3f} & {float(adaptive['auac']):.3f} & "
            f"{float(contrast['mean_difference']):+.3f} & {float(adaptive['t50']):.1f} \\\\"
        )
        headline["mobile"][architecture] = {
            "passive_auac": float(passive["auac"]),
            "adaptive_auac": float(adaptive["auac"]),
            "paired_difference": float(contrast["mean_difference"]),
            "paired_ci": [float(contrast["ci_low"]), float(contrast["ci_high"])],
            "paired_q": float(contrast["p_value_bh"]),
            "adaptive_t50": float(adaptive["t50"]),
            "adaptive_t50_event_fraction": float(adaptive["t50_event_fraction"]),
        }
    main_lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    (output_dir / "main_results.tex").write_text("\n".join(main_lines), encoding="utf-8")

    function_lines = [
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Architecture & Text & Presence & Media & File & Real-time \\\\",
        "\\midrule",
    ]
    for architecture in ARCHITECTURES:
        adaptive = mobile[(architecture, "adaptive_cross_layer")]
        values = " & ".join(f"{float(adaptive[f'auac_{function}']):.3f}" for function in ("text", "presence", "media", "file", "realtime"))
        function_lines.append(
            f"{_latex_escape(ARCHITECTURES[architecture].label)} & {values} \\\\"
        )
    function_lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    (output_dir / "function_results.tex").write_text("\n".join(function_lines), encoding="utf-8")

    layer_values = {
        (row["architecture"], row["layer"]): float(row["auac_loss_contribution"])
        for row in shapley
    }
    layer_lines = [
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Architecture & Path & Endpoint & Platform \\\\",
        "\\midrule",
    ]
    for architecture in ARCHITECTURES:
        layer_lines.append(
            f"{_latex_escape(ARCHITECTURES[architecture].label)} & "
            f"{layer_values[(architecture, 'path')]:.3f} & "
            f"{layer_values[(architecture, 'endpoint')]:.3f} & "
            f"{layer_values[(architecture, 'platform')]:.3f} \\\\"
        )
    layer_lines.extend(["\\bottomrule", "\\end{tabular}", ""])
    (output_dir / "layer_results.tex").write_text("\n".join(layer_lines), encoding="utf-8")
    write_json(output_dir / "headline_results.json", headline)
    return headline


def generate(processed_dir: Path, artifact_generated_dir: Path) -> dict[str, object]:
    aggregates = read_csv(processed_dir / "aggregate_metrics.csv")
    contrasts = read_csv(processed_dir / "paired_contrasts.csv")
    shapley = read_csv(processed_dir / "shapley_attribution.csv")
    curves = read_csv(processed_dir / "survival_curves.csv")
    figure_dir = artifact_generated_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    survival_figure(curves, figure_dir / "survival_curves.pdf")
    auac_figure(aggregates, figure_dir / "lifecycle_auac.pdf")
    attribution_figure(shapley, figure_dir / "layer_attribution.pdf")
    function_heatmap(aggregates, figure_dir / "function_heatmap.pdf")
    headline = write_tables(aggregates, contrasts, shapley, artifact_generated_dir)
    manifest = {
        "schema_version": 1,
        "synthetic_only": True,
        "figures": [
            "figures/survival_curves.pdf",
            "figures/lifecycle_auac.pdf",
            "figures/layer_attribution.pdf",
            "figures/function_heatmap.pdf",
        ],
        "tables": ["main_results.tex", "function_results.tex", "layer_results.tex"],
        "headline_results": headline,
    }
    write_json(artifact_generated_dir / "generation_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--artifact-generated", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = generate(args.processed, args.artifact_generated)
    print(json.dumps({"figures": len(manifest["figures"]), "tables": len(manifest["tables"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
