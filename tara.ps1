# FACEIT CS2 Coach — tek komut tara modu
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

python -m src.main --nickname Jurses --demo-folder data/demos --tara
$exitCode = $LASTEXITCODE

$reportPath = Join-Path $PSScriptRoot "data\ai_exports\jurses_tara_latest.md"
if (Test-Path $reportPath) {
    notepad $reportPath
}

exit $exitCode
