# WinWiz

Control de lámparas WiZ desde la bandeja del sistema de Windows. Vive como un ícono flotante: un click y aparece un panel con tus lámparas y grupos, sin tener que abrir la app oficial.

## Funcionalidades

- **Descubrimiento automático** de lámparas WiZ en la red local (UDP broadcast).
- Control individual por lámpara: encendido/apagado, brillo, temperatura de color y matiz.
- **Grupos**: agrupá varias lámparas y controlalas como una sola unidad, con sincronización de sliders entre el grupo y cada lámpara individual.
- **Selector de color exacto**: además del slider de matiz (que solo cubre colores a saturación/brillo máximo), un color picker nativo de Windows para elegir cualquier tono exacto por RGB/HEX.
- **Borrado** de lámparas y grupos, con confirmación.
- Ventana flotante sin bordes que aparece al lado del cursor y se oculta sola al alejar el mouse (se pausa automáticamente mientras hay un diálogo abierto, como el color picker).
- Persistencia de lámparas y grupos entre sesiones.

## Requisitos

- Windows (usa `QSystemTrayIcon` e íconos `.ico`; no probado en Linux/Mac)
- Python 3.10+
- Lámparas WiZ en la misma red local que la PC (el descubrimiento usa broadcast UDP, no funciona a través de VPN o redes separadas por VLAN sin mDNS/broadcast relay)

## Instalación (modo desarrollo)

```powershell
git clone https://github.com/<tu-usuario>/winwiz.git
cd winwiz
python -m venv venv
.\venv\Scripts\activate
pip install PyQt6
python main.py
```

## Compilar a ejecutable (.exe)

```powershell
.\venv\Scripts\activate
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --name WizLampControl main.py
```

El ejecutable queda en `dist\WizLampControl.exe`, autocontenido (no necesita Python instalado en la PC destino).

## Dónde guarda los datos

La app guarda las lámparas y grupos descubiertos en:

```
%LOCALAPPDATA%\WizLampControl\lamps_data.json
```

Esto es independiente de dónde esté instalado el `.exe`, así que funciona incluso si lo instalás en `Program Files` sin permisos de administrador.

## Estructura del proyecto

```
main.py       # Toda la app: descubrimiento, lógica de red, UI y tray icon
icon.ico      # Ícono de la bandeja del sistema y del ejecutable
```

## Limitaciones conocidas

- El slider de matiz solo representa colores a saturación y brillo máximos; para tonos pasteles u oscuros exactos, usar el color picker.
- El descubrimiento depende de que las lámparas respondan a broadcast UDP en el puerto `38899`; routers con "AP/client isolation" activado pueden bloquearlo.
