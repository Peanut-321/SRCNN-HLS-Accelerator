param(
    [Parameter(Mandatory=$true)][string]$Component,
    [Parameter(Mandatory=$true)][string]$Vectors,
    [Parameter(Mandatory=$true)][string]$WorkDir,
    [string]$VivadoRoot = 'C:\AMDDesignTools\2026.1\Vivado',
    [ValidateSet(1,2)][int]$FrameCount = 1,
    [switch]$Deployment,
    [switch]$RejectCorruptGolden,
    [switch]$RejectSecondFrameGolden
)
# Reuse the established AXI scoreboard without Vitis autotb/UVM or RTL changes.
$ErrorActionPreference = 'Stop'
$top = if ($Deployment) {'srcnn_axis_dataflow_top'} else {'srcnn_axis_dataflow_cosim_13x17_top'}
$pixels = if ($Deployment) {65025} else {221}
$shape = if ($Deployment) {'1,255,255'} else {'1,13,17'}
if ($RejectSecondFrameGolden -and ($FrameCount -ne 2 -or $RejectCorruptGolden)) {
    throw 'Second-frame negative control requires two frames and excludes first-frame corruption.'
}
$rtl = Join-Path $Component 'hls\syn\verilog'
$tb = Join-Path $PSScriptRoot '..\..\tests\rtl\srcnn_axis_independent_tb.sv'
if (Test-Path -LiteralPath $WorkDir) { throw 'Use a new RTL work directory.' }
if (!(Test-Path -LiteralPath (Join-Path $rtl "$top.v"))) { throw "Missing synthesized top: $top" }
$provenance = Get-Content -LiteralPath (Join-Path $Component 'source-manifest.json') -Raw | ConvertFrom-Json
if ($provenance.top -ne $top -or $provenance.clock_ns -ne 5 -or
    $provenance.flags -notmatch 'SRCNN_HLS_OFFICIAL_Q20_12=1') {
    throw 'Component is not the requested 5 ns Q20.12 RTL.'
}
foreach ($source in $provenance.source_hashes) {
    if ((Get-FileHash -LiteralPath $source.path).Hash -ne $source.sha256) {
        throw "Source changed since component creation: $($source.path)"
    }
}
$vectorManifest = Get-Content -LiteralPath (Join-Path $Vectors 'vectors-manifest.json') -Raw | ConvertFrom-Json
if ($vectorManifest.numeric_profile -ne 'official_q20_12_v1' -or $vectorManifest.top -ne $top -or
    ($vectorManifest.shape -join ',') -ne $shape -or
    ($vectorManifest.numeric_contract.accumulator_bits -join ',') -ne '31,37,44' -or
    $vectorManifest.numeric_contract.scale -ne 4096) { throw 'Vector profile mismatch.' }
