import PySimpleGUI as sg
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem
from PIL import Image
import asyncio
import queue
import threading
import sys
import logging

# --- imports propios ---
from wiz_controller import set_light_state, set_all_lights
from config_manager import load_config, add_or_update_light, delete_light

# Cola de comunicación entre el hilo de la GUI y el hilo asíncrono
async_queue = queue.Queue()

# Variable global para el ícono de la bandeja del sistema
icon = None

# Configura el logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# --- Hilo de trabajo asíncrono ---
def asyncio_worker(q):
    """Ejecuta un único y persistente bucle de eventos asíncrono en un hilo dedicado."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def process_queue():
        while True:
            try:
                # Get the command from the queue
                command = await asyncio.to_thread(q.get)
                
                if isinstance(command, dict):
                    # Handle individual light commands
                    if "cmd" in command and "ip" in command:
                        if command["cmd"] == "on":
                            await set_light_state(command["ip"], state=True)
                        elif command["cmd"] == "off":
                            await set_light_state(command["ip"], state=False)
                    # Handle the 'turn all on/off' commands
                    elif "cmd" in command and command["cmd"] == "all":
                        await set_all_lights(state=command["state"])
                else:
                    # Handle coroutine commands
                    await command
            except Exception as e:
                logging.error(f"Error processing async command: {e}")

    try:
        loop.run_until_complete(process_queue())
    except RuntimeError as e:
        logging.error(f"Error en el bucle de eventos asíncrono: {e}")
    finally:
        loop.close()


# --- Helper functions para el hilo de la GUI ---
def send_async_command(coro):
    """Envía una corrutina al hilo asíncrono a través de la cola."""
    async_queue.put(coro)


def turn_on_light(name):
    """Sends a command to turn a single light on."""
    config = load_config()
    ip = config.get(name)
    if ip:
        # Send a dictionary with the command and IP
        async_queue.put({"cmd": "on", "ip": ip})
        logging.info(f"Comando enviado: encender luz {name} ({ip})")
    else:
        logging.warning(f"No se encontró IP para la luz: {name}")


def turn_off_light(name):
    """Sends a command to turn a single light off."""
    config = load_config()
    ip = config.get(name)
    if ip:
        # Send a dictionary with the command and IP
        async_queue.put({"cmd": "off", "ip": ip})
        logging.info(f"Comando enviado: apagar luz {name} ({ip})")
    else:
        logging.warning(f"No se encontró IP para la luz: {name}")


def turn_all_lights_on():
    """Turns all lights on."""
    async_queue.put({"cmd": "all", "state": True})
    logging.info("Comando enviado: encender todas las luces")


def turn_all_lights_off():
    """Turns all lights off."""
    async_queue.put({"cmd": "all", "state": False})
    logging.info("Comando enviado: apagar todas las luces")


# --- Bandeja del sistema ---
def create_tray_menu():
    """Crea el menú dinámico para la bandeja del sistema."""
    lights_config = load_config()

    menu_items = []

    menu_items.append(
        MenuItem("Encender todas", lambda icon: turn_all_lights_on())
    )
    menu_items.append(
        MenuItem("Apagar todas", lambda icon: turn_all_lights_off())
    )
    menu_items.append(TrayMenu.SEPARATOR)

    if lights_config:
        for name in lights_config:
            # Create closures to capture the current value of 'name'
            def make_turn_on_handler(light_name):
                return lambda icon: turn_on_light(light_name)
            
            def make_turn_off_handler(light_name):
                return lambda icon: turn_off_light(light_name)
            
            menu_items.append(
                MenuItem(
                    f"Luz: {name}",
                    TrayMenu(
                        MenuItem("Encender", make_turn_on_handler(name)),
                        MenuItem("Apagar", make_turn_off_handler(name)),
                    ),
                )
            )

    menu_items.append(TrayMenu.SEPARATOR)
    menu_items.append(MenuItem("Configuración...", lambda icon: open_config_window()))
    menu_items.append(MenuItem("Salir", lambda icon: icon.stop()))

    return TrayMenu(*menu_items)


def setup_tray_icon():
    """Configura el icono en la bandeja del sistema."""
    global icon
    try:
        image = Image.open("icon.ico")
    except FileNotFoundError:
        logging.error(
            "No se encontró el archivo 'icon.ico'. Asegúrate de que está en el mismo directorio."
        )
        return

    icon = TrayIcon("WiZ Control", image, "WiZ Control", create_tray_menu())
    icon.run()


# --- Ventana de Configuración ---
def create_config_layout():
    """Layout de la ventana de configuración."""
    lights = load_config()
    layout = [
        [sg.Text("Gestión de Luces WiZ", font=("Helvetica", 16, "bold"))],
        [sg.HorizontalSeparator()],
        [sg.Text("Nombre de la Luz:"), sg.InputText(key="-NAME-")],
        [sg.Text("Dirección IP:"), sg.InputText(key="-IP-")],
        [sg.Button("Guardar", key="-SAVE-"), sg.Button("Eliminar", key="-DELETE-")],
        [sg.HorizontalSeparator()],
        [sg.Text("Luces guardadas:", font=("Helvetica", 12, "bold"))],
    ]
    if lights:
        for name, ip in lights.items():
            layout.append(
                [
                    sg.Text(f"   - {name} ({ip})"),
                    sg.Button("Cargar", key=f"-LOAD_{name}"),
                ]
            )
    else:
        layout.append([sg.Text("No hay luces guardadas.")])
    layout.append([sg.HorizontalSeparator()])
    layout.append([sg.Button("Cerrar")])
    return layout


def open_config_window():
    """Abre la ventana de configuración."""
    window = sg.Window("Configuración", create_config_layout(), finalize=True)

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, "Cerrar"):
            break

        if event == "-SAVE-":
            name, ip = values["-NAME-"], values["-IP-"]
            if name and ip:
                add_or_update_light(name, ip)
                sg.popup("Luz guardada/actualizada con éxito!")
                window.close()
                icon.menu = create_tray_menu()
                break
            else:
                sg.popup_error("Por favor, ingresa un nombre y una IP válidos.")

        elif event == "-DELETE-":
            name = values["-NAME-"]
            if name:
                delete_light(name)
                sg.popup("Luz eliminada con éxito!")
                window.close()
                icon.menu = create_tray_menu()
                break
            else:
                sg.popup_error("Por favor, ingresa el nombre de la luz a eliminar.")

        elif event.startswith("-LOAD_"):
            name = event.split("_", 1)[1]
            lights = load_config()
            window["-NAME-"].update(name)
            window["-IP-"].update(lights[name])

    window.close()


# --- Main ---
if __name__ == "__main__":
    # Inicia el hilo de trabajo asíncrono
    asyncio_thread = threading.Thread(
        target=asyncio_worker, args=(async_queue,), daemon=True
    )
    asyncio_thread.start()

    # Inicia el ícono de la bandeja del sistema
    setup_tray_icon()