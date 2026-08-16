param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath("Desktop")) "VictorBackup")
)

$ErrorActionPreference = "Stop"
$source = Join-Path $env:LOCALAPPDATA "VictorPriceChecker"
if (-not (Test-Path -LiteralPath $source)) {
    throw "データ保存先が見つかりません: $source"
}
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $Destination "Victor-$timestamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $backup -Recurse
Write-Host "Backup created: $backup"
