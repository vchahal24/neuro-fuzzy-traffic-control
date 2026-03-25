# PLOT RESULTS STAGE
# Purpose: read experiment output CSV and generate baseline vs ANFIS comparison plots
# supports two input styles
# 1. long rows (one row per controller per count_id)
# 2. paired columns (baseline_* and anfis_* in same row)

from __future__ import annotations

# command line args
import argparse

# structured holder for all cleaned plotting data
from dataclasses import dataclass

# output file path handling
from pathlib import Path

# plotting + numeric
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# global dark mode toggle
darkThemeEnabled = False


# everything needed for plotting in one object
@dataclass
class Object:
    pairedDataFrame: pd.DataFrame
    longDataFrame: pd.DataFrame
    delayImprovePctSeries: pd.Series
    baselineZeroDelayRows: int
    baselineCtrlName: str
    anfisCtrlName: str


# parse CLI args
def parseCLIArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create result plots from experiment CSV.")

    parser.add_argument("--results", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--baseline-controller", default="baseline_fixed")
    parser.add_argument("--anfis-controller", default="anfis")
    parser.add_argument("--demand-bins", type=int, default=4)
    parser.add_argument("--timeseries", default="")
    parser.add_argument("--timeseries-count-id", default="")
    parser.add_argument("--dark-theme", action="store_true")
    parser.add_argument("--report-style", action="store_true")

    return parser.parse_args()


# set matplotlib dark theme defaults
def setDarkTheme(darkTheme: bool) -> None:
    global darkThemeEnabled
    darkThemeEnabled = darkTheme
    match darkTheme:
        case False:
            return
        case True:
            plt.rcParams.update(
                {
                    "figure.facecolor": "black",
                    "axes.facecolor": "black",
                    "savefig.facecolor": "black",
                    "text.color": "white",
                    "axes.labelcolor": "white",
                    "axes.edgecolor": "white",
                    "xtick.color": "white",
                    "ytick.color": "white",
                    "legend.facecolor": "black",
                    "legend.edgecolor": "white",
                }
            )


# force dark colors on each figure object
# this makes sure legends/spines/text still look right in dark mode
def applyDarkThemeToFigure(fig: plt.Figure) -> None:
    match darkThemeEnabled:
        case False:
            return
        case True:
            pass

    fig.patch.set_facecolor("black")
    for ax in fig.axes:
        ax.set_facecolor("black")
        ax.title.set_color("white")
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("white")

        legend = ax.get_legend()
        if legend is not None:
            legend.get_frame().set_facecolor("black")
            legend.get_frame().set_edgecolor("white")
            for txt in legend.get_texts():
                txt.set_color("white")
            legendTitle = legend.get_title()
            if legendTitle is not None:
                legendTitle.set_color("white")


# safe numeric conversion helper
def toNumericSafe(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


# simple 95% CI helper for bar plot
def calc95Ci(series: pd.Series) -> float:
    cleanSeries = toNumericSafe(series).dropna()
    count = len(cleanSeries)
    if count <= 1:
        return 0.0
    return float(1.96 * cleanSeries.std(ddof=1) / np.sqrt(count))


# finds the first candidate column that exists (case-insensitive)
def findColumn(columns: list[str], candidates: list[str]) -> str:
    loweredMap = {col.lower(): col for col in columns}
    for cand in candidates:
        if cand.lower() in loweredMap:
            return loweredMap[cand.lower()]
    raise KeyError(f"Could not find any of columns: {candidates}")

# build plot context when CSV is long format rows
def buildPlotContextLong(
    allRows: pd.DataFrame,
    baselineCtrlName: str,
    anfisCtrlName: str,
) -> Object:
    requiredCols = [
        "count_id",
        "controller",
        "avg_delay_per_vehicle_seconds",
        "throughput_vehicles",
        "max_queue_vehicles",
    ]
    missingCols = [col for col in requiredCols if col not in allRows.columns]
    if missingCols:
        raise ValueError(f"Long-format input missing required columns: {missingCols}")

    baselineRows = allRows[allRows["controller"] == baselineCtrlName].copy()
    anfisRows = allRows[allRows["controller"] == anfisCtrlName].copy()
    match (baselineRows.empty, anfisRows.empty):
        case (True, _):
            raise ValueError(f"No rows found for baseline controller '{baselineCtrlName}'.")
        case (_, True):
            raise ValueError(f"No rows found for ANFIS controller '{anfisCtrlName}'.")
        case _:
            pass

    baselineRows = baselineRows.rename(
        columns={
            "avg_delay_per_vehicle_seconds": "baseline_delay",
            "throughput_vehicles": "baseline_throughput",
            "max_queue_vehicles": "baseline_max_queue",
        }
    )
    anfisRows = anfisRows.rename(
        columns={
            "avg_delay_per_vehicle_seconds": "anfis_delay",
            "throughput_vehicles": "anfis_throughput",
            "max_queue_vehicles": "anfis_max_queue",
        }
    )

    pairedDf = baselineRows[["count_id", "baseline_delay", "baseline_throughput", "baseline_max_queue"]].merge(
        anfisRows[["count_id", "anfis_delay", "anfis_throughput", "anfis_max_queue"]],
        on="count_id",
        how="inner",
    )

    for col in ["leg_type", "total_vehicle_day", "peak_hour_start"]:
        if col in baselineRows.columns and col not in pairedDf.columns:
            pairedDf = pairedDf.merge(
                baselineRows[["count_id", col]].drop_duplicates("count_id"),
                on="count_id",
                how="left",
            )

    baselineDelaySeries = toNumericSafe(pairedDf["baseline_delay"])
    anfisDelaySeries = toNumericSafe(pairedDf["anfis_delay"])
    delayImprovePctSeries = ((baselineDelaySeries - anfisDelaySeries) / baselineDelaySeries.replace(0, np.nan)) * 100.0

    return Object(
        pairedDataFrame=pairedDf,
        longDataFrame=allRows[allRows["controller"].isin([baselineCtrlName, anfisCtrlName])].copy(),
        delayImprovePctSeries=delayImprovePctSeries,
        baselineZeroDelayRows=int((baselineDelaySeries == 0).sum()),
        baselineCtrlName=baselineCtrlName,
        anfisCtrlName=anfisCtrlName,
    )


# build plot context when CSV is paired format columns
def buildPlotContextPaired(allRows: pd.DataFrame) -> Object:
    allCols = list(allRows.columns)

    baselineDelayCol = findColumn(allCols, ["baseline_avg_delay_per_vehicle_seconds", "baseline_delay", "baseline_avg_delay_per_vehicle"])
    anfisDelayCol = findColumn(allCols, ["anfis_avg_delay_per_vehicle_seconds", "anfis_delay", "anfis_avg_delay_per_vehicle"])
    baselineThroughputCol = findColumn(allCols, ["baseline_throughput_vehicles", "baseline_throughput"])
    anfisThroughputCol = findColumn(allCols, ["anfis_throughput_vehicles", "anfis_throughput"])
    baselineQueueCol = findColumn(allCols, ["baseline_max_queue_vehicles", "baseline_max_queue"])
    anfisQueueCol = findColumn(allCols, ["anfis_max_queue_vehicles", "anfis_max_queue"])

    pairedDf = allRows.copy().rename(
        columns={
            baselineDelayCol: "baseline_delay",
            anfisDelayCol: "anfis_delay",
            baselineThroughputCol: "baseline_throughput",
            anfisThroughputCol: "anfis_throughput",
            baselineQueueCol: "baseline_max_queue",
            anfisQueueCol: "anfis_max_queue",
        }
    )

    if "count_id" not in pairedDf.columns:
        pairedDf["count_id"] = np.arange(len(pairedDf)).astype(str)

    baselineDelaySeries = toNumericSafe(pairedDf["baseline_delay"])
    anfisDelaySeries = toNumericSafe(pairedDf["anfis_delay"])
    delayImprovePctSeries = ((baselineDelaySeries - anfisDelaySeries) / baselineDelaySeries.replace(0, np.nan)) * 100.0

    longDf = pd.DataFrame(
        {
            "count_id": pd.concat([pairedDf["count_id"], pairedDf["count_id"]], ignore_index=True),
            "controller": ["baseline"] * len(pairedDf) + ["anfis"] * len(pairedDf),
            "avg_delay_per_vehicle_seconds": pd.concat([pairedDf["baseline_delay"], pairedDf["anfis_delay"]], ignore_index=True),
            "throughput_vehicles": pd.concat([pairedDf["baseline_throughput"], pairedDf["anfis_throughput"]], ignore_index=True),
            "max_queue_vehicles": pd.concat([pairedDf["baseline_max_queue"], pairedDf["anfis_max_queue"]], ignore_index=True),
        }
    )

    for col in ["leg_type", "total_vehicle_day", "peak_hour_start"]:
        if col in pairedDf.columns:
            longDf[col] = pd.concat([pairedDf[col], pairedDf[col]], ignore_index=True)

    return Object(
        pairedDataFrame=pairedDf,
        longDataFrame=longDf,
        delayImprovePctSeries=delayImprovePctSeries,
        baselineZeroDelayRows=int((baselineDelaySeries == 0).sum()),
        baselineCtrlName="baseline",
        anfisCtrlName="anfis",
    )


# auto pick correct context builder
def buildPlotContext(
    allRows: pd.DataFrame,
    baselineCtrlName: str,
    anfisCtrlName: str,
) -> Object:
    match "controller" in allRows.columns:
        case True:
            return buildPlotContextLong(allRows, baselineCtrlName, anfisCtrlName)
        case False:
            return buildPlotContextPaired(allRows)


# common save helper
def saveFigure(fig: plt.Figure, outPath: Path) -> None:
    applyDarkThemeToFigure(fig)
    fig.tight_layout()
    fig.savefig(outPath, dpi=220, facecolor=fig.get_facecolor())
    plt.close(fig)


def controllerDisplayName(name: str) -> str:
    mapping = {
        "baseline_fixed": "Fixed baseline",
        "baseline_proportional": "Proportional baseline",
        "neuro_fuzzy_octave": "Neuro-fuzzy Octave",
        "anfis": "ANFIS",
    }
    return mapping.get(str(name), str(name))


def addBarValueLabels(ax: plt.Axes, bars, fmt: str = "{:.2f}", suffix: str = "", fontsize: int = 10) -> None:
    for bar in bars:
        value = float(bar.get_height())
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            value,
            f"{fmt.format(value)}{suffix}",
            ha="center",
            va="bottom",
            fontsize=fontsize,
        )


def percentImprovement(oldVal: float, newVal: float) -> float:
    if oldVal == 0:
        return float("nan")
    return ((oldVal - newVal) / oldVal) * 100.0


def plotOverallImprovementSummary(plotCtx: Object, outPath: Path) -> None:
    baselineMean = float(toNumericSafe(plotCtx.pairedDataFrame["baseline_delay"]).mean())
    anfisMean = float(toNumericSafe(plotCtx.pairedDataFrame["anfis_delay"]).mean())
    improvePct = percentImprovement(baselineMean, anfisMean)

    baseName = controllerDisplayName(plotCtx.baselineCtrlName)
    anfisName = controllerDisplayName(plotCtx.anfisCtrlName)

    fig = plt.figure(figsize=(10.0, 6.2))
    ax = fig.add_subplot(111)
    compLabel = f"{anfisName} vs {baseName}"
    barColor = "#2a9d8f" if improvePct >= 0 else "#e76f51"
    bars = ax.bar([compLabel], [improvePct], color=[barColor], width=0.6)
    addBarValueLabels(ax, bars, fmt="{:.2f}", suffix="%", fontsize=12)
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_title(f"{anfisName} Improvement vs {baseName}", fontsize=15)
    ax.set_ylabel("Mean improvement vs baseline (%)", fontsize=12)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.tick_params(axis="both", labelsize=11)
    ax.text(
        0.5,
        0.95,
        f"Based on delay burden per served vehicle",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=10,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.7, "edgecolor": "#cccccc"},
    )
    saveFigure(fig, outPath)


