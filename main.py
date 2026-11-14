import sys
import json
import socket
import os
import copy
import ctypes
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QLabel,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QGridLayout,
    QSlider,
    QScrollArea,
    QAbstractScrollArea,
    QFrame,
    QColorDialog,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsBlurEffect,
)
from PyQt6.QtGui import (
    QAction,
    QCursor,
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPen,
    QPainterPath,
    QIcon,
    QPixmap,
    QLinearGradient,
    QBrush,
    QImage,
    QWheelEvent,
)
from PyQt6.QtCore import (
    QPoint,
    QPointF,
    Qt,
    QThread,
    pyqtSignal,
    QPropertyAnimation,
    QVariantAnimation,
    QTimer,
    QRect,
    QEasingCurve,
    QRectF,
    QEvent,
)
import time

TEMP_MIN = 2200
TEMP_MAX = 6500


def resource_path(relative_path):
    """Ruta a archivos empaquetados de solo lectura (ej: el ícono).
    Cuando corre normal, es la carpeta del script. Cuando corre compilado
    con PyInstaller (--onefile), los recursos viven en una carpeta temporal
    apuntada por sys._MEIPASS."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_data_dir():
    """Carpeta persistente y con permisos de escritura para guardar datos
    del usuario (lamps_data.json), sin importar dónde esté instalado el .exe."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.local/share")
    path = os.path.join(base, "WizLampControl")
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Ajustes de apariencia (settings.json, junto a lamps_data.json)
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "glass": {
        "enabled": True,
        # "auto": usa el blur nativo de DWM si está disponible; si no, captura.
        # "capture": captura + desenfoque propio, con intensidad ajustable.
        "mode": "auto",
        "tint": "#181818",
        "opacity": 135,  # 0-255
        "blur": 5,  # 2-10, solo se usa en modo "capture"
    },
    "sliders": {
        "accent": "#005fb8",
        "thickness": 4,  # 2-28 px (el switch usa el mismo valor para su barra)
        "handle": 12,  # 6-24 px
    },
    "toggle": {
        # "on" se sincroniza siempre con sliders.accent (no se edita aparte).
        "on": "#005fb8",  # botón encendido
        "off": "#5c5c5c",  # botón apagado
        "knob": "#ffffff",  # perilla
    },
}

# Rango compartido por sliders y switches. El grosor llega hasta 28 px para
# que la barra del slider pueda igualar o superar el grosor de la barra del
# switch, que nunca puede ser más fina que su perilla.
SLIDER_THICKNESS_MIN = 2
SLIDER_THICKNESS_MAX = 28
SLIDER_HANDLE_MIN = 6
SLIDER_HANDLE_MAX = 24


def control_bar_height(thickness, handle):
    """Alto de la barra de sliders y switches.

    La barra siempre envuelve al tirador/perilla con 2 px de aire, así el
    tirador queda adentro en los dos controles. Con el tirador y el grosor
    por defecto da 16 px."""
    bar = max(14, max(thickness, handle + 4))
    bar = min(32, bar)
    return bar - (bar % 2)


def get_settings_path():
    return os.path.join(get_data_dir(), "settings.json")


def _clamp_setting(value, minimum, maximum, fallback):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return fallback


def _even_setting(value, minimum, maximum, fallback):
    """Entero **par** dentro del rango.

    Qt dibuja el tirador con ``border-radius`` en píxeles enteros. Si el
    tirador (o el grosor de la barra) es impar, el radio y el margen quedan
    fraccionarios (por ejemplo ``6.5px``), Qt descarta esos valores y el
    tirador sale con las esquinas cuadradas. Manteniéndolos pares, la división
    es exacta y el círculo queda perfecto con cualquier tamaño."""
    clamped = _clamp_setting(value, minimum, maximum, fallback)
    if clamped % 2:
        clamped += 1 if clamped < maximum else -1
    return max(minimum, min(maximum, clamped))


def _valid_color_setting(value, fallback):
    color = QColor(value) if isinstance(value, str) else QColor()
    return color.name() if color.isValid() else fallback


def load_settings():
    """Carga settings.json y completa lo que falte con los valores por defecto."""
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(get_settings_path(), "r", encoding="utf-8") as f:
            stored = json.load(f)
    except (OSError, ValueError):
        return settings
    if not isinstance(stored, dict):
        return settings

    glass = stored.get("glass")
    if isinstance(glass, dict):
        defaults = DEFAULT_SETTINGS["glass"]
        enabled = glass.get("enabled", defaults["enabled"])
        settings["glass"]["enabled"] = enabled if isinstance(enabled, bool) else True
        mode = glass.get("mode", defaults["mode"])
        settings["glass"]["mode"] = mode if mode in ("auto", "capture") else "auto"
        settings["glass"]["tint"] = _valid_color_setting(
            glass.get("tint"), defaults["tint"]
        )
        settings["glass"]["opacity"] = _clamp_setting(
            glass.get("opacity"), 0, 255, defaults["opacity"]
        )
        settings["glass"]["blur"] = _clamp_setting(
            glass.get("blur"), 2, 10, defaults["blur"]
        )

    sliders = stored.get("sliders")
    if isinstance(sliders, dict):
        defaults = DEFAULT_SETTINGS["sliders"]
        settings["sliders"]["accent"] = _valid_color_setting(
            sliders.get("accent"), defaults["accent"]
        )
        settings["sliders"]["thickness"] = _even_setting(
            sliders.get("thickness"),
            SLIDER_THICKNESS_MIN,
            SLIDER_THICKNESS_MAX,
            defaults["thickness"],
        )
        settings["sliders"]["handle"] = _even_setting(
            sliders.get("handle"),
            SLIDER_HANDLE_MIN,
            SLIDER_HANDLE_MAX,
            defaults["handle"],
        )

    toggle = stored.get("toggle")
    if isinstance(toggle, dict):
        defaults = DEFAULT_SETTINGS["toggle"]
        for key in ("on", "off", "knob"):
            settings["toggle"][key] = _valid_color_setting(
                toggle.get(key), defaults[key]
            )
    # El botón de encendido comparte el color de acento de los sliders: una
    # sola opción controla las dos cosas.
    settings["toggle"]["on"] = settings["sliders"]["accent"]
    return settings


