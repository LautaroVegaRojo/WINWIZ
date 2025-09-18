import tkinter as tk
from tkinter import ttk, messagebox, font
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


# --- Clase para la ventana de configuración con estilo Windows 11 ---
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
    def __init__(self):
        self.root = None
        self.lights = load_config()
        
    def apply_windows11_style(self, widget):
        """Aplica el estilo de Windows 11 a los widgets."""
        # Configurar colores de Windows 11
        bg_color = "#FAFAFA"  # Fondo principal
        accent_color = "#0078D4"  # Azul de Windows 11
        text_color = "#323130"  # Texto principal
        border_color = "#D1D1D1"  # Bordes
        
        if isinstance(widget, tk.Tk):
            widget.configure(bg=bg_color)
        elif isinstance(widget, tk.Frame):
            widget.configure(bg=bg_color, relief="flat")
        elif isinstance(widget, tk.Label):
            widget.configure(bg=bg_color, fg=text_color, font=("Segoe UI", 9))
        elif isinstance(widget, tk.Button):
            widget.configure(
                font=("Segoe UI", 9),
                relief="flat",
                borderwidth=0,
                cursor="hand2",
                pady=8,
                padx=20
            )
        elif isinstance(widget, tk.Entry):
            widget.configure(
                font=("Segoe UI", 9),
                relief="solid",
                borderwidth=1,
                highlightthickness=2,
                highlightbackground=border_color,
                highlightcolor=accent_color,
                insertbackground=text_color  # Color del cursor de texto
            )
    
    def create_config_window(self):
        """Crea la ventana de configuración con estilo Windows 11."""
        self.root = tk.Tk()
        self.root.title("🏠 WiZ Light Controller")
        self.root.geometry("600x700")
        self.root.resizable(True, True)
        self.root.minsize(500, 600)
        
        # Aplicar estilo Windows 11
        self.apply_windows11_style(self.root)
        
        # Configurar el ícono de la ventana si existe
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        # Frame principal con padding
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=30, pady=20)
        self.apply_windows11_style(main_frame)
        
        # Header
        self.create_header(main_frame)
        
        # Separador
        sep1 = ttk.Separator(main_frame, orient="horizontal")
        sep1.pack(fill="x", pady=(15, 25))
        
        # Formulario de entrada
        self.create_input_form(main_frame)
        
        # Separador
        sep2 = ttk.Separator(main_frame, orient="horizontal")
        sep2.pack(fill="x", pady=(25, 20))
        
        # Lista de luces
        self.create_lights_list(main_frame)
        
        # Botón cerrar
        self.create_footer(main_frame)
        
        # Centrar la ventana
        self.center_window()
        
        return self.root
    
    def create_header(self, parent):
        """Crea el header de la ventana."""
        header_frame = tk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 10))
        self.apply_windows11_style(header_frame)
        
        title_label = tk.Label(
            header_frame, 
            text="🏠 WiZ Light Controller", 
            font=("Segoe UI", 24, "normal"),
            fg="#0078D4"
        )
        title_label.pack()
        self.apply_windows11_style(title_label)
        
        subtitle_label = tk.Label(
            header_frame, 
            text="Gestiona tus luces inteligentes WiZ", 
            font=("Segoe UI", 11),
            fg="#605E5C"
        )
        subtitle_label.pack(pady=(5, 0))
        self.apply_windows11_style(subtitle_label)
    
    def create_input_form(self, parent):
        """Crea el formulario de entrada."""
        # Título de sección
        section_title = tk.Label(
            parent, 
            text="➕ Agregar Nueva Luz", 
            font=("Segoe UI", 14, "bold"),
            fg="#8A2BE2"
        )
        section_title.pack(anchor="w", pady=(0, 15))
        self.apply_windows11_style(section_title)
        
        # Frame del formulario
        form_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg="#F8F9FA")
        form_frame.pack(fill="x", pady=(0, 10))
        
        inner_frame = tk.Frame(form_frame, bg="#F8F9FA")
        inner_frame.pack(fill="x", padx=20, pady=20)
        
        # Campo nombre
        name_frame = tk.Frame(inner_frame, bg="#F8F9FA")
        name_frame.pack(fill="x", pady=(0, 15))
        
        name_label = tk.Label(name_frame, text="💡 Nombre de la luz:", bg="#F8F9FA")
        name_label.pack(anchor="w")
        self.apply_windows11_style(name_label)
        
        self.name_entry = tk.Entry(name_frame, width=40)
        self.name_entry.pack(fill="x", pady=(5, 0))
        self.apply_windows11_style(self.name_entry)
        
        # Campo IP
        ip_frame = tk.Frame(inner_frame, bg="#F8F9FA")
        ip_frame.pack(fill="x", pady=(0, 20))
        
        ip_label = tk.Label(ip_frame, text="🌐 Dirección IP:", bg="#F8F9FA")
        ip_label.pack(anchor="w")
        self.apply_windows11_style(ip_label)
        
        self.ip_entry = tk.Entry(ip_frame, width=40)
        self.ip_entry.pack(fill="x", pady=(5, 0))
        self.apply_windows11_style(self.ip_entry)
        
        # Botones
        button_frame = tk.Frame(inner_frame, bg="#F8F9FA")
        button_frame.pack(fill="x")
        
        save_btn = tk.Button(
            button_frame, 
            text="💾 Guardar", 
            command=self.save_light,
            bg="#107C10",
            fg="white",
            activebackground="#0E6E0E"
        )
        save_btn.pack(side="left", padx=(0, 10))
        self.apply_windows11_style(save_btn)
        
        delete_btn = tk.Button(
            button_frame, 
            text="🗑️ Eliminar", 
            command=self.delete_light,
            bg="#D13438",
            fg="white",
            activebackground="#B52328"
        )
        delete_btn.pack(side="left")
        self.apply_windows11_style(delete_btn)
    
    def create_lights_list(self, parent):
        """Crea la lista de luces configuradas."""
        # Título de sección
        section_title = tk.Label(
            parent, 
            text="📋 Luces Configuradas", 
            font=("Segoe UI", 14, "bold"),
            fg="#8A2BE2"
        )
        section_title.pack(anchor="w", pady=(0, 15))
        self.apply_windows11_style(section_title)
        
        # Frame con scroll para la lista
        list_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg="#FFFFFF")
        list_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        # Canvas y scrollbar para scroll vertical
        canvas = tk.Canvas(list_frame, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#FFFFFF")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Actualizar lista de luces
        self.update_lights_list()
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def update_lights_list(self):
        """Actualiza la lista de luces en la interfaz."""
        # Limpiar frame
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.lights = load_config()
        
        if not self.lights:
            # Mostrar mensaje cuando no hay luces
            no_lights_frame = tk.Frame(self.scrollable_frame, bg="#FFF3CD", relief="solid", borderwidth=1)
            no_lights_frame.pack(fill="x", padx=10, pady=10)
            
            warning_label = tk.Label(
                no_lights_frame, 
                text="⚠️ No hay luces configuradas", 
                font=("Segoe UI", 11, "bold"),
                bg="#FFF3CD",
                fg="#856404"
            )
            warning_label.pack(pady=10)
            
            help_label = tk.Label(
                no_lights_frame, 
                text="Agrega tu primera luz usando el formulario de arriba", 
                font=("Segoe UI", 9),
                bg="#FFF3CD",
                fg="#856404"
            )
            help_label.pack(pady=(0, 10))
        else:
            # Mostrar luces configuradas
            for i, (name, ip) in enumerate(self.lights.items()):
                bg_color = "#F8F9FA" if i % 2 == 0 else "#E9ECEF"
                
                light_frame = tk.Frame(self.scrollable_frame, bg=bg_color, relief="solid", borderwidth=1)
                light_frame.pack(fill="x", padx=10, pady=5)
                
                content_frame = tk.Frame(light_frame, bg=bg_color)
                content_frame.pack(fill="x", padx=15, pady=10)
                
                # Información de la luz
                info_frame = tk.Frame(content_frame, bg=bg_color)
                info_frame.pack(side="left", fill="x", expand=True)
                
                name_label = tk.Label(
                    info_frame, 
                    text=f"💡 {name}", 
                    font=("Segoe UI", 11, "bold"),
                    bg=bg_color,
                    fg="#0078D4"
                )
                name_label.pack(anchor="w")
                
                ip_label = tk.Label(
                    info_frame, 
                    text=f"📍 {ip}", 
                    font=("Segoe UI", 9),
                    bg=bg_color,
                    fg="#605E5C"
                )
                ip_label.pack(anchor="w")
                
                # Botón cargar
                load_btn = tk.Button(
                    content_frame, 
                    text="📝 Cargar", 
                    command=lambda n=name: self.load_light(n),
                    bg="#0078D4",
                    fg="white",
                    activebackground="#106EBE"
                )
                load_btn.pack(side="right")
                self.apply_windows11_style(load_btn)
    
    def create_footer(self, parent):
        """Crea el footer con el botón cerrar."""
        footer_frame = tk.Frame(parent)
        footer_frame.pack(fill="x", pady=(10, 0))
        self.apply_windows11_style(footer_frame)
        
        close_btn = tk.Button(
            footer_frame, 
            text="✅ Cerrar", 
            command=self.close_window,
            bg="#6C757D",
            fg="white",
            activebackground="#5A6268",
            width=15
        )
        close_btn.pack(anchor="center")
        self.apply_windows11_style(close_btn)
    
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
                f"La luz '{name}' ha sido guardada/actualizada correctamente."
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
                "Por favor, ingresa un nombre y una dirección IP válidos."
            )
    
    def delete_light(self):
        """Elimina una luz."""
        name = self.name_entry.get().strip()
        
        if name:
            lights = load_config()
            if name in lights:
                result = messagebox.askyesno(
                    "🗑️ Confirmar Eliminación",
                    f"¿Estás seguro de que deseas eliminar la luz '{name}'?"
                )
                if result:
                    delete_light(name)
                    messagebox.showinfo(
                        "✅ ¡Eliminada!",
                        f"La luz '{name}' ha sido eliminada correctamente."
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
                    f"La luz '{name}' no existe en la configuración."
                )
        else:
            messagebox.showerror(
                "❌ Error de Validación",
                "Por favor, ingresa el nombre de la luz a eliminar."
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
        """Cierra la ventana."""
        if self.root:
            self.root.destroy()


# Variable global para evitar múltiples ventanas
config_window_instance = None

def open_config_window():
    """Abre la ventana de configuración."""
    global config_window_instance
    
    # Si ya hay una ventana abierta, enfocarla
    if config_window_instance and config_window_instance.root and config_window_instance.root.winfo_exists():
        config_window_instance.root.lift()
        config_window_instance.root.focus_force()
        return
    
    # Crear nueva ventana
    config_window_instance = ConfigWindow()
    root = config_window_instance.create_config_window()
    
    # Configurar el cierre de ventana
    def on_closing():
        global config_window_instance
        config_window_instance = None
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
class ConfigWindow:
    def __init__(self):
        self.root = None
        self.lights = load_config()
        
    def apply_windows11_style(self, widget):
        """Aplica el estilo de Windows 11 a los widgets."""
        # Configurar colores de Windows 11
        bg_color = "#FAFAFA"  # Fondo principal
        accent_color = "#0078D4"  # Azul de Windows 11
        text_color = "#323130"  # Texto principal
        border_color = "#D1D1D1"  # Bordes
        
        if isinstance(widget, tk.Tk):
            widget.configure(bg=bg_color)
        elif isinstance(widget, tk.Frame):
            widget.configure(bg=bg_color, relief="flat")
        elif isinstance(widget, tk.Label):
            widget.configure(bg=bg_color, fg=text_color, font=("Segoe UI", 9))
        elif isinstance(widget, tk.Button):
            widget.configure(
                font=("Segoe UI", 9),
                relief="flat",
                borderwidth=0,
                cursor="hand2",
                pady=8,
                padx=20
            )
        elif isinstance(widget, tk.Entry):
            widget.configure(
                font=("Segoe UI", 9),
                relief="solid",
                borderwidth=1,
                highlightthickness=2,
                highlightbackground=border_color,
                highlightcolor=accent_color,
                insertbackground=text_color  # Color del cursor de texto
            )
    
    def create_config_window(self):
        """Crea la ventana de configuración con estilo Windows 11."""
        self.root = tk.Tk()
        self.root.title("🏠 WiZ Light Controller")
        self.root.geometry("600x700")
        self.root.resizable(True, True)
        self.root.minsize(500, 600)
        
        # Aplicar estilo Windows 11
        self.apply_windows11_style(self.root)
        
        # Configurar el ícono de la ventana si existe
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
        
        # Frame principal con padding
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=30, pady=20)
        self.apply_windows11_style(main_frame)
        
        # Header
        self.create_header(main_frame)
        
        # Separador
        sep1 = ttk.Separator(main_frame, orient="horizontal")
        sep1.pack(fill="x", pady=(15, 25))
        
        # Formulario de entrada
        self.create_input_form(main_frame)
        
        # Separador
        sep2 = ttk.Separator(main_frame, orient="horizontal")
        sep2.pack(fill="x", pady=(25, 20))
        
        # Lista de luces
        self.create_lights_list(main_frame)
        
        # Botón cerrar
        self.create_footer(main_frame)
        
        # Centrar la ventana
        self.center_window()
        
        return self.root
    
    def create_header(self, parent):
        """Crea el header de la ventana."""
        header_frame = tk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 10))
        self.apply_windows11_style(header_frame)
        
        title_label = tk.Label(
            header_frame, 
            text="🏠 WiZ Light Controller", 
            font=("Segoe UI", 24, "normal"),
            fg="#0078D4"
        )
        title_label.pack()
        self.apply_windows11_style(title_label)
        
        subtitle_label = tk.Label(
            header_frame, 
            text="Gestiona tus luces inteligentes WiZ", 
            font=("Segoe UI", 11),
            fg="#605E5C"
        )
        subtitle_label.pack(pady=(5, 0))
        self.apply_windows11_style(subtitle_label)
    
    def create_input_form(self, parent):
        """Crea el formulario de entrada."""
        # Título de sección
        section_title = tk.Label(
            parent, 
            text="➕ Agregar Nueva Luz", 
            font=("Segoe UI", 14, "bold"),
            fg="#8A2BE2"
        )
        section_title.pack(anchor="w", pady=(0, 15))
        self.apply_windows11_style(section_title)
        
        # Frame del formulario
        form_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg="#F8F9FA")
        form_frame.pack(fill="x", pady=(0, 10))
        
        inner_frame = tk.Frame(form_frame, bg="#F8F9FA")
        inner_frame.pack(fill="x", padx=20, pady=20)
        
        # Campo nombre
        name_frame = tk.Frame(inner_frame, bg="#F8F9FA")
        name_frame.pack(fill="x", pady=(0, 15))
        
        name_label = tk.Label(name_frame, text="💡 Nombre de la luz:", bg="#F8F9FA")
        name_label.pack(anchor="w")
        self.apply_windows11_style(name_label)
        
        self.name_entry = tk.Entry(name_frame, width=40)
        self.name_entry.pack(fill="x", pady=(5, 0))
        self.apply_windows11_style(self.name_entry)
        
        # Campo IP
        ip_frame = tk.Frame(inner_frame, bg="#F8F9FA")
        ip_frame.pack(fill="x", pady=(0, 20))
        
        ip_label = tk.Label(ip_frame, text="🌐 Dirección IP:", bg="#F8F9FA")
        ip_label.pack(anchor="w")
        self.apply_windows11_style(ip_label)
        
        self.ip_entry = tk.Entry(ip_frame, width=40)
        self.ip_entry.pack(fill="x", pady=(5, 0))
        self.apply_windows11_style(self.ip_entry)
        
        # Botones
        button_frame = tk.Frame(inner_frame, bg="#F8F9FA")
        button_frame.pack(fill="x")
        
        save_btn = tk.Button(
            button_frame, 
            text="💾 Guardar", 
            command=self.save_light,
            bg="#107C10",
            fg="white",
            activebackground="#0E6E0E"
        )
        save_btn.pack(side="left", padx=(0, 10))
        self.apply_windows11_style(save_btn)
        
        delete_btn = tk.Button(
            button_frame, 
            text="🗑️ Eliminar", 
            command=self.delete_light,
            bg="#D13438",
            fg="white",
            activebackground="#B52328"
        )
        delete_btn.pack(side="left")
        self.apply_windows11_style(delete_btn)
    
    def create_lights_list(self, parent):
        """Crea la lista de luces configuradas."""
        # Título de sección
        section_title = tk.Label(
            parent, 
            text="📋 Luces Configuradas", 
            font=("Segoe UI", 14, "bold"),
            fg="#8A2BE2"
        )
        section_title.pack(anchor="w", pady=(0, 15))
        self.apply_windows11_style(section_title)
        
        # Frame con scroll para la lista
        list_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg="#FFFFFF")
        list_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        # Canvas y scrollbar para scroll vertical
        canvas = tk.Canvas(list_frame, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#FFFFFF")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Actualizar lista de luces
        self.update_lights_list()
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def update_lights_list(self):
        """Actualiza la lista de luces en la interfaz."""
        # Limpiar frame
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.lights = load_config()
        
        if not self.lights:
            # Mostrar mensaje cuando no hay luces
            no_lights_frame = tk.Frame(self.scrollable_frame, bg="#FFF3CD", relief="solid", borderwidth=1)
            no_lights_frame.pack(fill="x", padx=10, pady=10)
            
            warning_label = tk.Label(
                no_lights_frame, 
                text="⚠️ No hay luces configuradas", 
                font=("Segoe UI", 11, "bold"),
                bg="#FFF3CD",
                fg="#856404"
            )
            warning_label.pack(pady=10)
            
            help_label = tk.Label(
                no_lights_frame, 
                text="Agrega tu primera luz usando el formulario de arriba", 
                font=("Segoe UI", 9),
                bg="#FFF3CD",
                fg="#856404"
            )
            help_label.pack(pady=(0, 10))
        else:
            # Mostrar luces configuradas
            for i, (name, ip) in enumerate(self.lights.items()):
                bg_color = "#F8F9FA" if i % 2 == 0 else "#E9ECEF"
                
                light_frame = tk.Frame(self.scrollable_frame, bg=bg_color, relief="solid", borderwidth=1)
                light_frame.pack(fill="x", padx=10, pady=5)
                
                content_frame = tk.Frame(light_frame, bg=bg_color)
                content_frame.pack(fill="x", padx=15, pady=10)
                
                # Información de la luz
                info_frame = tk.Frame(content_frame, bg=bg_color)
                info_frame.pack(side="left", fill="x", expand=True)
                
                name_label = tk.Label(
                    info_frame, 
                    text=f"💡 {name}", 
                    font=("Segoe UI", 11, "bold"),
                    bg=bg_color,
                    fg="#0078D4"
                )
                name_label.pack(anchor="w")
                
                ip_label = tk.Label(
                    info_frame, 
                    text=f"📍 {ip}", 
                    font=("Segoe UI", 9),
                    bg=bg_color,
                    fg="#605E5C"
                )
                ip_label.pack(anchor="w")
                
                # Botón cargar
                load_btn = tk.Button(
                    content_frame, 
                    text="📝 Cargar", 
                    command=lambda n=name: self.load_light(n),
                    bg="#0078D4",
                    fg="white",
                    activebackground="#106EBE"
                )
                load_btn.pack(side="right")
                self.apply_windows11_style(load_btn)
    
    def create_footer(self, parent):
        """Crea el footer con el botón cerrar."""
        footer_frame = tk.Frame(parent)
        footer_frame.pack(fill="x", pady=(10, 0))
        self.apply_windows11_style(footer_frame)
        
        close_btn = tk.Button(
            footer_frame, 
            text="✅ Cerrar", 
            command=self.close_window,
            bg="#6C757D",
            fg="white",
            activebackground="#5A6268",
            width=15
        )
        close_btn.pack(anchor="center")
        self.apply_windows11_style(close_btn)
    
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
                f"La luz '{name}' ha sido guardada/actualizada correctamente."
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
                "Por favor, ingresa un nombre y una dirección IP válidos."
            )
    
    def delete_light(self):
        """Elimina una luz."""
        name = self.name_entry.get().strip()
        
        if name:
            lights = load_config()
            if name in lights:
                result = messagebox.askyesno(
                    "🗑️ Confirmar Eliminación",
                    f"¿Estás seguro de que deseas eliminar la luz '{name}'?"
                )
                if result:
                    delete_light(name)
                    messagebox.showinfo(
                        "✅ ¡Eliminada!",
                        f"La luz '{name}' ha sido eliminada correctamente."
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
                    f"La luz '{name}' no existe en la configuración."
                )
        else:
            messagebox.showerror(
                "❌ Error de Validación",
                "Por favor, ingresa el nombre de la luz a eliminar."
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
        """Cierra la ventana."""
        if self.root:
            self.root.destroy()


# Variable global para evitar múltiples ventanas
config_window_instance = None

def open_config_window():
    """Abre la ventana de configuración."""
    global config_window_instance
    
    # Si ya hay una ventana abierta, enfocarla
    if config_window_instance and config_window_instance.root and config_window_instance.root.winfo_exists():
        config_window_instance.root.lift()
        config_window_instance.root.focus_force()
        return
    
    # Crear nueva ventana
    config_window_instance = ConfigWindow()
    root = config_window_instance.create_config_window()
    
    # Configurar el cierre de ventana
    def on_closing():
        global config_window_instance
        config_window_instance = None
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


# --- Main ---
if __name__ == "__main__":
    # Inicia el hilo de trabajo asíncrono
    asyncio_thread = threading.Thread(
        target=asyncio_worker, args=(async_queue,), daemon=True
    )
    asyncio_thread.start()

    # Inicia el ícono de la bandeja del sistema
    setup_tray_icon()