def plotDelayPerIntersection(plotCtx: Object, outPath: Path) -> None:
    delayImprove = toNumericSafe(plotCtx.delayImprovePctSeries)
    tempDf = pd.DataFrame(
        {
            "count_id": plotCtx.pairedDataFrame["count_id"].astype(str),
            "improvement": delayImprove,
        }
    ).dropna()
    if tempDf.empty:
        return
    tempDf = tempDf.sort_values("improvement", ascending=False)

    fig = plt.figure(figsize=(10.5, max(5.0, 0.55 * len(tempDf) + 2.0)))
    ax = fig.add_subplot(111)
    colors = np.where(tempDf["improvement"] >= 0, "#2a9d8f", "#e76f51")
    bars = ax.barh(tempDf["count_id"], tempDf["improvement"], color=colors)
    ax.axvline(0.0, color="black", linewidth=1)
    ax.invert_yaxis()
    ax.set_title("Delay Improvement by Intersection", fontsize=14)
    ax.set_xlabel("Improvement (%)", fontsize=12)
    ax.set_ylabel("Count ID", fontsize=12)
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.tick_params(axis="both", labelsize=10)

    for bar, val in zip(bars, tempDf["improvement"]):
        x = bar.get_width()
        xOffset = 0.5 if x >= 0 else -0.5
        ha = "left" if x >= 0 else "right"
        ax.text(
            x + xOffset,
            bar.get_y() + bar.get_height() / 2.0,
            f"{val:.2f}%",
            va="center",
            ha=ha,
            fontsize=9,
        )
    saveFigure(fig, outPath)


