#!/usr/bin/env python3
"""Plot measured endpoint metrics without selecting a best protocol.

The script reads the real endpoint CSV summaries, never plots source
performance or simulation predictions, and keeps the requested fraction fixed.
Means and standard deviations are computational summaries, not confidence
intervals.
"""

from __future__ import annotations

import argparse
import csv
import json
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


METHODS: List[str] = [
    "FS",
    "random_frozen",
    "TL_frozen",
    "TL_finetune",
    "Ridge",
    "mean_baseline",
]
METHOD_LABELS: Mapping[str, str] = {
    "FS": "FS",
    "random_frozen": "Random\nfrozen",
    "TL_frozen": "TL\nfrozen",
    "TL_finetune": "TL\nfine-tune",
    "Ridge": "Ridge",
    "mean_baseline": "Mean\nbaseline",
}
# Fixed Okabe-Ito-inspired palette: color-blind-aware and not performance-ranked.
METHOD_COLORS: Mapping[str, str] = {
    "FS": "#0072B2",
    "random_frozen": "#E69F00",
    "TL_frozen": "#009E73",
    "TL_finetune": "#D55E00",
    "Ridge": "#CC79A7",
    "mean_baseline": "#56B4E9",
}
METRICS: List[str] = ["r2", "rmse", "mae"]
METRIC_LABELS: Mapping[str, str] = {"r2": "R²", "rmse": "RMSE", "mae": "MAE"}
METRIC_TITLES: Mapping[str, str] = {
    "r2": "R² — measured endpoint comparison",
    "rmse": "RMSE — q as recorded (unit unconfirmed)",
    "mae": "MAE — q as recorded (unit unconfirmed)",
}
DEFAULT_TARGET_ORDER = [
    "Al:Si-APTS", "Al:Si-APTS-CO", "Fe:Si", "Fe:Si-APTS", "Fe:Si-APTS-CO",
]


class PlotDataError(RuntimeError):
    pass


def read_csv_records(path: Path, label: str) -> List[Dict[str, str]]:
    if not path.exists():
        raise PlotDataError(f"Required {label} file not found: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception as exc:
        raise PlotDataError(f"Could not read {label} CSV: {path}: {exc}") from exc


def fnum(value: Any, default: float = float("nan")) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def close_to(a: Any, b: float, atol: float = 1e-9) -> bool:
    av = fnum(a)
    return bool(np.isfinite(av) and np.isclose(av, b, rtol=0.0, atol=atol))


def protocol_config(results: Path) -> dict:
    path = results / "protocol.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        warnings.warn(f"Could not parse protocol.json ({exc}); using CSV metadata.")
        return {}


def clean_source_rows(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    kept: List[Dict[str, Any]] = []
    excluded = 0
    for row in rows:
        target = str(row.get("target", ""))
        low = target.strip().lower()
        is_source = "source" in low or low in {"source", "source_domain", "source performance"}
        if is_source:
            excluded += 1
        else:
            kept.append(dict(row))
    return kept, excluded


def filter_fraction(rows: Sequence[Dict[str, Any]], fraction: float) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows if close_to(row.get("fraction"), fraction)]


def group_rows(rows: Iterable[Dict[str, Any]], keys: Sequence[str]) -> Dict[Tuple[str, ...], List[Dict[str, Any]]]:
    groups: Dict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(str(row.get(key, "")) for key in keys)].append(row)
    return groups


def mean(values: Sequence[float]) -> float:
    vals = [float(v) for v in values if finite(v)]
    return float(np.mean(vals)) if vals else float("nan")


def sample_sd(values: Sequence[float]) -> float:
    vals = [float(v) for v in values if finite(v)]
    return float(np.std(vals, ddof=1)) if len(vals) > 1 else float("nan")


def _base_record(group: Sequence[Dict[str, Any]], keys: Sequence[str]) -> Dict[str, Any]:
    first = group[0]
    return {key: first.get(key, "") for key in keys}


