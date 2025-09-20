import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem
from PIL import Image
import asyncio
import queue
import threading
import sys
import logging

# --- imports propios ---
from wiz_controller import (
    set_light_state,
    set_all_lights,
    set_light_color,
    set_light_brightness,
)
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
                        elif command["cmd"] == "color":
                            await set_light_color(command["ip"], command["rgb"])
                        elif command["cmd"] == "brightness":
                            await set_light_brightness(
                                command["ip"], command["brightness"]
                            )
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
        async_queue.put({"cmd": "on", "ip": ip})
        logging.info(f"Comando enviado: encender luz {name} ({ip})")
    else:
        logging.warning(f"No se encontró IP para la luz: {name}")


def turn_off_light(name):
    """Sends a command to turn a single light off."""
    config = load_config()
    ip = config.get(name)
    if ip:
        async_queue.put({"cmd": "off", "ip": ip})
        logging.info(f"Comando enviado: apagar luz {name} ({ip})")
    else:
        logging.warning(f"No se encontró IP para la luz: {name}")


def set_light_color_cmd(name, rgb):
    """Sets a light's color."""
    config = load_config()
    ip = config.get(name)
    if ip:
        async_queue.put({"cmd": "color", "ip": ip, "rgb": rgb})
        logging.info(f"Comando enviado: cambiar color luz {name} ({ip}) a RGB {rgb}")
    else:
        logging.warning(f"No se encontró IP para la luz: {name}")


def set_light_brightness_cmd(name, brightness):
    """Sets a light's brightness."""
    config = load_config()
    ip = config.get(name)
    if ip:
        async_queue.put({"cmd": "brightness", "ip": ip, "brightness": brightness})
        logging.info(
            f"Comando enviado: cambiar brillo luz {name} ({ip}) a {brightness}%"
        )
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