def plotDelayDumbbell(plotCtx: Object, outPath: Path) -> None:
    tempDf = pd.DataFrame(
        {
            "count_id": plotCtx.pairedDataFrame["count_id"].astype(str),
            "baseline_delay": toNumericSafe(plotCtx.pairedDataFrame["baseline_delay"]),
            "anfis_delay": toNumericSafe(plotCtx.pairedDataFrame["anfis_delay"]),
        }
    ).dropna()
    if tempDf.empty:
        return
    tempDf = tempDf.sort_values("baseline_delay", ascending=False).reset_index(drop=True)
    yPos = np.arange(len(tempDf))

    baseName = controllerDisplayName(plotCtx.baselineCtrlName)
    anfisName = controllerDisplayName(plotCtx.anfisCtrlName)

    fig = plt.figure(figsize=(10.5, max(5.0, 0.55 * len(tempDf) + 2.0)))
    ax = fig.add_subplot(111)
    for idx, row in tempDf.iterrows():
        ax.plot([row["baseline_delay"], row["anfis_delay"]], [yPos[idx], yPos[idx]], color="#999999", linewidth=1.5)
    ax.scatter(tempDf["baseline_delay"], yPos, color="#4c78a8", s=45, label=baseName, zorder=3)
    ax.scatter(tempDf["anfis_delay"], yPos, color="#2a9d8f", s=45, label=anfisName, zorder=3)
    ax.set_yticks(yPos)
    ax.set_yticklabels(tempDf["count_id"])
    ax.invert_yaxis()
    ax.set_title("Per-Intersection Delay Burden: Baseline vs Neuro-fuzzy", fontsize=14)
    ax.set_xlabel("Delay burden per served vehicle (s)", fontsize=12)
    ax.set_ylabel("Count ID", fontsize=12)
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.tick_params(axis="both", labelsize=10)
    ax.legend(fontsize=10)
    saveFigure(fig, outPath)


