param(
    [Parameter(Mandatory=$true)][string]$Component,
    [string]$Part = 'xck26-sfvc784-2LV-c',
    [double]$ClockNs = 5.0,
    [string]$VitisRoot = 'C:\AMDDesignTools\2026.1\Vitis',
    [ValidateSet('all','synthesis','package')][string]$Stage = 'all'
)
# Deployment-only gate after small-frame independent RTL verification.
# Uses the Unified HLS CLI; never invokes the blocked automatic co-sim flow.
$ErrorActionPreference = 'Stop'
if ($ClockNs -le 0) { throw 'ClockNs must be positive' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$repoUnix = $repo.Replace('\','/')
if ($repoUnix -match '\s') { throw 'Use a repository path without spaces for this Vitis 2026.1 per-file include config.' }
$period = $ClockNs.ToString('0.0########',[Globalization.CultureInfo]::InvariantCulture)
$sources = @('srcnn_axis_dataflow.cpp','srcnn_hls.cpp','srcnn_hls_line_buffer.cpp')
$lines = @("part=$Part",'','[hls]',"clock=${period}ns",'syn.top=srcnn_axis_dataflow_top')
foreach ($source in $sources) { $lines += "syn.file=$repoUnix/hls/src/$source" }
foreach ($source in $sources) {
    $lines += "syn.file_cflags=$repoUnix/hls/src/$source,-std=c++14 -I$repoUnix/hls/include -DSRCNN_HLS_FIXED_POINT=1"
}
$lines += @('package.output.format=ip_catalog','package.output.syn=false')
$cfgText = ($lines -join "`n")+"`n"
if ($Stage -ne 'package') {
    if (Test-Path -LiteralPath $Component) {
        throw 'Use a new component path for synthesis; existing projects are not overwritten.'
    }
    New-Item -ItemType Directory -Path $Component | Out-Null
    [IO.File]::WriteAllText((Join-Path $Component 'hls_config.cfg'),$cfgText,[Text.UTF8Encoding]::new($false))
} else {
    $existing = [IO.File]::ReadAllText((Join-Path $Component 'hls_config.cfg')).Replace("`r`n","`n")
    if ($existing -ne $cfgText) { throw 'Package-only config differs from requested deployment config.' }
    if (!(Test-Path -LiteralPath (Join-Path $Component 'hls\syn\report\csynth.xml'))) {
        throw 'No completed synthesis found for package-only stage.'
    }
}
$Component = (Resolve-Path -LiteralPath $Component).Path
$revision = (& git -C $repo rev-parse HEAD).Trim()
$manifest = @{
    revision=$revision; top='srcnn_axis_dataflow_top'; part=$Part; clock_ns=$ClockNs;
    numeric_flags='-std=c++14 -DSRCNN_HLS_FIXED_POINT=1'; stage=$Stage;
    source_hashes=@(Get-ChildItem -LiteralPath (Join-Path $repo 'hls\include') -Recurse -File | ForEach-Object {
        @{path=$_.FullName.Substring($repo.Length+1);sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
    }) + @($sources | ForEach-Object {
        $path=Join-Path $repo "hls\src\$_"
        @{path="hls/src/$_";sha256=(Get-FileHash $path -Algorithm SHA256).Hash}
    })
}
$manifestPath = Join-Path $Component 'source-manifest.json'
if ($Stage -eq 'package') {
    $synthManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($synthManifest.top -ne $manifest.top -or $synthManifest.part -ne $Part -or
        $synthManifest.clock_ns -ne $ClockNs) {
        throw 'Synthesis provenance differs from requested deployment config.'
    }
    foreach ($sourceHash in $manifest.source_hashes) {
        $recorded = @($synthManifest.source_hashes | Where-Object { $_.path -eq $sourceHash.path })
        if ($recorded.Count -ne 1 -or $recorded[0].sha256 -ne $sourceHash.sha256) {
            throw "Source changed since synthesis: $($sourceHash.path)"
        }
    }
} else {
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
}
Push-Location $Component
try {
    if ($Stage -ne 'package') {
        & (Join-Path $VitisRoot 'bin\v++.bat') --compile --mode hls --config hls_config.cfg --work_dir . 2>&1 |
            Tee-Object -FilePath 'synthesis-cli.log'
        if ($LASTEXITCODE -ne 0) { throw 'Deployment C synthesis failed; inspect synthesis-cli.log' }
    }
    if ($Stage -ne 'synthesis') {
        & (Join-Path $VitisRoot 'bin\vitis-run.bat') --mode hls --package --config hls_config.cfg --work_dir . 2>&1 |
            Tee-Object -FilePath 'package-cli.log'
        if ($LASTEXITCODE -ne 0) { throw 'Deployment IP packaging failed; inspect package-cli.log' }
    }
} finally { Pop-Location }