# --- Clase para la ventana de configuración con tema oscuro moderno ---
class ConfigWindow:
    def __init__(self):
        self.root = None
        self.lights = load_config()
        # Colores del tema oscuro moderno
        self.colors = {
            "bg": "#1E1E1E",  # Fondo principal oscuro
            "surface": "#252526",  # Superficie elevada
            "surface_light": "#2D2D30",  # Superficie más clara
            "accent": "#007ACC",  # Azul moderno
            "accent_hover": "#1177BB",  # Azul hover
            "text": "#CCCCCC",  # Texto principal
            "text_secondary": "#969696",  # Texto secundario
            "success": "#4CAF50",  # Verde éxito
            "danger": "#F44336",  # Rojo peligro
            "warning": "#FF9800",  # Naranja advertencia
            "border": "#3E3E42",  # Bordes
        }

    def apply_dark_theme(self, widget, widget_type="default"):
        """Aplica el tema oscuro moderno a los widgets."""
        if isinstance(widget, tk.Tk):
            widget.configure(bg=self.colors["bg"])
        elif isinstance(widget, tk.Frame):
            widget.configure(bg=self.colors["bg"], relief="flat")
        elif isinstance(widget, tk.Label):
            widget.configure(
                bg=self.colors["bg"], fg=self.colors["text"], font=("Segoe UI", 9)
            )
        elif isinstance(widget, tk.Button):
            if widget_type == "primary":
                bg_color = self.colors["accent"]
                active_bg = self.colors["accent_hover"]
            elif widget_type == "success":
                bg_color = self.colors["success"]
                active_bg = "#45A049"
            elif widget_type == "danger":
                bg_color = self.colors["danger"]
                active_bg = "#E53935"
            elif widget_type == "warning":
                bg_color = self.colors["warning"]
                active_bg = "#FB8C00"
            else:
                bg_color = self.colors["surface_light"]
                active_bg = "#3C3C3C"

            widget.configure(
                font=("Segoe UI", 9, "bold"),
                relief="flat",
                borderwidth=0,
                cursor="hand2",
                pady=10,
                padx=20,
                bg=bg_color,
                fg="white",
                activebackground=active_bg,
                activeforeground="white",
            )
        elif isinstance(widget, tk.Entry):
            widget.configure(
                font=("Segoe UI", 9),
                relief="flat",
                borderwidth=2,
                highlightthickness=0,
                bg=self.colors["surface"],
                fg=self.colors["text"],
                insertbackground=self.colors["text"],
                selectbackground=self.colors["accent"],
                selectforeground="white",
            )
        elif isinstance(widget, tk.Scale):
            widget.configure(
                bg=self.colors["bg"],
                fg=self.colors["text"],
                troughcolor=self.colors["surface"],
                activebackground=self.colors["accent"],
                highlightthickness=0,
                font=("Segoe UI", 8),
            )

    def create_config_window(self):
        """Crea la ventana de configuración con tema oscuro moderno."""
        self.root = tk.Tk()
        self.root.title("WiZ Light Controller")
        self.root.geometry("700x800")
        self.root.resizable(True, True)
        self.root.minsize(600, 700)

        # Aplicar tema oscuro
        self.apply_dark_theme(self.root)

        # Configurar el ícono de la ventana si existe
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass

        # Frame principal con padding
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=25, pady=20)
        self.apply_dark_theme(main_frame)

        # Header
        self.create_header(main_frame)

        # Separador personalizado
        self.create_separator(main_frame)

        # Formulario de entrada
        self.create_input_form(main_frame)

        # Separador
        self.create_separator(main_frame)

        # Lista de luces
        self.create_lights_list(main_frame)

        # Botón cerrar
        self.create_footer(main_frame)

        # Centrar la ventana
        self.center_window()

        return self.root

    def create_separator(self, parent):
        """Crea un separador con el tema oscuro."""
        sep_frame = tk.Frame(parent, height=1, bg=self.colors["border"])
        sep_frame.pack(fill="x", pady=15)

    def create_header(self, parent):
        """Crea el header de la ventana."""
        header_frame = tk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 10))
        self.apply_dark_theme(header_frame)

        # Ícono y título en línea
        title_frame = tk.Frame(header_frame)
        title_frame.pack()
        self.apply_dark_theme(title_frame)

        title_label = tk.Label(
            title_frame,
            text="💡 WiZ Light Controller",
            font=("Segoe UI", 26, "normal"),
            fg=self.colors["accent"],
        )
        title_label.pack()
        self.apply_dark_theme(title_label)

        subtitle_label = tk.Label(
            header_frame,
            text="Control avanzado de luces inteligentes",
            font=("Segoe UI", 11),
            fg=self.colors["text_secondary"],
        )
        subtitle_label.pack(pady=(8, 0))
        self.apply_dark_theme(subtitle_label)

    def create_input_form(self, parent):
        """Crea el formulario de entrada."""
        # Título de sección
        section_title = tk.Label(
            parent,
            text="➕ Gestionar Luces",
            font=("Segoe UI", 16, "bold"),
            fg=self.colors["accent"],
        )
        section_title.pack(anchor="w", pady=(0, 15))
        self.apply_dark_theme(section_title)

        # Frame del formulario con fondo elevado
        form_frame = tk.Frame(
            parent, bg=self.colors["surface"], relief="flat", borderwidth=2
        )
        form_frame.pack(fill="x", pady=(0, 10))

        inner_frame = tk.Frame(form_frame, bg=self.colors["surface"])
        inner_frame.pack(fill="x", padx=25, pady=25)

        # Campo nombre
        name_frame = tk.Frame(inner_frame, bg=self.colors["surface"])
        name_frame.pack(fill="x", pady=(0, 20))

        name_label = tk.Label(
            name_frame,
            text="Nombre de la luz",
            bg=self.colors["surface"],
            font=("Segoe UI", 10, "bold"),
        )
        name_label.pack(anchor="w", pady=(0, 5))
        self.apply_dark_theme(name_label)

        self.name_entry = tk.Entry(name_frame, width=50, font=("Segoe UI", 10))
        self.name_entry.pack(fill="x", ipady=8)
        self.apply_dark_theme(self.name_entry)

        # Campo IP
        ip_frame = tk.Frame(inner_frame, bg=self.colors["surface"])
        ip_frame.pack(fill="x", pady=(0, 25))

        ip_label = tk.Label(
            ip_frame,
            text="Dirección IP",
            bg=self.colors["surface"],
            font=("Segoe UI", 10, "bold"),
        )
        ip_label.pack(anchor="w", pady=(0, 5))
        self.apply_dark_theme(ip_label)

        self.ip_entry = tk.Entry(ip_frame, width=50, font=("Segoe UI", 10))
        self.ip_entry.pack(fill="x", ipady=8)
        self.apply_dark_theme(self.ip_entry)

        # Botones
        button_frame = tk.Frame(inner_frame, bg=self.colors["surface"])
        button_frame.pack(fill="x")

        save_btn = tk.Button(
            button_frame, text="💾 Guardar", command=self.save_light, width=12
        )
        save_btn.pack(side="left", padx=(0, 15))
        self.apply_dark_theme(save_btn, "success")

        delete_btn = tk.Button(
            button_frame, text="🗑️ Eliminar", command=self.delete_light, width=12
        )
        delete_btn.pack(side="left")
        self.apply_dark_theme(delete_btn, "danger")

    def create_lights_list(self, parent):
        """Crea la lista de luces configuradas con controles avanzados."""
        # Título de sección
        section_title = tk.Label(
            parent,
            text="🏠 Luces Configuradas",
            font=("Segoe UI", 16, "bold"),
            fg=self.colors["accent"],
        )
        section_title.pack(anchor="w", pady=(0, 15))
        self.apply_dark_theme(section_title)

        # Frame con scroll para la lista
        list_frame = tk.Frame(
            parent, bg=self.colors["surface"], relief="flat", borderwidth=2
        )
        list_frame.pack(fill="both", expand=True, pady=(0, 20))

        # Canvas y scrollbar para scroll vertical
        canvas = tk.Canvas(list_frame, bg=self.colors["surface"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=self.colors["surface"])

        self.scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Configurar estilo del scrollbar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Vertical.TScrollbar",
            background=self.colors["surface_light"],
            troughcolor=self.colors["surface"],
            borderwidth=0,
            arrowcolor=self.colors["text"],
            darkcolor=self.colors["surface_light"],
            lightcolor=self.colors["surface_light"],
        )

        # Actualizar lista de luces
        self.update_lights_list()

        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def update_lights_list(self):
        """Actualiza la lista de luces en la interfaz."""
        # Limpiar frame
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.lights = load_config()

        if not self.lights:
            # Mostrar mensaje cuando no hay luces
            no_lights_frame = tk.Frame(
                self.scrollable_frame,
                bg=self.colors["surface_light"],
                relief="flat",
                borderwidth=2,
            )
            no_lights_frame.pack(fill="x", padx=20, pady=20)

            warning_label = tk.Label(
                no_lights_frame,
                text="⚠️ No hay luces configuradas",
                font=("Segoe UI", 12, "bold"),
                bg=self.colors["surface_light"],
                fg=self.colors["warning"],
            )
            warning_label.pack(pady=20)

            help_label = tk.Label(
                no_lights_frame,
                text="Agrega tu primera luz usando el formulario de arriba",
                font=("Segoe UI", 10),
                bg=self.colors["surface_light"],
                fg=self.colors["text_secondary"],
            )
            help_label.pack(pady=(0, 20))
        else:
            # Mostrar luces configuradas
            for i, (name, ip) in enumerate(self.lights.items()):
                self.create_light_card(name, ip, i)

    def create_light_card(self, name, ip, index):
        """Crea una tarjeta individual para cada luz con controles completos."""
        # Frame principal de la tarjeta
        card_frame = tk.Frame(
            self.scrollable_frame,
            bg=self.colors["surface_light"],
            relief="flat",
            borderwidth=2,
        )
        card_frame.pack(fill="x", padx=15, pady=10)

        # Header de la tarjeta
        header_frame = tk.Frame(card_frame, bg=self.colors["surface_light"])
        header_frame.pack(fill="x", padx=20, pady=(15, 10))

        # Información de la luz
        info_frame = tk.Frame(header_frame, bg=self.colors["surface_light"])
        info_frame.pack(side="left", fill="x", expand=True)

        name_label = tk.Label(
            info_frame,
            text=f"💡 {name}",
            font=("Segoe UI", 13, "bold"),
            bg=self.colors["surface_light"],
            fg=self.colors["text"],
        )
        name_label.pack(anchor="w")

        ip_label = tk.Label(
            info_frame,
            text=f"📍 {ip}",
            font=("Segoe UI", 9),
            bg=self.colors["surface_light"],
            fg=self.colors["text_secondary"],
        )
        ip_label.pack(anchor="w", pady=(2, 0))

        # Botón cargar
        load_btn = tk.Button(
            header_frame,
            text="📝 Cargar",
            command=lambda n=name: self.load_light(n),
            width=10,
        )
        load_btn.pack(side="right")
        self.apply_dark_theme(load_btn, "primary")

        # Controles de la luz
        controls_frame = tk.Frame(card_frame, bg=self.colors["surface_light"])
        controls_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Botones de encendido/apagado
        power_frame = tk.Frame(controls_frame, bg=self.colors["surface_light"])
        power_frame.pack(fill="x", pady=(0, 15))

        power_label = tk.Label(
            power_frame,
            text="💡 Control:",
            font=("Segoe UI", 9, "bold"),
            bg=self.colors["surface_light"],
            fg=self.colors["text"],
        )
        power_label.pack(side="left", padx=(0, 15))

        on_btn = tk.Button(
            power_frame,
            text="✨ ON",
            command=lambda n=name: turn_on_light(n),
            width=8,
        )
        on_btn.pack(side="left", padx=(0, 10))
        self.apply_dark_theme(on_btn, "success")

        off_btn = tk.Button(
            power_frame,
            text="💤 OFF",
            command=lambda n=name: turn_off_light(n),
            width=8,
        )
        off_btn.pack(side="left")
        self.apply_dark_theme(off_btn, "danger")

        # Control de brillo
        brightness_frame = tk.Frame(controls_frame, bg=self.colors["surface_light"])
        brightness_frame.pack(fill="x", pady=(0, 15))

        brightness_label = tk.Label(
            brightness_frame,
            text="🔆 Brillo:",
            font=("Segoe UI", 9, "bold"),
            bg=self.colors["surface_light"],
            fg=self.colors["text"],
        )
        brightness_label.pack(side="left", padx=(0, 15))

        # Variable para el brillo
        brightness_var = tk.IntVar(value=100)
        brightness_scale = tk.Scale(
            brightness_frame,
            from_=10,
            to=100,
            orient="horizontal",
            variable=brightness_var,
            command=lambda val, n=name: self.on_brightness_change(n, val),
            length=200,
        )
        brightness_scale.pack(side="left", padx=(0, 10))
        self.apply_dark_theme(brightness_scale)

        brightness_value = tk.Label(
            brightness_frame,
            text="100%",
            font=("Segoe UI", 9),
            bg=self.colors["surface_light"],
            fg=self.colors["text_secondary"],
            width=5,
        )
        brightness_value.pack(side="left")

        # Actualizar etiqueta cuando cambie el valor
        def update_brightness_label(*args):
            brightness_value.config(text=f"{brightness_var.get()}%")

        brightness_var.trace("w", update_brightness_label)

        # Control de color
        color_frame = tk.Frame(controls_frame, bg=self.colors["surface_light"])
        color_frame.pack(fill="x")

        color_label = tk.Label(
            color_frame,
            text="🎨 Color:",
            font=("Segoe UI", 9, "bold"),
            bg=self.colors["surface_light"],
            fg=self.colors["text"],
        )
        color_label.pack(side="left", padx=(0, 15))

        color_btn = tk.Button(
            color_frame,
            text="🎨 Elegir Color",
            command=lambda n=name: self.choose_color(n),
            width=15,
        )
        color_btn.pack(side="left", padx=(0, 10))
        self.apply_dark_theme(color_btn, "primary")

        # Botones de colores predefinidos
        preset_colors = [
            ("🟥 Rojo", (255, 0, 0)),
            ("🟩 Verde", (0, 255, 0)),
            ("🟦 Azul", (0, 0, 255)),
            ("🟨 Amarillo", (255, 255, 0)),
            ("🟪 Púrpura", (128, 0, 128)),
            ("🟧 Naranja", (255, 165, 0)),
        ]

        for color_name, rgb in preset_colors:
            preset_btn = tk.Button(
                color_frame,
                text=color_name.split()[0],  # Solo el emoji
                command=lambda n=name, c=rgb: set_light_color_cmd(n, c),
                width=3,
                font=("Segoe UI", 8),
            )
            preset_btn.pack(side="left", padx=2)
            self.apply_dark_theme(preset_btn)

    def on_brightness_change(self, name, value):
        """Maneja el cambio de brillo."""
        set_light_brightness_cmd(name, int(value))

    def choose_color(self, name):
        """Abre el selector de color."""
        color = colorchooser.askcolor(title=f"Elegir color para {name}", color="#FFFFFF")
        if color[0]:  # Si se eligió un color
            rgb = tuple(int(c) for c in color[0])
            set_light_color_cmd(name, rgb)

    def create_footer(self, parent):
        """Crea el footer con el botón cerrar."""
        footer_frame = tk.Frame(parent)
        footer_frame.pack(fill="x", pady=(15, 0))
        self.apply_dark_theme(footer_frame)

        close_btn = tk.Button(
            footer_frame,
            text="✅ Cerrar",
            command=self.close_window,
            width=15,
        )
        close_btn.pack(anchor="center")
        self.apply_dark_theme(close_btn)

    def center_window(self):
        """Centra la ventana en la pantalla."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        pos_x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        pos_y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    def save_light(self):
        """Guarda o actualiza una luz."""
        name = self.name_entry.get().strip()
        ip = self.ip_entry.get().strip()

        if name and ip:
            add_or_update_light(name, ip)
            messagebox.showinfo(
                "✅ ¡Éxito!",
                f"La luz '{name}' ha sido guardada/actualizada correctamente.",
                parent=self.root,
            )
            # Limpiar campos
            self.name_entry.delete(0, tk.END)
            self.ip_entry.delete(0, tk.END)
            # Actualizar lista y menú
            self.update_lights_list()
            global icon
            if icon:
                icon.menu = create_tray_menu()
        else:
            messagebox.showerror(
                "❌ Error de Validación",
                "Por favor, ingresa un nombre y una dirección IP válidos.",
                parent=self.root,
            )

    def delete_light(self):
        """Elimina una luz."""
        name = self.name_entry.get().strip()

        if name:
            lights = load_config()
            if name in lights:
                result = messagebox.askyesno(
                    "🗑️ Confirmar Eliminación",
                    f"¿Estás seguro de que deseas eliminar la luz '{name}'?",
                    parent=self.root,
                )
                if result:
                    delete_light(name)
                    messagebox.showinfo(
                        "✅ ¡Eliminada!",
                        f"La luz '{name}' ha sido eliminada correctamente.",
                        parent=self.root,
                    )
                    # Limpiar campos
                    self.name_entry.delete(0, tk.END)
                    self.ip_entry.delete(0, tk.END)
                    # Actualizar lista y menú
                    self.update_lights_list()
                    global icon
                    if icon:
                        icon.menu = create_tray_menu()
            else:
                messagebox.showerror(
                    "❌ Error",
                    f"La luz '{name}' no existe en la configuración.",
                    parent=self.root,
                )
        else:
            messagebox.showerror(
                "❌ Error de Validación",
                "Por favor, ingresa el nombre de la luz a eliminar.",
                parent=self.root,
            )

    def load_light(self, name):
        """Carga los datos de una luz en el formulario."""
        lights = load_config()
        if name in lights:
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, name)
            self.ip_entry.delete(0, tk.END)
            self.ip_entry.insert(0, lights[name])

    def close_window(self):
        """Cierra la ventana correctamente."""
        global config_window_instance
        config_window_instance = None
        if self.root:
            self.root.quit()
            self.root.destroy()


# --- Bandeja del sistema ---
def create_tray_menu():
    """Crea el menú dinámico para la bandeja del sistema."""
    lights_config = load_config()

    menu_items = []

    # Sección de control general con iconos
    menu_items.append(
        MenuItem("🔆 Encender todas las luces", lambda icon: turn_all_lights_on())
    )
    menu_items.append(
        MenuItem("🔅 Apagar todas las luces", lambda icon: turn_all_lights_off())
    )
    menu_items.append(TrayMenu.SEPARATOR)

    if lights_config:
        # Título de sección para luces individuales
        menu_items.append(MenuItem("💡 Luces Individuales", None))
        menu_items.append(TrayMenu.SEPARATOR)

        for name in lights_config:
            # Create closures to capture the current value of 'name'
            def make_turn_on_handler(light_name):
                return lambda icon: turn_on_light(light_name)

            def make_turn_off_handler(light_name):
                return lambda icon: turn_off_light(light_name)

            menu_items.append(
                MenuItem(
                    f"🏠 {name}",
                    TrayMenu(
                        MenuItem("✨ Encender", make_turn_on_handler(name)),
                        MenuItem("💤 Apagar", make_turn_off_handler(name)),
                    ),
                )
            )
    else:
        menu_items.append(MenuItem("⚠️ No hay luces configuradas", None))

    menu_items.append(TrayMenu.SEPARATOR)
    menu_items.append(MenuItem("⚙️ Configuración...", lambda icon: open_config_window()))
    menu_items.append(TrayMenu.SEPARATOR)
    menu_items.append(MenuItem("❌ Salir", lambda icon: icon.stop()))

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


# Variable global para evitar múltiples ventanas
config_window_instance = None


def open_config_window():
    """Abre la ventana de configuración."""
    global config_window_instance

    # Si ya hay una ventana abierta, enfocarla
    if (
        config_window_instance
        and config_window_instance.root
        and config_window_instance.root.winfo_exists()
    ):
        config_window_instance.root.lift()
        config_window_instance.root.focus_force()
        return

    # Crear nueva ventana en un hilo separado para evitar bloqueo
    def run_window():
        global config_window_instance
        config_window_instance = ConfigWindow()
        root = config_window_instance.create_config_window()

        # Configurar el cierre de ventana
        def on_closing():
            global config_window_instance
            config_window_instance = None
            root.quit()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()

    # Ejecutar en hilo separado
    window_thread = threading.Thread(target=run_window, daemon=True)
    window_thread.start()


# --- Main ---
if __name__ == "__main__":
    # Inicia el hilo de trabajo asíncrono
    asyncio_thread = threading.Thread(
        target=asyncio_worker, args=(async_queue,), daemon=True
    )
    asyncio_thread.start()

    # Inicia el ícono de la bandeja del sistema
    setup_tray_icon()