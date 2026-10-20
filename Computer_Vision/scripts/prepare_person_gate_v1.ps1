[CmdletBinding()]
param(
    [string]$SourceDirectory = "sss",
    [string]$MallDirectory = "mall_dataset/frames",
    [string]$OutputDirectory = "datasets/person_gate_v1",
    [int]$MallSampleCount = 250,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot $SourceDirectory
$mallRoot = Join-Path $projectRoot $MallDirectory
$outputRoot = Join-Path $projectRoot $OutputDirectory

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "Khong tim thay ffmpeg trong PATH."
}
if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "Khong tim thay thu muc video: $sourceRoot"
}

# Không tách các đoạn gần nhau của cùng một video sang nhiều tập. Điều này
# tránh rò rỉ dữ liệu và làm sai lệch kết quả validation/test.
$splits = @(
    [pscustomobject]@{ Video = "1.mp4";  Split = "train"; Fps = 2 },
    [pscustomobject]@{ Video = "4.mp4";  Split = "train"; Fps = 2 },
    [pscustomobject]@{ Video = "5.mp4";  Split = "train"; Fps = 1 },
    [pscustomobject]@{ Video = "9.mp4";  Split = "train"; Fps = 1 },
    [pscustomobject]@{ Video = "10.mp4"; Split = "train"; Fps = 1 },
    [pscustomobject]@{ Video = "11.mp4"; Split = "train"; Fps = 2 },
    [pscustomobject]@{ Video = "2.mp4";  Split = "val";   Fps = 2 },
    [pscustomobject]@{ Video = "8.mp4";  Split = "val";   Fps = 2 },
    [pscustomobject]@{ Video = "3.mp4";  Split = "test";  Fps = 1 },
    [pscustomobject]@{ Video = "6.mp4";  Split = "test";  Fps = 1 }
)

foreach ($splitName in @("train", "val", "test")) {
    $imageDirectory = Join-Path $outputRoot "images/$splitName"
    $labelDirectory = Join-Path $outputRoot "labels/$splitName"
    New-Item -ItemType Directory -Force -Path $imageDirectory, $labelDirectory | Out-Null

    $existingImages = @(Get-ChildItem -LiteralPath $imageDirectory -Filter "*.jpg" -File)
    if ($existingImages.Count -gt 0 -and -not $Force) {
        throw "Thu muc $imageDirectory da co anh. Dung -Force neu muon ghi lai."
    }
}

foreach ($item in $splits) {
    $sourcePath = Join-Path $sourceRoot $item.Video
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Thieu video nguon: $sourcePath"
    }

    $videoId = [IO.Path]::GetFileNameWithoutExtension($item.Video).PadLeft(2, "0")
    $destination = Join-Path $outputRoot "images/$($item.Split)"
    $pattern = Join-Path $destination "video${videoId}_%06d.jpg"

    if ($Force) {
        Get-ChildItem -LiteralPath $destination -Filter "video${videoId}_*.jpg" -File |
            Remove-Item -Force
    }

    Write-Host "[$($item.Split)] $($item.Video) -> $($item.Fps) frame/giay"
    & ffmpeg -hide_banner -loglevel error -y -i $sourcePath `
        -vf "fps=$($item.Fps)" -q:v 2 -start_number 1 $pattern
    if ($LASTEXITCODE -ne 0) {
        throw "FFmpeg that bai voi video $($item.Video)"
    }
}

# Mall Dataset là một chuỗi từ cùng camera. Lấy mẫu đều toàn bộ chuỗi và chỉ
# đưa vào train để tránh rò rỉ cùng bối cảnh sang validation hoặc test.
if (-not (Test-Path -LiteralPath $mallRoot -PathType Container)) {
    throw "Khong tim thay thu muc Mall Dataset: $mallRoot"
}
$mallImages = @(Get-ChildItem -LiteralPath $mallRoot -Filter "*.jpg" -File | Sort-Object Name)
if ($MallSampleCount -lt 1 -or $MallSampleCount -gt $mallImages.Count) {
    throw "MallSampleCount phai nam trong khoang 1..$($mallImages.Count)"
}

$trainDirectory = Join-Path $outputRoot "images/train"
if ($Force) {
    Get-ChildItem -LiteralPath $trainDirectory -Filter "mall_*.jpg" -File |
        Remove-Item -Force
}

$mallManifest = @()
$selectedIndices = 0..($MallSampleCount - 1) | ForEach-Object {
    if ($MallSampleCount -eq 1) { 0 }
    else { [int][Math]::Round($_ * ($mallImages.Count - 1) / ($MallSampleCount - 1)) }
}
foreach ($index in $selectedIndices) {
    $sourceImage = $mallImages[$index]
    $destinationName = "mall_$($sourceImage.Name)"
    $destinationPath = Join-Path $trainDirectory $destinationName
    Copy-Item -LiteralPath $sourceImage.FullName -Destination $destinationPath
    $mallManifest += [pscustomobject]@{
        SourceImage = $sourceImage.Name
        OutputImage = $destinationName
        Split = "train"
    }
}

$mallManifestPath = Join-Path $outputRoot "mall_train_manifest.csv"
$mallManifest | Export-Csv -LiteralPath $mallManifestPath -NoTypeInformation -Encoding utf8
Write-Host "[train] Mall Dataset -> $MallSampleCount anh rai deu"

$manifestPath = Join-Path $outputRoot "split_manifest.csv"
$splits | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8

Write-Host ""
Write-Host "Da hoan thanh:"
foreach ($splitName in @("train", "val", "test")) {
    $count = @(Get-ChildItem -LiteralPath (Join-Path $outputRoot "images/$splitName") `
        -Filter "*.jpg" -File).Count
    Write-Host ("  {0,-5}: {1} anh" -f $splitName, $count)
}
Write-Host "Manifest: $manifestPath"
Write-Host "Mall manifest: $mallManifestPath"
Write-Host "Video 7.mp4 khong duoc su dung vi trung noi dung voi 3.mp4."