def summary_from_fold_mean_sd(results: Path, fraction: float) -> Tuple[List[Dict[str, Any]], str, int]:
    path = results / "fold_mean_sd.csv"
    if not path.exists():
        return [], "", 0
    raw = read_csv_records(path, "fold_mean_sd")
    required = {
        "target", "fraction", "protocol", "held_temperature_C",
        "r2_mean", "rmse_mean", "mae_mean",
    }
    if raw and not required.issubset(raw[0].keys()):
        return [], "", 0
    filtered, source_rows = clean_source_rows(filter_fraction(raw, fraction))
    filtered = [row for row in filtered if row.get("protocol") in METHODS]
    if not filtered:
        return [], "", source_rows

    keys = ["target", "fraction", "protocol", "held_temperature_C"]
    output: List[Dict[str, Any]] = []
    for _, group in group_rows(filtered, keys).items():
        record = _base_record(group, keys)
        record["n_seed"] = max([fnum(row.get("seed_count"), 1.0) for row in group] or [1.0])
        record["n_raw_rows"] = len(group)
        for metric in METRICS:
            record[metric] = mean([fnum(row.get(f"{metric}_mean")) for row in group])
            sds = [fnum(row.get(f"{metric}_sd")) for row in group]
            record[f"{metric}_sd"] = max([v for v in sds if finite(v)] or [float("nan")])
        record["data_source"] = "fold_mean_sd.csv"
        output.append(record)
    return output, "fold_mean_sd.csv", source_rows


def summary_from_all_metrics(results: Path, fraction: float) -> Tuple[List[Dict[str, Any]], str, int]:
    raw = read_csv_records(results / "all_metrics.csv", "all_metrics")
    required = {"target", "fraction", "protocol", "held_temperature_C", "r2", "rmse", "mae"}
    if not raw:
        return [], "all_metrics.csv", 0
    missing = required.difference(raw[0].keys())
    if missing:
        raise PlotDataError(f"all_metrics.csv is missing columns: {sorted(missing)}")
    filtered, source_rows = clean_source_rows(filter_fraction(raw, fraction))
    filtered = [row for row in filtered if row.get("protocol") in METHODS]
    if not filtered:
        return [], "all_metrics.csv", source_rows

    # First average CV folds within each seed, then summarize across seeds.
    seed_key = "seed" if "seed" in filtered[0] else "_seed_fallback"
    if seed_key == "_seed_fallback":
        filtered = [dict(row, _seed_fallback="0") for row in filtered]
    keys = ["target", "fraction", "protocol", "held_temperature_C"]
    seed_keys = keys + [seed_key]
    seed_rows: List[Dict[str, Any]] = []
    for _, group in group_rows(filtered, seed_keys).items():
        record = _base_record(group, seed_keys)
        for metric in METRICS:
            record[metric] = mean([fnum(row.get(metric)) for row in group])
        seed_rows.append(record)

    output: List[Dict[str, Any]] = []
    for _, group in group_rows(seed_rows, keys).items():
        record = _base_record(group, keys)
        record["n_seed"] = len({str(row.get(seed_key, "")) for row in group})
        # Count original CV rows represented by this target/protocol/fraction/temp.
        record["n_raw_rows"] = sum(
            1
            for row in filtered
            if all(
                (str(row.get(key, "")) == str(record.get(key, "")))
                for key in keys
            )
        )
        for metric in METRICS:
            values = [fnum(row.get(metric)) for row in group]
            record[metric] = mean(values)
            record[f"{metric}_sd"] = sample_sd(values)
        record["data_source"] = "all_metrics.csv"
        output.append(record)
    return output, "all_metrics.csv", source_rows


def load_plot_data(results: Path, fraction: float) -> Tuple[List[Dict[str, Any]], str, int, int]:
    summary, source, source_rows = summary_from_fold_mean_sd(results, fraction)
    if not summary:
        summary, source, fallback_excluded = summary_from_all_metrics(results, fraction)
        source_rows += fallback_excluded
    if not summary:
        raise PlotDataError(f"No measured endpoint rows found for fraction={fraction:g}.")
    summary = [row for row in summary if row.get("protocol") in METHODS]
    summary = [row for row in summary if row.get("target", "") and finite(row.get("held_temperature_C"))]
    if not summary:
        raise PlotDataError("No complete target/method/held-temperature rows remain.")
    for row in summary:
        for metric in METRICS:
            row[metric] = fnum(row.get(metric))
            row[f"{metric}_sd"] = fnum(row.get(f"{metric}_sd"))
        row["held_temperature_C"] = fnum(row.get("held_temperature_C"))
        row["fraction"] = fnum(row.get("fraction"), fraction)
    methods_present = len({str(row.get("protocol")) for row in summary})
    return summary, source, source_rows, methods_present


