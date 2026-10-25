"""Diminishing-return and relic figures, in the style of the old plots."""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

_BAND_ALPHA = 0.2

FIGURES_DIR = os.path.join("figures", "dr")


def write_plots(result, out_dir: str = FIGURES_DIR) -> tuple[str, str]:
    """Writes the derivative plot and the relic plot. Returns both paths."""
    os.makedirs(out_dir, exist_ok=True)
    stem = result.name.replace("/", "_").replace(os.sep, "_")
    derivative_path = os.path.join(out_dir, f"drMPC_{stem}.png")
    relic_path = os.path.join(out_dir, f"relics_{stem}.png")
    _save_derivatives(derivative_path, result)
    _save_relics(relic_path, result)
    return derivative_path, relic_path


def _save_derivatives(path: str, result) -> None:
    fig, ax = _setup_figure(
        f"Diminishing returns: Mastery vs Power vs Crit - {result.name}",
        result.xlabel,
        r"$\partial\,\mathrm{DPS}\;/\;\partial\,\mathrm{Rating}$  (DPS per rating point)",
    )
    _plot_bands(ax, result.crit, (
        ("Mastery", "blue", result.mastery_slope, result.mastery_sigma),
        ("Power", "orange", result.power_slope, result.power_sigma),
        (result.sweep_label, "red", result.crit_slope, result.crit_sigma),
    ))
    _add_footer(fig, result.game_version, result.author)
    _finish(fig, path)


def _save_relics(path: str, result) -> None:
    fig, ax = _setup_figure(
        f"Relics: Mastery vs Power vs Crit - {result.name}",
        result.xlabel,
        r"$\partial\,\mathrm{DPS}$ vs. no relics",
    )
    ax.set_title(result.gear_label, fontsize="small")
    _plot_bands(ax, result.crit, result.relic_gains)
    _add_footer(fig, result.game_version, result.author)
    _finish(fig, path)


def _setup_figure(title: str, xlabel: str, ylabel: str):
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot()
    fig.suptitle(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid()
    ax.set_axisbelow(True)
    return fig, ax


def _plot_bands(ax, crit, series) -> None:
    """Draws each curve with a 1σ band in the same color."""
    handles = []
    for label, color, values, sigma in series:
        line, = ax.plot(crit, values, color=color, label=label, zorder=3)
        ax.fill_between(
            crit,
            values - sigma,
            values + sigma,
            color=color,
            alpha=_BAND_ALPHA,
            linewidth=0,
            zorder=2,
        )
        handles.append(line)
    handles.append(Patch(facecolor="0.45", alpha=_BAND_ALPHA, label="1σ"))
    ax.legend(handles=handles)


def _add_footer(fig, version: str, author: str) -> None:
    fig.text(
        0.99,
        0.01,
        f"{version}, by {author}",
        ha="right",
        va="bottom",
        fontsize="small",
    )


def _finish(fig, path: str) -> None:
    fig.tight_layout(rect=(0.0, 0.04, 1.0, 0.95))
    fig.savefig(path, dpi=300)
    plt.close(fig)
