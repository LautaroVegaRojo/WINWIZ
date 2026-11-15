<#
.SYNOPSIS
    Instalador de WINWIZ (WiZ Control) para Windows.

.DESCRIPTION
    Descarga la aplicacion desde GitHub, prepara un entorno de Python aislado
    con PyQt6 y crea los accesos directos. No necesita permisos de
    administrador: todo queda en el perfil del usuario.

    Instalacion (pegar en PowerShell):
        irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/install.ps1 | iex

    Desinstalacion:
        irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/uninstall.ps1 | iex
#>
param(
    [string]$Branch = "feature/frosted-glass",
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\WINWIZ",
    [switch]$NoStartMenuShortcut,
    [switch]$NoDesktopShortcut,
    [switch]$StartWithWindows,
    [switch]$NoLaunch,
    [switch]$NoRegistry,
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch { }

$Repo = "LautaroVegaRojo/WINWIZ"
$AppTitle = "WiZ Control"
$DataDir = Join-Path $env:LOCALAPPDATA "WizLampControl"

# Permite configurar el instalador tambien desde el comando de una linea.
if (-not $PSBoundParameters.ContainsKey("Branch") -and $env:WINWIZ_BRANCH) {
    $Branch = $env:WINWIZ_BRANCH
}
if (-not $PSBoundParameters.ContainsKey("InstallDir") -and $env:WINWIZ_INSTALL_DIR) {
    $InstallDir = $env:WINWIZ_INSTALL_DIR
}
if ($env:WINWIZ_DRY_RUN -eq "1") { $DryRun = $true }

function Write-Step([string]$Text) {
    if (-not $Quiet) { Write-Host "  $Text" -ForegroundColor Gray }
}

function Write-Ok([string]$Text) {
    if (-not $Quiet) { Write-Host "  [OK] $Text" -ForegroundColor Green }
}

function Get-PythonVersion([string]$Exe) {
    try {
        $lines = & $Exe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $lines) { return $null }
        $text = ($lines | Select-Object -Last 1).ToString().Trim()
        return [version]$text
    } catch {
        return $null
    }
}

function Find-Python {
    $candidates = New-Object System.Collections.Generic.List[string]

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $launcher) { $launcher = Get-Command py -ErrorAction SilentlyContinue }
    if ($launcher) {
        foreach ($version in @("3.12", "3.13", "3.11", "3.10", "3")) {
            try {
                $path = & $launcher.Source "-$version" -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $path) {
                    $path = ($path | Select-Object -Last 1).ToString().Trim()
                    if ($path -and (Test-Path -LiteralPath $path)) {
                        $candidates.Add($path)
                    }
                }
            } catch { }
        }
    }

    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -and $command.Source -notlike "*\WindowsApps\*") {
            $candidates.Add($command.Source)
        }
    }

    $roots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        (Join-Path $env:ProgramFiles "Python"),
        (Join-Path ${env:ProgramFiles(x86)} "Python")
    )
    foreach ($root in $roots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        $dirs = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending
        foreach ($dir in $dirs) {
            $candidate = Join-Path $dir.FullName "python.exe"
            if (Test-Path -LiteralPath $candidate) { $candidates.Add($candidate) }
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        $key = $candidate.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $version = Get-PythonVersion $candidate
        if ($version -and $version -ge [version]"3.9") {
            return [pscustomobject]@{ Path = $candidate; Version = $version }
        }
    }
    return $null
}

function Install-Python {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { $winget = Get-Command winget -ErrorAction SilentlyContinue }

    if ($winget) {
        Write-Step "No se encontro Python. Instalando Python 3.12 con winget..."
        try {
            & $winget.Source install --id Python.Python.3.12 --exact --source winget `
                --silent --accept-package-agreements --accept-source-agreements `
                --scope user 2>&1 | Out-Null
        } catch { }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "User")
        $found = Find-Python
        if ($found) { return $found }
    }

    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $installer = Join-Path ([IO.Path]::GetTempPath()) "python-3.12.10-amd64.exe"
    Write-Step "Descargando e instalando Python 3.12 desde python.org..."
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    Start-Process -FilePath $installer -Wait -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1",
        "Include_launcher=1", "Include_test=0"
    )
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [Environment]::GetEnvironmentVariable("Path", "User")
    return Find-Python
}

