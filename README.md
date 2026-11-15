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
