param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    Get-ChildItem -Path "dist" -Filter "Victor*" -ErrorAction SilentlyContinue |
        Remove-Item -Force

    $pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($pythonVersion -ne "3.13") {
        throw "Windows配布版のビルドにはPython 3.13が必要です (現在: $pythonVersion)。"
    }
    if (-not $SkipInstall) {
        python -m pip install -r requirements-dev.txt
    }
    python -c "import tkinter, _tkinter; print('Tk', tkinter.TkVersion)"
    python -m unittest discover
    python -m PyInstaller --clean --noconfirm Victor.spec
    $warnings = "build\Victor\warn-Victor.txt"
    if ((Test-Path $warnings) -and (Select-String -Path $warnings -Pattern "missing module named tkinter" -Quiet)) {
        throw "tkinterを同梱できませんでした。tkinterを含むPython 3.13環境で再実行してください。"
    }

    $app = Start-Process -FilePath "dist\Victor.exe" -PassThru
    Start-Sleep -Seconds 5
    if ($app.HasExited) {
        throw "ビルドしたVictor.exeが起動直後に終了しました (exit code: $($app.ExitCode))。"
    }
    Stop-Process -Id $app.Id

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
} catch {
    Get-ChildItem -Path "dist" -Filter "Victor*" -ErrorAction SilentlyContinue |
        Remove-Item -Force
    throw
} finally {
    Pop-Location
}
