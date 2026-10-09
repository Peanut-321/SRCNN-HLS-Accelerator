param(
    [Parameter(Mandatory=$true)][string]$Component,
    [Parameter(Mandatory=$true)][string]$WorkDir,
    [string]$VectorComponent = '',
    [string]$VivadoRoot = 'C:\AMDDesignTools\2026.1\Vivado',
    [switch]$Fixed13x17,
    [switch]$RejectCorruptGolden
)
$ErrorActionPreference = 'Stop'
if (!$VectorComponent) { $VectorComponent = $Component }
$rtl = Join-Path $Component 'hls\syn\verilog'
$vectors = Join-Path $VectorComponent 'hls\sim\tv\cdatafile'
$tb = Join-Path $PSScriptRoot '..\..\tests\rtl\srcnn_axis_independent_tb.sv'
if (!(Test-Path -LiteralPath $tb)) { throw "Missing testbench: $tb" }
$top = if ($Fixed13x17) {'srcnn_axis_dataflow_cosim_13x17_top'} else {'srcnn_axis_dataflow_cosim_top'}
if (!(Test-Path -LiteralPath (Join-Path $rtl "$top.v"))) { throw "Missing synthesized top: $top" }
New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
$WorkDir = (Resolve-Path -LiteralPath $WorkDir).Path

function Read-TextVector([string]$FileName, [int]$Count) {
    $lines = Get-Content -LiteralPath (Join-Path $vectors $FileName)
    if (($lines | Where-Object { $_ -match '^\[\[transaction\]\]' }).Count -ne 1 -or
        ($lines | Where-Object { $_ -match '^\[\[/transaction\]\]' }).Count -ne 1 -or
        $lines[0] -ne '[[[runtime]]]' -or $lines[-1] -ne '[[[/runtime]]]') {
        throw "Invalid transaction delimiters: $FileName"
    }
    $words = @($lines | Where-Object { $_ -match '^0x[0-9a-fA-F]+$' } | ForEach-Object { $_.Substring(2).PadLeft(8,'0') })
    if ($words.Count -ne $Count) { throw "Wrong sample count: $FileName, got $($words.Count), expected $Count" }
    return $words
}

