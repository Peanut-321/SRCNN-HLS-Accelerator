param(
    [Parameter(Mandatory=$true)][string]$Component,
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [Parameter(Mandatory=$true)][string]$ResultDir,
    [ValidateSet('all','bd','implement')][string]$Stage = 'all',
    [ValidateRange(1,8)][int]$Jobs = 2,
    [switch]$RestartInterruptedImplementation,
    [string]$VivadoRoot = 'C:\AMDDesignTools\2026.1\Vivado'
)
# Reuse the validated KV260 integration, keeping Q20.12 provenance/artifacts separate.
$ErrorActionPreference = 'Stop'
$Component = (Resolve-Path -LiteralPath $Component).Path
$source = Get-Content -LiteralPath (Join-Path $Component 'source-manifest.json') -Raw | ConvertFrom-Json
if ($source.top -ne 'srcnn_axis_dataflow_top' -or $source.part -ne 'xck26-sfvc784-2LV-c' -or
    $source.clock_ns -ne 5 -or $source.flags -notmatch '-DSRCNN_HLS_FIXED_POINT=1(\s|$)' -or
    $source.flags -notmatch '-DSRCNN_HLS_OFFICIAL_Q20_12=1(\s|$)' -or !$source.source_hashes) {
    throw 'Require the fixed 255x255, 5 ns, K26 official Q20.12 deployment component.'
}
foreach ($file in $source.source_hashes) {
    if ((Get-FileHash -LiteralPath $file.path).Hash -ne $file.sha256) {
        throw "Source changed since HLS preparation: $($file.path)"
    }
}
$ip = Join-Path $Component 'hls\impl\ip'
$syn = Join-Path $Component 'hls\syn\verilog'
$rtlChecks = @()
foreach ($file in (Get-ChildItem -LiteralPath $syn -File | Where-Object {$_.Extension -in '.v','.dat'})) {
    $peer = Join-Path $ip ('hdl\verilog\' + $file.Name)
    if (!(Test-Path -LiteralPath $peer)) { throw "Export missing synthesized file: $($file.Name)" }
    $synHash = (Get-FileHash -LiteralPath $file.FullName).Hash
    $ipHash = (Get-FileHash -LiteralPath $peer).Hash
    $check = 'byte-identical'
    if ($synHash -ne $ipHash) {
        if ($file.Name -ne 'srcnn_axis_dataflow_top.v') { throw "Exported RTL differs: $($file.Name)" }
        $synthText = [IO.File]::ReadAllText($file.FullName).Replace("`r`n","`n")
        $exportText = [IO.File]::ReadAllText($peer).Replace("`r`n","`n")
        # Only the known Vitis 2026.1 appended simulation monitors are allowed.
        foreach ($monitor in @(
            @('find_df_deadlock','srcnn_axis_dataflow_top_hls_deadlock_detector.vh'),
            @('find_kernel_block','srcnn_axis_dataflow_top_hls_deadlock_kernel_monitor_top.vh')
        )) {
            $addition = 'reg '+$monitor[0]+' = 0;'+"`n"+'// synthesis translate_off'+"`n"+
                        '`include "'+$monitor[1]+'"'+"`n"+'// synthesis translate_on'
            if (!$exportText.Contains($addition)) { throw 'Unexpected exported top instrumentation.' }
            $exportText = $exportText.Replace($addition,'')
        }
        if (($synthText -replace '\s','') -ne ($exportText -replace '\s','')) {
            throw 'Exported top has differences beyond the known simulation monitors.'
        }
        $check = 'identical except known vendor simulation monitors'
    }
    $rtlChecks += @{name=$file.Name;synthesis_sha256=$synHash;export_sha256=$ipHash;check=$check}
}
if ($rtlChecks.Count -eq 0) { throw 'No synthesized deployment RTL found.' }
New-Item -ItemType Directory -Path $ResultDir -Force | Out-Null
$ResultDir = (Resolve-Path -LiteralPath $ResultDir).Path
if ($Stage -eq 'implement') {
    # Bind resumption to the IP snapshot that actually created this project.
    $creation = @('input-manifest-all.json','input-manifest-bd.json') |
        ForEach-Object {Join-Path $ResultDir $_} | Where-Object {Test-Path -LiteralPath $_} |
        Select-Object -First 1
    if (!$creation) { throw 'Missing project-creation manifest; use the original result directory.' }
    $original = Get-Content -LiteralPath $creation -Raw | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($original.project) -ne [IO.Path]::GetFullPath($ProjectDir) -or
        [IO.Path]::GetFullPath($original.ip_directory) -ne [IO.Path]::GetFullPath($ip)) {
        throw 'Existing project belongs to a different IP/project checkpoint.'
    }
    foreach ($file in $original.ip_files) {
        if ((Get-FileHash -LiteralPath (Join-Path $ip $file.path)).Hash -ne $file.sha256) {
            throw "Project-creation IP snapshot changed: $($file.path)"
        }
    }
}
@{numeric_profile='official_q20_12_v1';source=$source;component=$Component;rtl_checks=$rtlChecks;
  ip_archive_sha256=(Get-FileHash -LiteralPath (Join-Path $ip 'xilinx_com_hls_srcnn_axis_dataflow_top_1_0.zip')).Hash;
  stage=$Stage;project=$ProjectDir;board_tested=$false} |
    ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $ResultDir "q20-input-$Stage.json") -Encoding utf8
