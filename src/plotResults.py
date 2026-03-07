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


# fig 01
def plotMeanDelay(plotCtx: Object, outPath: Path) -> None:
    delayCol = "avg_delay_per_vehicle_seconds"
    baselineSeries = toNumericSafe(plotCtx.longDataFrame[plotCtx.longDataFrame["controller"] == plotCtx.baselineCtrlName][delayCol]).dropna()
    anfisSeries = toNumericSafe(plotCtx.longDataFrame[plotCtx.longDataFrame["controller"] == plotCtx.anfisCtrlName][delayCol]).dropna()

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.bar(
        [plotCtx.baselineCtrlName, plotCtx.anfisCtrlName],
        [float(baselineSeries.mean()), float(anfisSeries.mean())],
        yerr=[calc95Ci(baselineSeries), calc95Ci(anfisSeries)],
        capsize=5,
    )
    ax.set_title("mean delay / veh (95% CI)")
    ax.set_ylabel("avg_delay_per_vehicle_seconds")
    ax.set_xlabel("controller")
    saveFigure(fig, outPath)


# fig 02
def plotDelayBox(plotCtx: Object, outPath: Path) -> None:
    baselineSeries = toNumericSafe(plotCtx.pairedDataFrame["baseline_delay"]).dropna()
    anfisSeries = toNumericSafe(plotCtx.pairedDataFrame["anfis_delay"]).dropna()

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.boxplot([baselineSeries, anfisSeries], labels=[plotCtx.baselineCtrlName, plotCtx.anfisCtrlName], showfliers=False)
    ax.set_title("delay distribution")
    ax.set_ylabel("avg_delay_per_vehicle_seconds")
    ax.set_xlabel("controller")
    saveFigure(fig, outPath)


# fig 03
def plotDelayImproveHist(plotCtx: Object, outPath: Path) -> None:
    improveSeries = toNumericSafe(plotCtx.delayImprovePctSeries).dropna()

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.hist(improveSeries, bins=20)
    ax.set_title("delay improvement pct distribution")
    ax.set_xlabel("improvement_pct")
    ax.set_ylabel("intersection_count")
    saveFigure(fig, outPath)


# fig 04
def plotCongestionVsImprove(plotCtx: Object, outPath: Path) -> None:
    xSeries = toNumericSafe(plotCtx.pairedDataFrame["baseline_delay"])
    ySeries = toNumericSafe(plotCtx.delayImprovePctSeries)
    validMask = xSeries.notna() & ySeries.notna()

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.scatter(xSeries[validMask], ySeries[validMask], alpha=0.75)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("benefit vs baseline congestion")
    ax.set_xlabel("baseline_avg_delay_per_vehicle_seconds")
    ax.set_ylabel("improvement_pct")
    saveFigure(fig, outPath)


# fig 05
def plotDemandVsImprove(plotCtx: Object, outPath: Path) -> None:
    if "total_vehicle_day" not in plotCtx.pairedDataFrame.columns:
        return

    xSeries = toNumericSafe(plotCtx.pairedDataFrame["total_vehicle_day"])
    ySeries = toNumericSafe(plotCtx.delayImprovePctSeries)
    validMask = xSeries.notna() & ySeries.notna()
    if validMask.sum() == 0:
        return

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.scatter(xSeries[validMask], ySeries[validMask], alpha=0.75)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("benefit vs demand")
    ax.set_xlabel("total_vehicle_day")
    ax.set_ylabel("improvement_pct")
    saveFigure(fig, outPath)


# fig 06
def plotLegTypeImproveBar(plotCtx: Object, outPath: Path) -> None:
    if "leg_type" not in plotCtx.pairedDataFrame.columns:
        return

    tempDf = pd.DataFrame(
        {
            "leg_type": plotCtx.pairedDataFrame["leg_type"].astype(str),
            "improvement": toNumericSafe(plotCtx.delayImprovePctSeries),
        }
    ).dropna()
    if tempDf.empty:
        return

    groupedMean = tempDf.groupby("leg_type", dropna=False)["improvement"].mean().sort_values(ascending=False)

    fig = plt.figure(figsize=(8.0, 5.0))
    ax = fig.add_subplot(111)
    ax.bar(groupedMean.index.astype(str), groupedMean.values)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("mean improvement by leg type")
    ax.set_xlabel("leg_type")
    ax.set_ylabel("improvement_pct")
    ax.tick_params(axis="x", labelrotation=20)
    saveFigure(fig, outPath)


