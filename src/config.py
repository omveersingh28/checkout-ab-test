"""Paths, constants and three tiny helpers shared by all scripts.

Everything is built from the location of this file, so the project works from any
folder on any computer (no absolute paths are written anywhere).
"""
import sqlite3
from pathlib import Path

# ---- Paths (all relative to the project root) -------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "maven.db"
SQL_DIR = ROOT / "sql"
RESULTS_DIR = ROOT / "results"
CHARTS_DIR = ROOT / "reports" / "charts"

# ---- Constants --------------------------------------------------------------------------
SEED = 42      # one fixed seed so the bootstrap gives the same numbers on every run
ALPHA = 0.05   # significance level for the A/B test (two-sided)
POWER = 0.80   # power used for the minimum-detectable-effect calculation
N_BOOT = 2000  # number of bootstrap resamples

CONTROL = "/billing"      # old billing page
TREATMENT = "/billing-2"  # new billing page

# Same colour for the same variant in every chart, so the reader learns it once.
COLOR_CONTROL = "#2a78d6"    # blue   = old page (/billing)
COLOR_TREATMENT = "#eb6834"  # orange = new page (/billing-2)
COLOR_NEUTRAL = "#52514e"    # dark grey = charts that are not about the two variants
COLOR_MARKER = "#898781"     # light grey = vertical "event" lines and their labels


def connect():
    """Open the SQLite database (it is created by src/01_build_database.py)."""
    return sqlite3.connect(DB_PATH)


def load_queries(filename):
    """Read a .sql file and return {query_name: query_text}.

    Why: the SQL lives in sql/ as a deliverable. Each query in a file starts with a
    comment line '-- name: something', so Python can pick a query by its name.
    """
    queries, name, lines = {}, None, []
    for line in (SQL_DIR / filename).read_text().splitlines():
        if line.startswith("-- name:"):
            if name:
                queries[name] = "\n".join(lines)
            name, lines = line.replace("-- name:", "").strip(), []
        elif name:
            lines.append(line)
    if name:
        queries[name] = "\n".join(lines)
    return queries


def apply_chart_style():
    """One quiet, consistent look for every chart: light grid, no box around the plot."""
    import matplotlib
    matplotlib.use("Agg")  # draw straight to PNG files; no window needed
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 120, "savefig.dpi": 150, "savefig.bbox": "tight",
        "figure.facecolor": "white", "axes.facecolor": "white",
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.labelcolor": "#52514e",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#c3c2b7", "axes.grid": True, "axes.axisbelow": True,
        "grid.color": "#e1e0d9", "grid.linewidth": 0.8,
        "xtick.color": "#52514e", "ytick.color": "#52514e",
        "legend.frameon": False, "lines.linewidth": 2,
    })
    return plt
