param(
    [Parameter(Mandatory = $true)]
    [string]$MapName,

    [Parameter(Mandatory = $true)]
    [string]$SourcePath,

    [string]$ClientVersion = "",

    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$OptimizedRoot = Join-Path $RepoRoot "data/maps3d/optimized"
$TargetDir = Join-Path $OptimizedRoot $MapName
$MaxGlbBytes = 2GB

function Write-Log([string]$Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $Message"
}

function Test-MapName([string]$Name) {
    return $Name -match '^[a-z0-9_]+$' -and $Name -notmatch '\.\.'
}

function Find-OptimizationTool {
    $candidates = @(
        @{ Name = "gltfpack"; Command = "gltfpack"; License = "MIT (Meshoptimizer)" },
        @{ Name = "gltf-transform"; Command = "gltf-transform"; License = "MIT" },
        @{ Name = "blender"; Command = "blender"; License = "GPL" }
    )
    foreach ($candidate in $candidates) {
        $resolved = Get-Command $candidate.Command -ErrorAction SilentlyContinue
        if ($resolved) {
            $version = try {
                & $resolved.Source --version 2>&1 | Select-Object -First 1
            } catch {
                "unknown version"
            }
            return [PSCustomObject]@{
                Name = $candidate.Name
                Path = $resolved.Source
                License = $candidate.License
                Version = $version
            }
        }
    }
    return $null
}

function Get-SourceGltf([string]$Root) {
    $gltf = Get-ChildItem -Path $Root -Filter *.gltf -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($gltf) { return $gltf.FullName }
    $glb = Get-ChildItem -Path $Root -Filter *.glb -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($glb) { return $glb.FullName }
    return $null
}

function Test-SourceReferences([string]$GltfPath) {
    $dir = Split-Path -Parent $GltfPath
    $ext = [IO.Path]::GetExtension($GltfPath).ToLowerInvariant()
    if ($ext -eq ".glb") {
        return @()
    }
    $json = Get-Content -Raw -Path $GltfPath | ConvertFrom-Json
    $missing = @()
    if ($json.buffers) {
        foreach ($buffer in $json.buffers) {
            if ($buffer.uri -and -not ($buffer.uri -like "data:*")) {
                $candidate = Join-Path $dir $buffer.uri
                if (-not (Test-Path $candidate)) { $missing += $buffer.uri }
            }
        }
    }
    if ($json.images) {
        foreach ($image in $json.images) {
            if ($image.uri -and -not ($image.uri -like "data:*")) {
                $candidate = Join-Path $dir $image.uri
                if (-not (Test-Path $candidate)) { $missing += $image.uri }
            }
        }
    }
    return $missing
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

if (-not (Test-MapName $MapName)) {
    throw "Invalid map name: $MapName"
}

$sourceResolved = Resolve-Path -LiteralPath $SourcePath -ErrorAction Stop
if ($sourceResolved.ProviderPath -notlike "$RepoRoot*") {
    Write-Log "Source path is outside repo; output still stays under data/maps3d/optimized."
}

$sourceGltf = Get-SourceGltf $sourceResolved.ProviderPath
if (-not $sourceGltf) {
    throw "No .gltf or .glb found in source path: $SourcePath"
}

$missingRefs = Test-SourceReferences $sourceGltf
if ($missingRefs.Count -gt 0) {
    throw "Missing referenced files in source export: $($missingRefs -join ', ')"
}

$tool = Find-OptimizationTool
if (-not $tool) {
    throw "No optimization tool found (gltfpack, gltf-transform, or blender). Install one manually; this script does not download tools."
}

Write-Log "Optimization backend: $($tool.Name) $($tool.Version) [$($tool.License)]"

$drive = (Split-Path -Qualifier $OptimizedRoot)
$free = (Get-PSDrive ($drive.TrimEnd(':'))).Free
if ($free -lt 1GB) {
    throw "Insufficient disk space under $OptimizedRoot"
}

if ((Test-Path $TargetDir) -and (Get-ChildItem $TargetDir -ErrorAction SilentlyContinue)) {
    throw "Target already exists; refusing to overwrite optimized output: $TargetDir"
}

if ($WhatIf) {
    Write-Log "WhatIf: would optimize '$sourceGltf' -> '$TargetDir/scene.glb' and write manifest.json"
    exit 0
}

New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
$tempGlb = Join-Path $TargetDir "scene.tmp.glb"

switch ($tool.Name) {
    "gltfpack" {
        & $tool.Path -i $sourceGltf -o $tempGlb
    }
    "gltf-transform" {
        & $tool.Path optimize $sourceGltf $tempGlb
    }
    default {
        throw "Selected optimization backend '$($tool.Name)' is detected but no automated conversion path is configured."
    }
}

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tempGlb)) {
    throw "Optimization failed using $($tool.Name)"
}

$size = (Get-Item $tempGlb).Length
if ($size -gt $MaxGlbBytes) {
    Remove-Item $tempGlb -Force
    throw "Optimized GLB exceeds 2 GB limit ($size bytes). Use glTF folder export instead."
}
if ($size -gt ($MaxGlbBytes / 2)) {
    Write-Log "WARNING: optimized GLB is large ($([math]::Round($size/1MB, 1)) MB)"
}

Move-Item -Force $tempGlb (Join-Path $TargetDir "scene.glb")
$sha = Get-Sha256 (Join-Path $TargetDir "scene.glb")
$manifest = @{
    schemaVersion = 1
    mapName = $MapName
    source = "user_exported_from_local_cs2_install"
    sourceTool = "Source 2 Viewer"
    sourceClientVersion = if ($ClientVersion) { $ClientVersion } else { $null }
    coordinateFrame = "source2_world_z_up"
    units = "hammer_units"
    viewerTransformVersion = 1
    sceneFile = "scene.glb"
    sceneSha256 = $sha
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    licenseNotice = "Local user-provided game asset; do not commit or redistribute."
}
$manifestPath = Join-Path $TargetDir "manifest.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, [System.Text.UTF8Encoding]::new($false))

Write-Log "Prepared map asset at $TargetDir"
Write-Log "sceneSha256=$sha"
