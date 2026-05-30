param(
  [switch]$NoPush
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = "http://127.0.0.1:10808" }
if (-not $env:HTTP_PROXY) { $env:HTTP_PROXY = "http://127.0.0.1:10808" }

$platforms = @(
  @{ id = "toutiao" },
  @{ id = "baidu" },
  @{ id = "wallstreetcn-hot" },
  @{ id = "thepaper" },
  @{ id = "bilibili-hot-search" },
  @{ id = "cls-hot" },
  @{ id = "ifeng" },
  @{ id = "tieba" },
  @{ id = "weibo" },
  @{ id = "douyin" },
  @{ id = "zhihu" }
)

$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$rawDir = Join-Path $env:TEMP "hotspot-miniapp-report\$runStamp"
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null

foreach ($platform in $platforms) {
  $sourceUrl = "https://newsnow.busiyi.world/api/s?id=$($platform.id)&latest"
  $target = Join-Path $rawDir "$($platform.id).json"
  $errorTarget = Join-Path $rawDir "$($platform.id).error.json"

  try {
    $response = Invoke-WebRequest -Uri $sourceUrl -UseBasicParsing -TimeoutSec 45
    $stream = $response.RawContentStream
    if ($stream.CanSeek) { $stream.Position = 0 }
    $memory = New-Object IO.MemoryStream
    $stream.CopyTo($memory)
    [IO.File]::WriteAllBytes($target, $memory.ToArray())
    Write-Host "Fetched $($platform.id) -> $target"
  } catch {
    $failure = @{
      id = $platform.id
      sourceUrl = $sourceUrl
      error = $_.Exception.Message
      fetchedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    } | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText($errorTarget, $failure, [Text.Encoding]::UTF8)
    Write-Warning "Failed $($platform.id): $($_.Exception.Message)"
  }
}

node .\scripts\build-report.js --raw $rawDir

$status = git status --short
if (-not $status) {
  Write-Host "No report changes to commit."
  exit 0
}

git add data/latest.json data/history.json reports
$commitMessage = "Run daily hotspot report $(Get-Date -Format 'yyyy-MM-dd')"
git commit -m $commitMessage

if ($NoPush) {
  Write-Host "NoPush specified; commit created locally but not pushed."
  exit 0
}

git push
