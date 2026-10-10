param(
    [Parameter(Mandatory=$true)][string]$WorkRoot,
    [string]$VitisRoot = 'C:\AMDDesignTools\2026.1\Vitis',
    [ValidateSet('prepare','all')][string]$Stage = 'all'
)
# Always creates new components; never resets a legacy Q24.8 component.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$repoUnix = $repo.Replace('\','/')
if ($repoUnix -match '\s') { throw 'Use a repository path without spaces for per-file CFLAGS.' }
if (Test-Path -LiteralPath $WorkRoot) { throw 'Use a new Q20.12 WorkRoot.' }
New-Item -ItemType Directory -Path $WorkRoot | Out-Null
$WorkRoot = (Resolve-Path -LiteralPath $WorkRoot).Path
$flags = "-std=c++14 -I$repoUnix/hls/include -DSRCNN_HLS_FIXED_POINT=1 -DSRCNN_HLS_OFFICIAL_Q20_12=1"
$revision = (& git -C $repo rev-parse HEAD).Trim()
$paths = @(Get-ChildItem -LiteralPath (Join-Path $repo 'hls\include') -Recurse -File) +
         @(Get-ChildItem -LiteralPath (Join-Path $repo 'hls\src') -Filter '*.cpp' -File) +
         @(Get-Item -LiteralPath (Join-Path $repo 'tests\test_srcnn_axis_dataflow.cpp'))
$hashes = @($paths | ForEach-Object { @{path=$_.FullName;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash} })
foreach ($name in 'small_13x17_5ns','deployment_255x255_5ns') {
    $small = $name.StartsWith('small')
    $top = if ($small) {'srcnn_axis_dataflow_cosim_13x17_top'} else {'srcnn_axis_dataflow_top'}
    $dir = Join-Path $WorkRoot $name
    New-Item -ItemType Directory -Path $dir | Out-Null
    $lines = @('part=xck26-sfvc784-2LV-c','','[hls]','clock=5.0ns',"syn.top=$top")
    foreach ($source in 'srcnn_axis_dataflow.cpp','srcnn_hls.cpp','srcnn_hls_line_buffer.cpp') {
        $lines += "syn.file=$repoUnix/hls/src/$source"
        $lines += "syn.file_cflags=$repoUnix/hls/src/$source,$flags"
    }
    if ($small) {
        $lines += @("tb.file=$repoUnix/tests/test_srcnn_axis_dataflow.cpp",
                    "tb.file_cflags=$repoUnix/tests/test_srcnn_axis_dataflow.cpp,$flags -DSRCNN_AXIS_DATAFLOW_TEST_CASE=3 -DSRCNN_AXIS_DATAFLOW_USE_FIXED_13X17_TOP=1",
                    'cosim.tool=xsim','cosim.rtl=verilog','cosim.trace_level=port',
                    'cosim.wave_debug=false','cosim.enable_dataflow_profiling=false','cosim.enable_fifo_sizing=false')
    }
    [IO.File]::WriteAllText((Join-Path $dir 'hls_config.cfg'),($lines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
    @{commit=$revision;top=$top;part='xck26-sfvc784-2LV-c';clock_ns=5;flags=$flags;source_hashes=$hashes} |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $dir 'source-manifest.json') -Encoding utf8
}
if ($Stage -eq 'prepare') { return }
function Invoke-HlsGate([string]$Directory,[string]$Gate) {
    foreach ($source in $hashes) {
        if ((Get-FileHash -LiteralPath $source.path).Hash -ne $source.sha256) {
            throw "Source changed after configuration: $($source.path)"
        }
    }
    Push-Location $Directory
    try {
        if ($Gate -eq 'csim') {
            & (Join-Path $VitisRoot 'bin\vitis-run.bat') --mode hls --csim --config hls_config.cfg --work_dir . 2>&1 | Tee-Object -FilePath csim-cli.log
        } else {
            & (Join-Path $VitisRoot 'bin\v++.bat') --compile --mode hls --config hls_config.cfg --work_dir . 2>&1 | Tee-Object -FilePath synthesis-cli.log
        }
        if ($LASTEXITCODE -ne 0) { throw "Q20.12 $Gate failed in $Directory" }
    } finally { Pop-Location }
}
Invoke-HlsGate (Join-Path $WorkRoot 'small_13x17_5ns') 'csim'
Invoke-HlsGate (Join-Path $WorkRoot 'small_13x17_5ns') 'synthesis'
Invoke-HlsGate (Join-Path $WorkRoot 'deployment_255x255_5ns') 'synthesis'
# Independent XSIM validation is a separate step using run_axis_q20_12_rtl.ps1.
# Ignore auto-generated diagnostic IP: only deployment_255x255_5ns is deployable.
