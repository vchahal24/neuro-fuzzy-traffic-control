param(
    [ValidateSet("help", "install-deps", "run", "plot", "all")]
    [string]$Task = "help",

    [string]$CountId = "",
    [string[]]$CountIds = @(),
    [string]$CountIdsFile = "",

    [string]$Controllers = "baseline_fixed,baseline_proportional",
    [ValidateSet("full_day", "single_interval")]
    [string]$SimMode = "single_interval",
    [int]$TopN = 50,
    [string]$LegType = "all",
    [switch]$MostRecentOnly = $true,
    [int]$IntervalIndex = 0,

    [string]$OutTag = "",
    [string]$BaselineController = "baseline_fixed",
    [string]$AnfisController = "baseline_proportional",
    [switch]$DarkTheme = $false
)

$ErrorActionPreference = "Stop"

function Show-Usage {
    Write-Host "Usage examples:"
    Write-Host "  .\scripts\tasks.ps1 -Task install-deps"
    Write-Host "  .\scripts\tasks.ps1 -Task run -CountId 39339 -OutTag one_39339"
    Write-Host "  .\scripts\tasks.ps1 -Task run -CountIds 39339,112962 -OutTag two_sites"
    Write-Host "  .\scripts\tasks.ps1 -Task run -CountIdsFile .\ids.txt -OutTag id_file_run"
    Write-Host "  .\scripts\tasks.ps1 -Task all -CountId 39339 -SimMode full_day -OutTag one_39339_full_day"
    Write-Host "  .\scripts\tasks.ps1 -Task plot -OutTag one_39339"
}

function Get-PythonExe {
    $venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    $venvPython = [System.IO.Path]::GetFullPath($venvPython)
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Resolve-CountIds {
    $ids = New-Object System.Collections.Generic.List[string]

    if ($CountId -and $CountId.Trim().Length -gt 0) {
        $ids.Add($CountId.Trim())
    }

    foreach ($id in $CountIds) {
        if ($id -and $id.Trim().Length -gt 0) {
            $ids.Add($id.Trim())
        }
    }

    if ($CountIdsFile -and (Test-Path $CountIdsFile)) {
        Get-Content $CountIdsFile | ForEach-Object {
            $line = $_.Trim()
            if ($line.Length -gt 0) {
                $ids.Add($line)
            }
        }
    }

    return $ids | Select-Object -Unique
}

function Get-OutTag([string[]]$ids) {
    if ($OutTag -and $OutTag.Trim().Length -gt 0) {
        return $OutTag.Trim()
    }
    if ($ids.Count -eq 1) {
        return "one_$($ids[0])"
    }
    if ($ids.Count -gt 1) {
        return "selected_ids"
    }
    return "latest"
}

function Install-Deps([string]$pythonExe) {
    & $pythonExe -m pip install -r requirements.txt
}

function Build-SelectedCsvs([string]$pythonExe, [string[]]$ids, [string]$tag) {
    if ($ids.Count -eq 0) {
        return $null
    }

    $safeTag = ($tag -replace "[^a-zA-Z0-9_\-]", "_")
    $intervalOut = "outputs/preprocessed/selection_${safeTag}_interval.csv"
    $dailyOut = "outputs/preprocessed/selection_${safeTag}_daily.csv"
    $metaOut = "outputs/preprocessed/selection_${safeTag}_meta.csv"

    $idsEscaped = @($ids) | ForEach-Object { '"' + ($_.Replace('"', '\"')) + '"' }
    $idsJson = "[" + ($idsEscaped -join ",") + "]"
    $code = @"
import json
import pandas as pd

ids = {str(x).strip() for x in json.loads(r'''$idsJson''') if str(x).strip()}

interval = pd.read_csv('outputs/preprocessed/tmc_interval_features_all.csv')
daily = pd.read_csv('outputs/preprocessed/tmc_daily_features_all.csv')
meta = pd.read_csv('outputs/preprocessed/tmc_intersection_metadata_all.csv')

interval['count_id'] = interval['count_id'].astype(str)
daily['count_id'] = daily['count_id'].astype(str)
meta['count_id'] = meta['count_id'].astype(str)

interval_sel = interval[interval['count_id'].isin(ids)].copy()
daily_sel = daily[daily['count_id'].isin(ids)].copy()
meta_sel = meta[meta['count_id'].isin(ids)].copy()

interval_sel.to_csv(r'''$intervalOut''', index=False)
daily_sel.to_csv(r'''$dailyOut''', index=False)
meta_sel.to_csv(r'''$metaOut''', index=False)

print('Selected IDs requested:', len(ids))
print('Daily rows written:', len(daily_sel))
print('Interval rows written:', len(interval_sel))
print('Metadata rows written:', len(meta_sel))
"@
    & $pythonExe -c $code | ForEach-Object { Write-Host $_ }

    if (!(Test-Path $intervalOut) -or !(Test-Path $dailyOut) -or !(Test-Path $metaOut)) {
        throw "Failed to create filtered CSVs for selected intersection IDs."
    }

    return @{
        IntervalCsv = $intervalOut
        DailyCsv = $dailyOut
        MetaCsv = $metaOut
    }
}

function Run-Experiments([string]$pythonExe, [string]$tag, [hashtable]$selectedCsvs) {
    $outDir = "outputs/experiments/$tag"

    $args = @(
        "src/runExperiments.py",
        "--controllers", $Controllers,
        "--sim-mode", $SimMode,
        "--interval-index", "$IntervalIndex",
        "--out-dir", $outDir
    )

    if ($MostRecentOnly) {
        $args += "--most-recent-only"
    }
    if ($LegType -and $LegType -ne "all") {
        $args += @("--leg-type-filter", $LegType)
    }
    if ($TopN -gt 0) {
        $args += @("--top-n-by-volume", "$TopN")
    }

    if ($null -ne $selectedCsvs) {
        $args += @("--interval-csv", $selectedCsvs.IntervalCsv)
        $args += @("--daily-csv", $selectedCsvs.DailyCsv)
        $args += @("--metadata-csv", $selectedCsvs.MetaCsv)
    }

    & $pythonExe @args
}

function Plot-Results([string]$pythonExe, [string]$tag) {
    $results = "outputs/experiments/$tag/results_per_intersection.csv"
    $figDir = "outputs/experiments/$tag/figs"
    $args = @(
        "runPlotResults.py",
        "--results", $results,
        "--out-dir", $figDir,
        "--baseline-controller", $BaselineController,
        "--anfis-controller", $AnfisController
    )
    if ($DarkTheme) {
        $args += "--dark-theme"
    }
    & $pythonExe @args
}

$pythonExe = Get-PythonExe
$ids = Resolve-CountIds
$tag = Get-OutTag -ids $ids

if ($Task -eq "help") {
    Show-Usage
    exit 0
}

if ($Task -eq "install-deps") {
    Install-Deps -pythonExe $pythonExe
    exit 0
}

$selectedCsvs = Build-SelectedCsvs -pythonExe $pythonExe -ids $ids -tag $tag

if ($Task -eq "run") {
    Run-Experiments -pythonExe $pythonExe -tag $tag -selectedCsvs $selectedCsvs
    exit 0
}

if ($Task -eq "plot") {
    Plot-Results -pythonExe $pythonExe -tag $tag
    exit 0
}

if ($Task -eq "all") {
    Run-Experiments -pythonExe $pythonExe -tag $tag -selectedCsvs $selectedCsvs
    Plot-Results -pythonExe $pythonExe -tag $tag
    exit 0
}