def save_settings(settings):
    """Guarda los ajustes; si falla (permisos, disco lleno) no rompe la app."""
    try:
        with open(get_settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Efecto "frosted glass": blur en tiempo real del escritorio
# ---------------------------------------------------------------------------
# Método principal (Windows 11, build 22000+): DWM difumina el contenido que
# hay detrás de la ventana en la GPU. No cuesta CPU, va a la frecuencia del
# monitor y no parpadea. DWM recorta además la ventana con esquinas redondeadas.
# Método alternativo (Windows 10 2004+): se excluye la ventana del capturador
# (WDA_EXCLUDEFROMCAPTURE), se fotografía el escritorio de atrás y se difumina
# esa imagen. Se usa solo si el sistema no soporta el blur nativo.

_WDA_NONE = 0x00000000
_WDA_EXCLUDEFROMCAPTURE = 0x00000011

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_WCA_ACCENT_POLICY = 19
_ACCENT_DISABLED = 0
_ACCENT_ENABLE_BLURBEHIND = 3


def _set_display_affinity(hwnd, affinity):
    """Marca la ventana como invisible (o no) para las capturas de pantalla."""
    if sys.platform != "win32":
        return False
    try:
        return bool(
            ctypes.windll.user32.SetWindowDisplayAffinity(
                ctypes.c_void_p(hwnd), affinity
            )
        )
    except Exception:
        return False


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttribData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _set_accent_state(hwnd, state):
    """Aplica un estado de la política de acento de DWM a la ventana."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    # Sin tinte propio: el color lo pone Qt en paintEvent así el resultado es
    # idéntico al del método por captura.
    accent = _AccentPolicy(state, 0, 0x00000000, 0)
    data = _WindowCompositionAttribData(
        _WCA_ACCENT_POLICY,
        ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
        ctypes.sizeof(accent),
    )
    setter = user32.SetWindowCompositionAttribute
    setter.argtypes = [wintypes.HWND, ctypes.POINTER(_WindowCompositionAttribData)]
    setter.restype = wintypes.BOOL
    return bool(setter(wintypes.HWND(hwnd), ctypes.byref(data)))


def _apply_blur_behind(hwnd):
    """Activa el blur nativo de DWM detrás de la ventana (GPU, sin CPU)."""
    return _set_accent_state(hwnd, _ACCENT_ENABLE_BLURBEHIND)


def disable_native_blur(window):
    """Quita el blur nativo de DWM (al desactivar el vidrio o usar captura)."""
    if sys.platform != "win32":
        return False
    try:
        return _set_accent_state(int(window.winId()), _ACCENT_DISABLED)
    except Exception:
        return False


def _set_round_corners(hwnd):
    """Pide a DWM esquinas redondeadas para la ventana (Windows 11 build 22000+).

    Devuelve False si el sistema no soporta la preferencia; en ese caso el
    blur nativo quedaría con esquinas cuadradas y conviene el otro método."""
    from ctypes import wintypes

    try:
        preference = ctypes.c_int(_DWMWCP_ROUND)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return result == 0
    except Exception:
        return False


def enable_native_blur(window):
    """Blur en vivo de DWM con esquinas redondeadas. Devuelve True si pudo."""
    if sys.platform != "win32":
        return False
    try:
        if sys.getwindowsversion().build < 22000:  # Windows 11
            return False
        hwnd = int(window.winId())
        # Primero las esquinas: si el sistema no las soporta, el blur nativo
        # dejaría las esquinas cuadradas y es mejor usar la captura.
        if not _set_round_corners(hwnd):
            return False
        return _apply_blur_behind(hwnd)
    except Exception:
        return False


def blur_pixmap(pixmap, radius):
    """Devuelve una copia difuminada del pixmap (blur tipo gaussiano)."""
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    image = QImage(pixmap.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    scene.render(painter, QRectF(image.rect()), QRectF(pixmap.rect()))
    painter.end()
    return QPixmap.fromImage(image)


class DiscoveryThread(QThread):
    lamp_found = pyqtSignal(dict)

    def run(self):
        UDP_PORT = 38899
        BROADCAST_IP = "255.255.255.255"
        DISCOVERY_MESSAGE = '{"method":"getSystemConfig","params":{}}'.encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1)

        discovered_macs = set()
        start_time = time.time()

        try:
            sock.sendto(DISCOVERY_MESSAGE, (BROADCAST_IP, UDP_PORT))

            while time.time() - start_time < 3:
                try:
                    data, addr = sock.recvfrom(1024)
                    try:
                        response = json.loads(data.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    mac = response.get("result", {}).get("mac")
                    ip = addr[0]

                    if mac and ip and mac not in discovered_macs:
                        discovered_macs.add(mac)
                        cleaned_mac = mac.replace(":", "")
                        name = f"WiZ-{cleaned_mac[-6:]}"
                        self.lamp_found.emit({"ip": ip, "mac": mac, "name": name})
                except socket.timeout:
                    pass
                except Exception:
                    continue
        finally:
            sock.close()


class WizManager:
    DATA_FILE = os.path.join(get_data_dir(), "lamps_data.json")

    def __init__(self):
        self.lamps = {}
        self.groups = {}
        self._socket = None
        # Guardar el JSON en cada movimiento del slider bloquea la interfaz
        # (acceso a disco en el hilo de la UI). Se escribe una sola vez cuando
        # el usuario deja de mover los controles.
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._write_data)
        self.load_data()

    def load_data(self):
        if not os.path.exists(self.DATA_FILE):
            return
        try:
            with open(self.DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            self.lamps = {}
            self.groups = {}
            return
        if isinstance(data, dict):
            lamps = data.get("lamps")
            groups = data.get("groups")
            self.lamps = lamps if isinstance(lamps, dict) else {}
            self.groups = groups if isinstance(groups, dict) else {}
        else:
            self.lamps = {}
            self.groups = {}

    def save_data(self):
        """Guarda ya mismo. Solo para cambios estructurales (agregar/borrar)."""
        self._save_timer.stop()
        self._write_data()

    def schedule_save(self):
        """Guarda en segundo plano cuando la UI queda quieta un momento."""
        self._save_timer.start()

    def flush(self):
        """Escribe cualquier cambio pendiente (al cerrar la app)."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._write_data()

    def shutdown(self):
        self.flush()
        self._close_socket()

    def _write_data(self):
        try:
            with open(self.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"lamps": self.lamps, "groups": self.groups}, f, indent=4)
        except OSError:
            # Disco lleno / permisos: no se pierde la sesión en memoria.
            pass

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
        else:
            # Si la lámpara ya existe, actualizar la IP si cambió
            if self.lamps[mac]['ip'] != ip:
                self.lamps[mac]['ip'] = ip
                self.save_data()
                return True  # Retornar True para refrescar la interfaz
        return False

    def add_group(self, group_name, lamp_macs):
        self.groups[group_name] = lamp_macs
        self.save_data()

    def delete_lamp(self, mac):
        """Borra una lámpara y la saca de cualquier grupo donde estuviera"""
        if mac in self.lamps:
            del self.lamps[mac]
            for lamp_macs in self.groups.values():
                if mac in lamp_macs:
                    lamp_macs.remove(mac)
            self.save_data()

    def delete_group(self, group_name):
        """Borra un grupo. Las lámparas del grupo NO se borran, quedan sueltas"""
        if group_name in self.groups:
            del self.groups[group_name]
            self.save_data()

    def get_groups(self):
        return self.groups

    def get_lamps_in_group(self, group_name):
        lamp_macs = self.groups.get(group_name, [])
        return [self.lamps[mac] for mac in lamp_macs if mac in self.lamps]

    def get_lamp_groups(self, mac):
        """Retorna lista de nombres de grupos que contienen esta lámpara"""
        groups = []
        for group_name, lamp_macs in self.groups.items():
            if mac in lamp_macs:
                groups.append(group_name)
        return groups

    def update_lamp_state(
        self, mac, brightness=None, color_hex=None, last_temp_kelvin=None
    ):
        if mac in self.lamps:
            if brightness is not None:
                self.lamps[mac]["last_brightness"] = brightness
            if color_hex is not None:
                self.lamps[mac]["last_color_hex"] = color_hex
            if last_temp_kelvin is not None:
                self.lamps[mac]["last_temp_kelvin"] = last_temp_kelvin
            self.schedule_save()

    def get_lamps(self):
        return list(self.lamps.values())

    def get_ungrouped_lamps(self):
        """Retorna lámparas que no pertenecen a ningún grupo"""
        grouped_macs = set()
        for lamp_macs in self.groups.values():
            grouped_macs.update(lamp_macs)

        return [lamp for lamp in self.lamps.values() if lamp["mac"] not in grouped_macs]

    def send_command(self, ip, command_params):
        """Envía un comando UDP reutilizando un único socket.

        Crear y cerrar un socket por comando era costoso al arrastrar un
        slider (varios comandos por segundo); reutilizarlo mantiene el
        movimiento fluido."""
        sock = self._get_socket()
        if sock is None:
            return
        try:
            command_json = json.dumps(command_params).encode("utf-8")
            sock.sendto(command_json, (ip, 38899))
        except OSError:
            # El socket quedó inservible: se descarta y se recrea al próximo.
            self._close_socket()

    def _get_socket(self):
        if self._socket is None:
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setblocking(False)
            except OSError:
                self._socket = None
        return self._socket

    def _close_socket(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def send_command_to_group(self, group_name, command_params):
        """Envía un comando a todas las lámparas de un grupo"""
        lamps = self.get_lamps_in_group(group_name)
        for lamp in lamps:
            self.send_command(lamp["ip"], command_params)


class ImprovedSlider(QSlider):
    """Slider que responde en todo el ancho y sigue al mouse.

    Se dibuja a mano (no con QSS) para que el surco, el relleno y el tirador
    queden perfectamente redondeados con cualquier combinación de grosor y
    tamaño, incluso cuando el valor está en los extremos.

    Puntos que se corrigieron respecto de la versión anterior:

    * El temporizador ya **no se reinicia** en cada movimiento (eso era un
      *debounce*): mientras se arrastra se emite como máximo un valor cada
      ``THROTTLE_MS``, así la lámpara acompaña el movimiento en vivo en vez de
      esperar a que se suelte el mouse.
    * Si el botón se suelta fuera de la ventana (o el popup se oculta en medio
      del arrastre), el estado de arrastre se libera igual y se envía el valor
      final. Antes quedaba "pegado".
    * La posición se traduce con ``QStyle.sliderValueFromPosition``, que usa el
      ancho real del surco y respeta la dirección del slider.
    * La rueda del mouse no cambia el valor sin querer: se deja pasar al scroll.
    * El tirador queda siempre dentro del widget: en los extremos ya no se
      recorta contra el borde.
    """

    valueChangedDelayed = pyqtSignal(int)

    THROTTLE_MS = 60

    COLOR_STOPS = (
        (0.0, "#ff0000"),
        (0.17, "#ffff00"),
        (0.33, "#00ff00"),
        (0.5, "#00ffff"),
        (0.67, "#0000ff"),
        (0.83, "#ff00ff"),
        (1.0, "#ff0000"),
    )

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        # El fondo se dibuja a mano sobre el vidrio del popup: sin esto Qt
        # pinta un fondo opaco de paleta detrás del slider.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._is_dragging = False
        self._last_emitted = None
        self._suspend_emit = False

        defaults = DEFAULT_SETTINGS["sliders"]
        self._accent = QColor(defaults["accent"])
        self._thickness = defaults["thickness"]
        self._handle = defaults["handle"]
        self._off_color = QColor(DEFAULT_SETTINGS["toggle"]["off"])
        self._handle_color = QColor(DEFAULT_SETTINGS["toggle"]["knob"])
        self._gradient = False
        self._bar_height = control_bar_height(self._thickness, self._handle)
        self.setMinimumHeight(self._bar_height + 4)

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(self.THROTTLE_MS)
        self._update_timer.timeout.connect(self._emit_delayed_value)

        self.valueChanged.connect(self._on_value_changed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- apariencia --------------------------------------------------------

    def apply_appearance(self, settings, gradient=False):
        """Aplica los ajustes unificados de controles.

        El acento, el color de apagado y el de la perilla se comparten con el
        switch; el grosor y el tamaño del tirador también. Así un solo juego de
        controles modifica sliders y botones a la vez.

        ``gradient=True`` se usa para el slider de matiz (degradé arcoíris y
        sin relleno)."""
        sliders = settings["sliders"]
        defaults = DEFAULT_SETTINGS["sliders"]
        toggle = settings.get("toggle", DEFAULT_SETTINGS["toggle"])
        toggle_defaults = DEFAULT_SETTINGS["toggle"]
        self._accent = QColor(
            _valid_color_setting(sliders.get("accent"), defaults["accent"])
        )
        self._thickness = _even_setting(
            sliders.get("thickness"),
            SLIDER_THICKNESS_MIN,
            SLIDER_THICKNESS_MAX,
            defaults["thickness"],
        )
        self._handle = _even_setting(
            sliders.get("handle"),
            SLIDER_HANDLE_MIN,
            SLIDER_HANDLE_MAX,
            defaults["handle"],
        )
        self._off_color = QColor(
            _valid_color_setting(toggle.get("off"), toggle_defaults["off"])
        )
        self._handle_color = QColor(
            _valid_color_setting(toggle.get("knob"), toggle_defaults["knob"])
        )
        self._gradient = bool(gradient)
        self._bar_height = control_bar_height(self._thickness, self._handle)
        self.setMinimumHeight(self._bar_height + 4)
        self.update()

    def _groove_rect(self):
        """Barra completa del slider: el tirador siempre queda adentro."""
        return QRectF(
            0,
            (self.height() - self._bar_height) / 2,
            max(1.0, float(self.width())),
            self._bar_height,
        )

    def _handle_padding(self):
        """Aire entre el tirador y el borde de la barra.

        Es el mismo margen que usa la perilla del switch (2 px cuando la
        barra es fina y más si el grosor supera al tirador), así el tirador
        del slider y la perilla del botón quedan ubicados igual."""
        return max(0.0, (self._bar_height - self._handle) / 2)

    def _travel_span(self):
        """Recorrido del centro del tirador dentro de la barra."""
        if self.orientation() == Qt.Orientation.Horizontal:
            available = self.width() - self._handle - 2 * self._handle_padding()
        else:
            available = self.height() - self._handle - 2 * self._handle_padding()
        return max(1, int(round(available)))

    def _slider_position(self):
        span = self._travel_span()
        if self.orientation() == Qt.Orientation.Horizontal:
            upside_down = self.invertedAppearance()
        else:
            upside_down = not self.invertedAppearance()
        return QStyle.sliderPositionFromValue(
            self.minimum(), self.maximum(), self.value(), span, upside_down
        )

    def paintEvent(self, event):
        # Los sliders verticales no se usan en la app; se deja el dibujo
        # nativo por si alguno aparece en el futuro.
        if self.orientation() != Qt.Orientation.Horizontal:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        groove = self._groove_rect()
        radius = groove.height() / 2
        position = self._slider_position()
        center_x = self._handle_padding() + self._handle / 2 + position

        if self._gradient:
            gradient = QLinearGradient(groove.left(), 0, groove.right(), 0)
            for stop, color in self.COLOR_STOPS:
                gradient.setColorAt(stop, QColor(color))
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(groove, radius, radius)
        else:
            span = self._travel_span()
            if position <= 0:
                # Todo apagado: una sola píldora continua, igual que el
                # switch apagado.
                painter.setBrush(self._off_color)
                painter.drawRoundedRect(groove, radius, radius)
            elif position >= span:
                # Todo encendido: también una sola píldora, así no queda el
                # color de apagado alrededor del tirador.
                painter.setBrush(self._accent)
                painter.drawRoundedRect(groove, radius, radius)
            else:
                # Barra continua: se dibuja UNA sola píldora completa y el
                # cambio de color se hace con un degradé suave CENTRADO en el
                # tirador: el acento se desvanece hacia el apagado a lo ancho
                # del tirador. En el centro de la barra lo tapa el tirador y
                # en las franjas de arriba/abajo se ve una transición
                # difuminada, sin costura ni borde recto.
                fade = max(10.0, float(self._handle))
                bar_width = max(1.0, groove.width())
                fade_start = max(groove.left(), center_x - fade / 2)
                fade_end = min(groove.right(), center_x + fade / 2)
                start = (fade_start - groove.left()) / bar_width
                end = (fade_end - groove.left()) / bar_width
                gradient = QLinearGradient(groove.left(), 0, groove.right(), 0)
                gradient.setColorAt(0.0, self._accent)
                gradient.setColorAt(max(0.0, start), self._accent)
                gradient.setColorAt(min(1.0, end), self._off_color)
                gradient.setColorAt(1.0, self._off_color)
                painter.setBrush(QBrush(gradient))
                painter.drawRoundedRect(groove, radius, radius)

        # Tirador: mismo color que la perilla del switch y con el mismo aire
        # respecto de la barra.
        padding = self._handle_padding()
        painter.setBrush(self._handle_color)
        painter.drawEllipse(
            QRectF(
                center_x - self._handle / 2,
                groove.top() + padding,
                self._handle,
                self._handle,
            )
        )

    # -- emisión -----------------------------------------------------------

    def set_value_silently(self, value):
        """Cambia el valor sin disparar ``valueChangedDelayed``.

        Se usa para sincronizaciones (estado inicial de la tarjeta, cambios
        que llegan desde un grupo o desde el selector de color). Si no, Qt
        trata el ``setValue`` como una acción del usuario y manda comandos a
        las lámparas apenas se abre el panel."""
        self._suspend_emit = True
        try:
            self.setValue(value)
        finally:
            self._suspend_emit = False
        self._update_timer.stop()
        self._last_emitted = self.value()

    def _on_value_changed(self, value):
        if self._suspend_emit:
            return
        # Un único timer activo a la vez (throttle). No se reinicia con cada
        # evento, por eso los comandos salen también durante el arrastre.
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _emit_delayed_value(self):
        value = self.value()
        if value == self._last_emitted:
            return
        self._last_emitted = value
        self.valueChangedDelayed.emit(value)

    # -- arrastre ----------------------------------------------------------

    def _start_drag(self):
        self._is_dragging = True
        self.setSliderDown(True)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        hook = getattr(self.window(), "slider_interaction_started", None)
        if hook is not None:
            hook()

    def _finish_drag(self):
        if not self._is_dragging:
            self._update_timer.stop()
            return
        self._is_dragging = False
        self.setSliderDown(False)
        self._update_timer.stop()
        self._emit_delayed_value()  # valor final, sin esperar al throttle
        hook = getattr(self.window(), "slider_interaction_finished", None)
        if hook is not None:
            hook()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_drag()
            self._update_value_from_position(event.position().toPoint())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            # Red de seguridad: si el release se perdió (por ejemplo al
            # ocultarse el popup), el próximo movimiento lo detecta.
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._finish_drag()
                return
            self._update_value_from_position(event.position().toPoint())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._update_value_from_position(event.position().toPoint())
            self._finish_drag()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._finish_drag()
        super().hideEvent(event)

    def focusOutEvent(self, event):
        # Si otra ventana se queda con el foco en medio del arrastre, el
        # release nunca llega a este widget: se cierra igual y se avisa el
        # valor final.
        if self._is_dragging:
            self._finish_drag()
        super().focusOutEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self._finish_drag()
        super().changeEvent(event)

    def wheelEvent(self, event):
        """La rueda no cambia el brillo sin querer: scrollea el panel.

        Se reenvía al ``QScrollArea`` que contiene al slider; si no hay uno,
        se ignora. Así el panel se puede recorrer con la rueda aunque el
        cursor esté sobre un control."""
        area = self.parentWidget()
        while area is not None and not isinstance(area, QAbstractScrollArea):
            area = area.parentWidget()
        if area is None:
            event.ignore()
            return
        viewport = area.viewport()
        local_pos = viewport.mapFromGlobal(event.globalPosition().toPoint())
        QApplication.sendEvent(
            viewport,
            QWheelEvent(
                QPointF(local_pos),
                event.globalPosition(),
                event.pixelDelta(),
                event.angleDelta(),
                event.buttons(),
                event.modifiers(),
                event.phase(),
                event.inverted(),
            ),
        )
        event.accept()

    def _update_value_from_position(self, pos):
        """Calcula el valor del slider según la posición del mouse.

        Se descuenta el aire lateral y media pieza del tirador para que su
        centro recorra el mismo tramo que se usa al dibujarlo: así el tirador
        queda siempre completo y con el mismo margen que la perilla del
        switch."""
        padding = self._handle_padding()
        span = self._travel_span()
        if self.orientation() == Qt.Orientation.Horizontal:
            position = max(
                0, min(pos.x() - padding - self._handle / 2, span)
            )
            upside_down = self.invertedAppearance()
        else:
            position = max(
                0, min(pos.y() - padding - self._handle / 2, span)
            )
            upside_down = not self.invertedAppearance()
        self.setValue(
            QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(round(position)),
                span,
                upside_down,
            )
        )


class ModernToggle(QWidget):
    stateChanged = pyqtSignal(int)

    # Paleta compartida: PopupWindow y el diálogo la actualizan según settings.
    colors = {"on": "#005fb8", "off": "#5c5c5c", "knob": "#ffffff"}
    # Grosor de barra y tamaño de tirador compartidos con los sliders.
    metrics = {"thickness": 4, "handle": 12}

    @classmethod
    def set_colors(cls, colors):
        """Actualiza la paleta de todos los toggles (incluidos los ya creados)."""
        merged = dict(cls.colors)
        for key in ("on", "off", "knob"):
            value = colors.get(key) if isinstance(colors, dict) else None
            color = QColor(value) if isinstance(value, str) else QColor()
            if color.isValid():
                merged[key] = color.name()
        if merged == cls.colors:
            return
        cls.colors = merged
        cls._refresh_widgets()

    @classmethod
    def set_metrics(cls, metrics):
        """Actualiza grosor y tamaño de perilla de todos los toggles.

        Son los mismos valores que usan los sliders, así un solo control
        modifica ambos componentes."""
        defaults = DEFAULT_SETTINGS["sliders"]
        thickness = _even_setting(
            metrics.get("thickness"),
            SLIDER_THICKNESS_MIN,
            SLIDER_THICKNESS_MAX,
            defaults["thickness"],
        )
        handle = _even_setting(
            metrics.get("handle"),
            SLIDER_HANDLE_MIN,
            SLIDER_HANDLE_MAX,
            defaults["handle"],
        )
        if (thickness, handle) == (cls.metrics["thickness"], cls.metrics["handle"]):
            return
        cls.metrics = {"thickness": thickness, "handle": handle}
        cls._refresh_widgets()

    @classmethod
    def apply_appearance(cls, settings):
        """Colores + métricas en una sola llamada (sliders y botones unificados)."""
        sliders = settings.get("sliders", {}) if isinstance(settings, dict) else {}
        toggle = settings.get("toggle", {}) if isinstance(settings, dict) else {}
        # El "encendido" siempre es el acento del slider, aunque el llamador
        # pase un valor viejo: una sola opción manda en ambos componentes.
        colors = dict(toggle) if isinstance(toggle, dict) else {}
        if sliders.get("accent"):
            colors["on"] = sliders["accent"]
        cls.set_colors(colors)
        cls.set_metrics(sliders)

    @classmethod
    def _refresh_widgets(cls):
        app = QApplication.instance()
        if app is not None:
            for widget in app.allWidgets():
                if isinstance(widget, ModernToggle):
                    widget._apply_metrics()
                    widget.update()

    def __init__(self, parent=None):
        super().__init__(parent)
        # El fondo se dibuja completo con los bordes redondeados.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._checked = False
        self._position = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_metrics()

    def _geometry(self):
        """Dimensiones derivadas de los ajustes compartidos con los sliders.

        La barra del switch usa el mismo alto que la del slider y siempre
        envuelve a la perilla. La perilla mide lo mismo que el tirador."""
        thickness = self.metrics["thickness"]
        handle = self.metrics["handle"]
        bar = control_bar_height(thickness, handle)
        knob = min(handle, bar - 4)
        return bar * 2, bar, knob

    def _apply_metrics(self):
        width, height, _ = self._geometry()
        if self.width() != width or self.height() != height:
            self.setFixedSize(width, height)
        self.update()

    def _on_anim(self, value):
        self._position = float(value)
        self.update()

    def _animate_to(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(target)
        self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._animate_to(1.0 if self._checked else 0.0)
            self.stateChanged.emit(
                Qt.CheckState.Checked.value
                if self._checked
                else Qt.CheckState.Unchecked.value
            )
            event.accept()

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        if self.isVisible():
            self._animate_to(1.0 if checked else 0.0)
        else:
            self._anim.stop()
            self._position = 1.0 if checked else 0.0
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        on = QColor(self.colors["on"])
        off = QColor(self.colors["off"])
        t = self._position
        background = QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
        )

        width, height, knob = self._geometry()
        radius = height / 2
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)

        padding = (height - knob) / 2
        x = padding + (width - knob - 2 * padding) * t
        painter.setBrush(QColor(self.colors["knob"]))
        painter.drawEllipse(QRectF(x, padding, knob, knob))


