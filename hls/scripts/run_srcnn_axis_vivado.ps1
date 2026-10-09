param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [Parameter(Mandatory=$true)][string]$IPDir,
    [Parameter(Mandatory=$true)][string]$ResultDir,
    [ValidateSet('all','bd','implement')][string]$Stage = 'all',
    [ValidateRange(1,8)][int]$Jobs = 2,
    [switch]$RestartInterruptedImplementation,
    [string]$VivadoRoot = 'C:\AMDDesignTools\2026.1\Vivado'
)
$ErrorActionPreference = 'Stop'
if ($RestartInterruptedImplementation -and $Stage -ne 'implement') {
    throw 'RestartInterruptedImplementation requires Stage implement.'
}
if ($RestartInterruptedImplementation -and (Get-Process vivado -ErrorAction SilentlyContinue)) {
    throw 'Close or wait for running Vivado processes before restarting an interrupted run.'
}
$IPDir = (Resolve-Path -LiteralPath $IPDir).Path
[xml]$metadata = Get-Content -LiteralPath (Join-Path $IPDir 'component.xml') -Raw
if ($metadata.component.name -ne 'srcnn_axis_dataflow_top') {
    throw 'Expected fixed 255x255 deployment IP, not a diagnostic top.'
}
if ($Stage -ne 'implement' -and (Test-Path -LiteralPath (Join-Path $ProjectDir 'srcnn_axis_kv260.xpr'))) {
    throw 'Choose a new ProjectDir; existing Vivado projects are not overwritten.'
}
New-Item -ItemType Directory -Path $ResultDir -Force | Out-Null
$ResultDir = (Resolve-Path -LiteralPath $ResultDir).Path
if ($RestartInterruptedImplementation) {
    $interruptedRun = Join-Path $ProjectDir 'srcnn_axis_kv260.runs\impl_1'
    if (Test-Path -LiteralPath $interruptedRun) {
        $backupRun = Join-Path $ResultDir ('interrupted-impl_1-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Copy-Item -LiteralPath $interruptedRun -Destination $backupRun -Recurse
    }
}
$tcl = Join-Path $PSScriptRoot 'run_srcnn_axis_vivado.tcl'
$manifest = @{
    project=$ProjectDir; ip_directory=$IPDir; stage=$Stage; jobs=$Jobs;
    restart_interrupted_implementation=$RestartInterruptedImplementation.IsPresent;
    top='srcnn_axis_dataflow_top'; part='xck26-sfvc784-2LV-c'; clock_ns=5.0;
    tcl_sha256=(Get-FileHash -LiteralPath $tcl -Algorithm SHA256).Hash;
    ip_files=@(Get-ChildItem -LiteralPath (Join-Path $IPDir 'hdl') -Recurse -File | ForEach-Object {
        @{path=$_.FullName.Substring($IPDir.Length+1);sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
    }) + @(@{path='component.xml';sha256=(Get-FileHash -LiteralPath (Join-Path $IPDir 'component.xml') -Algorithm SHA256).Hash})
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ResultDir "input-manifest-$Stage.json") -Encoding utf8
& (Join-Path $VivadoRoot 'bin\vivado.bat') -mode batch -nojournal `
    -log (Join-Path $ResultDir "vivado-$Stage.log") -source $tcl `
    -tclargs $ProjectDir $IPDir $ResultDir $Stage $Jobs ([int]$RestartInterruptedImplementation.IsPresent) 2>&1 |
    Tee-Object -FilePath (Join-Path $ResultDir "console-$Stage.log")
if ($LASTEXITCODE -ne 0) { throw "Vivado $Stage gate failed; inspect the saved reports and logs." }