function New-Shortcut {
    param(
        [string]$Path,
        [string]$Target,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$Icon,
        [string]$Description
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = $Icon
    $shortcut.Description = $Description
    $shortcut.Save()
}

function Install-Winwiz {
    if ($env:OS -ne "Windows_NT") {
        throw "Este instalador es solo para Windows."
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "Se requiere una version de Windows de 64 bits."
    }

    $InstallDir = [Environment]::ExpandEnvironmentVariables($InstallDir)

    Write-Host ""
    Write-Host "  WINWIZ - $AppTitle" -ForegroundColor Cyan
    Write-Host "  Instalador para Windows" -ForegroundColor DarkGray
    Write-Host ""

    if ($DryRun) {
        Write-Host "  Modo de prueba: no se descarga ni se modifica nada." -ForegroundColor Yellow
        Write-Host "  Rama:       $Branch"
        Write-Host "  Instalaria: $InstallDir"
        Write-Host ""
        return
    }

    # -- Comprobar que la app no este abierta (reinstalacion) --------------
    $running = $null
    try {
        $running = Get-CimInstance Win32_Process `
            -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.ToLowerInvariant().Contains($InstallDir.ToLowerInvariant())
            }
    } catch { $running = $null }
    if ($running) {
        throw "WINWIZ esta abierto. Cerralo desde el icono de la bandeja y volve a ejecutar el instalador."
    }

    # -- Carpeta de instalacion --------------------------------------------
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    try {
        $probe = Join-Path $InstallDir ".write-test"
        Set-Content -LiteralPath $probe -Value "ok" -Encoding ASCII
        Remove-Item -LiteralPath $probe -Force
    } catch {
        throw "No se puede escribir en '$InstallDir'."
    }

    # -- Descargar el codigo desde GitHub ----------------------------------
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("winwiz-install-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        $zipUrl = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
        $zipPath = Join-Path $tempRoot "winwiz.zip"
        Write-Step "Descargando WINWIZ ($Branch)..."
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

        $extractDir = Join-Path $tempRoot "src"
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
        $sourceDir = Get-ChildItem -LiteralPath $extractDir -Directory | Select-Object -First 1
        if (-not $sourceDir -or -not (Test-Path -LiteralPath (Join-Path $sourceDir.FullName "main.py"))) {
            throw "El paquete descargado no contiene main.py. Revisa la rama '$Branch'."
        }

        Copy-Item -LiteralPath (Join-Path $sourceDir.FullName "main.py") -Destination $InstallDir -Force
        Copy-Item -LiteralPath (Join-Path $sourceDir.FullName "icon.ico") -Destination $InstallDir -Force
        foreach ($extra in @("requirements.txt", "uninstall.ps1")) {
            $source = Join-Path $sourceDir.FullName $extra
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination $InstallDir -Force
            }
        }
        Write-Ok "Archivos descargados."
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    # -- Python + entorno aislado ------------------------------------------
    Write-Step "Buscando Python..."
    $python = Find-Python
    if (-not $python) { $python = Install-Python }
    if (-not $python) {
        throw "No se pudo instalar Python automaticamente. Instalalo desde https://www.python.org/downloads/ y volve a intentar."
    }
    Write-Ok "Python $($python.Version) encontrado."

    $venvDir = Join-Path $InstallDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creando entorno aislado..."
        & $python.Path -m venv $venvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
            throw "No se pudo crear el entorno de Python."
        }
    }
    $venvPythonw = Join-Path $venvDir "Scripts\pythonw.exe"
    if (-not (Test-Path -LiteralPath $venvPythonw)) { $venvPythonw = $venvPython }

    Write-Step "Instalando PyQt6 (puede tardar unos minutos)..."
    & $venvPython -m pip install --upgrade pip --disable-pip-version-check --quiet
    if ($LASTEXITCODE -ne 0) { throw "No se pudo actualizar pip." }

    $requirements = Join-Path $InstallDir "requirements.txt"
    if (Test-Path -LiteralPath $requirements) {
        & $venvPython -m pip install -r $requirements --disable-pip-version-check --quiet
    } else {
        & $venvPython -m pip install PyQt6 --disable-pip-version-check --quiet
    }
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo instalar PyQt6. Revisa la conexion a internet e intenta de nuevo."
    }
    Write-Ok "Dependencias listas."

    # -- Lanzador de consola (para diagnostico) ----------------------------
    $mainPy = Join-Path $InstallDir "main.py"
    $launcher = Join-Path $InstallDir "WINWIZ.cmd"
    $cmdContent = @"
@echo off
cd /d "%~dp0"
"$venvPythonw" "$mainPy"
"@
    Set-Content -LiteralPath $launcher -Value $cmdContent -Encoding ASCII

    # -- Accesos directos ---------------------------------------------------
    $iconPath = Join-Path $InstallDir "icon.ico"
    $startMenuDir = [Environment]::GetFolderPath("Programs")
    $startMenuCreated = $false
    if ($startMenuDir -and -not $NoStartMenuShortcut) {
        New-Shortcut -Path (Join-Path $startMenuDir "WINWIZ.lnk") `
            -Target $venvPythonw -Arguments "`"$mainPy`"" `
            -WorkingDirectory $InstallDir -Icon $iconPath `
            -Description "WiZ Control - luces WiZ"
        $startMenuCreated = $true
        Write-Ok "Acceso directo en el menu Inicio."
    }

    $uninstallScript = Join-Path $InstallDir "uninstall.ps1"
    if ($startMenuDir -and -not $NoStartMenuShortcut -and (Test-Path -LiteralPath $uninstallScript)) {
        $powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
        New-Shortcut -Path (Join-Path $startMenuDir "Desinstalar WINWIZ.lnk") `
            -Target $powershellExe `
            -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`" -Pause" `
            -WorkingDirectory $InstallDir -Icon $iconPath `
            -Description "Desinstalar WINWIZ"
    }

    if (-not $NoDesktopShortcut) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        if ($desktop) {
            New-Shortcut -Path (Join-Path $desktop "WINWIZ.lnk") `
                -Target $venvPythonw -Arguments "`"$mainPy`"" `
                -WorkingDirectory $InstallDir -Icon $iconPath `
                -Description "WiZ Control - luces WiZ"
            Write-Ok "Acceso directo en el escritorio."
        }
    }

    if ($StartWithWindows) {
        $startup = [Environment]::GetFolderPath("Startup")
        if ($startup) {
            New-Shortcut -Path (Join-Path $startup "WINWIZ.lnk") `
                -Target $venvPythonw -Arguments "`"$mainPy`"" `
                -WorkingDirectory $InstallDir -Icon $iconPath `
                -Description "WiZ Control - luces WiZ"
            Write-Ok "WINWIZ se abrira con Windows."
        }
    }

    # -- Registro de desinstalacion (Configuracion > Aplicaciones) ---------
    if (-not $NoRegistry) {
        $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WINWIZ"
        New-Item -Path $uninstallKey -Force | Out-Null
        $size = (Get-ChildItem -LiteralPath $InstallDir -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        $sizeKb = if ($size) { [int]($size / 1KB) } else { 0 }
        $uninstallCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`" -Pause"

        Set-ItemProperty -Path $uninstallKey -Name DisplayName -Value "WINWIZ - WiZ Control"
        Set-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value (Get-Date -Format "yyyy.MM.dd")
        Set-ItemProperty -Path $uninstallKey -Name Publisher -Value "Lautaro Vega Rojo"
        Set-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $InstallDir
        Set-ItemProperty -Path $uninstallKey -Name DisplayIcon -Value $iconPath
        Set-ItemProperty -Path $uninstallKey -Name UninstallString -Value $uninstallCommand
        Set-ItemProperty -Path $uninstallKey -Name EstimatedSize -Value $sizeKb -Type DWord
        Set-ItemProperty -Path $uninstallKey -Name InstallDate -Value (Get-Date -Format "yyyyMMdd")
        New-ItemProperty -Path $uninstallKey -Name NoModify -PropertyType DWord -Value 1 -Force | Out-Null
        New-ItemProperty -Path $uninstallKey -Name NoRepair -PropertyType DWord -Value 1 -Force | Out-Null
    }

    @(
        "branch=$Branch",
        "installed=$(Get-Date -Format o)",
        "install_dir=$InstallDir"
    ) | Set-Content -LiteralPath (Join-Path $InstallDir "install-info.txt") -Encoding UTF8

    # -- Listo ---------------------------------------------------------------
    Write-Host ""
    Write-Host "  WINWIZ se instalo correctamente." -ForegroundColor Green
    Write-Host "  Carpeta: $InstallDir" -ForegroundColor Gray
    Write-Host "  Datos:   $DataDir" -ForegroundColor Gray
    if ($startMenuCreated) {
        Write-Host "  Acceso:  Menu Inicio > WINWIZ" -ForegroundColor Gray
    }
    if (-not $NoDesktopShortcut) {
        Write-Host "           Escritorio > WINWIZ" -ForegroundColor Gray
    }
    Write-Host ""
    if (-not $NoRegistry) {
        Write-Host "  Para desinstalar: Configuracion > Aplicaciones > WINWIZ" -ForegroundColor DarkGray
        Write-Host "  o ejecuta el comando de desinstalacion del README." -ForegroundColor DarkGray
    } else {
        Write-Host "  Para desinstalar: ejecuta uninstall.ps1 de $InstallDir" -ForegroundColor DarkGray
    }
    Write-Host ""

    if (-not $NoLaunch -and -not $Quiet) {
        Start-Process -FilePath $venvPythonw -ArgumentList "`"$mainPy`"" -WorkingDirectory $InstallDir
    }
}

try {
    Install-Winwiz
} catch {
    Write-Host ""
    Write-Host "  No se pudo instalar WINWIZ." -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
}