def plotThroughputReadable(plotCtx: Object, outPath: Path) -> None:
    baselineMean = float(toNumericSafe(plotCtx.pairedDataFrame["baseline_throughput"]).mean())
    anfisMean = float(toNumericSafe(plotCtx.pairedDataFrame["anfis_throughput"]).mean())
    improvePct = float("nan") if baselineMean == 0 else ((anfisMean - baselineMean) / baselineMean) * 100.0

    baseName = controllerDisplayName(plotCtx.baselineCtrlName)
    anfisName = controllerDisplayName(plotCtx.anfisCtrlName)

    fig = plt.figure(figsize=(9.2, 6.0))
    ax = fig.add_subplot(111)
    bars = ax.bar([baseName, anfisName], [baselineMean, anfisMean], color=["#4c78a8", "#2a9d8f"])
    addBarValueLabels(ax, bars, fmt="{:.1f}", suffix="", fontsize=11)
    ax.set_title(f"Mean Throughput Comparison: {baseName} vs {anfisName}", fontsize=14)
    ax.set_ylabel("Throughput (vehicles)", fontsize=12)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.tick_params(axis="both", labelsize=11)
    ax.text(
        0.5,
        0.95,
        f"Throughput change: {improvePct:.2f}%",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=11,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.7, "edgecolor": "#cccccc"},
    )
    saveFigure(fig, outPath)


