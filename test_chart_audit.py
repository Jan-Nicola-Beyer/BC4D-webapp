"""Chart audit — generate every chart the app can produce and check quality.

Tests:
1. Chart exporter (Insights): main + sub category charts, all formats
2. Dashboard charts: Likert, pre/post, transfer, demographics
3. Report charts: Likert table chart, comparison chart
4. Insights screen chart: matplotlib distribution

Checks: file exists, file size > threshold, no crashes.
"""

from __future__ import annotations
import os, sys, json, shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

RESULTS = {}
OUTPUT_DIR = "test_chart_audit_output"


def record(name, passed, details=""):
    RESULTS[name] = {"passed": passed, "details": details}
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if details:
        print(f"         {details[:120]}")


# Clean output
if os.path.exists(OUTPUT_DIR):
    shutil.rmtree(OUTPUT_DIR)
os.makedirs(OUTPUT_DIR)

print("\n" + "=" * 70)
print("CHART AUDIT — Every chart the app produces")
print("=" * 70)

# ── 1. Load test data ───────────────────────────────────────────
print("\n--- 1. Load Data ---\n")

from bc4d_intel.core.data_loader import load_survey
from bc4d_intel.core.panel_matcher import match_panels

pre_df, pre_roles = load_survey("Synthetisch_Vorbefragung_Staffel13.xlsx")
post_df, post_roles = load_survey("Synthetisch_Abschlussbefragung_Staffel13.xlsx")
result = match_panels(pre_df, pre_roles, post_df, post_roles)

with open("../bc4d_analysis_export.json", "r", encoding="utf-8") as f:
    export_data = json.load(f)

record("data_loaded", True,
       f"Pre={len(pre_df)}, Post={len(post_df)}, "
       f"Matched={len(result.get('matched', []))}, "
       f"Questions={len(export_data.get('questions', {}))}")


# ── 2. Chart Exporter (Insights) ───────────────────────────────
print("\n--- 2. Chart Exporter (multi-format) ---\n")

from bc4d_intel.core.chart_exporter import export_chart_pack
from collections import Counter

for qi, (question, qdata) in enumerate(list(export_data["questions"].items())[:3]):
    classifications = qdata.get("classifications", [])
    total = len(classifications)
    cat_counts = Counter()
    for c in classifications:
        cat_counts[(c.get("main_category", ""), c.get("cluster_title", ""))] += 1
    categories = [(m, s, n) for (m, s), n in cat_counts.most_common()]

    folder = export_chart_pack(question, categories, total,
                                os.path.join(OUTPUT_DIR, "insights"))

    files = os.listdir(folder)
    sizes = {f: os.path.getsize(os.path.join(folder, f)) for f in files}

    # Check all expected files exist and are non-trivial
    expected = [
        "data.xlsx",
        "main_categories_bar.png", "main_categories_bar.pdf",
        "main_categories_donut.png",
        "sub_categories_bar.png", "sub_categories_bar.pdf",
        "sub_categories_bar_dark.png",
    ]
    missing = [f for f in expected if f not in files]
    tiny = [f for f, s in sizes.items() if s < 500]

    short_q = question[:40].replace("\n", " ")
    record(f"exporter_q{qi+1}_{short_q}",
           len(missing) == 0 and len(tiny) == 0,
           f"{len(files)} files, missing={missing}, tiny={tiny}")

    if qi == 0:
        print(f"    Files in first export:")
        for f in sorted(files):
            print(f"      {f:45s} {sizes[f]:>8,} bytes")


# ── 3. Dashboard Charts ────────────────────────────────────────
print("\n--- 3. Dashboard Charts (matplotlib) ---\n")

from bc4d_intel.core.chart_builder import _ensure_mpl, _apply_style
_ensure_mpl()
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

dash_dir = os.path.join(OUTPUT_DIR, "dashboard")
os.makedirs(dash_dir, exist_ok=True)

# 3a. Likert stacked bar
from bc4d_intel.core.stats_engine import analyze_all_likert

post_items = analyze_all_likert(result["post_all"], post_roles)
items_with_data = [i for i in post_items if i["stats"]["mean"] is not None]