class HoverButton(QPushButton):
    """Botón sin fondo definido que se ilumina suavemente al pasar el mouse.

    Imita a los iconos de la barra de tareas: en reposo solo se ve el texto o
    el icono; al hacer hover aparece un fondo redondeado translúcido."""

    def __init__(
        self,
        text="",
        parent=None,
        hover_color=QColor(255, 255, 255, 34),
        radius=6,
    ):
        super().__init__(text, parent)
        self._hover_color = QColor(hover_color)
        self._radius = radius
        self._progress = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_progress)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_progress(self, value):
        self._progress = float(value)
        self.update()

    def _animate_to(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        if self.isEnabled():
            self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        if self._progress > 0.001:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self._hover_color)
            color.setAlpha(round(color.alpha() * self._progress))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        super().paintEvent(event)


class FolderIcon(QWidget):
    """Icono de carpeta relleno, en la misma línea visual que el engranaje.

    Se dibuja como dos piezas sólidas con esquinas redondeadas (pestaña y
    cuerpo) en lugar del contorno fino anterior, que a 15 px se veía más
    "dibujado a mano" que el resto de los iconos."""

    def __init__(self, parent=None, size=16, color=QColor("#D0D0D0")):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(color)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        w = float(self.width())
        h = float(self.height())

        # Pestaña trasera: un poco más apagada para dar profundidad.
        tab = QColor(self._color)
        tab.setAlphaF(0.72)
        painter.setBrush(tab)
        painter.drawRoundedRect(
            QRectF(0.10 * w, 0.20 * h, 0.42 * w, 0.20 * h),
            0.05 * w,
            0.05 * w,
        )

        # Cuerpo de la carpeta.
        painter.setBrush(self._color)
        painter.drawRoundedRect(
            QRectF(0.08 * w, 0.28 * h, 0.84 * w, 0.54 * h),
            0.10 * w,
            0.10 * w,
        )