def target_order(summary: Sequence[Dict[str, Any]], protocol: dict) -> List[str]:
    present = {str(row["target"]) for row in summary}
    config_targets = protocol.get("config", {}).get("targets", []) if isinstance(protocol.get("config", {}), dict) else []
    ordered: List[str] = []
    for value in list(config_targets) + DEFAULT_TARGET_ORDER + [row["target"] for row in summary]:
        value = str(value)
        if value in present and value not in ordered:
            ordered.append(value)
    return ordered


def held_temperature_order(summary: Sequence[Dict[str, Any]], protocol: dict) -> List[float]:
    present = sorted({fnum(row["held_temperature_C"]) for row in summary if finite(row["held_temperature_C"])})
    config_temps = protocol.get("config", {}).get("held_temperatures", []) if isinstance(protocol.get("config", {}), dict) else []
    ordered: List[float] = []
    for value in list(config_temps) + present:
        temp = fnum(value)
        if finite(temp) and any(np.isclose(temp, p, rtol=0.0, atol=1e-9) for p in present) and temp not in ordered:
            ordered.append(temp)
    return ordered


def format_temp(temp: float) -> str:
    return f"{int(temp)} °C" if float(temp).is_integer() else f"{temp:g} °C"


def format_value(value: float) -> str:
    return "NA" if not finite(value) else f"{float(value):.3f}"


def metric_ylim(summary: Sequence[Dict[str, Any]], metric: str) -> Tuple[float, float]:
    values: List[float] = []
    for row in summary:
        value = fnum(row.get(metric))
        if finite(value):
            sd = fnum(row.get(f"{metric}_sd"), 0.0)
            sd = max(sd, 0.0) if finite(sd) else 0.0
            values.extend([value - sd, value + sd])
    if not values:
        return -1.0, 1.0
    low, high = min(values), max(values)
    low = min(low, 0.0)
    if metric == "r2":
        high = max(high, 0.0)
    span = max(high - low, 0.1)
    pad = max(0.10 * span, 0.05)
    return low - pad, high + pad


def panel_rows(summary: Sequence[Dict[str, Any]], target: str, held_temp: float) -> Dict[str, Dict[str, Any]]:
    selected = [
        row for row in summary
        if str(row.get("target")) == str(target) and close_to(row.get("held_temperature_C"), held_temp)
    ]
    return {str(row["protocol"]): row for row in selected}


