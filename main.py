import sys
import json
import socket
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, QStyle, QLabel, QVBoxLayout, QPushButton,
    QHBoxLayout, QSlider, QScrollArea, QFrame, QColorDialog, QLineEdit, QMessageBox
)
from PyQt6.QtGui import QIcon, QAction, QCursor, QColor
from PyQt6.QtCore import QPoint, Qt, QThread, pyqtSignal

# ----------------------------------------------------------------------
# --- CLASES DE LÓGICA DE NEGOCIO Y RED ---
# ----------------------------------------------------------------------

# Clase para el descubrimiento de lámparas WiZ en un hilo separado
class DiscoveryThread(QThread):
    """Hilo para realizar el descubrimiento UDP sin bloquear la interfaz."""
    lamp_found = pyqtSignal(dict) # Señal que emite los datos de la lámpara encontrada

    def run(self):
        # El puerto 38899 es el puerto de respuesta de los dispositivos WiZ.
        UDP_PORT = 38899 
        BROADCAST_IP = '255.255.255.255'
        
        # Comando de WiZ para obtener la información del dispositivo
        # {"method":"getSystemConfig","params":{}} es el comando de consulta.
        DISCOVERY_MESSAGE = '{"method":"getSystemConfig","params":{}}'.encode('utf-8')
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1) # Esperar 1 segundo por respuesta

        # Enviar el mensaje de descubrimiento (broadcast)
        sock.sendto(DISCOVERY_MESSAGE, (BROADCAST_IP, UDP_PORT))

        while True:
            try:
                # Recibir respuesta
                data, addr = sock.recvfrom(1024)
                response = json.loads(data.decode('utf-8'))
                
                # Extraer la MAC y la IP
                mac = response.get('result', {}).get('mac')
                ip = addr[0]
                
                if mac and ip:
                    self.lamp_found.emit({
                        'ip': ip,
                        'mac': mac,
                        'name': f"WiZ-{mac[-6:]}" # Nombre por defecto
                    })
                
            except socket.timeout:
                # Si se acaba el tiempo de espera, terminamos el descubrimiento
                break
            except Exception:
                # Ignorar errores de decodificación o JSON
                continue
        
        sock.close()