$validated = @{}
$vectorFrames = if ($vectorManifest.frame_count) {$vectorManifest.frame_count} else {1}
if ($vectorFrames -ne $FrameCount) { throw 'Vector frame count mismatch.' }
$names = @('input.hex','model.hex','expected.hex')
if ($FrameCount -eq 2) { $names += @('input2.hex','model2.hex','expected2.hex') }
foreach ($name in $names) {
    $path = Join-Path $Vectors $name
    $count = if ($name -match '^model') {8129} else {$pixels}
    $record = $vectorManifest.artifacts.$name
    $words = @(Get-Content -LiteralPath $path)
    if ($record.words -ne $count -or $words.Count -ne $count -or
        ($words | Where-Object {$_ -notmatch '^[0-9a-fA-F]{8}$'}).Count -ne 0 -or
        (Get-FileHash -LiteralPath $path).Hash -ne $record.sha256) { throw "Invalid vector: $name" }
    $validated[$name] = $words
}
New-Item -ItemType Directory -Path $WorkDir | Out-Null
$WorkDir = (Resolve-Path -LiteralPath $WorkDir).Path
foreach ($name in $validated.Keys) {
    [IO.File]::WriteAllLines((Join-Path $WorkDir $name),[string[]]$validated[$name])
}
if ($RejectCorruptGolden -or $RejectSecondFrameGolden) {
    $corruptName = if ($RejectSecondFrameGolden) {'expected2.hex'} else {'expected.hex'}
    $wrong = $validated[$corruptName].Clone()
    $wrong[0] = if ($wrong[0] -eq '00000000') {'00000001'} else {'00000000'}
    [IO.File]::WriteAllLines((Join-Path $WorkDir $corruptName),[string[]]$wrong)
}
$files = @()
$rtlHashes = @()
Get-ChildItem -LiteralPath $rtl -File | Where-Object {$_.Extension -in '.v','.dat'} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $WorkDir
    $rtlHashes += @{name=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash}
    if ($_.Extension -eq '.v') { $files += 'verilog xil_defaultlib "'+$_.Name+'"' }
}
Copy-Item -LiteralPath $tb -Destination $WorkDir
$files += 'sv xil_defaultlib "srcnn_axis_independent_tb.sv"'
[IO.File]::WriteAllLines((Join-Path $WorkDir 'rtl.prj'),[string[]]$files)
@{component=$Component;source=$provenance;vectors=$vectorManifest;rtl=$rtlHashes;
  testbench_sha256=(Get-FileHash -LiteralPath $tb).Hash;frame_count=$FrameCount;deployment=[bool]$Deployment;
  corrupt_golden=[bool]$RejectCorruptGolden;corrupt_second_golden=[bool]$RejectSecondFrameGolden} |
    ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $WorkDir 'run-manifest.json') -Encoding utf8
@'
log_wave [get_objects /srcnn_axis_independent_tb/dut/s_axi_control_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/m_axi_model_mem_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/input_r_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/output_r_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/ap_start]
log_wave [get_objects /srcnn_axis_independent_tb/dut/ap_done]
run all
close_sim
quit
'@ | Set-Content -LiteralPath (Join-Path $WorkDir 'simulate.tcl') -Encoding ascii
Push-Location $WorkDir
try {
    $defines = @('--define', $(if ($Deployment) {'DEPLOYMENT_255X255'} else {'FIXED_13X17'}))
    if ($FrameCount -eq 2) { $defines += @('--define','TWO_FRAMES') }
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') --prj rtl.prj @defines 2>&1 | Tee-Object -FilePath compile.log
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $VivadoRoot 'bin\xelab.bat') xil_defaultlib.srcnn_axis_independent_tb -s independent_srcnn -debug typical 2>&1 | Tee-Object -FilePath elaborate.log
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $VivadoRoot 'bin\xsim.bat') independent_srcnn -tclbatch simulate.tcl -wdb independent_srcnn.wdb 2>&1 | Tee-Object -FilePath simulate.log
    $exitCode = $LASTEXITCODE
    $result = Get-Content -LiteralPath simulate.log -Raw
    if ($RejectSecondFrameGolden) {
        if ($result -notmatch 'PASS frame=1 ' -or $result -notmatch 'Fatal: Output 0 expected=.*frame=2') {
            throw 'Second-frame corruption was not rejected after a complete first frame.'
        }
        Write-Output 'PASS negative check: second-frame corrupt golden rejected after frame one PASS'
    } elseif ($RejectCorruptGolden) {
        if ($result -notmatch 'Fatal: Output 0 expected=') { throw 'Corrupt golden was not rejected at output 0.' }
        Write-Output 'PASS negative check: corrupt golden rejected at output 0'
    } elseif ($exitCode -ne 0 -or $result -notmatch "PASS independent RTL: transactions=$FrameCount inputs=$($FrameCount*$pixels) outputs=$($FrameCount*$pixels) model_reads=$($FrameCount*8129) unique=$($FrameCount*8129) " -or $result -match 'Fatal:') {
        throw 'Q20.12 independent RTL verification failed.'
    }
} finally { Pop-Location }
