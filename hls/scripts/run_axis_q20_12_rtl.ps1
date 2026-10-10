param(
    [Parameter(Mandatory=$true)][string]$Component,
    [Parameter(Mandatory=$true)][string]$Vectors,
    [Parameter(Mandatory=$true)][string]$WorkDir,
    [string]$VivadoRoot = 'C:\AMDDesignTools\2026.1\Vivado',
    [switch]$RejectCorruptGolden
)
# Reuse the established AXI scoreboard without Vitis autotb/UVM or RTL changes.
$ErrorActionPreference = 'Stop'
$top = 'srcnn_axis_dataflow_cosim_13x17_top'
$rtl = Join-Path $Component 'hls\syn\verilog'
$tb = Join-Path $PSScriptRoot '..\..\tests\rtl\srcnn_axis_independent_tb.sv'
if (Test-Path -LiteralPath $WorkDir) { throw 'Use a new RTL work directory.' }
if (!(Test-Path -LiteralPath (Join-Path $rtl "$top.v"))) { throw 'Missing fixed 13x17 synthesized top.' }
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
    ($vectorManifest.shape -join ',') -ne '1,13,17' -or
    ($vectorManifest.numeric_contract.accumulator_bits -join ',') -ne '31,37,44' -or
    $vectorManifest.numeric_contract.scale -ne 4096) { throw 'Vector profile mismatch.' }
$validated = @{}
foreach ($name in 'input.hex','model.hex','expected.hex') {
    $path = Join-Path $Vectors $name
    $count = if ($name -eq 'model.hex') {8129} else {221}
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
if ($RejectCorruptGolden) {
    $wrong = $validated['expected.hex'].Clone()
    $wrong[0] = if ($wrong[0] -eq '00000000') {'00000001'} else {'00000000'}
    [IO.File]::WriteAllLines((Join-Path $WorkDir 'expected.hex'),[string[]]$wrong)
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
  testbench_sha256=(Get-FileHash -LiteralPath $tb).Hash;corrupt_golden=[bool]$RejectCorruptGolden} |
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
    & (Join-Path $VivadoRoot 'bin\xvlog.bat') --prj rtl.prj --define FIXED_13X17 2>&1 | Tee-Object -FilePath compile.log
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $VivadoRoot 'bin\xelab.bat') xil_defaultlib.srcnn_axis_independent_tb -s independent_srcnn -debug typical 2>&1 | Tee-Object -FilePath elaborate.log
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $VivadoRoot 'bin\xsim.bat') independent_srcnn -tclbatch simulate.tcl -wdb independent_srcnn.wdb 2>&1 | Tee-Object -FilePath simulate.log
    $exitCode = $LASTEXITCODE
    $result = Get-Content -LiteralPath simulate.log -Raw
    if ($RejectCorruptGolden) {
        if ($result -notmatch 'Fatal: Output 0 expected=') { throw 'Corrupt golden was not rejected at output 0.' }
        Write-Output 'PASS negative check: corrupt golden rejected at output 0'
    } elseif ($exitCode -ne 0 -or $result -notmatch 'PASS independent RTL:' -or $result -match 'Fatal:') {
        throw 'Q20.12 independent RTL verification failed.'
    }
} finally { Pop-Location }
