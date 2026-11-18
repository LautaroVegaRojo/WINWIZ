# WINWIZ - WiZ Control

Control de lámparas WiZ desde la bandeja del sistema de Windows. Vive como un
ícono flotante: un click y aparece un panel con tus lámparas y grupos, sin
tener que abrir la app oficial.

## Funcionalidades

- **Descubrimiento automático** de lámparas WiZ en la red local (UDP broadcast),
  con reintentos y opción de **agregar por IP** si el broadcast no llega.
- Control individual por lámpara: encendido/apagado, brillo, temperatura de color y matiz.
- **Grupos**: agrupá varias lámparas y controlalas como una sola unidad, con sincronización de sliders entre el grupo y cada lámpara individual.
- **Selector de color exacto**: además del slider de matiz (que solo cubre colores a saturación/brillo máximo), un color picker nativo de Windows para elegir cualquier tono exacto por RGB/HEX.
- **Estado en línea**: detecta las lámparas que dejaron de responder y las atenúa.
- **Renombrar** lámparas y grupos con clic derecho, y **borrado** con confirmación.
- Ventana flotante sin bordes, con vidrio esmerilado, que aparece al lado del cursor y se oculta sola al alejar el mouse (se pausa mientras hay un diálogo abierto, como el color picker).
- Persistencia de lámparas y grupos entre sesiones.
- **Actualización desde la app**: el botón de actualización (flecha circular), al lado del engranaje, revisa GitHub al iniciar, gira si hay una versión nueva y la instala con un clic.

## Requisitos

- Windows (usa `QSystemTrayIcon` e íconos `.ico`; no probado en Linux/Mac)
- Python 3.10+
- Lámparas WiZ en la misma red local que la PC (el descubrimiento usa broadcast UDP, no funciona a través de VPN o redes separadas por VLAN sin mDNS/broadcast relay)

## Instalar en cualquier PC con Windows

Abrí **PowerShell** (no hace falta ejecutarlo como administrador) y pegá:

```powershell
irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/main/install.ps1 | iex
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
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/main/install.ps1))) -NoDesktopShortcut -NoLaunch
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

## Actualizaciones desde la app

Al lado del engranaje de ajustes hay un botón con una **flecha circular**:

- Al abrir WINWIZ se fija silenciosamente si hay una versión nueva en GitHub.
  Si la hay, **el ícono empieza a girar** y cambia al color de acento.
- Clic en el ícono abre una confirmación con la versión instalada y la
  nueva; al aceptar, se descarga y aplica el instalador, WINWIZ se cierra y
  **vuelve a abrir solo** al terminar. Se conservan lámparas, grupos y ajustes.
- Si apretás el botón cuando no hay una actualización detectada, fuerza una
  búsqueda manual y muestra el resultado en la barrita del panel.
- En **Ajustes de apariencia → Actualizaciones** podés elegir el color del
  ícono en reposo. Cuando hay una versión nueva, el ícono gira y usa el color
  de acento para que se distinga.

Necesita conexión a Internet. La primera vez que corre una instalación antigua
toma el commit actual como base, así que el aviso aparece recién cuando haya un
commit nuevo en el branch instalado.

## Desinstalar

Desde PowerShell:

```powershell
irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/main/uninstall.ps1 | iex
```

También podés usar **Configuración → Aplicaciones → WINWIZ** o el acceso
directo **Desinstalar WINWIZ** del menú Inicio.

Por defecto se conservan las lámparas y los ajustes. Para borrarlos también:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/main/uninstall.ps1))) -RemoveData
```

## Volver a poner el icono en el inicio (Startup)

Si por cualquier motivo desapareció el acceso de inicio (`WINWIZ.lnk` en la
carpeta Startup), la forma más simple es reinstalar con `-StartWithWindows`:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/LautaroVegaRojo/WINWIZ/main/install.ps1))) -StartWithWindows
```

El instalador siempre escribe el mismo archivo, así que **no crea duplicados**
aunque el acceso ya exista. Eso sí: cerrá WINWIZ desde el icono de la bandeja
antes de reinstalar (si está abierto, el instalador no continúa).

Si preferís no reinstalar, abrí **PowerShell** y pegá esto para crear el acceso
directamente:

```powershell
$installDir = Join-Path $env:LOCALAPPDATA "Programs\WINWIZ"
$pythonw = Join-Path $installDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw)) { $pythonw = Join-Path $installDir ".venv\Scripts\python.exe" }
$mainPy = Join-Path $installDir "main.py"
$icon = Join-Path $installDir "icon.ico"
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "WINWIZ.lnk"

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $mainPy + '"'
$shortcut.WorkingDirectory = $installDir
$shortcut.IconLocation = $icon
$shortcut.Description = "WiZ Control - luces WiZ"
$shortcut.Save()
```

En los dos casos queda un único acceso en
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` apuntando a la
instalación actual. Para confirmar, cerrá sesión y volvé a entrar o revisá
**Administrador de tareas → Inicio**. El desinstalador elimina este acceso, así
que después de desinstalar hay que volver a agregarlo.

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

## Dónde guarda los datos

La app guarda las lámparas y grupos descubiertos en:

```
%LOCALAPPDATA%\WizLampControl\lamps_data.json
```

Esto es independiente de dónde esté instalado el `.exe`, así que funciona
incluso si lo instalás en `Program Files` sin permisos de administrador.

## Estructura del proyecto

```
main.py                # Toda la app: descubrimiento, lógica de red, UI y tray icon
install.ps1            # Instalador de un comando
uninstall.ps1          # Desinstalador
WizLampControl.spec    # Receta de PyInstaller
icon.ico               # Ícono de la bandeja del sistema y del ejecutable
```

## Limitaciones conocidas

- El slider de matiz solo representa colores a saturación y brillo máximos; para tonos pasteles u oscuros exactos, usar el color picker.
- El descubrimiento depende de que las lámparas respondan a broadcast UDP en el puerto `38899`; routers con "AP/client isolation" activado pueden bloquearlo.