# Vitis binary model vector: BE transaction index, BE depth, BE 32-bit words,
# then 0x5a5aa5a5 and 0x0f0ff0f0 end markers. Check the whole envelope.
$modelFile = Join-Path $vectors 'c.srcnn_axis_dataflow_cosim_top.autotvin_model_mem.dat'
$bytes = [IO.File]::ReadAllBytes($modelFile)
if ($bytes.Length -ne (8129*4+16) -or [BitConverter]::ToString($bytes[0..7]) -ne '00-00-00-00-00-00-1F-C1' -or
    [BitConverter]::ToString($bytes[($bytes.Length-8)..($bytes.Length-1)]) -ne '5A-5A-A5-A5-0F-0F-F0-F0') {
    throw 'Model vector envelope/count/end markers invalid'
}
$model = for ($i=0; $i -lt 8129; $i++) {
    $offset=8+4*$i
    '{0:x2}{1:x2}{2:x2}{3:x2}' -f $bytes[$offset],$bytes[$offset+1],$bytes[$offset+2],$bytes[$offset+3]
}
$inputWords = Read-TextVector 'c.srcnn_axis_dataflow_cosim_top.autotvin_input_r_V_data_V.dat' 221
$golden = Read-TextVector 'c.srcnn_axis_dataflow_cosim_top.autotvout_output_r_V_data_V.dat' 221
foreach ($direction in @('autotvin_input','autotvout_output')) {
    foreach ($sideband in @('keep','strb','last')) {
        $words = Read-TextVector "c.srcnn_axis_dataflow_cosim_top.${direction}_r_V_${sideband}_V.dat" 221
        for ($i=0; $i -lt 221; $i++) {
            $expected = if ($sideband -ne 'last') {'0000000f'} elseif ($i -eq 220) {'00000001'} else {'00000000'}
            if ($words[$i] -ne $expected) { throw "Invalid vector sideband $direction/$sideband/$i" }
        }
    }
}
if ($RejectCorruptGolden) { $golden[0] = if ($golden[0] -eq '00000000') {'00000001'} else {'00000000'} }
[IO.File]::WriteAllLines((Join-Path $WorkDir 'model.hex'),[string[]]$model)
[IO.File]::WriteAllLines((Join-Path $WorkDir 'input.hex'),[string[]]$inputWords)
[IO.File]::WriteAllLines((Join-Path $WorkDir 'expected.hex'),[string[]]$golden)
$manifest = @{
    top=$top; component=(Resolve-Path $Component).Path;
    vector_component=(Resolve-Path $VectorComponent).Path;
    clock_ns=5; inputs=221; outputs=221; model_words=8129;
    model_sha256=(Get-FileHash $modelFile -Algorithm SHA256).Hash;
    corrupt_golden=[bool]$RejectCorruptGolden;
    rtl=@(Get-ChildItem -LiteralPath $rtl -Filter '*.v' -File | ForEach-Object {
        @{name=$_.Name;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
    })
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $WorkDir 'manifest.json') -Encoding utf8
# Use only synthesized RTL, not the auto-generated co-sim harness.
$sources = @()
Get-ChildItem -LiteralPath $rtl -File | Where-Object {$_.Extension -in '.v','.dat'} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $WorkDir
    if ($_.Extension -eq '.v') { $sources += 'verilog xil_defaultlib "'+$_.Name+'"' }
}
Copy-Item -LiteralPath $tb -Destination $WorkDir
$sources += 'sv xil_defaultlib "srcnn_axis_independent_tb.sv"'
[IO.File]::WriteAllLines((Join-Path $WorkDir 'rtl.prj'),[string[]]$sources)
# Record real DUT port/control waveforms; do not record 2M clock transitions.
@'
log_wave [get_objects /srcnn_axis_independent_tb/dut/s_axi_control_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/m_axi_model_mem_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/input_r_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/output_r_*]
log_wave [get_objects /srcnn_axis_independent_tb/dut/ap_start]
log_wave [get_objects /srcnn_axis_independent_tb/dut/ap_done]
log_wave [get_objects /srcnn_axis_independent_tb/dut/ap_idle]
log_wave [get_objects /srcnn_axis_independent_tb/dut/ap_ready]
run all
close_sim
quit
'@ | Set-Content -LiteralPath (Join-Path $WorkDir 'simulate.tcl') -Encoding ascii
Push-Location $WorkDir
try {
    $vlog = Join-Path $VivadoRoot 'bin\xvlog.bat'
    $elab = Join-Path $VivadoRoot 'bin\xelab.bat'
    $sim = Join-Path $VivadoRoot 'bin\xsim.bat'
    $compileArgs = @('--prj','rtl.prj')
    if ($Fixed13x17) { $compileArgs += @('--define','FIXED_13X17') }
    & $vlog @compileArgs 2>&1 | Tee-Object -FilePath 'compile.log'
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & $elab 'xil_defaultlib.srcnn_axis_independent_tb' '-s' 'independent_srcnn' '-debug' 'typical' 2>&1 | Tee-Object -FilePath 'elaborate.log'
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & $sim 'independent_srcnn' '-tclbatch' 'simulate.tcl' '-wdb' 'independent_srcnn.wdb' 2>&1 | Tee-Object -FilePath 'simulate.log'
    $result = Get-Content -LiteralPath 'simulate.log' -Raw
    if ($RejectCorruptGolden) {
        if ($result -notmatch 'Fatal: Output 0 expected=') { throw 'Corrupt-golden negative check did not reject the output' }
        Write-Output 'PASS negative check: corrupt golden was rejected at output 0'
    } elseif ($result -notmatch 'PASS independent RTL:' -or $result -match 'Fatal:') {
        throw 'Independent RTL validation failed; see simulate.log'
    }
} finally { Pop-Location }