class WizManager:
    """Gestiona la lista de lámparas y la persistencia de datos."""
    
    DATA_FILE = 'lamps_data.json'
    
    def __init__(self):
        self.lamps = {}  # {mac: {'ip': '...', 'name': '...', 'last_brightness': 100, ...}}
        self.load_lamps()

    def load_lamps(self):
        """Carga los datos de las lámparas desde el archivo JSON."""
        if os.path.exists(self.DATA_FILE):
            with open(self.DATA_FILE, 'r') as f:
                try:
                    self.lamps = json.load(f)
                except json.JSONDecodeError:
                    self.lamps = {}
        
    def save_lamps(self):
        """Guarda los datos de las lámparas en el archivo JSON."""
        with open(self.DATA_FILE, 'w') as f:
            json.dump(self.lamps, f, indent=4)
            
    def add_lamp(self, mac, ip, name):
        """Añade una lámpara descubierta a la lista si no existe."""
        
        # 🟢 CORRECCIÓN: Usar la MAC como clave principal, asegurando que todos 
        # los campos básicos estén presentes, incluso si solo tenemos MAC e IP.
        
        if mac not in self.lamps:
            # Si la lámpara es nueva, creamos un registro completo:
            self.lamps[mac] = {
                'ip': ip if ip else "0.0.0.0", # Usar IP proporcionada o por defecto
                'name': name if name else f"WiZ-{mac[-6:]}", # Usar nombre proporcionado o MAC
                'mac': mac, # Aseguramos que la MAC esté en los datos internos
                'last_brightness': 100,
                'last_color_hex': '#ffffff'
            }
            self.save_lamps()
            return True
        return False
        
    def get_lamps(self):
        """Devuelve la lista actual de lámparas."""
        return list(self.lamps.values())

    def update_lamp_state(self, mac, brightness=None, color_hex=None):
        """Actualiza el estado de una lámpara en la memoria y en el archivo."""
        if mac in self.lamps:
            if brightness is not None:
                self.lamps[mac]['last_brightness'] = brightness
            if color_hex is not None:
                self.lamps[mac]['last_color_hex'] = color_hex
            self.save_lamps()

    def send_command(self, ip, command_params):
        """Envía un comando UDP a la lámpara WiZ."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.1) # Breve timeout
            
            # Construye el comando JSON completo
            command_json = json.dumps(command_params).encode('utf-8')
            
            # El puerto de control de WiZ es el 38899
            sock.sendto(command_json, (ip, 38899))
            sock.close()
            print(f"Comando enviado a {ip}: {command_params['method']}")
        except Exception as e:
            print(f"Error al enviar comando a {ip}: {e}")

# ----------------------------------------------------------------------
# --- WIDGETS DE LA INTERFAZ ---
# ----------------------------------------------------------------------

class LampControl(QWidget):
    """Widget individual para controlar una lámpara."""
    def __init__(self, lamp_data, wiz_manager, parent=None):
        super().__init__(parent)
        self.mac = lamp_data['mac']
        self.ip = lamp_data['ip']
        self.wiz_manager = wiz_manager
        
        self.current_color = QColor(lamp_data['last_color_hex']) 
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # --- Nombre y Brillo ---
        name_brightness_layout = QHBoxLayout()
        name_brightness_layout.addWidget(QLabel(f"<b>{lamp_data['name']}</b> ({self.ip})", alignment=Qt.AlignmentFlag.AlignLeft))
        
        # Slider de Brillo
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(10, 100) # Brillo WiZ va de 10 a 100
        self.brightness_slider.setValue(lamp_data['last_brightness'])
        self.brightness_slider.setFixedWidth(100)
        self.brightness_slider.valueChanged.connect(self.send_brightness_command)
        
        self.brightness_label = QLabel(f"{lamp_data['last_brightness']}%")
        
        name_brightness_layout.addStretch()
        name_brightness_layout.addWidget(self.brightness_slider)
        name_brightness_layout.addWidget(self.brightness_label)
        
        main_layout.addLayout(name_brightness_layout)
        
        # --- Control de Color ---
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color (HSL):"))
        
        self.color_button = QPushButton()
        self.color_button.setFixedSize(20, 20)
        self.color_button.setStyleSheet(f"background-color: {self.current_color.name()}")
        self.color_button.clicked.connect(self.show_color_dialog)
        
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()
        
        main_layout.addLayout(color_layout)

    # ----------------------------------------------------------------------
    # --- MÉTODOS DE COMANDO WIZ ---
    # ----------------------------------------------------------------------

    def send_brightness_command(self, value):
        """Envía el comando UDP de brillo."""
        self.brightness_label.setText(f"{value}%")
        self.wiz_manager.update_lamp_state(self.mac, brightness=value)
        
        command = {
            "method": "setPilot",
            "params": {"dimming": value}
        }
        self.wiz_manager.send_command(self.ip, command)

    def show_color_dialog(self):
        """Abre el diálogo para seleccionar el color y envía el comando RGB."""
        color = QColorDialog.getColor(self.current_color, self, "Seleccionar Color")
        
        if color.isValid():
            self.current_color = color
            self.color_button.setStyleSheet(f"background-color: {self.current_color.name()}")
            self.wiz_manager.update_lamp_state(self.mac, color_hex=color.name())
            
            # Obtener los valores RGB (Rango 0-255)
            r = color.red()
            g = color.green()
            b = color.blue()
            
            # Obtener el brillo actual del slider (Rango 10-100)
            dimming = self.brightness_slider.value()

            # 🟢 CORRECCIÓN CLAVE: Envío del comando RGB + Forzado de Modo
            command = {
                "method": "setPilot",
                "params": {
                    "r": int(r),
                    "g": int(g),
                    "b": int(b),
                    "dimming": int(dimming),
                    "state": True,
                    # Esto fuerza la lámpara a usar el modo de color puro (RGB).
                    "colorMode": "rgb" 
                }
            }
            self.wiz_manager.send_command(self.ip, command)
            print(f"Comando de color RGB forzado enviado a {self.ip}. R:{r}, G:{g}, B:{b}, D:{dimming}")

class PopupWindow(QWidget):
    """Ventana principal (pop-up) que contiene la lista de lámparas."""
    def __init__(self, wiz_manager):
        super().__init__()
        self.wiz_manager = wiz_manager
        self.setWindowTitle("Control de Lámparas")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setGeometry(0, 0, 350, 400) # Tamaño aumentado

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 1. Título y botones de gestión
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Control WiZ</b>", alignment=Qt.AlignmentFlag.AlignCenter))
        
        self.discover_button = QPushButton("Descubrir")
        self.discover_button.setFixedSize(70, 25)
        self.discover_button.clicked.connect(self.start_discovery)
        
        header_layout.addWidget(self.discover_button)
        main_layout.addLayout(header_layout)
        
        # 2. Área Desplazable
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.scroll_area)
        
        self.lamp_list_container = QWidget()
        self.lamp_list_layout = QVBoxLayout(self.lamp_list_container)
        self.lamp_list_layout.setSpacing(10)
        self.lamp_list_layout.addStretch() 
        self.scroll_area.setWidget(self.lamp_list_container)

        # 3. Botones Inferiores
        footer_layout = QHBoxLayout()
        self.hide_button = QPushButton("Ocultar")
        self.exit_button = QPushButton("Salir")
        footer_layout.addWidget(self.hide_button)
        footer_layout.addWidget(self.exit_button)
        main_layout.addLayout(footer_layout)

        self.hide_button.clicked.connect(self.hide) 
        
        self.load_lamp_widgets()

    def load_lamp_widgets(self):
        """Carga los widgets de las lámparas guardadas."""
        # Limpiar widgets antiguos
        for i in reversed(range(self.lamp_list_layout.count() - 1)):
            widget = self.lamp_list_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        
        # Cargar los nuevos widgets
        for lamp_data in self.wiz_manager.get_lamps():
            # Aseguramos que los datos esenciales existan antes de llamar a add_lamp_widget.
            if 'mac' in lamp_data and 'ip' in lamp_data: 
                self.add_lamp_widget(lamp_data)
            else:
                print(f"Advertencia: Saltando lámpara incompleta en JSON: {lamp_data}")

    def add_lamp_widget(self, lamp_data):
        """Agrega un nuevo widget de control de lámpara a la interfaz."""
        # La verificación de seguridad que agregamos en la corrección anterior
        if 'mac' not in lamp_data:
            # Este mensaje ahora solo debería aparecer si hay un error en el flujo de ejecución.
            print("Error: Intentando crear LampControl sin clave 'mac'.") 
            return
            
        new_lamp = LampControl(lamp_data, self.wiz_manager)
        # Insertar arriba de 'addStretch()'
        self.lamp_list_layout.insertWidget(self.lamp_list_layout.count() - 1, new_lamp)
        
    def start_discovery(self):
        """Inicia el proceso de descubrimiento en un hilo."""
        self.discover_button.setEnabled(False)
        self.discover_button.setText("Buscando...")
        
        self.discovery_thread = DiscoveryThread()
        self.discovery_thread.lamp_found.connect(self.handle_lamp_found)
        self.discovery_thread.finished.connect(self.discovery_finished)
        self.discovery_thread.start()
        
    def handle_lamp_found(self, lamp_data):
        """
        CORRECCIÓN: Maneja la señal de una lámpara descubierta. 
        Añade el widget SOLO si la lámpara se agregó exitosamente al manager y luego 
        recupera los datos completos y guardados para construir la interfaz.
        """
        mac = lamp_data.get('mac')
        ip = lamp_data.get('ip')
        name = lamp_data.get('name')
        
        if not mac:
            print("Advertencia: Lámpara descubierta sin MAC válida. Ignorando respuesta incompleta.")
            return

        # Intenta añadir la lámpara al manager. Retorna True si es nueva.
        if self.wiz_manager.add_lamp(mac, ip, name):
            
            # 🟢 CLAVE DE LA CORRECCIÓN: Recuperar los datos completos del diccionario 
            # del manager, que ya están validados y tienen el estado inicial.
            saved_lamp_data = self.wiz_manager.lamps.get(mac)
            
            if saved_lamp_data:
                self.add_lamp_widget(saved_lamp_data)
                print(f"Nueva lámpara descubierta y añadida: {name} ({ip})")
            else:
                # Este caso es muy improbable, pero cubre la falla de guardado.
                print(f"Error crítico: Lámpara {mac} agregada al manager pero no se pudo recuperar.")


    def discovery_finished(self):
        """Se ejecuta cuando el hilo de descubrimiento termina."""
        QMessageBox.information(self, "Descubrimiento", "Búsqueda de lámparas finalizada.")
        self.discover_button.setEnabled(True)
        self.discover_button.setText("Descubrir")

# ----------------------------------------------------------------------
# --- TRAY ICON Y EJECUCIÓN ---
# ----------------------------------------------------------------------

class TrayAppQt:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Inicializar el manager de datos
        self.wiz_manager = WizManager()

        # Icono de Bandeja
        style = self.app.style()
        self.icon = QSystemTrayIcon(style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.icon.setToolTip("Control de Lámparas WiZ")
        self.icon.setVisible(True)

        # Menú de Contexto
        menu = QMenu()
        show_action = QAction("Mostrar Control", menu)
        exit_action = QAction("Salir", menu)
        menu.addAction(show_action)
        menu.addAction(exit_action)
        self.icon.setContextMenu(menu)

        # Ventana Pop-up
        self.window = PopupWindow(self.wiz_manager)
        
        # Conexiones
        self.icon.activated.connect(self.handle_icon_click)
        show_action.triggered.connect(lambda: self.show_window(self.icon.contextMenu().pos())) 
        exit_action.triggered.connect(self.app.quit)
        self.window.exit_button.clicked.connect(self.app.quit) 
        
        # Inicialización forzada del menú para el posicionamiento
        self.icon.contextMenu() 

    def handle_icon_click(self, reason):
        """Maneja el evento de clic izquierdo usando la posición del cursor."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            cursor_pos = QCursor.pos()
            self.show_window(cursor_pos)

    def show_window(self, tray_position: QPoint):
        """Muestra y posiciona la ventana pop-up justo al lado del ícono."""
        x = tray_position.x() - self.window.width() 
        y = tray_position.y() - self.window.height() 
        
        self.window.move(QPoint(x, y))
        self.window.show()

    def run(self):
        return self.app.exec()

if __name__ == '__main__':
    # Verificar si el sistema soporta UDP y Threads antes de ejecutar
    if sys.platform == "win32" or sys.platform.startswith("linux"):
        app = TrayAppQt()
        sys.exit(app.run())
    else:
        print("Este código está optimizado para Windows o Linux.")
        sys.exit(1)