def plot_panel(
    ax: plt.Axes,
    panel: Mapping[str, Dict[str, Any]],
    metric: str,
    y_limits: Tuple[float, float],
    *,
    show_ylabel: bool,
    show_xlabel: bool,
) -> None:
    x = np.arange(len(METHODS), dtype=float)
    means = np.full(len(METHODS), np.nan, dtype=float)
    sds = np.zeros(len(METHODS), dtype=float)
    for i, method in enumerate(METHODS):
        row = panel.get(method)
        if row is None:
            continue
        value = fnum(row.get(metric))
        sd = fnum(row.get(f"{metric}_sd"), 0.0)
        means[i] = value
        sds[i] = max(sd, 0.0) if finite(sd) else 0.0
    finite_mask = np.isfinite(means)
    ax.bar(
        x[finite_mask],
        means[finite_mask],
        width=0.72,
        color=[METHOD_COLORS[METHODS[i]] for i in range(len(METHODS)) if finite_mask[i]],
        edgecolor="#24313d",
        linewidth=0.55,
        alpha=0.90,
        yerr=sds[finite_mask],
        error_kw={"ecolor": "#24313d", "elinewidth": 0.85, "capsize": 3, "capthick": 0.85},
        zorder=2,
    )
    ax.scatter(x[finite_mask], means[finite_mask], s=16, color="#17212b", zorder=4, linewidths=0)
    lo, hi = y_limits
    span = hi - lo
    for i, value in enumerate(means):
        if not np.isfinite(value):
            continue
        top = value + sds[i] if value >= 0 else value - sds[i]
        y = top + (0.018 * span if value >= 0 else -0.018 * span)
        ax.text(x[i], y, format_value(value), ha="center", va="bottom" if value >= 0 else "top", fontsize=8.2, color="#17212b", clip_on=False, zorder=5)
    if metric == "r2":
        ax.axhline(0.0, color="#303030", linewidth=1.0, linestyle=(0, (4, 2)), zorder=1)
    ax.set_ylim(*y_limits)
    ax.set_xticks(x)
    ax.set_xticklabels([METHOD_LABELS[m] for m in METHODS], fontsize=8.4)
    ax.tick_params(axis="y", labelsize=8.5)
    ax.grid(axis="y", color="#d9dee3", linewidth=0.65, alpha=0.85, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#9aa5ad")
    ax.spines["bottom"].set_color("#9aa5ad")
    if show_ylabel:
        ax.set_ylabel(METRIC_LABELS[metric], fontsize=10, fontweight="bold")
    if not show_xlabel:
        ax.tick_params(axis="x", labelbottom=False)


def smoke_banner(protocol: dict, summary: Sequence[Dict[str, Any]]) -> str:
    config = protocol.get("config", {}) if isinstance(protocol, dict) else {}
    epochs = config.get("epochs")
    seeds = config.get("seeds", [])
    temps = sorted({fnum(row.get("held_temperature_C")) for row in summary if finite(row.get("held_temperature_C"))})
    if epochs == 2 and len(seeds) == 1 and len(temps) == 1 and float(temps[0]) == 60.0:
        return "INTEGRATION TEST ONLY — 2 epochs, 1 seed, 60 °C"
    purpose = protocol.get("claims_and_scope", {}).get("benchmark_purpose", "unknown")
    if purpose == "integration_smoke":
        return f"INTEGRATION TEST ONLY — {epochs} epochs, {len(seeds)} seed(s)"
    if purpose == "retrospective_benchmark":
        return f"Retrospective endpoint benchmark — {epochs} max epochs, {len(seeds)} seeds"
    return "Endpoint metrics — execution status unverified"


def subtitle(fraction: float, summary: Sequence[Dict[str, Any]]) -> str:
    targets = len({str(row["target"]) for row in summary})
    temps = len({fnum(row["held_temperature_C"]) for row in summary})
    return f"Fraction={fraction:g} · {targets} target system(s) · {temps} held-temperature facet(s) · {len(summary)} summary rows · no protocol selection"


def footer_text() -> str:
    return "RMSE/MAE: q as recorded (unit unconfirmed); no mg/g claim. Bars are computational means; error bars are computational SD, not confidence intervals. R² is unclipped and includes the zero reference."


def save_figure(fig: plt.Figure, out_base: Path) -> None:
    fig.savefig(out_base.with_suffix(".png"), dpi=150, facecolor="white")
    svg_path = out_base.with_suffix(".svg")
    fig.savefig(svg_path, facecolor="white")
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text().splitlines()) + "\n")
    plt.close(fig)


def plot_metric_figure(summary: Sequence[Dict[str, Any]], metric: str, targets: Sequence[str], held_temps: Sequence[float], fraction: float, banner: str, out_base: Path) -> None:
    nrows, ncols = len(targets), len(held_temps)
    figsize = (12.0, 8.0) if ncols == 1 and nrows <= 2 else (max(12.0, 4.2 * ncols), max(7.0, 3.6 * nrows + 1.2))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False, sharey=True)
    y_limits = metric_ylim(summary, metric)
    for r, target in enumerate(targets):
        for c, held_temp in enumerate(held_temps):
            ax = axes[r, c]
            panel = panel_rows(summary, target, held_temp)
            plot_panel(ax, panel, metric, y_limits, show_ylabel=(c == 0), show_xlabel=(r == nrows - 1))
            nseed = max([fnum(row.get("n_seed")) for row in panel.values() if finite(row.get("n_seed"))] or [float("nan")])
            seed_note = f" · n seed={int(nseed)}" if finite(nseed) else ""
            ax.set_title(f"{target}\nheld-out {format_temp(float(held_temp))}{seed_note}", fontsize=10, fontweight="bold", pad=8)
            if not panel:
                ax.text(0.5, 0.5, "No retained row", ha="center", va="center", transform=ax.transAxes, color="#65717b", fontsize=10)
    fig.suptitle(banner, fontsize=18, fontweight="bold", y=0.985)
    fig.text(0.5, 0.945, METRIC_TITLES[metric], ha="center", va="center", fontsize=13)
    fig.text(0.5, 0.918, subtitle(fraction, summary), ha="center", va="center", fontsize=9.5, color="#45515b")
    fig.text(0.5, 0.012, footer_text(), ha="center", va="bottom", fontsize=8.6, color="#45515b")
    fig.tight_layout(rect=[0.025, 0.075, 0.985, 0.89], h_pad=1.7, w_pad=1.8)
    save_figure(fig, out_base)


