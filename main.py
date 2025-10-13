import sys
import json
import socket
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, QStyle, QLabel, QVBoxLayout, QPushButton,
    QHBoxLayout, QSlider, QScrollArea, QFrame, QColorDialog, QCheckBox, QMessageBox, 
    QGraphicsDropShadowEffect, QLineEdit, QDialog, QListWidget, QListWidgetItem
)
from PyQt6.QtGui import QAction, QCursor, QColor, QFont, QPainter, QPen, QPainterPath, QIcon
from PyQt6.QtCore import (
    QPoint, Qt, QThread, pyqtSignal, QPropertyAnimation, QTimer, QRect, QEasingCurve, QRectF
)

TEMP_MIN = 2200
TEMP_MAX = 6500

class DiscoveryThread(QThread):
    lamp_found = pyqtSignal(dict)

    def run(self):
        UDP_PORT = 38899
        BROADCAST_IP = '255.255.255.255'
        DISCOVERY_MESSAGE = '{"method":"getSystemConfig","params":{}}'.encode('utf-8')

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(3)  # Timeout de 3 segundos como el original

        discovered_macs = set()  # Para evitar duplicados

        try:
            sock.sendto(DISCOVERY_MESSAGE, (BROADCAST_IP, UDP_PORT))
            
            # Seguir escuchando hasta timeout (como el código original)
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = json.loads(data.decode('utf-8'))
                    mac = response.get('result', {}).get('mac')
                    ip = addr[0]
                    
                    if mac and ip and mac not in discovered_macs:
                        discovered_macs.add(mac)
                        self.lamp_found.emit({'ip': ip, 'mac': mac, 'name': f"WiZ-{mac[-6:]}"})
                except socket.timeout:
                    break  # Sale del bucle cuando no hay más respuestas
                except Exception:
                    continue
        finally:
            sock.close()

class WizManager:
    DATA_FILE = 'lamps_data.json'

    def __init__(self):
        self.lamps = {}
        self.groups = {}
        self.load_data()

    def load_data(self):
        if os.path.exists(self.DATA_FILE):
            with open(self.DATA_FILE, 'r') as f:
                try:
                    data = json.load(f)
                    self.lamps = data.get('lamps', {})
                    self.groups = data.get('groups', {})
                except json.JSONDecodeError:
                    self.lamps = {}
                    self.groups = {}

    def save_data(self):
        with open(self.DATA_FILE, 'w') as f:
            json.dump({'lamps': self.lamps, 'groups': self.groups}, f, indent=4)

    def add_lamp(self, mac, ip, name):
        if mac not in self.lamps:
            self.lamps[mac] = {
                'ip': ip if ip else "0.0.0.0",
                'name': name if name else f"WiZ-{mac[-6:]}",
                'mac': mac,
                'last_brightness': 100,
                'last_color_hex': '#ffffff',
                'last_temp_kelvin': 2700
            }
            self.save_data()
            return True
        return False

    def add_group(self, group_name, lamp_macs):
        self.groups[group_name] = lamp_macs
        self.save_data()

    def get_groups(self):
        return self.groups

    def get_lamps_in_group(self, group_name):
        lamp_macs = self.groups.get(group_name, [])
        return [self.lamps[mac] for mac in lamp_macs if mac in self.lamps]

    def update_lamp_state(self, mac, brightness=None, color_hex=None, last_temp_kelvin=None):
        if mac in self.lamps:
            if brightness is not None:
                self.lamps[mac]['last_brightness'] = brightness
            if color_hex is not None:
                self.lamps[mac]['last_color_hex'] = color_hex
            if last_temp_kelvin is not None:
                self.lamps[mac]['last_temp_kelvin'] = last_temp_kelvin
            self.save_data()

    def get_lamps(self):
        return list(self.lamps.values())

    def send_command(self, ip, command_params):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.05)  # Timeout más corto para mejor rendimiento
            command_json = json.dumps(command_params).encode('utf-8')
            sock.sendto(command_json, (ip, 38899))
            sock.close()
        except Exception:
            pass

