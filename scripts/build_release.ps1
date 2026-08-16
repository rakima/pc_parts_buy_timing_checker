param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not $SkipInstall) {
        python -m pip install -r requirements-dev.txt
    }
    python -m unittest discover
    python -m PyInstaller --clean --noconfirm Victor.spec
    $warnings = "build\Victor\warn-Victor.txt"
    if ((Test-Path $warnings) -and (Select-String -Path $warnings -Pattern "missing module named tkinter" -Quiet)) {
        throw "tkinterを同梱できませんでした。tkinterを含むPython 3.13環境で再実行してください。"
    }

    $version = python -c "from victor import __version__; print(__version__)"
    $archive = "dist\Victor-v$version-windows-x64.zip"
    if (Test-Path $archive) {
        Remove-Item -LiteralPath $archive
    }
    Compress-Archive -Path "dist\Victor.exe", "README.md", "CHANGELOG.md", "LICENSE" `
        -DestinationPath $archive
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$archive.sha256" -Value "$hash  $(Split-Path -Leaf $archive)" -Encoding ascii
    Write-Host "Created $archive"
} finally {
    Pop-Location
}
