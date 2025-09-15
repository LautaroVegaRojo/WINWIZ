import json
import os

CONFIG_FILE = "lights_config.json"

def save_config(lights):
    """Guarda la configuración en un archivo JSON."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(lights, f, indent=4)

def load_config():
    """Carga la configuración de luces desde JSON."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def add_or_update_light(name, ip):
    """Añade o actualiza una luz."""
    lights = load_config()
    lights[name] = ip
    save_config(lights)

def delete_light(name):
    """Elimina una luz de la configuración."""
    lights = load_config()
    if name in lights:
        del lights[name]
        save_config(lights)