class LampControl(QWidget):
    delete_requested = pyqtSignal(str)  # emite el mac de la lámpara a borrar

    def __init__(self, lamp_data, wiz_manager, parent=None):
        super().__init__(parent)
        self.mac = lamp_data["mac"]
        self.ip = lamp_data["ip"]
        self.name = lamp_data["name"]
        self.wiz_manager = wiz_manager

        initial_brightness = lamp_data.get("last_brightness", 100)
        self.is_on = initial_brightness > 0
        self.current_color = QColor(lamp_data.get("last_color_hex", "#ffffff"))
        self.current_temp = lamp_data.get("last_temp_kelvin", 2700)
        self.current_hue = (
            self.current_color.hue() if self.current_color.hue() >= 0 else 0
        )

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

        name_label = QLabel(lamp_data["name"])
        name_label.setObjectName("lampName")
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        self.toggle = ModernToggle()
        self.toggle.setChecked(self.is_on)
        self.toggle.stateChanged.connect(self.send_toggle_command)
        header_layout.addWidget(self.toggle)

        self.delete_button = HoverButton(
            "✕", hover_color=QColor(255, 80, 80, 55), radius=5
        )
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.setFixedSize(20, 20)
        self.delete_button.clicked.connect(self.confirm_delete)
        header_layout.addWidget(self.delete_button)

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

        self.brightness_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(10, 100)
        self.brightness_slider.set_value_silently(initial_brightness)
        self.brightness_slider.valueChangedDelayed.connect(self.send_brightness_command)
        self.brightness_slider.valueChanged.connect(self.update_brightness_label)
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

        self.temp_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.set_value_silently(self.kelvin_to_slider(self.current_temp))
        self.temp_slider.valueChangedDelayed.connect(self.send_temp_command)
        self.temp_slider.valueChanged.connect(self.update_temp_label)
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

        self.color_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.color_slider.setRange(0, 359)
        self.color_slider.set_value_silently(self.current_hue)
        self.color_slider.setObjectName("colorSlider")
        self.color_slider.valueChangedDelayed.connect(self.send_color_command)
        self.color_slider.valueChanged.connect(self.update_color_preview_only)
        color_layout.addWidget(self.color_slider)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(35, 20)
        self.color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.color_preview.setToolTip("Elegir color exacto")

        def color_preview_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.open_color_picker()

        self.color_preview.mousePressEvent = color_preview_click
        self.update_color_preview()
        color_layout.addWidget(self.color_preview)

        main_layout.addLayout(color_layout)

    def update_color_preview(self):
        color = self.current_color
        self.color_preview.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color.name()};
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
            }}
        """
        )

    def kelvin_to_slider(self, kelvin):
        return int(((kelvin - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * 100)

    def slider_to_kelvin(self, slider_val):
        return int(((slider_val / 100) * (TEMP_MAX - TEMP_MIN)) + TEMP_MIN)

    def update_brightness_label(self, value):
        """Actualiza solo el label sin enviar comando"""
        self.brightness_value.setText(f"{value}%")

    def update_temp_label(self, slider_val):
        """Actualiza solo el label sin enviar comando"""
        kelvin = self.slider_to_kelvin(slider_val)
        self.temp_value.setText(f"{kelvin}K")

    def update_color_preview_only(self, hue):
        """Actualiza solo el preview sin enviar comando"""
        self.current_hue = hue
        color = QColor.fromHsv(hue, 255, 255)
        self.color_preview.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color.name()};
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
            }}
        """
        )

    def send_toggle_command(self, state):
        is_on = state == Qt.CheckState.Checked.value
        self.is_on = is_on
        dimming = self.brightness_slider.value() if is_on else 100
        command = {"method": "setPilot", "params": {"state": is_on, "dimming": dimming}}
        self.wiz_manager.send_command(self.ip, command)

    def send_brightness_command(self, value):
        self.wiz_manager.update_lamp_state(self.mac, brightness=value)
        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)
        command = {"method": "setPilot", "params": {"dimming": value, "state": True}}
        self.wiz_manager.send_command(self.ip, command)

    def send_temp_command(self, slider_val):
        kelvin = self.slider_to_kelvin(slider_val)
        self.current_temp = kelvin
        self.wiz_manager.update_lamp_state(self.mac, last_temp_kelvin=kelvin)
        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)
        command = {
            "method": "setPilot",
            "params": {
                "temp": int(kelvin),
                "dimming": self.brightness_slider.value(),
                "state": True,
                "colorMode": "temp",
            },
        }
        self.wiz_manager.send_command(self.ip, command)

    def send_color_command(self, hue):
        self.current_hue = hue
        color = QColor.fromHsv(hue, 255, 255)
        self.current_color = color

        self.wiz_manager.update_lamp_state(self.mac, color_hex=color.name())
        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)

        r, g, b = color.red(), color.green(), color.blue()
        dimming = self.brightness_slider.value()
        command = {
            "method": "setPilot",
            "params": {
                "r": int(r),
                "g": int(g),
                "b": int(b),
                "dimming": int(dimming),
                "state": True,
                "colorMode": "rgb",
            },
        }
        self.wiz_manager.send_command(self.ip, command)

    def open_color_picker(self):
        popup = self.window()
        if hasattr(popup, "pause_auto_hide"):
            popup.pause_auto_hide()

        color = QColorDialog.getColor(self.current_color, self, "Elegir color exacto")

        if hasattr(popup, "resume_auto_hide"):
            popup.resume_auto_hide()

        if color.isValid():
            self.apply_exact_color(color)

    def apply_exact_color(self, color):
        self.current_color = color
        if color.hue() >= 0:
            self.current_hue = color.hue()

        # Sincronizar el slider de matiz sin re-disparar el comando
        self.color_slider.set_value_silently(self.current_hue)
        self.update_color_preview()

        self.wiz_manager.update_lamp_state(self.mac, color_hex=color.name())
        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)

        r, g, b = color.red(), color.green(), color.blue()
        command = {
            "method": "setPilot",
            "params": {
                "r": int(r),
                "g": int(g),
                "b": int(b),
                "dimming": int(self.brightness_slider.value()),
                "state": True,
                "colorMode": "rgb",
            },
        }
        self.wiz_manager.send_command(self.ip, command)

    def confirm_delete(self):
        reply = QMessageBox.question(
            self,
            "Borrar lámpara",
            f"¿Seguro que querés borrar '{self.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.mac)


class GroupControl(QWidget):
    """Control para un grupo de lámparas con expansión/colapso y controles completos"""

    delete_requested = pyqtSignal(str)       # emite el nombre del grupo a borrar
    lamp_delete_requested = pyqtSignal(str)  # reenvía el mac de una lámpara interna

    def __init__(self, group_name, wiz_manager, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.wiz_manager = wiz_manager
        self.is_expanded = False
        self.lamp_widgets = []

        # Estado inicial del grupo
        self.is_on = True
        self.current_brightness = 100
        self.current_temp = 2700
        self.current_hue = 0
        self.current_color = QColor.fromHsv(0, 255, 255)

        self.setObjectName("GroupCard")
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Header con flecha expandible
        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # Toda la zona del nombre expande/colapsa el grupo: la flecha sola es
        # un blanco muy chico y era fácil errarle.
        arrow_container = QWidget()
        arrow_container.setCursor(Qt.CursorShape.PointingHandCursor)
        arrow_layout = QHBoxLayout(arrow_container)
        arrow_layout.setContentsMargins(0, 0, 0, 0)

        self.arrow_label = QLabel("▶")
        self.arrow_label.setFixedWidth(16)
        self.arrow_label.setStyleSheet("font-size: 10px; color: #E0E0E0;")
        arrow_layout.addWidget(self.arrow_label)

        def arrow_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.toggle_expansion()

        arrow_container.mousePressEvent = arrow_click
        header.mousePressEvent = arrow_click

        header_layout.addWidget(arrow_container)

        # Nombre del grupo con icono de carpeta minimalista
        name_row = QWidget()
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(6)
        self.folder_icon = FolderIcon()
        name_layout.addWidget(self.folder_icon)
        name_label = QLabel(self.group_name)
        name_label.setObjectName("groupName")
        name_layout.addWidget(name_label)
        header_layout.addWidget(name_row)

        # Contador de lámparas en formato píldora
        lamp_count = len(self.wiz_manager.get_lamps_in_group(self.group_name))
        count_label = QLabel(str(lamp_count))
        count_label.setObjectName("lampCount")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_label.setToolTip(
            f"{lamp_count} {'luz' if lamp_count == 1 else 'luces'} en el grupo"
        )
        header_layout.addWidget(count_label)

        header_layout.addStretch()

        # Toggle para todo el grupo
        self.toggle = ModernToggle()
        self.toggle.setChecked(self.is_on)
        self.toggle.stateChanged.connect(self.send_toggle_command)
        header_layout.addWidget(self.toggle)

        self.delete_button = HoverButton(
            "✕", hover_color=QColor(255, 80, 80, 55), radius=5
        )
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.setFixedSize(20, 20)
        self.delete_button.clicked.connect(self.confirm_delete)
        header_layout.addWidget(self.delete_button)

        main_layout.addWidget(header)

        # Controles del grupo (como una lámpara)
        # Brillo
        brightness_layout = QHBoxLayout()
        brightness_layout.setSpacing(8)

        bright_label = QLabel("☀")
        bright_label.setFixedWidth(16)
        bright_label.setStyleSheet("font-size: 12px; color: #E0E0E0;")
        brightness_layout.addWidget(bright_label)

        self.brightness_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(10, 100)
        self.brightness_slider.set_value_silently(self.current_brightness)
        self.brightness_slider.valueChangedDelayed.connect(self.send_brightness_command)
        self.brightness_slider.valueChanged.connect(self.update_brightness_label)
        brightness_layout.addWidget(self.brightness_slider)

        self.brightness_value = QLabel(f"{self.current_brightness}%")
        self.brightness_value.setObjectName("valueLabel")
        self.brightness_value.setFixedWidth(35)
        brightness_layout.addWidget(self.brightness_value)

        main_layout.addLayout(brightness_layout)

        # Temperatura
        temp_layout = QHBoxLayout()
        temp_layout.setSpacing(8)

        temp_label = QLabel("◐")
        temp_label.setFixedWidth(16)
        temp_label.setStyleSheet("font-size: 12px; color: #E0E0E0;")
        temp_layout.addWidget(temp_label)

        self.temp_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.set_value_silently(self.kelvin_to_slider(self.current_temp))
        self.temp_slider.valueChangedDelayed.connect(self.send_temp_command)
        self.temp_slider.valueChanged.connect(self.update_temp_label)
        temp_layout.addWidget(self.temp_slider)

        self.temp_value = QLabel(f"{self.current_temp}K")
        self.temp_value.setObjectName("valueLabel")
        self.temp_value.setFixedWidth(35)
        temp_layout.addWidget(self.temp_value)

        main_layout.addLayout(temp_layout)

        # Color
        color_layout = QHBoxLayout()
        color_layout.setSpacing(8)

        color_label = QLabel("●")
        color_label.setFixedWidth(16)
        color_label.setStyleSheet("font-size: 12px; color: #E0E0E0;")
        color_layout.addWidget(color_label)

        self.color_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.color_slider.setRange(0, 359)
        self.color_slider.set_value_silently(self.current_hue)
        self.color_slider.setObjectName("colorSlider")
        self.color_slider.valueChangedDelayed.connect(self.send_color_command)
        self.color_slider.valueChanged.connect(self.update_color_preview_only)
        color_layout.addWidget(self.color_slider)

        self.color_preview = QLabel()
        self.color_preview.setFixedSize(35, 20)
        self.color_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.color_preview.setToolTip("Elegir color exacto")

        def color_preview_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.open_color_picker()

        self.color_preview.mousePressEvent = color_preview_click
        self.update_color_preview()
        color_layout.addWidget(self.color_preview)

        main_layout.addLayout(color_layout)

        # Contenedor de lámparas individuales (inicialmente oculto)
        self.lamps_container = QWidget()
        self.lamps_layout = QVBoxLayout(self.lamps_container)
        self.lamps_layout.setContentsMargins(20, 8, 0, 0)  # Indentación
        self.lamps_layout.setSpacing(6)
        self.lamps_container.hide()

        main_layout.addWidget(self.lamps_container)

        # Crear controles de las lámparas individuales
        self.create_lamp_controls()

    def kelvin_to_slider(self, kelvin):
        return int(((kelvin - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * 100)

    def slider_to_kelvin(self, slider_val):
        return int(((slider_val / 100) * (TEMP_MAX - TEMP_MIN)) + TEMP_MIN)

    def update_brightness_label(self, value):
        """Actualiza solo el label sin enviar comando"""
        self.brightness_value.setText(f"{value}%")

    def update_temp_label(self, slider_val):
        """Actualiza solo el label sin enviar comando"""
        kelvin = self.slider_to_kelvin(slider_val)
        self.temp_value.setText(f"{kelvin}K")

    def update_color_preview_only(self, hue):
        """Actualiza solo el preview sin enviar comando"""
        color = QColor.fromHsv(hue, 255, 255)
        self.color_preview.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color.name()};
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
            }}
        """
        )

    def update_color_preview(self):
        color = self.current_color
        self.color_preview.setStyleSheet(
            f"""
            QLabel {{
                background-color: {color.name()};
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
            }}
        """
        )

    def create_lamp_controls(self):
        """Crea los controles para cada lámpara del grupo"""
        lamps = self.wiz_manager.get_lamps_in_group(self.group_name)
        for lamp in lamps:
            lamp_widget = LampControl(lamp, self.wiz_manager)
            lamp_widget.delete_requested.connect(self.lamp_delete_requested.emit)
            self.lamps_layout.addWidget(lamp_widget)
            self.lamp_widgets.append(lamp_widget)

    def toggle_expansion(self):
        """Alterna entre expandido y colapsado"""
        self.is_expanded = not self.is_expanded

        if self.is_expanded:
            self.arrow_label.setText("▼")
            self.lamps_container.show()
        else:
            self.arrow_label.setText("▶")
            self.lamps_container.hide()

    def send_toggle_command(self, state):
        """Envía comando de encendido/apagado a todas las lámparas del grupo"""
        is_on = state == Qt.CheckState.Checked.value
        self.is_on = is_on
        dimming = self.brightness_slider.value() if is_on else 100
        command = {"method": "setPilot", "params": {"state": is_on, "dimming": dimming}}
        self.wiz_manager.send_command_to_group(self.group_name, command)

        # Actualizar toggles de las lámparas individuales
        for lamp_widget in self.lamp_widgets:
            lamp_widget.is_on = is_on
            lamp_widget.toggle.setChecked(is_on)

    def send_brightness_command(self, value):
        """Envía comando de brillo a todas las lámparas del grupo"""
        self.current_brightness = value
        self.brightness_value.setText(f"{value}%")

        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)

        command = {"method": "setPilot", "params": {"dimming": value, "state": True}}
        self.wiz_manager.send_command_to_group(self.group_name, command)

        # Actualizar sliders de las lámparas individuales
        for lamp_widget in self.lamp_widgets:
            lamp_widget.is_on = True
            lamp_widget.toggle.setChecked(True)
            lamp_widget.brightness_slider.set_value_silently(value)

    def send_temp_command(self, slider_val):
        """Envía comando de temperatura a todas las lámparas del grupo"""
        kelvin = self.slider_to_kelvin(slider_val)
        self.current_temp = kelvin
        self.temp_value.setText(f"{kelvin}K")

        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)

        command = {
            "method": "setPilot",
            "params": {
                "temp": int(kelvin),
                "dimming": self.brightness_slider.value(),
                "state": True,
                "colorMode": "temp",
            },
        }
        self.wiz_manager.send_command_to_group(self.group_name, command)

        # Actualizar sliders de las lámparas individuales
        for lamp_widget in self.lamp_widgets:
            lamp_widget.is_on = True
            lamp_widget.toggle.setChecked(True)
            lamp_widget.temp_slider.set_value_silently(slider_val)
            lamp_widget.current_temp = kelvin

    def send_color_command(self, hue):
        """Envía comando de color a todas las lámparas del grupo"""
        self.current_hue = hue
        color = QColor.fromHsv(hue, 255, 255)
        self.current_color = color
        self.update_color_preview()

        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)

        r, g, b = color.red(), color.green(), color.blue()
        dimming = self.brightness_slider.value()
        command = {
            "method": "setPilot",
            "params": {
                "r": int(r),
                "g": int(g),
                "b": int(b),
                "dimming": int(dimming),
                "state": True,
                "colorMode": "rgb",
            },
        }
        self.wiz_manager.send_command_to_group(self.group_name, command)

        # Actualizar sliders de las lámparas individuales
        for lamp_widget in self.lamp_widgets:
            lamp_widget.is_on = True
            lamp_widget.toggle.setChecked(True)
            lamp_widget.color_slider.set_value_silently(hue)
            lamp_widget.current_hue = hue
            lamp_widget.current_color = color
            lamp_widget.update_color_preview()

    def open_color_picker(self):
        popup = self.window()
        if hasattr(popup, "pause_auto_hide"):
            popup.pause_auto_hide()

        color = QColorDialog.getColor(self.current_color, self, "Elegir color exacto")

        if hasattr(popup, "resume_auto_hide"):
            popup.resume_auto_hide()

        if color.isValid():
            self.apply_exact_color(color)

    def apply_exact_color(self, color):
        self.current_color = color
        if color.hue() >= 0:
            self.current_hue = color.hue()

        self.color_slider.set_value_silently(self.current_hue)
        self.update_color_preview()

        if not self.is_on:
            self.is_on = True
            self.toggle.setChecked(True)

        r, g, b = color.red(), color.green(), color.blue()
        dimming = self.brightness_slider.value()
        command = {
            "method": "setPilot",
            "params": {
                "r": int(r),
                "g": int(g),
                "b": int(b),
                "dimming": int(dimming),
                "state": True,
                "colorMode": "rgb",
            },
        }
        self.wiz_manager.send_command_to_group(self.group_name, command)

        # Aplicar el mismo color exacto a cada lámpara individual del grupo
        for lamp_widget in self.lamp_widgets:
            lamp_widget.is_on = True
            lamp_widget.toggle.setChecked(True)
            lamp_widget.color_slider.set_value_silently(self.current_hue)
            lamp_widget.current_hue = self.current_hue
            lamp_widget.current_color = color
            lamp_widget.update_color_preview()
            lamp_widget.wiz_manager.update_lamp_state(
                lamp_widget.mac, color_hex=color.name()
            )

    def confirm_delete(self):
        reply = QMessageBox.question(
            self,
            "Borrar grupo",
            f"¿Seguro que querés borrar el grupo '{self.group_name}'?\n"
            "Las lámparas no se borran, quedan sueltas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.group_name)


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
            item = QListWidgetItem(lamp["name"])
            item.setData(Qt.ItemDataRole.UserRole, lamp["mac"])
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


class SettingsDialog(QDialog):
    """Ajustes de apariencia con vista previa en vivo.

    Cada cambio emite ``preview`` con una copia de los ajustes; el popup los
    aplica al instante. Al cancelar se vuelve a los valores originales.
    """

    preview = pyqtSignal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._original = copy.deepcopy(settings)
        self._tint_color = QColor(settings["glass"]["tint"])
        self._accent_color = QColor(settings["sliders"]["accent"])

        # Aplicar la vista previa en cada píxel del arrastre re-estiliza el
        # popup y hasta recaptura la pantalla. Con 70 ms de retraso se siente
        # igual de inmediato pero sin tirones.
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(70)
        self._preview_timer.timeout.connect(self._emit_preview)

        self.setWindowTitle("Ajustes de apariencia")
        self.setModal(True)
        self.setMinimumWidth(390)

        self._build_ui(settings)
        self._connect_signals()
        self._apply_dialog_style()
        self._refresh_state()

    # -- construcción ------------------------------------------------------

    def _build_ui(self, settings):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # --- Vidrio -------------------------------------------------------
        glass_group = QGroupBox("Vidrio esmerilado")
        glass_grid = QGridLayout(glass_group)
        glass_grid.setContentsMargins(12, 18, 12, 12)
        glass_grid.setHorizontalSpacing(10)
        glass_grid.setVerticalSpacing(8)
        glass_grid.setColumnStretch(1, 1)

        self.enabled_check = QCheckBox("Activar vidrio esmerilado")
        self.enabled_check.setChecked(settings["glass"]["enabled"])
        glass_grid.addWidget(self.enabled_check, 0, 0, 1, 3)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Automático (rápido, GPU)", "auto")
        self.mode_combo.addItem("Captura personalizada (más CPU)", "capture")
        index = self.mode_combo.findData(settings["glass"]["mode"])
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        glass_grid.addWidget(QLabel("Modo:"), 1, 0)
        glass_grid.addWidget(self.mode_combo, 1, 1, 1, 2)

        self.tint_swatch = QPushButton()
        self.tint_swatch.setObjectName("colorSwatch")
        self.tint_swatch.setFixedSize(64, 22)
        self.tint_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tint_swatch.setToolTip("Elegir color del tinte")
        self.tint_hex = QLabel()
        self.tint_hex.setObjectName("settingValue")
        self._update_swatch(self.tint_swatch, self._tint_color)
        glass_grid.addWidget(QLabel("Color del tinte:"), 2, 0)
        glass_grid.addWidget(
            self._color_control(self.tint_swatch, self.tint_hex), 2, 1, 1, 2
        )

        (
            self.opacity_slider,
            self.opacity_value,
            opacity_control,
        ) = self._make_slider_row(0, 255, settings["glass"]["opacity"])
        glass_grid.addWidget(QLabel("Opacidad:"), 3, 0)
        glass_grid.addWidget(opacity_control, 3, 1, 1, 2)

        (
            self.blur_slider,
            self.blur_value,
            blur_control,
        ) = self._make_slider_row(2, 10, settings["glass"]["blur"])
        glass_grid.addWidget(QLabel("Desenfoque:"), 4, 0)
        glass_grid.addWidget(blur_control, 4, 1, 1, 2)

        self.blur_hint = QLabel(
            "La intensidad del desenfoque solo se ajusta en el modo "
            "Captura personalizada. El modo Automático usa el blur de "
            "Windows, que no cuesta CPU."
        )
        self.blur_hint.setObjectName("hintLabel")
        self.blur_hint.setWordWrap(True)
        glass_grid.addWidget(self.blur_hint, 5, 0, 1, 3)

        root.addWidget(glass_group)

        # --- Controles (mismas opciones para sliders y botones) -----------
        controls_group = QGroupBox("Sliders y botones de encendido")
        controls_grid = QGridLayout(controls_group)
        controls_grid.setContentsMargins(12, 18, 12, 12)
        controls_grid.setHorizontalSpacing(10)
        controls_grid.setVerticalSpacing(8)
        controls_grid.setColumnStretch(1, 1)

        # Un único juego de ajustes: cada opción modifica el slider y el switch
        # al mismo tiempo.
        self.accent_swatch = QPushButton()
        self.accent_swatch.setObjectName("colorSwatch")
        self.accent_swatch.setFixedSize(64, 22)
        self.accent_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accent_swatch.setToolTip(
            "Color de acento: relleno del slider y botón encendido"
        )
        self.accent_hex = QLabel()
        self.accent_hex.setObjectName("settingValue")
        self._update_swatch(self.accent_swatch, self._accent_color)
        controls_grid.addWidget(QLabel("Color de acento:"), 0, 0)
        controls_grid.addWidget(
            self._color_control(self.accent_swatch, self.accent_hex), 0, 1, 1, 2
        )

        self._toggle_colors = {
            key: QColor(settings["toggle"][key]) for key in ("off", "knob")
        }
        self.toggle_swatches = {}
        self.toggle_hex_labels = {}
        for row, (key, text) in enumerate(
            (
                ("off", "Color de apagado:"),
                ("knob", "Color del tirador y perilla:"),
            ),
            start=1,
        ):
            swatch = QPushButton()
            swatch.setObjectName("colorSwatch")
            swatch.setFixedSize(64, 22)
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            swatch.setToolTip(f"Elegir color: {text.rstrip(':').lower()}")
            hex_label = QLabel()
            hex_label.setObjectName("settingValue")
            self._update_swatch(swatch, self._toggle_colors[key])
            swatch.clicked.connect(
                lambda _checked=False, k=key: self._pick_toggle_color(k)
            )
            self.toggle_swatches[key] = swatch
            self.toggle_hex_labels[key] = hex_label
            controls_grid.addWidget(QLabel(text), row, 0)
            controls_grid.addWidget(
                self._color_control(swatch, hex_label), row, 1, 1, 2
            )

        (
            self.thickness_slider,
            self.thickness_value,
            thickness_control,
        ) = self._make_slider_row(
            SLIDER_THICKNESS_MIN,
            SLIDER_THICKNESS_MAX,
            settings["sliders"]["thickness"],
            step=2,
        )
        controls_grid.addWidget(QLabel("Grosor de la barra:"), 3, 0)
        controls_grid.addWidget(thickness_control, 3, 1, 1, 2)

        (
            self.handle_slider,
            self.handle_value,
            handle_control,
        ) = self._make_slider_row(
            SLIDER_HANDLE_MIN,
            SLIDER_HANDLE_MAX,
            settings["sliders"]["handle"],
            step=2,
        )
        controls_grid.addWidget(QLabel("Tamaño del tirador y perilla:"), 4, 0)
        controls_grid.addWidget(handle_control, 4, 1, 1, 2)

        # Vista previa combinada: slider y los dos estados del switch.
        preview_box = QWidget()
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(0, 2, 0, 2)
        preview_layout.setSpacing(8)

        self.preview_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.preview_slider.setObjectName("previewSlider")
        self.preview_slider.setRange(0, 100)
        self.preview_slider.setValue(65)
        preview_layout.addWidget(self.preview_slider)

        preview_toggle_row = QWidget()
        preview_toggle_layout = QHBoxLayout(preview_toggle_row)
        preview_toggle_layout.setContentsMargins(0, 0, 0, 0)
        preview_toggle_layout.setSpacing(14)
        self.toggle_preview_on = ModernToggle()
        self.toggle_preview_on.setChecked(True)
        self.toggle_preview_off = ModernToggle()
        preview_toggle_layout.addWidget(self.toggle_preview_on)
        preview_toggle_layout.addWidget(self.toggle_preview_off)
        preview_toggle_layout.addStretch(1)
        preview_layout.addWidget(preview_toggle_row)

        controls_grid.addWidget(QLabel("Vista previa:"), 5, 0)
        controls_grid.addWidget(preview_box, 5, 1, 1, 2)

        self.toggle_hint = QLabel(
            "Estos ajustes se aplican a la vez a los sliders y a los botones: "
            "el acento es el color de encendido, el apagado también pinta el "
            "riel de la barra y la perilla del botón mide lo mismo que el "
            "tirador del slider. La barra de los dos controles envuelve "
            "siempre al tirador con 2 px de aire, así el tirador del slider "
            "queda adentro igual que la perilla del botón (el grosor mínimo "
            "efectivo es el tirador + 4 px)."
        )
        self.toggle_hint.setObjectName("hintLabel")
        self.toggle_hint.setWordWrap(True)
        controls_grid.addWidget(self.toggle_hint, 6, 0, 1, 3)

        root.addWidget(controls_group)

        # --- Botones ------------------------------------------------------
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.reset_button = QPushButton("Restablecer")
        self.cancel_button = QPushButton("Cancelar")
        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setDefault(True)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        root.addLayout(buttons)

    @staticmethod
    def _color_control(swatch, value_label):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(swatch)
        row.addWidget(value_label)
        row.addStretch(1)
        return container

    @staticmethod
    def _make_slider_row(minimum, maximum, value, step=1):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setSingleStep(step)
        slider.setPageStep(step * 2)
        # Los valores guardados ya vienen pares; el paso par mantiene el
        # tirador redondo también al mover con el teclado.
        slider.setValue(value)

        label = QLabel()
        label.setObjectName("settingValue")
        label.setMinimumWidth(48)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(slider, 1)
        row.addWidget(label)
        return slider, label, container

    # -- estado ------------------------------------------------------------

    def _connect_signals(self):
        self.enabled_check.toggled.connect(self._refresh_state)
        self.mode_combo.currentIndexChanged.connect(self._refresh_state)
        self.opacity_slider.valueChanged.connect(self._refresh_state)
        self.blur_slider.valueChanged.connect(self._refresh_state)
        self.thickness_slider.valueChanged.connect(self._refresh_state)
        self.handle_slider.valueChanged.connect(self._refresh_state)
        self.tint_swatch.clicked.connect(self._pick_tint)
        self.accent_swatch.clicked.connect(self._pick_accent)
        self.reset_button.clicked.connect(self._reset)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def _refresh_state(self, *args):
        enabled = self.enabled_check.isChecked()
        custom = enabled and self.mode_combo.currentData() == "capture"

        for widget in (
            self.mode_combo,
            self.tint_swatch,
            self.opacity_slider,
            self.blur_slider,
        ):
            widget.setEnabled(enabled)
        # La intensidad solo tiene efecto en el método por captura.
        self.blur_slider.setEnabled(custom)
        self.blur_hint.setVisible(not custom)

        self.tint_hex.setText(self._tint_color.name().upper())
        self.accent_hex.setText(self._accent_color.name().upper())
        for key, label in self.toggle_hex_labels.items():
            label.setText(self._toggle_colors[key].name().upper())
        # Un solo juego de valores para todos los controles: acento, apagado,
        # perilla, grosor y tamaño se aplican a sliders y switches por igual.
        ModernToggle.apply_appearance(
            {
                "sliders": {
                    "thickness": self.thickness_slider.value(),
                    "handle": self.handle_slider.value(),
                },
                "toggle": {
                    "on": self._accent_color.name(),
                    "off": self._toggle_colors["off"].name(),
                    "knob": self._toggle_colors["knob"].name(),
                },
            }
        )
        opacity = self.opacity_slider.value()
        self.opacity_value.setText(f"{round(opacity / 255 * 100)}%")
        self.blur_value.setText(str(self.blur_slider.value()))
        self.thickness_value.setText(f"{self.thickness_slider.value()} px")
        self.handle_value.setText(f"{self.handle_slider.value()} px")

        self._update_preview_slider_appearance()
        self._preview_timer.start()

    def _emit_preview(self):
        self.preview.emit(self.get_settings())

    def _update_preview_slider_appearance(self):
        # La misma clase y el mismo dibujo que los sliders reales: la vista
        # previa muestra exactamente cómo va a quedar, incluidos los colores
        # compartidos con el switch.
        self.preview_slider.apply_appearance(
            {
                "sliders": {
                    "accent": self._accent_color.name(),
                    "thickness": self.thickness_slider.value(),
                    "handle": self.handle_slider.value(),
                },
                "toggle": {
                    "off": self._toggle_colors["off"].name(),
                    "knob": self._toggle_colors["knob"].name(),
                },
            }
        )

    def _update_swatch(self, button, color):
        button.setStyleSheet(
            "QPushButton {"
            f"background-color: {color.name()};"
            "border: 1px solid rgba(255, 255, 255, 0.30);"
            "border-radius: 4px;"
            "}"
        )

    def _pick_tint(self):
        color = QColorDialog.getColor(
            self._tint_color, self, "Color del tinte del vidrio"
        )
        if color.isValid():
            self._tint_color = color
            self._update_swatch(self.tint_swatch, color)
            self._refresh_state()

    def _pick_accent(self):
        color = QColorDialog.getColor(
            self._accent_color, self, "Color de acento (sliders y botones)"
        )
        if color.isValid():
            self._accent_color = color
            self._update_swatch(self.accent_swatch, color)
            self._apply_dialog_style()
            self._refresh_state()

    def _pick_toggle_color(self, key):
        titles = {
            "off": "Color de apagado (botón y riel del slider)",
            "knob": "Color del tirador y la perilla",
        }
        color = QColorDialog.getColor(
            self._toggle_colors[key], self, titles.get(key, "Color del botón")
        )
        if color.isValid():
            self._toggle_colors[key] = color
            self._update_swatch(self.toggle_swatches[key], color)
            self._refresh_state()

    def _reset(self):
        defaults = copy.deepcopy(DEFAULT_SETTINGS)
        widgets = (
            self.enabled_check,
            self.mode_combo,
            self.opacity_slider,
            self.blur_slider,
            self.thickness_slider,
            self.handle_slider,
        )
        for widget in widgets:
            widget.blockSignals(True)

        self._tint_color = QColor(defaults["glass"]["tint"])
        self._accent_color = QColor(defaults["sliders"]["accent"])
        self._toggle_colors = {
            key: QColor(defaults["toggle"][key]) for key in ("off", "knob")
        }
        self._update_swatch(self.tint_swatch, self._tint_color)
        self._update_swatch(self.accent_swatch, self._accent_color)
        for key, swatch in self.toggle_swatches.items():
            self._update_swatch(swatch, self._toggle_colors[key])
        self._apply_dialog_style()

        self.enabled_check.setChecked(defaults["glass"]["enabled"])
        index = self.mode_combo.findData(defaults["glass"]["mode"])
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self.opacity_slider.setValue(defaults["glass"]["opacity"])
        self.blur_slider.setValue(defaults["glass"]["blur"])
        self.thickness_slider.setValue(defaults["sliders"]["thickness"])
        self.handle_slider.setValue(defaults["sliders"]["handle"])

        for widget in widgets:
            widget.blockSignals(False)
        self._refresh_state()

    def get_settings(self):
        """Devuelve una copia independiente de los ajustes elegidos."""
        return copy.deepcopy(
            {
                "glass": {
                    "enabled": self.enabled_check.isChecked(),
                    "mode": self.mode_combo.currentData(),
                    "tint": self._tint_color.name(),
                    "opacity": self.opacity_slider.value(),
                    "blur": self.blur_slider.value(),
                },
                "sliders": {
                    "accent": self._accent_color.name(),
                    "thickness": self.thickness_slider.value(),
                    "handle": self.handle_slider.value(),
                },
                "toggle": {
                    **{
                        key: color.name()
                        for key, color in self._toggle_colors.items()
                    },
                    # Se guarda también "on" para que el JSON siga siendo
                    # autoexplicativo, pero siempre igual al acento.
                    "on": self._accent_color.name(),
                },
            }
        )

    def accept(self):
        # No dejar pendiente una vista previa que podría aplicarse después de
        # cerrar el diálogo.
        self._preview_timer.stop()
        super().accept()

    def reject(self):
        # Al cancelar, la vista previa vuelve a como estaba antes de abrir.
        self._preview_timer.stop()
        self.preview.emit(copy.deepcopy(self._original))
        super().reject()

    # -- estilo ------------------------------------------------------------

    def _apply_dialog_style(self):
        style = (
            """
            QDialog {
                background-color: #232323;
            }
            QLabel {
                color: #E8E8E8;
                font-size: 12px;
            }
            QLabel#settingValue {
                color: #B8B8B8;
                font-size: 11px;
            }
            QLabel#hintLabel {
                color: #9A9A9A;
                font-size: 11px;
            }
            QGroupBox {
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 6px;
                font-size: 12px;
                font-weight: 600;
                color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QCheckBox {
                color: #E8E8E8;
                font-size: 12px;
                spacing: 7px;
            }
            QComboBox {
                background-color: #2E2E2E;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 4px;
                padding: 4px 8px;
                color: #FFFFFF;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox QAbstractItemView {
                background-color: #2E2E2E;
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.16);
                selection-background-color: #005FB8;
            }
            QSlider {
                min-height: 16px;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: %ACCENT%;
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
            QPushButton {
                background-color: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 4px;
                padding: 6px 14px;
                color: #FFFFFF;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.17);
            }
            QPushButton#primaryButton {
                background-color: #005FB8;
                border: none;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background-color: #0A6FD0;
            }
            QPushButton:disabled {
                color: rgba(255, 255, 255, 0.35);
            }
            """
        )
        self.setStyleSheet(style.replace("%ACCENT%", self._accent_color.name()))


class PopupWindow(QWidget):
    def __init__(self, wiz_manager):
        super().__init__()
        self.wiz_manager = wiz_manager

        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.finished.connect(super().hide)

        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(400)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.start_hide_animation)

        self.check_timer = QTimer(self)
        self.check_timer.setInterval(100)
        self.check_timer.timeout.connect(self.check_hover_area)

        self._auto_hide_paused = False
        self._glass_mode = "none"
        self._backdrop = None
        self._backdrop_offset = QPoint(0, 0)
        self.settings = load_settings()
        ModernToggle.apply_appearance(self.settings)
        self._tint_color = QColor(self.settings["glass"]["tint"])
        self._tint_color.setAlpha(self.settings["glass"]["opacity"])

        self.blur_timer = QTimer(self)
        self.blur_timer.setInterval(150)
        self.blur_timer.timeout.connect(self.refresh_backdrop)

        # Recargar la lista una sola vez por ráfaga de lámparas encontradas:
        # antes se reconstruía toda la interfaz por cada lámpara.
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(150)
        self._reload_timer.timeout.connect(self.load_content)
        self._found_count = 0

        self.setWindowTitle("WiZ Control")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(0, 0, 340, 450)

        self.setup_ui()
        self.load_content()

    def start_hide_animation(self):
        self.animation.stop()
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(0.0)
        self.animation.start()

    def show(self):
        self.setWindowOpacity(1.0)
        if hasattr(self, "check_timer") and self.check_timer.isActive():
            self.check_timer.stop()
        super().show()

    def hide(self):
        pass

    def showEvent(self, event):
        super().showEvent(event)
        # El HWND ya existe en este punto: activamos el efecto de vidrio.
        self.enable_frosted_glass()

    def hideEvent(self, event):
        self.blur_timer.stop()
        super().hideEvent(event)

    def apply_settings(self, settings):
        """Aplica ajustes de apariencia (también en vivo desde el diálogo)."""
        previous = self.settings
        self.settings = copy.deepcopy(settings)
        tint = QColor(self.settings["glass"]["tint"])
        tint.setAlpha(self.settings["glass"]["opacity"])
        self._tint_color = tint
        # Los colores y las medidas se comparten con todos los controles.
        ModernToggle.apply_appearance(self.settings)
        # Cambiar cualquier ajuste de controles (color, grosor o tirador)
        # repinta los sliders: usan los mismos valores que el switch.
        if (
            previous["sliders"] != self.settings["sliders"]
            or previous["toggle"] != self.settings["toggle"]
        ):
            self.apply_slider_appearance()
        # El tinte y la opacidad se repintan en paintEvent: NO hace falta
        # recapturar la pantalla ni re-aplicar el blur de Windows mientras se
        # arrastra el slider de opacidad.
        if (
            previous["glass"]["enabled"] != self.settings["glass"]["enabled"]
            or previous["glass"]["mode"] != self.settings["glass"]["mode"]
        ):
            self.enable_frosted_glass()
        else:
            self.update()

    def open_settings(self):
        """Abre el diálogo de ajustes con vista previa en vivo."""
        self.pause_auto_hide()
        original = copy.deepcopy(self.settings)
        dialog = SettingsDialog(self.settings, self)
        dialog.preview.connect(self.apply_settings)
        self._place_settings_dialog(dialog)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self.settings = dialog.get_settings()
            save_settings(self.settings)
        else:
            # Cancelar: se descarta cualquier vista previa aplicada.
            self.settings = original
        self.resume_auto_hide()
        self.apply_settings(self.settings)

    def _place_settings_dialog(self, dialog):
        """Ubica el diálogo al lado del popup para que se vea la vista previa."""
        dialog.adjustSize()
        popup = self.frameGeometry()
        area = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        x = popup.right() + 12
        if x + dialog.width() > area.right():
            x = popup.left() - dialog.width() - 12
        if x < area.left():
            x = popup.center().x() - dialog.width() // 2
        y = min(max(area.top() + 8, popup.top()), area.bottom() - dialog.height() - 8)
        dialog.move(x, y)

    def enable_frosted_glass(self):
        """Elige el método de blur según los ajustes y arranca actualizaciones."""
        glass = self.settings["glass"]
        if not glass["enabled"]:
            disable_native_blur(self)
            self._glass_mode = "none"
            self.blur_timer.stop()
            self.update()
            return

        # Preferido: DWM difumina en la GPU. Cero CPU, sin parpadeos.
        if glass["mode"] == "auto" and enable_native_blur(self):
            self._glass_mode = "native"
            self.blur_timer.stop()
            self.update()
            return

        # A partir de aquí no se usa el blur nativo: si estaba activo, se quita
        # para que no se sume al fondo por captura ni al panel opaco.
        disable_native_blur(self)
        hwnd = int(self.winId())
        # Alternativa en Windows 10 2004+: ocultar la ventana de las capturas
        # para poder fotografiar el escritorio de atrás sin incluirnos.
        capture_supported = (
            sys.platform == "win32"
            and sys.getwindowsversion().build >= 19041
            and _set_display_affinity(hwnd, _WDA_EXCLUDEFROMCAPTURE)
        )
        if capture_supported:
            _set_display_affinity(hwnd, _WDA_NONE)
            self._glass_mode = "capture"
            # Con un diálogo encima no conviene capturar: se congelaría su
            # imagen dentro del vidrio. Se reanuda al cerrarlo.
            if not self._auto_hide_paused:
                self.refresh_backdrop()
                self.blur_timer.start()
        elif enable_native_blur(self):
            # El modo "personalizado" pidió captura, pero si no está
            # disponible es mejor el blur nativo que nada.
            self._glass_mode = "native"
            self.blur_timer.stop()
        else:
            self._glass_mode = "none"
            self.blur_timer.stop()
        self.update()

    def refresh_backdrop(self):
        """Captura el escritorio detrás de la ventana y lo difumina."""
        if self._glass_mode != "capture" or not self.isVisible():
            return

        geometry = self.frameGeometry()
        screen = self.screen() or QApplication.primaryScreen()
        visible = geometry.intersected(screen.geometry())
        if visible.isEmpty():
            return

        hwnd = int(self.winId())
        screen_origin = screen.geometry().topLeft()
        _set_display_affinity(hwnd, _WDA_EXCLUDEFROMCAPTURE)
        try:
            grabbed = screen.grabWindow(
                0,
                visible.x() - screen_origin.x(),
                visible.y() - screen_origin.y(),
                visible.width(),
                visible.height(),
            )
        finally:
            _set_display_affinity(hwnd, _WDA_NONE)

        if grabbed.isNull() or grabbed.width() == 0:
            return

        # Se reduce, se difumina y se vuelve a escalar: mismo resultado visual
        # con mucho menos costo de CPU.
        factor = self.settings["glass"]["blur"]
        small = grabbed.scaled(
            max(1, grabbed.width() // factor),
            max(1, grabbed.height() // factor),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        small.setDevicePixelRatio(1.0)
        blurred = blur_pixmap(small, factor + 1)
        backdrop = blurred.scaled(
            grabbed.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        backdrop.setDevicePixelRatio(grabbed.devicePixelRatio())

        self._backdrop = backdrop
        self._backdrop_offset = visible.topLeft() - geometry.topLeft()
        self.update()

    def get_detection_rect(self) -> QRect:
        win_rect = self.frameGeometry()
        margin_x = int(win_rect.width() * 0.10)
        margin_y = int(win_rect.height() * 0.10)
        return win_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)

    def slider_interaction_started(self):
        """Mientras se arrastra un slider, el panel no se cierra solo.

        Antes, si el arrastre se iba un poco fuera del panel, el temporizador
        de auto-cierre lo ocultaba en medio de la interacción."""
        self.hide_timer.stop()
        if self.check_timer.isActive():
            self.check_timer.stop()

    def slider_interaction_finished(self):
        if self._auto_hide_paused or not self.isVisible():
            return
        if not self.get_detection_rect().contains(QCursor.pos()):
            self.hide_timer.start()

    def pause_auto_hide(self):
        """Frena cualquier cierre automático mientras haya un diálogo hijo abierto"""
        self._auto_hide_paused = True
        self.hide_timer.stop()
        self.check_timer.stop()
        self.animation.stop()
        self.setWindowOpacity(1.0)
        # Congela el fondo mientras haya un diálogo encima: así no se captura
        # su imagen dentro del blur y se ahorra CPU.
        self.blur_timer.stop()

    def resume_auto_hide(self):
        """Reactiva el auto-cierre al cerrarse el diálogo hijo"""
        self._auto_hide_paused = False
        if self._glass_mode == "capture" and self.isVisible():
            self.refresh_backdrop()
            self.blur_timer.start()
        if not self.get_detection_rect().contains(QCursor.pos()):
            self.hide_timer.start()

    def check_hover_area(self):
        if self._auto_hide_paused:
            return
        detection_rect = self.get_detection_rect()
        cursor_pos = QCursor.pos()

        if not detection_rect.contains(cursor_pos):
            self.check_timer.stop()
            self.hide_timer.start()

    def enterEvent(self, event):
        self.hide_timer.stop()
        if hasattr(self, "check_timer") and self.check_timer.isActive():
            self.check_timer.stop()
        self.animation.stop()
        self.setWindowOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._auto_hide_paused:
            super().leaveEvent(event)
            return
        detection_rect = self.get_detection_rect()
        cursor_pos = QCursor.pos()

        if detection_rect.contains(cursor_pos):
            self.hide_timer.stop()
            self.check_timer.start()
        else:
            self.hide_timer.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)

        painter.setClipPath(path)

        if self._glass_mode == "capture":
            # El fondo es una foto difuminada del escritorio de atrás. Hasta la
            # primera captura solo se ve el tinte, nunca un panel opaco.
            if self._backdrop is not None:
                painter.drawPixmap(self._backdrop_offset, self._backdrop)
            painter.fillRect(self.rect(), self._tint_color)
        elif self._glass_mode == "native":
            # DWM ya difumina el escritorio detrás: solo hace falta el tinte.
            painter.fillRect(self.rect(), self._tint_color)
        else:
            painter.fillRect(self.rect(), QColor(32, 32, 32, 240))

        if self._glass_mode != "none":
            # Brillo sutil en la parte superior, típico del vidrio esmerilado.
            sheen = QLinearGradient(0, 0, 0, self.height())
            sheen.setColorAt(0.0, QColor(255, 255, 255, 20))
            sheen.setColorAt(0.45, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), QBrush(sheen))

        painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Botones superiores
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.discover_button = HoverButton("Descubrir")
        self.discover_button.setObjectName("discoverButton")
        self.discover_button.setFixedHeight(32)
        self.discover_button.clicked.connect(self.start_discovery)

        group_button = HoverButton("Crear Grupo")
        group_button.setObjectName("groupButton")
        group_button.setFixedHeight(32)
        group_button.clicked.connect(self.create_group)

        btn_row.addWidget(self.discover_button)
        btn_row.addWidget(group_button)

        self.settings_button = HoverButton("⚙", radius=6)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(28, 28)
        self.settings_button.setToolTip("Ajustes de apariencia")
        self.settings_button.clicked.connect(self.open_settings)
        btn_row.addWidget(self.settings_button)

        main_layout.addLayout(btn_row)

        # Área de scroll
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        main_layout.addWidget(self.scroll_area)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(6)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addStretch()
        self.scroll_area.setWidget(self.content_widget)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet(
            """
            QWidget {
                background-color: transparent;
                color: #FFFFFF;
            }
            QPushButton#discoverButton, QPushButton#groupButton {
                background-color: transparent;
                border: none;
                padding: 6px 12px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#settingsButton {
                background-color: transparent;
                border: none;
                color: #D0D0D0;
                font-size: 16px;
                font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif;
            }
            QPushButton#deleteButton {
                background-color: transparent;
                border: none;
                color: #A0A0A0;
                font-size: 12px;
            }
            QWidget#LampCard {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
            }
            QWidget#GroupCard {
                background-color: rgba(100, 150, 255, 0.12);
                border: 1px solid rgba(100, 150, 255, 0.2);
                border-radius: 4px;
            }
            QLabel#lampName {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#groupName {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#lampCount {
                color: #C9DCF7;
                background-color: rgba(120, 170, 255, 0.16);
                border: 1px solid rgba(120, 170, 255, 0.22);
                border-radius: 7px;
                padding: 0px 6px;
                min-height: 15px;
                max-height: 15px;
                font-size: 10px;
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
            QLabel#emptyState {
                color: #9A9A9A;
                font-size: 12px;
                padding: 28px 10px;
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
            """
        )
        self.apply_slider_appearance()

    def apply_slider_appearance(self):
        """Aplica la apariencia a cada slider (dibujo propio, barato).

        Así la vista previa de los ajustes solo actualiza los sliders en lugar
        de repasar todo el árbol de controles del popup."""
        for slider in self.findChildren(ImprovedSlider):
            slider.apply_appearance(
                self.settings, gradient=slider.objectName() == "colorSlider"
            )

    def load_content(self):
        """Carga grupos y lámparas no agrupadas"""
        # Limpiar contenido
        for i in reversed(range(self.content_layout.count() - 1)):
            widget = self.content_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Primero cargar los grupos
        for group_name in self.wiz_manager.get_groups().keys():
            group_widget = GroupControl(group_name, self.wiz_manager)
            group_widget.delete_requested.connect(self.handle_delete_group)
            group_widget.lamp_delete_requested.connect(self.handle_delete_lamp)
            self.content_layout.insertWidget(
                self.content_layout.count() - 1, group_widget
            )

        # Luego cargar lámparas que NO están en ningún grupo
        for lamp in self.wiz_manager.get_ungrouped_lamps():
            if "mac" in lamp and "ip" in lamp:
                lamp_widget = LampControl(lamp, self.wiz_manager)
                lamp_widget.delete_requested.connect(self.handle_delete_lamp)
                self.content_layout.insertWidget(
                    self.content_layout.count() - 1, lamp_widget
                )

        # Estado vacío: sin lámparas ni grupos el panel quedaba en blanco sin
        # explicar qué hacer.
        if not self.wiz_manager.get_lamps() and not self.wiz_manager.get_groups():
            empty = QLabel(
                "No hay luces todavía.\n"
                "Usá «Descubrir» para buscar las de tu red WiZ."
            )
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.content_layout.insertWidget(
                self.content_layout.count() - 1, empty
            )

        # Los sliders recién creados todavía no tienen apariencia.
        self.apply_slider_appearance()

    def handle_delete_lamp(self, mac):
        self.wiz_manager.delete_lamp(mac)
        self.load_content()

    def handle_delete_group(self, group_name):
        self.wiz_manager.delete_group(group_name)
        self.load_content()

    def create_group(self):
        dialog = GroupDialog(self.wiz_manager, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_content()

    def start_discovery(self):
        self.discover_button.setEnabled(False)
        self.discover_button.setText("Buscando...")
        self._found_count = 0
        self.discovery_thread = DiscoveryThread()
        self.discovery_thread.lamp_found.connect(self.handle_lamp_found)
        self.discovery_thread.finished.connect(self.discovery_finished)
        self.discovery_thread.start()

    def handle_lamp_found(self, lamp_data):
        mac = lamp_data.get("mac")
        if mac and self.wiz_manager.add_lamp(
            mac, lamp_data.get("ip"), lamp_data.get("name")
        ):
            self._found_count += 1
            # Si aparecen varias lámparas seguidas, se refresca una sola vez.
            self._reload_timer.start()

    def discovery_finished(self):
        self._reload_timer.stop()
        self.load_content()
        self.discover_button.setEnabled(True)
        self.discover_button.setText("Descubrir")
        count = self._found_count
        if count:
            QMessageBox.information(
                self,
                "Descubrimiento",
                f"Búsqueda finalizada.\n"
                f"{count} {'lámpara nueva' if count == 1 else 'lámparas nuevas'}.",
            )
        else:
            QMessageBox.information(
                self,
                "Descubrimiento",
                "Búsqueda finalizada. No se encontraron lámparas nuevas.",
            )
        self._found_count = 0

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
        # Guardar lo pendiente (brillo, color, temperatura) al salir.
        self.app.aboutToQuit.connect(self.wiz_manager.shutdown)

        # Tipografía: Windows 11 trae Segoe UI Variable, con mejor espaciado
        # y legibilidad que Segoe UI. Si no está, se usa la clásica.
        families = set(QFontDatabase.families())
        for family in ("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI"):
            if family in families:
                break
        else:
            family = self.app.font().family()
        font = QFont(family)
        font.setPointSizeF(10.0)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.app.setFont(font)

        icon_path = resource_path("icon.ico")
        icon_pixmap = QPixmap(icon_path)
        if icon_pixmap.isNull():
            print(f"Error: No se pudo cargar el icono desde '{icon_path}'")
            return
        icon = QIcon(icon_pixmap)
        self.icon = QSystemTrayIcon(icon)

        # Crear menú contextual
        menu = QMenu()
        show_action = QAction("Mostrar Control", menu)
        exit_action = QAction("Salir", menu)
        menu.addAction(show_action)
        menu.addAction(exit_action)
        self.icon.setContextMenu(menu)

        # Mostrar ícono
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
        cursor_pos = QCursor.pos()
        self.window.show_at_position(cursor_pos)

    def run(self):
        return self.app.exec()


if __name__ == "__main__":
    app = TrayAppQt()
    sys.exit(app.run())