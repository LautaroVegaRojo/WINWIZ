from pywizlight import wizlight, PilotBuilder
from config_manager import load_config
import asyncio
import logging


async def set_light_state(ip, state=None):
    """
    Controla el estado (encendido/apagado) de una luz individual.
    """
    if not ip:
        logging.warning("No se proporcionó IP para controlar la luz.")
        return
    try:
        # Crea el objeto wizlight y controla la luz
        light = wizlight(ip)
        if state is True:
            await light.turn_on()
        elif state is False:
            await light.turn_off()
        logging.info(f"Luz en IP {ip} controlada a estado: {state}")
    except Exception as e:
        logging.error(f"Error al controlar la luz {ip}: {e}")


async def set_light_color(ip, rgb):
    """
    Cambia el color de una luz individual.
    Args:
        ip (str): Dirección IP de la luz
        rgb (tuple): Tupla con valores RGB (r, g, b)
    """
    if not ip:
        logging.warning("No se proporcionó IP para controlar la luz.")
        return
    try:
        light = wizlight(ip)
        await light.turn_on(PilotBuilder(rgb=rgb))
        logging.info(f"Color de luz en IP {ip} cambiado a RGB {rgb}")
    except Exception as e:
        logging.error(f"Error al cambiar color de la luz {ip}: {e}")


async def set_light_brightness(ip, brightness):
    """
    Cambia el brillo de una luz individual.
    Args:
        ip (str): Dirección IP de la luz
        brightness (int): Brillo de 10 a 100
    """
    if not ip:
        logging.warning("No se proporcionó IP para controlar la luz.")
        return
    try:
        # Asegurar que el brillo esté en el rango válido
        brightness = max(10, min(100, int(brightness)))
        
        light = wizlight(ip)
        await light.turn_on(PilotBuilder(brightness=brightness))
        logging.info(f"Brillo de luz en IP {ip} cambiado a {brightness}%")
    except Exception as e:
        logging.error(f"Error al cambiar brillo de la luz {ip}: {e}")


async def set_all_lights(state=None):
    """
    Controla todas las luces a la vez usando set_light_state para cada una.
    """
    lights_config = load_config()
    ips = list(lights_config.values())
   
    if not ips:
        logging.info("No hay luces configuradas para controlar.")
        return
       
    # Crea tareas usando set_light_state para cada IP
    tasks = []
    for ip in ips:
        task = asyncio.create_task(set_light_state(ip, state))
        tasks.append(task)
    
    try:
        await asyncio.gather(*tasks)
        logging.info(f"Todas las luces controladas a estado: {state}")
    except Exception as e:
        logging.error(f"Error al controlar todas las luces: {e}")