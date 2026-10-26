$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $projectRoot "dist"
$stagingRoot = Join-Path $distRoot "visionflow-pi-docker"
$archivePath = Join-Path $distRoot "visionflow-pi-docker.zip"
$tarPath = Join-Path $distRoot "visionflow-pi-docker.tar.gz"

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
if (Test-Path -LiteralPath $stagingRoot) {
    $resolvedStage = (Resolve-Path -LiteralPath $stagingRoot).Path
    $resolvedDist = (Resolve-Path -LiteralPath $distRoot).Path
    if (-not $resolvedStage.StartsWith($resolvedDist + [IO.Path]::DirectorySeparatorChar)) {
        throw "Unsafe staging path: $resolvedStage"
    }
    Remove-Item -LiteralPath $resolvedStage -Recurse -Force
}
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
if (Test-Path -LiteralPath $tarPath) {
    Remove-Item -LiteralPath $tarPath -Force
}
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

$files = @(
    ".dockerignore",
    "Dockerfile.pi",
    "docker-compose.pi.yml",
    "config.pi.yaml",
    "custom_fasttrack.yaml",
    "requirements-pi.txt",
    "run_web.py",
    "README_DEPLOY_PI.md"
)
foreach ($relative in $files) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $relative) -Destination $stagingRoot
}

$directories = @("src", "web", "docker")
foreach ($relative in $directories) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $relative) -Destination $stagingRoot -Recurse
}

$scriptDest = Join-Path $stagingRoot "scripts"
New-Item -ItemType Directory -Force -Path $scriptDest | Out-Null
foreach ($name in @("smoke_ncnn.py", "deploy_docker_pi.sh", "export_docker_image_pi.sh", "install_ncnn_pi.sh", "install_docker_pi.sh", "publish_docker_pi.sh")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $scriptDest
}

# Archives built on Windows must keep Unix shell scripts in LF format. Git can
# normalize files in the index while the working tree still contains CRLF, so
# normalize the staged copies explicitly before creating the archives.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
Get-ChildItem -LiteralPath $stagingRoot -Recurse -Filter "*.sh" -File |
    ForEach-Object {
        $content = [IO.File]::ReadAllText($_.FullName)
        $content = $content.Replace("`r`n", "`n").Replace("`r", "`n")
        [IO.File]::WriteAllText($_.FullName, $content, $utf8NoBom)
    }

$modelsDest = Join-Path $stagingRoot "models"
New-Item -ItemType Directory -Force -Path $modelsDest | Out-Null
foreach ($name in @("yolo26n_person_v1_320_ncnn_int8", "osnet_x0_25_ncnn_model")) {
    Copy-Item -LiteralPath (Join-Path (Join-Path $projectRoot "models") $name) -Destination $modelsDest -Recurse
}

$uploadsDest = Join-Path $stagingRoot "uploads"
New-Item -ItemType Directory -Force -Path $uploadsDest | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $uploadsDest ".gitkeep") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $stagingRoot "database.db") | Out-Null

$manifestLines = Get-ChildItem -LiteralPath $stagingRoot -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($stagingRoot.Length + 1).Replace("\", "/")
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
Set-Content -LiteralPath (Join-Path $stagingRoot "SHA256SUMS.txt") -Value $manifestLines -Encoding utf8

Compress-Archive -LiteralPath $stagingRoot -DestinationPath $archivePath -CompressionLevel Optimal
$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archivePath.sha256" -Value "$archiveHash  visionflow-pi-docker.zip" -Encoding ascii

& tar -czf $tarPath -C $distRoot "visionflow-pi-docker"
if ($LASTEXITCODE -ne 0) {
    throw "tar failed with exit code $LASTEXITCODE"
}
$tarHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $tarPath).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$tarPath.sha256" -Value "$tarHash  visionflow-pi-docker.tar.gz" -Encoding ascii

Write-Host "Created: $archivePath"
Write-Host "SHA256: $archiveHash"
Write-Host "Created: $tarPath"
Write-Host "SHA256: $tarHash"
