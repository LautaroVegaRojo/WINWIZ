# WINWIZ - WiZ Control

Control de lámparas WiZ para Windows, con panel flotante, vidrio esmerilado,
grupos de luces, vista previa de color y ajustes de apariencia.

## Instalar en cualquier PC con Windows

Abrí **PowerShell** (no hace falta ejecutarlo como administrador) y pegá:

```powershell
irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/install.ps1 | iex
```

El comando hace todo solo:

- Descarga la última versión del código desde GitHub.
- Instala **Python 3.12** si no está (con `winget` o el instalador oficial).
- Crea un entorno aislado con **PyQt6** (no modifica tu Python global).
- Agrega accesos directos en el **menú Inicio** y en el **escritorio**.
- Registra WINWIZ en **Configuración → Aplicaciones** para desinstalarlo.
- Abre la app al terminar.

Todo se instala en `%LOCALAPPDATA%\Programs\WINWIZ` y **no requiere permisos
de administrador**. Las lámparas y los ajustes se guardan aparte, en
`%LOCALAPPDATA%\WizLampControl`, así que actualizar o reinstalar no los borra.

### Opciones

El comando de una línea instala con los valores por defecto. Si necesitás
alguna opción, usá la forma con parámetros:

```powershell
# Sin acceso directo en el escritorio y sin abrir la app al final
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/install.ps1))) -NoDesktopShortcut -NoLaunch
```

| Opción | Efecto |
|---|---|
| `-InstallDir "D:\Apps\WINWIZ"` | Instala en otra carpeta. |
| `-NoStartMenuShortcut` | No crea el acceso del menú Inicio. |
| `-NoDesktopShortcut` | No crea el acceso del escritorio. |
| `-StartWithWindows` | Abre WINWIZ al iniciar sesión. |
| `-NoLaunch` | No abre la app al terminar la instalación. |
| `-NoRegistry` | No registra la desinstalación en Configuración. |
| `-DryRun` | Muestra qué haría, sin descargar ni modificar nada. |
| `-Quiet` | Instalación silenciosa (sin mensajes ni apertura). |
| `-Branch "main"` | Instala desde otra rama del repositorio. |

## Desinstalar

Desde PowerShell:

```powershell
irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/uninstall.ps1 | iex
```

También podés usar **Configuración → Aplicaciones → WINWIZ** o el acceso
directo **Desinstalar WINWIZ** del menú Inicio.

Por defecto se conservan las lámparas y los ajustes. Para borrarlos también:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/feature/frosted-glass/uninstall.ps1))) -RemoveData
```

## Ejecutar desde el código

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py
```

## Compilar un EXE

El repositorio incluye `WizLampControl.spec` para PyInstaller:

```powershell
.\venv\Scripts\python.exe -m pip install pyinstaller
.\venv\Scripts\python.exe -m PyInstaller WizLampControl.spec
```

El ejecutable queda en `dist\WizLampControl.exe`.