def plot_combined_figure(summary: Sequence[Dict[str, Any]], targets: Sequence[str], held_temps: Sequence[float], fraction: float, banner: str, out_base: Path) -> None:
    one_temp = len(held_temps) == 1
    if one_temp:
        nrows, ncols = len(METRICS), len(targets)
    else:
        nrows, ncols = len(METRICS) * len(targets), len(held_temps)
    figsize = (12.0, 10.0 if len(targets) <= 2 else max(10.0, 3.5 * nrows)) if one_temp else (max(12.0, 4.0 * ncols), max(10.0, 2.9 * nrows + 1.5))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False, sharey=False)
    limits = {metric: metric_ylim(summary, metric) for metric in METRICS}
    if one_temp:
        for r, metric in enumerate(METRICS):
            for c, target in enumerate(targets):
                ax = axes[r, c]
                plot_panel(ax, panel_rows(summary, target, held_temps[0]), metric, limits[metric], show_ylabel=(c == 0), show_xlabel=(r == len(METRICS) - 1))
                ax.set_title(f"{target}\n{METRIC_LABELS[metric]} · held-out {format_temp(float(held_temps[0]))}", fontsize=10, fontweight="bold", pad=7)
    else:
        index = 0
        for metric in METRICS:
            for target in targets:
                for held_temp in held_temps:
                    r, c = divmod(index, ncols)
                    ax = axes[r, c]
                    plot_panel(ax, panel_rows(summary, target, held_temp), metric, limits[metric], show_ylabel=(c == 0), show_xlabel=(r == nrows - 1))
                    ax.set_title(f"{target}\n{METRIC_LABELS[metric]} · held-out {format_temp(float(held_temp))}", fontsize=9, fontweight="bold", pad=6)
                    index += 1
    fig.suptitle(banner, fontsize=18, fontweight="bold", y=0.985)
    fig.text(0.5, 0.943, "Combined endpoint comparison — R², RMSE and MAE", ha="center", va="center", fontsize=13)
    fig.text(0.5, 0.914, subtitle(fraction, summary), ha="center", va="center", fontsize=9.5, color="#45515b")
    fig.text(0.5, 0.012, footer_text(), ha="center", va="bottom", fontsize=8.6, color="#45515b")
    fig.tight_layout(rect=[0.025, 0.075, 0.985, 0.86], h_pad=1.55, w_pad=1.8)
    save_figure(fig, out_base)


def save_plotted_raw_data(summary: Sequence[Dict[str, Any]], out_dir: Path) -> Path:
    columns = ["target", "fraction", "protocol", "held_temperature_C", "n_seed", "n_raw_rows", "r2", "r2_sd", "rmse", "rmse_sd", "mae", "mae_sd", "data_source"]
    rows = sorted(summary, key=lambda row: (str(row.get("target")), fnum(row.get("held_temperature_C")), str(row.get("protocol"))))
    path = out_dir / "plotted_raw_data.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})
    return path