# fig 07
def plotDelayCdf(plotCtx: Object, outPath: Path) -> None:
    baselineSeries = np.sort(toNumericSafe(plotCtx.pairedDataFrame["baseline_delay"]).dropna().values)
    anfisSeries = np.sort(toNumericSafe(plotCtx.pairedDataFrame["anfis_delay"]).dropna().values)
    if len(baselineSeries) == 0 or len(anfisSeries) == 0:
        return

    baselineY = np.arange(1, len(baselineSeries) + 1) / len(baselineSeries)
    anfisY = np.arange(1, len(anfisSeries) + 1) / len(anfisSeries)

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.plot(baselineSeries, baselineY, label=plotCtx.baselineCtrlName)
    ax.plot(anfisSeries, anfisY, label=plotCtx.anfisCtrlName)
    ax.set_title("cdf of delay / veh")
    ax.set_xlabel("avg_delay_per_vehicle_seconds")
    ax.set_ylabel("cdf")
    ax.legend()
    saveFigure(fig, outPath)


# fig 08
def plotThroughputScatter(plotCtx: Object, outPath: Path) -> None:
    baselineSeries = toNumericSafe(plotCtx.pairedDataFrame["baseline_throughput"])
    anfisSeries = toNumericSafe(plotCtx.pairedDataFrame["anfis_throughput"])
    validMask = baselineSeries.notna() & anfisSeries.notna()
    if validMask.sum() == 0:
        return

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.scatter(baselineSeries[validMask], anfisSeries[validMask], alpha=0.75)
    minVal = float(min(baselineSeries[validMask].min(), anfisSeries[validMask].min()))
    maxVal = float(max(baselineSeries[validMask].max(), anfisSeries[validMask].max()))
    ax.plot([minVal, maxVal], [minVal, maxVal], linewidth=1)
    ax.set_title("throughput baseline vs anfis")
    ax.set_xlabel("baseline_throughput_vehicles")
    ax.set_ylabel("anfis_throughput_vehicles")
    saveFigure(fig, outPath)


# fig 09
def plotQueueMaxBox(plotCtx: Object, outPath: Path) -> None:
    baselineSeries = toNumericSafe(plotCtx.pairedDataFrame["baseline_max_queue"]).dropna()
    anfisSeries = toNumericSafe(plotCtx.pairedDataFrame["anfis_max_queue"]).dropna()
    if len(baselineSeries) == 0 or len(anfisSeries) == 0:
        return

    fig = plt.figure(figsize=(7.2, 5.0))
    ax = fig.add_subplot(111)
    ax.boxplot([baselineSeries, anfisSeries], labels=[plotCtx.baselineCtrlName, plotCtx.anfisCtrlName], showfliers=False)
    ax.set_title("max queue comparison")
    ax.set_ylabel("max_queue_vehicles")
    ax.set_xlabel("controller")
    saveFigure(fig, outPath)


# fig 10
def plotDemandBinImproveBar(plotCtx: Object, outPath: Path, demandBins: int) -> None:
    if "total_vehicle_day" not in plotCtx.pairedDataFrame.columns:
        return

    demandSeries = toNumericSafe(plotCtx.pairedDataFrame["total_vehicle_day"])
    improveSeries = toNumericSafe(plotCtx.delayImprovePctSeries)
    tempDf = pd.DataFrame({"demand": demandSeries, "improvement": improveSeries}).dropna()

    if len(tempDf) < max(4, demandBins):
        return

    try:
        tempDf["demand_bin"] = pd.qcut(tempDf["demand"], q=demandBins, duplicates="drop")
    except ValueError:
        return

    groupedMean = tempDf.groupby("demand_bin", dropna=False)["improvement"].mean()

    fig = plt.figure(figsize=(8.8, 5.0))
    ax = fig.add_subplot(111)
    ax.bar([str(x) for x in groupedMean.index], groupedMean.values)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("mean improvement by demand bin")
    ax.set_xlabel("total_vehicle_day_quantile_bin")
    ax.set_ylabel("improvement_pct")
    ax.tick_params(axis="x", labelrotation=20)
    saveFigure(fig, outPath)