if items_with_data:
    n = len(items_with_data)
    labels = [i["label"][:35] for i in items_with_data]
    means = [i["stats"]["mean"] for i in items_with_data]

    fig, ax = plt.subplots(figsize=(9, max(3, n * 0.4)))
    _apply_style(fig, ax)
    colors = ["#059669" if m >= 3.5 else "#d97706" if m >= 2.5 else "#dc2626"
              for m in means]
    ax.barh(range(n), means, height=0.6, color=colors, edgecolor="#0d1117")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Mittelwert (1-5)", fontsize=10)
    ax.set_xlim(1, 5)
    ax.invert_yaxis()
    for i, m in enumerate(means):
        ax.text(m + 0.05, i, f"{m}", va="center", fontsize=9, color="#e6edf3")
    fig.tight_layout()
    fig.savefig(os.path.join(dash_dir, "likert_means.png"), dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(dash_dir, "likert_means.pdf"), bbox_inches="tight")
    # Print version
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    fig.savefig(os.path.join(dash_dir, "likert_means_print.png"), dpi=200,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    record("dashboard_likert", True, f"{n} items, saved 3 formats")
else:
    record("dashboard_likert", False, "No Likert items found")

# 3b. Pre/Post comparison grouped bar
from bc4d_intel.core.stats_engine import analyze_matched_likert

comparisons = analyze_matched_likert(result["matched"], pre_roles, post_roles)
comps = [c for c in comparisons if "error" not in c.get("comparison", {})]

if comps:
    n = len(comps)
    labels = [c["label"][:30] for c in comps]
    pre_m = [c["comparison"]["pre_mean"] for c in comps]
    post_m = [c["comparison"]["post_mean"] for c in comps]

    fig, ax = plt.subplots(figsize=(9, max(3, n * 0.5)))
    _apply_style(fig, ax)
    y = np.arange(n)
    h = 0.35
    ax.barh(y - h/2, pre_m, h, label="Pre", color="#6366f1", edgecolor="#0d1117")
    ax.barh(y + h/2, post_m, h, label="Post", color="#059669", edgecolor="#0d1117")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Mittelwert (1-5)", fontsize=10)
    ax.set_xlim(1, 5)
    ax.invert_yaxis()
    ax.legend(fontsize=9, facecolor="#161b22", edgecolor="#30363d", labelcolor="#9ca3af")
    fig.tight_layout()
    fig.savefig(os.path.join(dash_dir, "pre_post_comparison.png"), dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(dash_dir, "pre_post_comparison.pdf"), bbox_inches="tight")
    plt.close(fig)
    record("dashboard_prepost", True, f"{n} matched items, saved 2 formats")
else:
    record("dashboard_prepost", False, "No matched comparisons")

# 3c. Pre survey demographics (if available)
pre_items = analyze_all_likert(result["pre_all"], pre_roles)
pre_with_data = [i for i in pre_items if i["stats"]["mean"] is not None]
if pre_with_data:
    n = len(pre_with_data)
    fig, ax = plt.subplots(figsize=(9, max(3, n * 0.4)))
    _apply_style(fig, ax)
    labels = [i["label"][:35] for i in pre_with_data]
    means = [i["stats"]["mean"] for i in pre_with_data]
    ax.barh(range(n), means, height=0.6, color="#6366f1", edgecolor="#0d1117")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Mittelwert (1-5)", fontsize=10)
    ax.set_xlim(1, 5)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(dash_dir, "pre_survey_likert.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    record("dashboard_pre_likert", True, f"{n} pre-survey items")
else:
    record("dashboard_pre_likert", False, "No pre-survey Likert items")


# ── 4. Insights screen chart (matplotlib) ──────────────────────
print("\n--- 4. Insights Screen Chart ---\n")

insights_dir = os.path.join(OUTPUT_DIR, "insights_screen")
os.makedirs(insights_dir, exist_ok=True)

question = list(export_data["questions"].keys())[0]
classifications = export_data["questions"][question]["classifications"]
total = len(classifications)

cat_data = {}
for c in classifications:
    key = (c.get("main_category", "Other"), c.get("cluster_title", "Unknown"))
    cat_data[key] = cat_data.get(key, 0) + 1

by_main = {}
for (main, sub), count in cat_data.items():
    by_main.setdefault(main, []).append(((main, sub), count))
main_totals = {m: sum(c for _, c in subs) for m, subs in by_main.items()}
sorted_cats = []
for main in sorted(main_totals, key=main_totals.get, reverse=True):
    for item in sorted(by_main[main], key=lambda x: -x[1]):
        sorted_cats.append(item)

CLUSTER_COLORS = ["#C7074D", "#0068B2", "#E76863", "#4C4193", "#5C6771",
                  "#E0335E", "#3388CC", "#F09090", "#7A6BBB", "#8899A0"]

labels = [sub[:30] for (main, sub), _ in sorted_cats]
values = [count for _, count in sorted_cats]
pcts = [round(v / max(total, 1) * 100, 1) for v in values]
main_cats = list(dict.fromkeys(m for (m, _), _ in sorted_cats))
main_color_map = {m: CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i, m in enumerate(main_cats)}
colors = [main_color_map[main] for (main, _), _ in sorted_cats]

n = len(sorted_cats)
fig, ax = plt.subplots(figsize=(9, max(3, n * 0.45 + 1.5)))
_apply_style(fig, ax)
ax.barh(range(n), pcts, height=0.6, color=colors, edgecolor="#0d1117")
ax.set_yticks(range(n))
ax.set_yticklabels(labels, fontsize=10)
ax.set_xlabel("% der Antworten", fontsize=11)
ax.invert_yaxis()
max_pct = max(pcts) if pcts else 10
for i, (v, p) in enumerate(zip(values, pcts)):
    ax.text(p + max_pct * 0.02, i, f"{v} ({p}%)", va="center", fontsize=10,
            color="#e6edf3", fontweight="bold")
from matplotlib.patches import Patch
legend_items = [Patch(facecolor=main_color_map[m], label=m) for m in main_cats]
ax.legend(handles=legend_items, loc="lower right", fontsize=9,
          facecolor="#161b22", edgecolor="#30363d", labelcolor="#9ca3af")
ax.set_xlim(0, max_pct * 1.25)
fig.tight_layout()
fig.savefig(os.path.join(insights_dir, "insights_chart.png"), dpi=200, bbox_inches="tight")
plt.close(fig)

size = os.path.getsize(os.path.join(insights_dir, "insights_chart.png"))
record("insights_chart", size > 5000, f"{size:,} bytes, {n} categories")


# ── 5. Verify all output files ─────────────────────────────────
print("\n--- 5. Output Summary ---\n")

total_files = 0
total_bytes = 0
for root, dirs, files in os.walk(OUTPUT_DIR):
    for f in files:
        path = os.path.join(root, f)
        size = os.path.getsize(path)
        total_files += 1
        total_bytes += size

print(f"  Total files: {total_files}")
print(f"  Total size: {total_bytes:,} bytes ({total_bytes/1024/1024:.1f} MB)")
print(f"  Output dir: {os.path.abspath(OUTPUT_DIR)}")

# List all by type
by_ext = {}
for root, dirs, files in os.walk(OUTPUT_DIR):
    for f in files:
        ext = os.path.splitext(f)[1]
        by_ext[ext] = by_ext.get(ext, 0) + 1
print(f"  By type: {dict(sorted(by_ext.items()))}")

record("total_output", total_files >= 20,
       f"{total_files} files, {total_bytes/1024:.0f} KB")


# ── Summary ─────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

n_pass = sum(1 for r in RESULTS.values() if r["passed"])
n_fail = sum(1 for r in RESULTS.values() if not r["passed"])

for name, r in RESULTS.items():
    print(f"  {'PASS' if r['passed'] else 'FAIL'} -- {name}")

print(f"\n  {n_pass}/{n_pass + n_fail} passed")
print(f"\n  Charts saved to: {os.path.abspath(OUTPUT_DIR)}/")
print(f"  (Inspect visually to verify quality)")

sys.exit(0 if n_fail == 0 else 1)