def save_notes(out_dir: Path, results: Path, fraction: float, summary: Sequence[Dict[str, Any]], data_source: str, source_rows_excluded: int, methods_present: int, protocol: dict) -> Path:
    config = protocol.get("config", {}) if isinstance(protocol, dict) else {}
    epochs = config.get("epochs", "não informado")
    seeds = config.get("seeds", sorted({row.get("n_seed") for row in summary}))
    targets = list(dict.fromkeys(str(row["target"]) for row in summary))
    temps = sorted({fnum(row["held_temperature_C"]) for row in summary})
    lines = [
        "# Notas dos gráficos de endpoint", "",
        "## Propósito", "",
        f"Os gráficos comparam os protocolos de endpoint retidos para a fração solicitada. Status: {protocol.get('claims_and_scope', {}).get('benchmark_purpose', 'unverified')}. Saídas integration_smoke não são resultados científicos finais; retrospective_benchmark continua sendo avaliação retrospectiva, não confirmação experimental independente.", "",
        "## Configuração detectada", "",
        f"- Resultados: `{results}`",
        f"- Fração fixa: `{fraction:g}` (nenhuma fração foi escolhida por desempenho).",
        f"- Épocas: `{epochs}`; seeds declaradas: `{seeds}`.",
        f"- Held temperatures retidas: `{', '.join(format_temp(value) for value in temps)}`.",
        f"- Sistemas/alvos retidos: `{', '.join(targets)}`.",
        f"- Métodos presentes: `{methods_present}/6` — {', '.join(METHODS)}.", "",
        "## Dados e contagens", "",
        f"- Arquivo resumido plotado: `{data_source}`.",
        f"- Linhas-resumo plotadas: `{len(summary)}`; linhas brutas representadas: `{sum(int(fnum(row.get('n_raw_rows'), 0)) for row in summary)}`.",
        f"- Linhas com alvo identificado como source excluídas: `{source_rows_excluded}`.",
        "- Arquivos `source_metrics.csv`/`source_observed_predictions.csv` não foram usados nas figuras.",
        "- `simulation_predictions.csv` não foi usado; nenhum dado simulado foi plotado.", "",
        "## Métricas e leitura", "",
        "- R² foi plotado sem clipping, com linha de referência em zero e espaço para valores negativos.",
        "- RMSE e MAE são mostrados em `q as recorded (unit unconfirmed)`; não há afirmação de mg/g.",
        "- Barras representam médias computacionais; barras de erro, quando disponíveis, são SD computacional entre seeds, não intervalos de confiança.",
        "- Os números anotados são as médias brutas usadas no desenho; não há transformação ou combinação de RMSE entre sistemas.",
        "- Os painéis mantêm held temperature explícito; não há média silenciosa entre temperaturas.", "",
        "## Arquivos", "",
        "Foram produzidos três pares de figuras (R², RMSE, MAE), uma comparação combinada e o CSV dos dados efetivamente plotados. PNG é a versão raster legível; SVG preserva a versão vetorial.", "",
    ]
    path = out_dir / "plot_notes_pt.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate measured endpoint metric comparisons without selecting a best protocol.")
    parser.add_argument("--results", required=True, type=Path, help="Directory containing all_metrics.csv/fold_mean_sd.csv and protocol.json.")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: <results parent>/figures).")
    parser.add_argument("--fraction", type=float, default=1.0, help="Single target fraction to plot; default: 1.0.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    results = args.results.expanduser().resolve()
    if not results.is_dir():
        raise SystemExit(f"Results directory does not exist: {results}")
    out_dir = args.out.expanduser().resolve() if args.out is not None else results.parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not np.isfinite(args.fraction) or args.fraction < 0:
        raise SystemExit("--fraction must be a finite non-negative number.")
    protocol = protocol_config(results)
    summary, data_source, source_rows, methods_present = load_plot_data(results, args.fraction)
    targets = target_order(summary, protocol)
    held_temps = held_temperature_order(summary, protocol)
    if not targets or not held_temps:
        raise SystemExit("No target systems or held temperatures available after filtering.")
    banner = smoke_banner(protocol, summary)
    for metric in METRICS:
        plot_metric_figure(summary, metric, targets, held_temps, args.fraction, banner, out_dir / f"endpoint_metrics_{metric}")
    plot_combined_figure(summary, targets, held_temps, args.fraction, banner, out_dir / "endpoint_metrics_combined")
    raw_path = save_plotted_raw_data(summary, out_dir)
    notes_path = save_notes(out_dir, results, args.fraction, summary, data_source, source_rows, methods_present, protocol)
    print(f"results={results}")
    print(f"out={out_dir}")
    print(f"fraction={args.fraction:g}")
    print(f"data_source={data_source}")
    print(f"summary_rows={len(summary)} targets={len(targets)} held_temps={len(held_temps)}")
    print(f"methods_present={methods_present}/6 source_rows_excluded={source_rows}")
    for metric in METRICS:
        print(f"figure={out_dir / f'endpoint_metrics_{metric}.png'}")
        print(f"figure={out_dir / f'endpoint_metrics_{metric}.svg'}")
    print(f"figure={out_dir / 'endpoint_metrics_combined.png'}")
    print(f"figure={out_dir / 'endpoint_metrics_combined.svg'}")
    print(f"raw_data={raw_path}")
    print(f"notes={notes_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlotDataError as exc:
        raise SystemExit(f"plot_endpoint_metrics.py: {exc}") from exc
