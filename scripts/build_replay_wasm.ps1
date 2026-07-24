param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$ParserDir = Join-Path $RepoRoot "third_party/cs2-2d-demo-viewer/parser"
$WasmDir = Join-Path $RepoRoot "third_party/cs2-2d-demo-viewer/web/public/wasm"
$WasmOut = Join-Path $WasmDir "csdemoparser.wasm"
$WasmExecOut = Join-Path $WasmDir "wasm_exec.js"

function Write-Step([string]$Message) {
    Write-Host $Message
}

$goVersionOutput = & go version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "go version check failed: $goVersionOutput"
}
Write-Step $goVersionOutput

if (-not (Test-Path $ParserDir)) {
    throw "Viewer parser directory not found: $ParserDir"
}
if (-not (Test-Path (Join-Path $ParserDir "wasm.go"))) {
    throw "wasm.go not found in parser directory"
}

$prevGoOs = $env:GOOS
$prevGoArch = $env:GOARCH

try {
    if (-not (Test-Path $WasmDir)) {
        New-Item -ItemType Directory -Path $WasmDir -Force | Out-Null
    }

    Push-Location $ParserDir
    $env:GOOS = "js"
    $env:GOARCH = "wasm"

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    & go build -ldflags="-s -w" -o $WasmOut .\wasm.go
    if ($LASTEXITCODE -ne 0) {
        throw "go build failed with exit code $LASTEXITCODE"
    }
    $stopwatch.Stop()

    $goRoot = & go env GOROOT
    if ($LASTEXITCODE -ne 0) {
        throw "go env GOROOT failed"
    }
    $wasmExecSrc = Join-Path $goRoot "lib/wasm/wasm_exec.js"
    if (-not (Test-Path $wasmExecSrc)) {
        throw "wasm_exec.js not found at $wasmExecSrc"
    }
    Copy-Item $wasmExecSrc $WasmExecOut -Force

    $wasmItem = Get-Item $WasmOut
    $wasmHash = (Get-FileHash $WasmOut -Algorithm SHA256).Hash
    $execItem = Get-Item $WasmExecOut

    Write-Step "WASM output: $WasmOut"
    Write-Step "  Size: $($wasmItem.Length) bytes"
    Write-Step "  LastWriteTime: $($wasmItem.LastWriteTime)"
    Write-Step "  SHA-256: $wasmHash"
    Write-Step "wasm_exec.js output: $WasmExecOut"
    Write-Step "  Size: $($execItem.Length) bytes"
    Write-Step "  LastWriteTime: $($execItem.LastWriteTime)"
    Write-Step "Build time: $($stopwatch.Elapsed.TotalSeconds.ToString('F2'))s"

    $gitignorePath = Join-Path $RepoRoot ".gitignore"
    if (Test-Path $gitignorePath) {
        $ignoreContent = Get-Content $gitignorePath -Raw
        if ($ignoreContent -match "cs2-2d-demo-viewer/web/public/wasm") {
            Write-Step "Parent .gitignore excludes web/public/wasm/"
        } else {
            Write-Warning "Parent .gitignore does not mention web/public/wasm/"
        }
    } else {
        Write-Warning "Parent .gitignore not found"
    }
}
finally {
    if ($null -ne $prevGoOs) {
        $env:GOOS = $prevGoOs
    } else {
        Remove-Item Env:GOOS -ErrorAction SilentlyContinue
    }
    if ($null -ne $prevGoArch) {
        $env:GOARCH = $prevGoArch
    } else {
        Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
    }
    Pop-Location -ErrorAction SilentlyContinue
}