def plotMaxQueueReadable(plotCtx: Object, outPath: Path) -> None:
    baselineMean = float(toNumericSafe(plotCtx.pairedDataFrame["baseline_max_queue"]).mean())
    anfisMean = float(toNumericSafe(plotCtx.pairedDataFrame["anfis_max_queue"]).mean())
    improvePct = percentImprovement(baselineMean, anfisMean)

    baseName = controllerDisplayName(plotCtx.baselineCtrlName)
    anfisName = controllerDisplayName(plotCtx.anfisCtrlName)

    fig = plt.figure(figsize=(9.2, 6.0))
    ax = fig.add_subplot(111)
    bars = ax.bar([baseName, anfisName], [baselineMean, anfisMean], color=["#4c78a8", "#2a9d8f"])
    addBarValueLabels(ax, bars, fmt="{:.2f}", suffix="", fontsize=11)
    ax.set_title("Mean Maximum Queue Comparison (Lower is better)", fontsize=14)
    ax.set_ylabel("Maximum queue (vehicles)", fontsize=12)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.tick_params(axis="both", labelsize=11)
    ax.text(
        0.5,
        0.95,
        f"Queue reduction: {improvePct:.2f}%",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=11,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.7, "edgecolor": "#cccccc"},
    )
    saveFigure(fig, outPath)