class ModernToggle(QWidget):
    """Toggle clickeable en toda su área"""
    stateChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 20)
        self._checked = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.stateChanged.emit(Qt.CheckState.Checked.value if self._checked else Qt.CheckState.Unchecked.value)
            event.accept()
        
    def isChecked(self):
        return self._checked
    
    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bg_color = QColor("#005FB8") if self._checked else QColor("#5C5C5C")
        circle_x = 22 if self._checked else 2
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(0, 0, 40, 20, 10, 10)
        
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(circle_x, 2, 16, 16)

class LampControl(QWidget):
    def __init__(self, lamp_data, wiz_manager, parent=None):
        super().__init__(parent)
        self.mac = lamp_data['mac']
        self.ip = lamp_data['ip']
        self.wiz_manager = wiz_manager
        
        initial_brightness = lamp_data.get('last_brightness', 100)
        self.is_on = (initial_brightness > 0)
        self.current_color = QColor(lamp_data.get('last_color_hex', '#ffffff')) 
        self.current_temp = lamp_data.get('last_temp_kelvin', 2700)
        self.current_hue = self.current_color.hue() if self.current_color.hue() >= 0 else 0
        
        self.setObjectName("LampCard")
        self.setup_ui(lamp_data, initial_brightness)

    def setup_ui(self, lamp_data, initial_brightness):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Header clickeable
        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        name_label = QLabel(lamp_data['name'])
        name_label.setObjectName("lampName")
        header_layout.addWidget(name_label)
        header_layout.addStretch()
        
        self.toggle = ModernToggle()
        self.toggle.setChecked(self.is_on)
        self.toggle.stateChanged.connect(self.send_toggle_command)
        header_layout.addWidget(self.toggle)
        
        def header_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.toggle.mousePressEvent(e)
        header.mousePressEvent = header_click
        
        main_layout.addWidget(header)
        
        # Brillo compacto
        brightness_layout = QHBoxLayout()
        brightness_layout.setSpacing(8)
        
        bright_label = QLabel("☀")
        bright_label.setFixedWidth(16)
        bright_label.setStyleSheet("font-size: 12px; color: #E0E0E0;")
        brightness_layout.addWidget(bright_label)
        
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(10, 100)
        self.brightness_slider.setValue(initial_brightness)
        self.brightness_slider.valueChanged.connect(self.send_brightness_command)
        brightness_layout.addWidget(self.brightness_slider)
        
        self.brightness_value = QLabel(f"{initial_brightness}%")
        self.brightness_value.setObjectName("valueLabel")
        self.brightness_value.setFixedWidth(35)
        brightness_layout.addWidget(self.brightness_value)
        
        main_layout.addLayout(brightness_layout)
        
        # Temperatura compacta
        temp_layout = QHBoxLayout()
        temp_layout.setSpacing(8)
        
        temp_label = QLabel("◐")
        temp_label.setFixedWidth(16)
        temp_label.setStyleSheet("font-size: 12px; color: #E0E0E0;")
        temp_layout.addWidget(temp_label)
        
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(self.kelvin_to_slider(self.current_temp))
        self.temp_slider.valueChanged.connect(self.send_temp_command)
        temp_layout.addWidget(self.temp_slider)
        
        self.temp_value = QLabel(f"{self.current_temp}K")
        self.temp_value.setObjectName("valueLabel")
        self.temp_value.setFixedWidth(35)
        temp_layout.addWidget(self.temp_value)
        
        main_layout.addLayout(temp_layout)
        
        # Color como slider de HUE
        color_layout = QHBoxLayout()
        color_layout.setSpacing(8)
        
        color_label = QLabel("●")
        color_label.setFixedWidth(16)
        color_label.setStyleSheet("font-size: 12px; color: #E0E0E0;")
        color_layout.addWidget(color_label)
        
        self.color_slider = QSlider(Qt.Orientation.Horizontal)
        self.color_slider.setRange(0, 359)
        self.color_slider.setValue(self.current_hue)
        self.color_slider.setObjectName("colorSlider")
        self.color_slider.valueChanged.connect(self.send_color_command)
        color_layout.addWidget(self.color_slider)
        
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(35, 20)
        self.update_color_preview()
        color_layout.addWidget(self.color_preview)
        
        main_layout.addLayout(color_layout)

    def update_color_preview(self):
        color = QColor.fromHsv(self.current_hue, 255, 255)
        self.color_preview.setStyleSheet(f"""
            QLabel {{
                background-color: {color.name()};
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
            }}
        """)

    def kelvin_to_slider(self, kelvin):
        return int(((kelvin - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * 100)

    def slider_to_kelvin(self, slider_val):
        return int(((slider_val / 100) * (TEMP_MAX - TEMP_MIN)) + TEMP_MIN)

    def send_toggle_command(self, state):
        is_on = state == Qt.CheckState.Checked.value
        self.is_on = is_on
        dimming = self.brightness_slider.value() if is_on else 100
        command = {"method": "setPilot", "params": {"state": is_on, "dimming": dimming}}
        self.wiz_manager.send_command(self.ip, command)

    def send_brightness_command(self, value):
        self.brightness_value.setText(f"{value}%")
        self.wiz_manager.update_lamp_state(self.mac, brightness=value)
        if not self.is_on:
            self.toggle.setChecked(True)
        command = {"method": "setPilot", "params": {"dimming": value, "state": True}}
        self.wiz_manager.send_command(self.ip, command)
        
    def send_temp_command(self, slider_val):
        kelvin = self.slider_to_kelvin(slider_val)
        self.current_temp = kelvin
        self.temp_value.setText(f"{kelvin}K")
        self.wiz_manager.update_lamp_state(self.mac, last_temp_kelvin=kelvin)
        if not self.is_on:
            self.toggle.setChecked(True)
        command = {
            "method": "setPilot",
            "params": {"temp": int(kelvin), "dimming": self.brightness_slider.value(), "state": True, "colorMode": "temp"}
        }
        self.wiz_manager.send_command(self.ip, command)

    def send_color_command(self, hue):
        self.current_hue = hue
        color = QColor.fromHsv(hue, 255, 255)
        self.current_color = color
        self.update_color_preview()
        
        self.wiz_manager.update_lamp_state(self.mac, color_hex=color.name())
        if not self.is_on:
            self.toggle.setChecked(True)
        
        r, g, b = color.red(), color.green(), color.blue()
        dimming = self.brightness_slider.value()
        command = {
            "method": "setPilot",
            "params": {"r": int(r), "g": int(g), "b": int(b), "dimming": int(dimming), "state": True, "colorMode": "rgb"}
        }
        self.wiz_manager.send_command(self.ip, command)

class GroupDialog(QDialog):
    def __init__(self, wiz_manager, parent=None):
        super().__init__(parent)
        self.wiz_manager = wiz_manager
        self.setWindowTitle("Crear Grupo")
        self.setModal(True)
        self.resize(300, 400)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Nombre del grupo:"))
        self.group_name_input = QLineEdit()
        layout.addWidget(self.group_name_input)
        
        layout.addWidget(QLabel("Seleccionar luces:"))
        self.lamp_list = QListWidget()
        for lamp in self.wiz_manager.get_lamps():
            item = QListWidgetItem(lamp['name'])
            item.setData(Qt.ItemDataRole.UserRole, lamp['mac'])
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lamp_list.addItem(item)
        layout.addWidget(self.lamp_list)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Guardar")
        cancel_btn = QPushButton("Cancelar")
        save_btn.clicked.connect(self.save_group)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
    
    def save_group(self):
        group_name = self.group_name_input.text().strip()
        if not group_name:
            QMessageBox.warning(self, "Error", "Ingresa un nombre para el grupo")
            return
        
        selected_macs = []
        for i in range(self.lamp_list.count()):
            item = self.lamp_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_macs.append(item.data(Qt.ItemDataRole.UserRole))
        
        if not selected_macs:
            QMessageBox.warning(self, "Error", "Selecciona al menos una luz")
            return
        
        self.wiz_manager.add_group(group_name, selected_macs)
        self.accept()

class PopupWindow(QWidget):
    def __init__(self, wiz_manager):
        super().__init__()
        self.wiz_manager = wiz_manager
        
        # 1. TEMPORIZADOR DE ANIMACIÓN
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.finished.connect(super().hide)
        
        # 2. TEMPORIZADOR DE OCULTAMIENTO (Inicia la animación)
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(400)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.start_hide_animation) 
        
        # 🚨 ¡AÑADE ESTO! TEMPORIZADOR DE MONITOREO (Para el área ampliada) 🚨
        self.check_timer = QTimer(self)
        self.check_timer.setInterval(100) # Chequea 10 veces por segundo
        # Conexión a la función sin argumentos (la que calcula el rectángulo dinámicamente)
        self.check_timer.timeout.connect(self.check_hover_area) 

        # 3. CONFIGURACIÓN VISUAL
        self.setWindowTitle("WiZ Control")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(0, 0, 340, 450) 
        
        self.setup_ui()
        self.load_content()
        
         # Nuevo método para iniciar la animación de ocultamiento
    def start_hide_animation(self):
        """Inicia el proceso de fundido a negro (fade out)."""
        self.animation.stop()
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(0.0)
        self.animation.start()

    def show(self):
        """Asegura la opacidad máxima al mostrar y detiene el monitoreo."""
        self.setWindowOpacity(1.0)
        if hasattr(self, 'check_timer') and self.check_timer.isActive():
            self.check_timer.stop()
        super().show()
        
    def hide(self):
        # Este método ahora es un 'placeholder' ya que super().hide es llamado por la animación
        pass 

    def get_detection_rect(self) -> QRect:
        """Calcula el rectángulo de detección ampliado (10% de margen) en coordenadas de pantalla."""
        win_rect = self.frameGeometry()
        
        # El 10% del tamaño, convertido a entero (pixel count)
        margin_x = int(win_rect.width() * 0.10)
        margin_y = int(win_rect.height() * 0.10)
        
        # Expande el rectángulo por el margen en todas direcciones
        return win_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)

    def check_hover_area(self):
        """Método llamado periódicamente por self.check_timer. Revisa si el cursor salió del área ampliada."""
        detection_rect = self.get_detection_rect()
        cursor_pos = QCursor.pos()

        if not detection_rect.contains(cursor_pos):
            # El mouse salió del área ampliada: detenemos el monitoreo e iniciamos el ocultamiento
            self.check_timer.stop()
            self.hide_timer.start()
            
    def enterEvent(self, event):
        """Al reingresar el mouse, detiene cualquier ocultamiento o monitoreo."""
        self.hide_timer.stop()
        if hasattr(self, 'check_timer') and self.check_timer.isActive():
            self.check_timer.stop()
            
        # Detiene la animación si el mouse regresa durante el fade out
        self.animation.stop()
        self.setWindowOpacity(1.0) 

        super().enterEvent(event)

    def leaveEvent(self, event):
        """Al salir del área visible, comprueba si debe iniciar el monitoreo o el ocultamiento."""
        detection_rect = self.get_detection_rect()
        cursor_pos = QCursor.pos()
        
        if detection_rect.contains(cursor_pos):
            # El mouse salió de lo visible, pero entró en el margen del 10%.
            self.hide_timer.stop()
            # Reiniciamos el chequeo para el nuevo rectángulo de detección.
            self.check_timer.start() 
        else:
            # El mouse salió completamente del área ampliada.
            self.hide_timer.start() 
            
        super().leaveEvent(event)


    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor(32, 32, 32, 240))
        
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Botones superiores
        btn_row = QHBoxLayout()
        self.discover_button = QPushButton("Descubrir")
        self.discover_button.setObjectName("discoverButton")
        self.discover_button.setFixedHeight(32)
        self.discover_button.clicked.connect(self.start_discovery)
        
        group_button = QPushButton("Crear Grupo")
        group_button.setObjectName("groupButton")
        group_button.setFixedHeight(32)
        group_button.clicked.connect(self.create_group)
        
        btn_row.addWidget(self.discover_button)
        btn_row.addWidget(group_button)
        main_layout.addLayout(btn_row)

        # Área de scroll CON wheelEvent filtrado
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Importante para el scroll
        main_layout.addWidget(self.scroll_area)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(6)  # Más compacto
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addStretch()
        self.scroll_area.setWidget(self.content_widget)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton#discoverButton, QPushButton#groupButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 6px 12px;
                color: #FFFFFF;
                font-size: 13px;
            }
            QPushButton#discoverButton:hover, QPushButton#groupButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
            }
            QWidget#LampCard {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
            }
            QLabel#lampName {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#controlLabel {
                color: #E0E0E0;
                font-size: 11px;
            }
            QLabel#valueLabel {
                color: #A0A0A0;
                font-size: 10px;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: none;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #005FB8;
                border-radius: 2px;
            }
            QSlider#colorSlider::groove:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF0000, stop:0.17 #FFFF00, stop:0.33 #00FF00,
                    stop:0.5 #00FFFF, stop:0.67 #0000FF, stop:0.83 #FF00FF, stop:1 #FF0000);
                height: 6px;
                border-radius: 3px;
            }
            QSlider#colorSlider::sub-page:horizontal {
                background: transparent;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                min-height: 20px;
                border-radius: 5px;
                margin: 2px;
            }
        """)
    def load_content(self):
        # Limpiar contenido
        for i in reversed(range(self.content_layout.count() - 1)):
            widget = self.content_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        # Cargar luces individuales
        for lamp in self.wiz_manager.get_lamps():
            if 'mac' in lamp and 'ip' in lamp:
                lamp_widget = LampControl(lamp, self.wiz_manager)
                self.content_layout.insertWidget(self.content_layout.count() - 1, lamp_widget)

    def create_group(self):
        dialog = GroupDialog(self.wiz_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_content()

    def start_discovery(self):
        self.discover_button.setEnabled(False)
        self.discover_button.setText("Buscando...")
        self.discovery_thread = DiscoveryThread()
        self.discovery_thread.lamp_found.connect(self.handle_lamp_found)
        self.discovery_thread.finished.connect(self.discovery_finished)
        self.discovery_thread.start()

    def handle_lamp_found(self, lamp_data):
        mac = lamp_data.get('mac')
        if mac and self.wiz_manager.add_lamp(mac, lamp_data.get('ip'), lamp_data.get('name')):
            self.load_content()

    def discovery_finished(self):
        QMessageBox.information(self, "Descubrimiento", "Búsqueda finalizada.")
        self.discover_button.setEnabled(True)
        self.discover_button.setText("Descubrir")

    def show_at_position(self, position: QPoint):
        x = position.x() - self.width() - 10
        y = position.y() - self.height() - 10
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self.activateWindow()

   

class TrayAppQt:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.wiz_manager = WizManager()

        self.app.setFont(QFont("Segoe UI", 10))

        style = self.app.style()
        self.icon = QSystemTrayIcon(style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.icon.setToolTip("WiZ Light Controller")
        
        # Crear menú contextual primero
        menu = QMenu()
        show_action = QAction("Mostrar Control", menu)
        exit_action = QAction("Salir", menu)
        menu.addAction(show_action)
        menu.addAction(exit_action)
        self.icon.setContextMenu(menu)
        
        # Mostrar ícono ANTES de crear la ventana
        self.icon.setVisible(True)

        self.window = PopupWindow(self.wiz_manager)

        # Conexiones
        self.icon.activated.connect(self.handle_icon_click)
        show_action.triggered.connect(self.show_window)
        exit_action.triggered.connect(self.app.quit)

    def handle_icon_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        # Obtener posición del cursor como fallback
        cursor_pos = QCursor.pos()
        self.window.show_at_position(cursor_pos)

    def run(self):
        return self.app.exec()

if __name__ == '__main__':
    app = TrayAppQt()
    sys.exit(app.run())