& (Join-Path $PSScriptRoot 'run_srcnn_axis_vivado.ps1') -ProjectDir $ProjectDir -IPDir $ip `
    -ResultDir $ResultDir -Stage $Stage -Jobs $Jobs -VivadoRoot $VivadoRoot `
    -RestartInterruptedImplementation:$RestartInterruptedImplementation
if ($Stage -eq 'bd') { return }
# Check timing coverage as well as setup/hold before labeling candidate artifacts.
$timingChecks = [regex]::Matches((Get-Content -LiteralPath (Join-Path $ResultDir 'check_timing.rpt') -Raw),
                               'checking (\w+) \((\d+)\)')
if ($timingChecks.Count -eq 0 -or @($timingChecks | Where-Object {[int]$_.Groups[2].Value -ne 0}).Count -ne 0) {
    throw 'Routed timing coverage checks did not all report zero.'
}
$expectedChecks = @('no_clock','constant_clock','pulse_width_clock',
    'unconstrained_internal_endpoints','no_input_delay','no_output_delay','multiple_clock',
    'generated_clocks','loops','partial_input_delay','partial_output_delay','latch_loops')
$actualChecks = @($timingChecks | ForEach-Object {$_.Groups[1].Value} | Sort-Object -Unique)
if (@(Compare-Object $expectedChecks $actualChecks).Count -ne 0) {
    throw 'Incomplete routed timing-coverage report.'
}
$clocks = Get-Content -LiteralPath (Join-Path $ResultDir 'clocks.rpt') -Raw
if ($clocks -notmatch '(?m)^clk_pl_0\s+5\.000\s') { throw 'Expected routed 5.000 ns PL0 clock.' }
$summaryText = Get-Content -LiteralPath (Join-Path $ResultDir 'post_route_timing.rpt') -Raw
$summary = [regex]::Match($summaryText,
    '(?m)^\s*WNS\(ns\)[^\r\n]*\r?\n[^\r\n]*\r?\n\s*([^\r\n]+)')
if (!$summary.Success) { throw 'Missing routed setup/hold/pulse-width summary.' }
$numbers = $summary.Groups[1].Value.Trim() -split '\s+'
if ($numbers.Count -ne 12) { throw 'Unexpected routed timing-summary format.' }
$culture = [Globalization.CultureInfo]::InvariantCulture
foreach ($index in 0,4,8) {
    if ([double]::Parse($numbers[$index],$culture) -lt 0 -or
        [double]::Parse($numbers[$index+1],$culture) -ne 0 -or
        [int]$numbers[$index+2] -ne 0 -or [int]$numbers[$index+3] -le 0) {
        throw 'Routed setup, hold or pulse-width timing failed or has no checked endpoints.'
    }
}
$artifacts = @()
foreach ($extension in 'bit','hwh','xsa') {
    $original = Join-Path $ResultDir "srcnn_axis_255x255.$extension"
    $named = Join-Path $ResultDir "srcnn_axis_q20_12_255x255.$extension"
    if ((Test-Path -LiteralPath $named) -and
        (Get-FileHash -LiteralPath $named).Hash -ne (Get-FileHash -LiteralPath $original).Hash) {
        throw "Existing Q20.12 artifact differs; use a new result directory: $named"
    }
    Copy-Item -LiteralPath $original -Destination $named -Force
    $artifacts += @{name=[IO.Path]::GetFileName($named);bytes=(Get-Item -LiteralPath $named).Length;
                    sha256=(Get-FileHash -LiteralPath $named).Hash}
}
@{schema='SRCNN_Q20_12_OVERLAY_CANDIDATE_V1';numeric_profile='official_q20_12_v1';
  top='srcnn_axis_dataflow_top';shape=@(1,255,255);part=$source.part;clock_ns=5;
  data_fraction_bits=12;accumulator_bits=@(31,37,44);board_tested=$false;
  validation='routed timing/DRC and timing-coverage PASS; board pending';artifacts=$artifacts;
  component=$Component;source_manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $Component 'source-manifest.json')).Hash;
  routed_gate=(Get-Content -LiteralPath (Join-Path $ResultDir 'implementation_gate.txt') -Raw)} |
    ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $ResultDir 'q20-overlay-manifest.json') -Encoding utf8
Write-Output 'GATE_Q20_CANDIDATE_PASS (not board validated)'