def plotImprovementByCategory(plotCtx: Object, outPath: Path) -> None:
    sourceDf = plotCtx.pairedDataFrame.copy()
    sourceDf["improvement"] = toNumericSafe(plotCtx.delayImprovePctSeries)
    sourceDf = sourceDf.dropna(subset=["improvement"])
    if sourceDf.empty:
        return

    categoryLabel = ""
    if len(sourceDf) < 10:
        if "leg_type" in sourceDf.columns and sourceDf["leg_type"].notna().sum() > 0:
            sourceDf["category"] = sourceDf["leg_type"].astype(str)
            categoryLabel = "Leg type"
        elif "peak_hour_start" in sourceDf.columns and sourceDf["peak_hour_start"].notna().sum() > 0:
            sourceDf["category"] = sourceDf["peak_hour_start"].fillna("").astype(str).str[-5:].replace("", "unknown")
            categoryLabel = "Peak hour"
        else:
            return
    elif "leg_type" in sourceDf.columns and sourceDf["leg_type"].notna().sum() > 0:
        sourceDf["category"] = sourceDf["leg_type"].astype(str)
        categoryLabel = "Leg type"
    elif "peak_hour_start" in sourceDf.columns and sourceDf["peak_hour_start"].notna().sum() > 0:
        sourceDf["category"] = sourceDf["peak_hour_start"].fillna("").astype(str).str[-5:].replace("", "unknown")
        categoryLabel = "Peak hour"
    else:
        return

    grouped = sourceDf.groupby("category", dropna=False)["improvement"].mean().sort_values(ascending=False)
    if grouped.empty:
        return

    fig = plt.figure(figsize=(10.0, 5.8))
    ax = fig.add_subplot(111)
    bars = ax.bar(grouped.index.astype(str), grouped.values, color="#4c78a8")
    ax.axhline(0.0, color="black", linewidth=1)
    ax.set_title(f"Mean Delay Improvement by {categoryLabel}", fontsize=14)
    ax.set_ylabel("Improvement (%)", fontsize=12)
    ax.set_xlabel(categoryLabel, fontsize=12)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.tick_params(axis="both", labelsize=10)
    if len(grouped) > 4:
        ax.tick_params(axis="x", labelrotation=20)

    for bar, val in zip(bars, grouped.values):
        va = "bottom" if val >= 0 else "top"
        offset = 0.6 if val >= 0 else -0.6
        ax.text(bar.get_x() + bar.get_width() / 2.0, val + offset, f"{val:.2f}%", ha="center", va=va, fontsize=9)
    saveFigure(fig, outPath)


# optional fig 12 and fig 13 from optional timeseries CSV
def plotOptionalTimeSeries(args: argparse.Namespace, outDir: Path) -> list[Path]:
    match (bool(args.timeseries), bool(args.timeseries_count_id)):
        case (False, _) | (_, False):
            return []
        case _:
            pass

    timeSeriesPath = Path(args.timeseries)
    match timeSeriesPath.exists():
        case False:
            return []
        case True:
            pass

    timeSeriesDf = pd.read_csv(timeSeriesPath)
    requiredCols = {"count_id", "controller", "time_index", "queue_ns", "queue_ew"}
    match requiredCols.issubset(set(timeSeriesDf.columns)):
        case False:
            return []
        case True:
            pass

    selectedDf = timeSeriesDf[timeSeriesDf["count_id"].astype(str) == str(args.timeseries_count_id)].copy()
    match selectedDf.empty:
        case True:
            return []
        case False:
            pass

    outFiles: list[Path] = []
    queueDefs = [
        ("queue_ns", "fig12_queueNsTimeSeries.png", "queue NS over time"),
        ("queue_ew", "fig13_queueEwTimeSeries.png", "queue EW over time"),
    ]

    for queueCol, fileName, plotTitle in queueDefs:
        fig = plt.figure(figsize=(8.8, 5.0))
        ax = fig.add_subplot(111)
        for ctrlName, ctrlRows in selectedDf.groupby("controller"):
            xSeries = toNumericSafe(ctrlRows["time_index"])
            ySeries = toNumericSafe(ctrlRows[queueCol])
            validMask = xSeries.notna() & ySeries.notna()
            if validMask.sum() > 0:
                ax.plot(xSeries[validMask], ySeries[validMask], label=str(ctrlName))

        ax.set_title(f"{plotTitle} (count_id={args.timeseries_count_id})")
        ax.set_xlabel("time_index")
        ax.set_ylabel(queueCol)
        ax.legend()

        outPath = outDir / fileName
        saveFigure(fig, outPath)
        outFiles.append(outPath)

    return outFiles


