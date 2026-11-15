<#
.SYNOPSIS
    Desinstalador de WINWIZ (WiZ Control).

.DESCRIPTION
    Quita los accesos directos, el registro de desinstalacion y la carpeta de
    la aplicacion. Por defecto conserva las lamparas y los ajustes guardados.

    Desinstalacion desde PowerShell:
        irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/uninstall.ps1 | iex

    Para borrar tambien los datos del usuario:
        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/uninstall.ps1))) -RemoveData
#>
param(
    [switch]$RemoveData,
    [switch]$Pause,
    [switch]$Silent
)

$ErrorActionPreference = "SilentlyContinue"

function Write-Step([string]$Text) {
    if (-not $Silent) { Write-Host "  $Text" -ForegroundColor Gray }
}

function Find-InstallDir {
    if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot "main.py"))) {
        return $PSScriptRoot
    }
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WINWIZ"
    $fromRegistry = (Get-ItemProperty -Path $key -Name InstallLocation).InstallLocation
    if ($fromRegistry) { return $fromRegistry }
    return (Join-Path $env:LOCALAPPDATA "Programs\WINWIZ")
}

$InstallDir = Find-InstallDir
$DataDir = Join-Path $env:LOCALAPPDATA "WizLampControl"

if (-not $Silent) {
    Write-Host ""
    Write-Host "  WINWIZ - Desinstalador" -ForegroundColor Cyan
    Write-Host ""
}

if (-not (Test-Path -LiteralPath $InstallDir)) {
    Write-Step "WINWIZ no parece estar instalado en '$InstallDir'."
} else {
    Write-Step "Cerrando WINWIZ si esta abierto..."
    Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.ToLowerInvariant().Contains($InstallDir.ToLowerInvariant())
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep -Milliseconds 500

    Write-Step "Quitando accesos directos..."
    $folders = @(
        [Environment]::GetFolderPath("Programs"),
        [Environment]::GetFolderPath("Desktop"),
        [Environment]::GetFolderPath("Startup"),
        (Join-Path $env:PUBLIC "Desktop")
    ) | Where-Object { $_ } | Select-Object -Unique
    foreach ($folder in $folders) {
        foreach ($name in @("WINWIZ.lnk", "Desinstalar WINWIZ.lnk")) {
            Remove-Item -LiteralPath (Join-Path $folder $name) -Force
        }
    }
    Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WINWIZ" -Recurse -Force

    Write-Step "Borrando archivos de la aplicacion..."
    Set-Location ([IO.Path]::GetTempPath())
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
    if (Test-Path -LiteralPath $InstallDir) {
        # Si algun archivo quedo bloqueado, se reintenta en segundo plano.
        Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c ping 127.0.0.1 -n 3 >nul & rmdir /s /q `"$InstallDir`"" `
            -WindowStyle Hidden
    }
}

if ($RemoveData) {
    Write-Step "Borrando lamparas y ajustes guardados..."
    Remove-Item -LiteralPath $DataDir -Recurse -Force
}

if (-not $Silent) {
    Write-Host ""
    Write-Host "  WINWIZ se desinstalo." -ForegroundColor Green
    if (-not $RemoveData) {
        Write-Host "  Los datos se conservaron en $DataDir" -ForegroundColor DarkGray
        Write-Host "  (usa -RemoveData para borrarlos tambien)" -ForegroundColor DarkGray
    }
    Write-Host ""
}

if ($Pause -and [Environment]::UserInteractive) {
    try { Read-Host "Presiona Enter para cerrar" | Out-Null } catch { }
}