# fig 11
def plotPeakHourImproveBar(plotCtx: Object, outPath: Path) -> None:
    if "peak_hour_start" not in plotCtx.pairedDataFrame.columns:
        return

    peakHourText = plotCtx.pairedDataFrame["peak_hour_start"].fillna("").astype(str).str[-5:]
    tempDf = pd.DataFrame(
        {
            "peak_hour_bucket": peakHourText.replace("", "unknown"),
            "improvement": toNumericSafe(plotCtx.delayImprovePctSeries),
        }
    ).dropna()
    if tempDf.empty:
        return

    groupedMean = tempDf.groupby("peak_hour_bucket", dropna=False)["improvement"].mean().sort_index().head(12)

    fig = plt.figure(figsize=(8.8, 5.0))
    ax = fig.add_subplot(111)
    ax.bar(groupedMean.index.astype(str), groupedMean.values)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("mean improvement by peak hour")
    ax.set_xlabel("peak_hour_bucket")
    ax.set_ylabel("improvement_pct")
    ax.tick_params(axis="x", labelrotation=25)
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

    throughputImprovePct = (
        (toNumericSafe(pairedDf["anfis_throughput"]) - toNumericSafe(pairedDf["baseline_throughput"]))
        / toNumericSafe(pairedDf["baseline_throughput"]).replace(0, np.nan)
        * 100.0
    )
    queueImprovePct = (
        (toNumericSafe(pairedDf["baseline_max_queue"]) - toNumericSafe(pairedDf["anfis_max_queue"]))
        / toNumericSafe(pairedDf["baseline_max_queue"]).replace(0, np.nan)
        * 100.0
    )

    totalRows = len(pairedDf)
    delayRows = int(toNumericSafe(pairedDf["delayImprovePct"]).notna().sum())
    throughputRows = int(toNumericSafe(throughputImprovePct).notna().sum())
    queueRows = int(toNumericSafe(queueImprovePct).notna().sum())

    print("plot summary:")
    print(f"- paired intersections: {totalRows}")
    print(f"- delay rows used: {delayRows} (skipped: {totalRows - delayRows})")
    print(f"- throughput rows used: {throughputRows}")
    print(f"- queue rows used: {queueRows}")
    print(f"- baseline=0 delay rows skipped by safe divide: {plotCtx.baselineZeroDelayRows}")
    print(f"- mean delay improvement pct: {toNumericSafe(pairedDf['delayImprovePct']).dropna().mean():.3f}")
    print(f"- mean throughput improvement pct: {toNumericSafe(throughputImprovePct).dropna().mean():.3f}")
    print(f"- mean queue improvement pct: {toNumericSafe(queueImprovePct).dropna().mean():.3f}")
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
        ("fig01_meanDelay.png", lambda: plotMeanDelay(plotCtx, outDir / "fig01_meanDelay.png")),
        ("fig02_delayBox.png", lambda: plotDelayBox(plotCtx, outDir / "fig02_delayBox.png")),
        ("fig03_delayImproveHist.png", lambda: plotDelayImproveHist(plotCtx, outDir / "fig03_delayImproveHist.png")),
        ("fig04_congestionVsImprove.png", lambda: plotCongestionVsImprove(plotCtx, outDir / "fig04_congestionVsImprove.png")),
        ("fig05_demandVsImprove.png", lambda: plotDemandVsImprove(plotCtx, outDir / "fig05_demandVsImprove.png")),
        ("fig06_legTypeImproveBar.png", lambda: plotLegTypeImproveBar(plotCtx, outDir / "fig06_legTypeImproveBar.png")),
        ("fig07_delayCdf.png", lambda: plotDelayCdf(plotCtx, outDir / "fig07_delayCdf.png")),
        ("fig08_throughputScatter.png", lambda: plotThroughputScatter(plotCtx, outDir / "fig08_throughputScatter.png")),
        ("fig09_queueMaxBox.png", lambda: plotQueueMaxBox(plotCtx, outDir / "fig09_queueMaxBox.png")),
        ("fig10_demandBinImproveBar.png", lambda: plotDemandBinImproveBar(plotCtx, outDir / "fig10_demandBinImproveBar.png", args.demand_bins)),
        ("fig11_peakHourImproveBar.png", lambda: plotPeakHourImproveBar(plotCtx, outDir / "fig11_peakHourImproveBar.png")),
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