# terminal summary at end so we can see what got generated
def printPlotSummary(plotCtx: Object, outFiles: list[Path]) -> None:
    pairedDf = plotCtx.pairedDataFrame.copy()
    pairedDf["delayImprovePct"] = toNumericSafe(plotCtx.delayImprovePctSeries)
    validImprove = toNumericSafe(pairedDf["delayImprovePct"]).dropna()
    throughputChange = (
        (toNumericSafe(pairedDf["anfis_throughput"]) - toNumericSafe(pairedDf["baseline_throughput"]))
        / toNumericSafe(pairedDf["baseline_throughput"]).replace(0, np.nan)
        * 100.0
    ).dropna()
    queueChange = (
        (toNumericSafe(pairedDf["baseline_max_queue"]) - toNumericSafe(pairedDf["anfis_max_queue"]))
        / toNumericSafe(pairedDf["baseline_max_queue"]).replace(0, np.nan)
        * 100.0
    ).dropna()

    improvedCount = int((validImprove > 0).sum())
    worsenedCount = int((validImprove < 0).sum())
    sameCount = int((validImprove == 0).sum())

    print("report summary:")
    print("- note: Delay metric shown in plots is a simulation-derived delay burden normalized by served vehicles; use relative comparison rather than absolute real-world interpretation.")
    print(f"- paired intersections: {len(pairedDf)}")
    print(f"- mean delay improvement %: {validImprove.mean():.3f}")
    print(f"- median delay improvement %: {validImprove.median():.3f}")
    print(f"- intersections improved: {improvedCount}")
    print(f"- intersections worsened: {worsenedCount}")
    print(f"- intersections unchanged: {sameCount}")

    if not validImprove.empty:
        bestIdx = validImprove.idxmax()
        worstIdx = validImprove.idxmin()
        bestCountId = str(pairedDf.loc[bestIdx, "count_id"])
        worstCountId = str(pairedDf.loc[worstIdx, "count_id"])
        print(f"- best intersection improvement: {bestCountId} ({validImprove.loc[bestIdx]:.3f}%)")
        print(f"- worst intersection improvement: {worstCountId} ({validImprove.loc[worstIdx]:.3f}%)")
    print(f"- mean throughput change %: {throughputChange.mean():.3f}")
    print(f"- mean max queue change %: {queueChange.mean():.3f}")

    print("- generated files:")
    for outPath in outFiles:
        print(f"  - {outPath}")


# run full plotting flow
def main() -> None:
    args = parseCLIArgs()
    setDarkTheme(args.dark_theme)

    resultsPath = Path(args.results)
    outDir = Path(args.out_dir)
    outDir.mkdir(parents=True, exist_ok=True)

    allRows = pd.read_csv(resultsPath)
    plotCtx = buildPlotContext(
        allRows,
        baselineCtrlName=args.baseline_controller,
        anfisCtrlName=args.anfis_controller,
    )

    outFiles: list[Path] = []
    plotJobs = [
        ("fig01_overallImprovementSummary.png", lambda: plotOverallImprovementSummary(plotCtx, outDir / "fig01_overallImprovementSummary.png")),
        ("fig02_delayPerIntersection.png", lambda: plotDelayPerIntersection(plotCtx, outDir / "fig02_delayPerIntersection.png")),
        ("fig03_delayDumbbell.png", lambda: plotDelayDumbbell(plotCtx, outDir / "fig03_delayDumbbell.png")),
        ("fig04_throughputReadable.png", lambda: plotThroughputReadable(plotCtx, outDir / "fig04_throughputReadable.png")),
        ("fig05_maxQueueReadable.png", lambda: plotMaxQueueReadable(plotCtx, outDir / "fig05_maxQueueReadable.png")),
        ("fig06_improvementByCategory.png", lambda: plotImprovementByCategory(plotCtx, outDir / "fig06_improvementByCategory.png")),
    ]

    for fileName, jobFunc in plotJobs:
        outPath = outDir / fileName
        jobFunc()
        if outPath.exists():
            outFiles.append(outPath)

    outFiles.extend(plotOptionalTimeSeries(args, outDir))
    printPlotSummary(plotCtx, outFiles)


if __name__ == "__main__":
    main()
