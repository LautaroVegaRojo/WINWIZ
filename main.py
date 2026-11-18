import sys
import json
import socket
import os
import copy
import ctypes
import ipaddress
import threading
import math
import re
import subprocess
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
    QPalette,
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
    QUrl,
    pyqtProperty,
)
from PyQt6.QtNetwork import (
    QAbstractSocket,
    QNetworkInterface,
    QNetworkAccessManager,
    QNetworkRequest,
    QNetworkReply,
)
import time

TEMP_MIN = 2200
TEMP_MAX = 6500


def _debug(message):
    """Diagnóstico por stderr sin romper el build sin consola."""
    try:
        print(message, file=sys.stderr)
    except Exception:
        pass


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
# Actualizaciones: la version instalada se identifica por el SHA del commit
# del branch desde el que se instalo (escrito por install.ps1).
# ---------------------------------------------------------------------------

UPDATE_REPO = "LautaroVegaRojo/WINWIZ"
UPDATE_CHECK_URL = "https://api.github.com/repos/{repo}/commits/{branch}"
UPDATE_INSTALLER_URL = (
    "https://raw.githubusercontent.com/{repo}/{branch}/install.ps1"
)
UPDATE_STATE_FILE = os.path.join(get_data_dir(), "update_state.json")


def _install_info():
    """Lee `install-info.txt` de la carpeta de la app (si viene del instalador)."""
    folder = os.path.dirname(os.path.abspath(__file__))
    values = {}
    try:
        # utf-8-sig tolera el BOM que escribian versiones anteriores del
        # instalador; si no, la clave "branch" se leia como "\\ufeffbranch".
        with open(
            os.path.join(folder, "install-info.txt"), "r", encoding="utf-8-sig"
        ) as f:
            for line in f:
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def get_update_branch():
    """Branch usado para chequear y descargar el instalador."""
    branch = _install_info().get("branch", "main")
    return re.sub(r"[^A-Za-z0-9._/-]", "", branch) or "main"


def get_local_commit():
    """Commit instalado: primero install-info.txt, luego el estado local."""
    commit = _install_info().get("commit", "")
    if commit:
        return commit
    try:
        with open(UPDATE_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("commit", "") if isinstance(data, dict) else ""
    except (OSError, ValueError):
        return ""


def set_update_baseline(commit):
    """Guarda el primer commit visto como base (instalaciones sin `commit=`)."""
    try:
        with open(UPDATE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"commit": commit}, f, indent=4)
    except OSError:
        pass


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
    "update": {
        # Color del ícono en reposo. Con versión nueva se usa el acento.
        "color": "#d0d0d0",
        # Tamaño del dibujo en px (el botón sigue midiendo 28x28 como el engranaje).
        "size": 11,
    },
    "temperature": {
        # Degradado frío/caliente en la barra del slider de temperatura.
        "gradient": True,
    },
}

UPDATE_ICON_SIZE_MIN = 10
UPDATE_ICON_SIZE_MAX = 20


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

    update = stored.get("update")
    if isinstance(update, dict):
        settings["update"]["color"] = _valid_color_setting(
            update.get("color"), DEFAULT_SETTINGS["update"]["color"]
        )
        settings["update"]["size"] = int(
            _clamp_setting(
                update.get("size"),
                UPDATE_ICON_SIZE_MIN,
                UPDATE_ICON_SIZE_MAX,
                DEFAULT_SETTINGS["update"]["size"],
            )
        )

    temperature = stored.get("temperature")
    if isinstance(temperature, dict):
        gradient = temperature.get(
            "gradient", DEFAULT_SETTINGS["temperature"]["gradient"]
        )
        settings["temperature"]["gradient"] = (
            gradient if isinstance(gradient, bool) else True
        )
    return settings


def save_settings(settings):
    """Guarda los ajustes; si falla (permisos, disco lleno) no rompe la app."""
    try:
        with open(get_settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Tema compartido por todas las ventanas y diálogos
# ---------------------------------------------------------------------------
# El panel principal es una ventana sin marco con vidrio esmerilado; los
# diálogos nativos (ajustes, crear grupo, selectores de color, mensajes)
# quedaban con el tema claro de Windows y desentonaban por completo. Abajo
# hay una única hoja de estilos y una clase base que aplican el mismo fondo
# oscuro, el mismo acento y el mismo redondeo a todas las ventanas.

ACCENT_FALLBACK = DEFAULT_SETTINGS["sliders"]["accent"]


def accent_color(settings=None):
    """Devuelve el color de acento actual como ``QColor``.

    Acepta los ajustes completos, un nombre de color o directamente un
    ``QColor``. Si no se pasa nada se leen los ajustes guardados en disco.
    Cualquier valor inválido cae en el acento por defecto.
    """
    if settings is None:
        settings = load_settings()
    if isinstance(settings, QColor):
        return QColor(settings) if settings.isValid() else QColor(ACCENT_FALLBACK)
    if isinstance(settings, str):
        color = QColor(settings)
        return color if color.isValid() else QColor(ACCENT_FALLBACK)
    try:
        color = QColor(settings["sliders"]["accent"])
    except (KeyError, TypeError):
        color = QColor(ACCENT_FALLBACK)
    return color if color.isValid() else QColor(ACCENT_FALLBACK)


def current_accent(parent=None):
    """Acento de la ventana que abre un diálogo (o el guardado en disco)."""
    window = parent.window() if isinstance(parent, QWidget) else parent
    settings = getattr(window, "settings", None) if window is not None else None
    return accent_color(settings)


def dialog_stylesheet(accent=None):
    """Hoja de estilos común para diálogos, menús y cuadros de mensaje.

    Se mantiene en un solo lugar para que cualquier ventana nueva herede el
    mismo tema sin repetir colores ni medidas.
    """
    accent_name = accent_color(accent).name()
    accent = QColor(accent_name)
    style = """
        QDialog, QMessageBox {
            background-color: #232323;
        }
        QLabel {
            color: #E8E8E8;
            font-size: 12px;
        }
        QLabel#dialogTitle {
            color: #FFFFFF;
            font-size: 15px;
            font-weight: 600;
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
        QCheckBox::indicator {
            width: 15px;
            height: 15px;
            border: 1px solid rgba(255, 255, 255, 0.32);
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.06);
        }
        QCheckBox::indicator:hover {
            border-color: rgba(255, 255, 255, 0.55);
        }
        QCheckBox::indicator:checked {
            background-color: %ACCENT%;
            border-color: %ACCENT%;
        }
        QComboBox {
            background-color: #2E2E2E;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 4px;
            padding: 4px 8px;
            color: #FFFFFF;
        }
        QComboBox:hover, QComboBox:focus {
            border-color: %ACCENT%;
        }
        QComboBox::drop-down {
            border: none;
            width: 18px;
        }
        QComboBox QAbstractItemView {
            background-color: #2E2E2E;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.16);
            selection-background-color: %ACCENT%;
            outline: none;
        }
        QLineEdit {
            background-color: #2E2E2E;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 4px;
            padding: 6px 8px;
            color: #FFFFFF;
            selection-background-color: %ACCENT%;
        }
        QLineEdit:focus {
            border-color: %ACCENT%;
        }
        QListWidget {
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 6px;
            padding: 4px;
            color: #E8E8E8;
            outline: none;
        }
        QListWidget::item {
            padding: 5px 6px;
            border-radius: 4px;
        }
        QListWidget::item:hover {
            background-color: rgba(255, 255, 255, 0.08);
        }
        QListWidget::item:selected {
            background-color: %ACCENT%;
            color: #FFFFFF;
        }
        QListWidget::indicator, QListView::indicator {
            width: 14px;
            height: 14px;
            border: 1px solid rgba(255, 255, 255, 0.32);
            border-radius: 3px;
            background-color: rgba(255, 255, 255, 0.06);
        }
        QListWidget::indicator:checked, QListView::indicator:checked {
            background-color: %ACCENT%;
            border-color: %ACCENT%;
        }
        QSpinBox {
            background-color: #2E2E2E;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 4px;
            padding: 3px 6px;
            color: #FFFFFF;
            selection-background-color: %ACCENT%;
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
        QPushButton:pressed {
            background-color: rgba(255, 255, 255, 0.24);
        }
        QPushButton#primaryButton {
            background-color: %ACCENT%;
            border: none;
            font-weight: 600;
        }
        QPushButton#primaryButton:hover {
            background-color: %ACCENT_HOVER%;
        }
        QPushButton#primaryButton:pressed {
            background-color: %ACCENT_PRESSED%;
        }
        QPushButton:disabled {
            color: rgba(255, 255, 255, 0.35);
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.22);
            min-height: 24px;
            border-radius: 4px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: transparent;
        }
        QMenu {
            background-color: #2A2A2A;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 6px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 22px 6px 14px;
            border-radius: 4px;
            color: #E8E8E8;
        }
        QMenu::item:selected {
            background-color: %ACCENT%;
            color: #FFFFFF;
        }
        QMenu::separator {
            height: 1px;
            background: rgba(255, 255, 255, 0.12);
            margin: 4px 8px;
        }
        QToolTip {
            background-color: #2A2A2A;
            color: #E8E8E8;
            border: 1px solid rgba(255, 255, 255, 0.18);
            padding: 4px 6px;
        }
    """
    return (
        style.replace("%ACCENT%", accent_name)
        .replace("%ACCENT_HOVER%", accent.lighter(118).name())
        .replace("%ACCENT_PRESSED%", accent.darker(112).name())
    )


def apply_dark_palette(widget, accent=None):
    """Paleta oscura para los controles que se pintan por fuera de Qt.

    ``QColorDialog`` dibuja varios selectores con su propia paleta; sin esto
    quedarían con fondo claro aunque la hoja de estilos sea oscura.
    """
    palette = widget.palette()
    accent = accent_color(accent)
    palette.setColor(QPalette.ColorRole.Window, QColor("#232323"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E8E8E8"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#2E2E2E"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2A2A2A"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2E2E2E"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E8E8E8"))
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2A2A2A"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#E8E8E8"))
    widget.setPalette(palette)
    return palette


_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY = 19


def apply_dark_title_bar(window):
    """Pinta la barra de título nativa de Windows en modo oscuro.

    Se prueban las dos versiones del atributo porque cambió de número entre
    builds de Windows 10 y 11. Si el sistema no lo soporta no pasa nada: el
    contenido del diálogo ya está oscuro.
    """
    if sys.platform != "win32":
        return False
    try:
        hwnd = int(window.winId())
        enabled = ctypes.c_int(1)
        for attribute in (
            _DWMWA_USE_IMMERSIVE_DARK_MODE,
            _DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY,
        ):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                attribute,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
            if result == 0:
                _set_round_corners(hwnd)
                return True
    except Exception:
        pass
    return False


class AppDialog(QDialog):
    """Base de todos los diálogos: tema oscuro y siempre por encima.

    El panel principal es una ventana «tool» marcada como siempre visible.
    Un diálogo modal común podía quedar detrás de otra ventana y, como
    bloquea la interacción con el panel, parecía que la app se había colgado.
    Con ``WindowStaysOnTopHint`` y un ``raise_()`` al mostrarse, el diálogo
    queda siempre al frente y deja claro por qué el panel no responde.
    """

    def __init__(self, parent=None, accent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._accent = accent_color(accent)
        self.apply_theme(self._accent)

    def apply_theme(self, accent=None):
        """Aplica la hoja de estilos compartida con un acento opcional."""
        if accent is not None:
            self._accent = accent_color(accent)
        self.setStyleSheet(dialog_stylesheet(self._accent))

    def showEvent(self, event):
        super().showEvent(event)
        # El handle nativo recién existe después de crear la ventana.
        apply_dark_title_bar(self)
        self.raise_()
        self.activateWindow()


def pick_color(parent, color, title):
    """Abre un selector de color no nativo, oscuro y siempre al frente."""
    dialog = QColorDialog(color, parent)
    dialog.setWindowTitle(title)
    dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    accent = current_accent(parent)
    apply_dark_palette(dialog, accent)
    dialog.setStyleSheet(dialog_stylesheet(accent))
    apply_dark_title_bar(dialog)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selectedColor()
    return QColor()


def show_message(
    parent,
    icon,
    title,
    text,
    buttons=QMessageBox.StandardButton.Ok,
    default=None,
):
    """Muestra un ``QMessageBox`` con el tema de la app y siempre arriba."""
    # Mientras el cuadro está abierto el panel no debe cerrarse solo.
    window = parent.window() if isinstance(parent, QWidget) else None
    pause = getattr(window, "pause_auto_hide", None)
    resume = getattr(window, "resume_auto_hide", None)
    if pause:
        pause()
    try:
        box = QMessageBox(parent)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        if default is not None:
            box.setDefaultButton(default)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        accent = current_accent(parent)
        apply_dark_palette(box, accent)
        box.setStyleSheet(dialog_stylesheet(accent))
        apply_dark_title_bar(box)
        return box.exec()
    finally:
        if resume:
            resume()


def ask_confirmation(parent, title, text):
    """Pregunta Sí/No con el tema de la app; devuelve True si acepta."""
    reply = show_message(
        parent,
        QMessageBox.Icon.Question,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default=QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


def show_warning(parent, title, text):
    show_message(parent, QMessageBox.Icon.Warning, title, text)


def show_information(parent, title, text):
    show_message(parent, QMessageBox.Icon.Information, title, text)


def apply_menu_theme(menu, accent=None):
    """Aplica el tema oscuro a un ``QMenu`` (por ejemplo el de la bandeja)."""
    menu.setStyleSheet(dialog_stylesheet(accent))


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


def discovery_broadcast_targets():
    """Direcciones donde buscar lámparas.

    ``255.255.255.255`` no siempre sale por la interfaz correcta (VPN, varias
    placas de red) y algunos routers no reenvían el broadcast limitado. Por
    eso también se prueba el broadcast dirigido de cada red IPv4 local.
    """
    targets = ["255.255.255.255"]
    try:
        interfaces = QNetworkInterface.allInterfaces()
    except Exception:
        return targets

    for interface in interfaces:
        flags = interface.flags()
        if not flags & QNetworkInterface.InterfaceFlag.IsUp:
            continue
        if not flags & QNetworkInterface.InterfaceFlag.IsRunning:
            continue
        if flags & QNetworkInterface.InterfaceFlag.IsLoopBack:
            continue
        if not flags & QNetworkInterface.InterfaceFlag.CanBroadcast:
            continue

        for entry in interface.addressEntries():
            address = entry.ip()
            if address.protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                continue
            try:
                iface = ipaddress.IPv4Interface(
                    f"{address.toString()}/{entry.netmask().toString()}"
                )
            except ValueError:
                continue
            if iface.ip.is_loopback or iface.ip.is_link_local:
                continue
            broadcast = str(iface.network.broadcast_address)
            if broadcast not in targets:
                targets.append(broadcast)

    return targets


def parse_discovery_response(data, ip):
    """Valida una respuesta de ``getSystemConfig``.

    Devuelve los datos de la lámpara o ``None`` si el paquete no sirve. Se
    mantiene fuera del hilo para poder probarlo sin red.
    """
    try:
        response = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(response, dict):
        return None

    result = response.get("result")
    if not isinstance(result, dict):
        return None

    mac = result.get("mac")
    if not isinstance(mac, str) or not mac or not ip:
        return None

    cleaned_mac = mac.replace(":", "").replace("-", "")
    model = result.get("moduleName")
    firmware = result.get("fwVersion")
    rssi = result.get("rssi")
    return {
        "ip": ip,
        "mac": mac,
        "name": f"WiZ-{cleaned_mac[-6:]}",
        "model": model if isinstance(model, str) else None,
        "firmware": firmware if isinstance(firmware, str) else None,
        "rssi": rssi if isinstance(rssi, int) else None,
    }


class DiscoveryThread(QThread):
    """Busca lámparas WiZ por broadcast UDP.

    El broadcast se repite varias veces: un solo paquete puede perderse (WiFi
    congestionada, routers que limitan broadcast) y la lámpara quedaba sin
    descubrir. La ventana de escucha es más larga que los envíos para dar
    tiempo a las lámparas que contestan lento.

    También acepta una lista de destinos para el "agregar por IP", donde solo
    se consulta una dirección concreta.
    """

    lamp_found = pyqtSignal(dict)
    error = pyqtSignal(str)

    UDP_PORT = 38899
    BROADCAST_IP = "255.255.255.255"
    DISCOVERY_MESSAGE = b'{"method":"getSystemConfig","params":{}}'
    MAX_PACKET = 4096
    ATTEMPTS = 5
    SEND_INTERVAL = 0.4
    LISTEN_TIME = 8.0
    RECV_TIMEOUT = 0.25

    def __init__(self, targets=None, listen_time=None, attempts=None, parent=None):
        super().__init__(parent)
        self._targets = list(targets) if targets else None
        self._listen_time = (
            listen_time if listen_time is not None else self.LISTEN_TIME
        )
        self._attempts = attempts if attempts is not None else self.ATTEMPTS

    def run(self):
        targets = self._targets or discovery_broadcast_targets()
        _debug(f"Descubrimiento: probando {', '.join(targets)}")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Descubrimientos seguidos reaprovechan el mismo puerto efímero
            # sin esperar a que el sistema lo libere.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(self.RECV_TIMEOUT)
        except OSError as error:
            _debug(f"Descubrimiento: no se pudo abrir el socket: {error}")
            self.error.emit("No se pudo iniciar la búsqueda en la red.")
            return

        discovered_macs = set()
        deadline = time.monotonic() + self._listen_time
        next_send = time.monotonic()
        sent = 0

        try:
            while (
                time.monotonic() < deadline
                and not self.isInterruptionRequested()
            ):
                now = time.monotonic()
                if sent < self._attempts and now >= next_send:
                    for target in targets:
                        try:
                            sock.sendto(
                                self.DISCOVERY_MESSAGE,
                                (target, self.UDP_PORT),
                            )
                        except OSError as error:
                            _debug(
                                "Descubrimiento: fallo al enviar a "
                                f"{target}: {error}"
                            )
                    sent += 1
                    next_send = now + self.SEND_INTERVAL

                try:
                    data, addr = sock.recvfrom(self.MAX_PACKET)
                except socket.timeout:
                    continue
                except OSError:
                    continue

                self._handle_packet(data, addr[0], discovered_macs)
        finally:
            sock.close()

    def _handle_packet(self, data, ip, discovered_macs):
        """Valida una respuesta y emite la lámpara si es nueva."""
        lamp = parse_discovery_response(data, ip)
        if lamp is None or lamp["mac"] in discovered_macs:
            return

        discovered_macs.add(lamp["mac"])
        self.lamp_found.emit(lamp)


class HeartbeatThread(QThread):
    """Avisa cuando una lámpara deja de responder o vuelve a la red.

    Los comandos son fire-and-forget: si una lámpara está desenchufada o
    cambió de IP, la interfaz seguía mostrándola como si funcionara. Este
    hilo consulta ``getSystemConfig`` cada ``INTERVAL_MS`` y emite el cambio
    de estado para que la tarjeta lo refleje.

    Se necesitan dos fallos seguidos para marcar "sin conexión": un paquete
    UDP suelto se pierde con facilidad y no queremos que la tarjeta parpadee.
    """

    status_changed = pyqtSignal(str, bool)  # mac, en línea

    UDP_PORT = 38899
    QUERY = b'{"method":"getSystemConfig","params":{}}'
    MAX_PACKET = 4096
    INTERVAL_MS = 30000
    TIMEOUT = 1.5
    FAILURES_BEFORE_OFFLINE = 2

    def __init__(self, wiz_manager, parent=None):
        super().__init__(parent)
        self.wiz_manager = wiz_manager
        self._failures = {}
        self._reported = {}

    def run(self):
        while not self.isInterruptionRequested():
            self._check_lamps()
            self._wait_next_round()

    def _wait_next_round(self):
        """Espera el intervalo en tramos cortos para poder salir rápido."""
        remaining = self.INTERVAL_MS
        while remaining > 0 and not self.isInterruptionRequested():
            step = min(100, remaining)
            self.msleep(step)
            remaining -= step

    def _check_lamps(self):
        for mac, ip in self.wiz_manager.get_lamp_targets():
            if self.isInterruptionRequested():
                return
            online = bool(ip) and ip != "0.0.0.0" and self._ping(ip)
            self._report(mac, online)

    def _ping(self, ip):
        """True si la lámpara contestó una respuesta válida."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.TIMEOUT)
        try:
            sock.sendto(self.QUERY, (ip, self.UDP_PORT))
            deadline = time.monotonic() + self.TIMEOUT
            while time.monotonic() < deadline:
                data, addr = sock.recvfrom(self.MAX_PACKET)
                if addr[0] != ip:
                    # Respuesta de otra lámpara: se ignora y se sigue escuchando.
                    continue
                try:
                    response = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(response, dict) and isinstance(
                    response.get("result"), dict
                ):
                    return True
            return False
        except (socket.timeout, OSError):
            return False
        finally:
            sock.close()

    def _report(self, mac, online):
        if online:
            self._failures[mac] = 0
        else:
            failures = self._failures.get(mac, 0) + 1
            self._failures[mac] = failures
            if failures < self.FAILURES_BEFORE_OFFLINE:
                return

        if self._reported.get(mac, True) == online:
            return
        self._reported[mac] = online
        self.status_changed.emit(mac, online)


class WizManager:
    DATA_FILE = os.path.join(get_data_dir(), "lamps_data.json")

    def __init__(self):
        self.lamps = {}
        self.groups = {}
        self._socket = None
        # El heartbeat lee la lista de lámparas desde otro hilo: el lock evita
        # recorrer un diccionario que la UI está modificando.
        self._lock = threading.Lock()
        # Estado transitorio (no se guarda en disco): mac -> en línea.
        self._online = {}
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

    def add_lamp(self, mac, ip, name, model=None, firmware=None, rssi=None):
        """Agrega una lámpara o actualiza la existente.

        Devuelve ``"new"``, ``"updated"`` (cambió la IP) o ``None``. El nombre
        que eligió el usuario nunca se pisa al volver a descubrir.
        """
        status = None
        changed = False
        with self._lock:
            lamp = self.lamps.get(mac)
            if lamp is None:
                self.lamps[mac] = {
                    'ip': ip if ip else "0.0.0.0",
                    'name': name if name else f"WiZ-{mac[-6:]}",
                    'mac': mac,
                    'model': model or "",
                    'firmware': firmware or "",
                    'rssi': rssi,
                    'last_brightness': 100,
                    'last_color_hex': '#ffffff',
                    'last_temp_kelvin': 2700
                }
                self._online[mac] = True
                status = "new"
                changed = True
            else:
                # Volvió a responder: el heartbeat pudo haberla marcado
                # sin conexión.
                self._online[mac] = True
                if ip and lamp.get('ip') != ip:
                    # La lámpara ya existe pero cambió de IP (DHCP).
                    lamp['ip'] = ip
                    status = "updated"
                    changed = True
                if model and lamp.get('model') != model:
                    lamp['model'] = model
                    changed = True
                if firmware and lamp.get('firmware') != firmware:
                    lamp['firmware'] = firmware
                    changed = True
                if rssi is not None and lamp.get('rssi') != rssi:
                    lamp['rssi'] = rssi
                    changed = True
        # Fuera del lock: escribir el JSON no debe frenar al heartbeat.
        if changed:
            self.save_data()
        return status

    def add_group(self, group_name, lamp_macs):
        self.groups[group_name] = lamp_macs
        self.save_data()

    def rename_lamp(self, mac, new_name):
        """Cambia el nombre visible de una lámpara."""
        new_name = (new_name or "").strip()
        if not new_name:
            return False
        with self._lock:
            lamp = self.lamps.get(mac)
            if lamp is None or lamp.get("name") == new_name:
                return False
            lamp["name"] = new_name
        self.save_data()
        return True

    def rename_group(self, old_name, new_name):
        """Renombra un grupo conservando el orden y sus lámparas.

        El nombre es la clave del diccionario, así que hay que reconstruirlo.
        """
        new_name = (new_name or "").strip()
        if not new_name or old_name not in self.groups:
            return False
        if new_name == old_name:
            return False
        # Evita dos grupos que solo difieran en mayúsculas/minúsculas.
        taken = {
            name.casefold()
            for name in self.groups
            if name != old_name
        }
        if new_name.casefold() in taken:
            return False
        self.groups = {
            (new_name if name == old_name else name): macs
            for name, macs in self.groups.items()
        }
        self.save_data()
        return True

    def group_name_exists(self, name, ignore=None):
        """True si ya hay un grupo con ese nombre (sin distinguir mayúsculas)."""
        target = (name or "").strip().casefold()
        return any(
            group.casefold() == target and group != ignore
            for group in self.groups
        )

    def delete_lamp(self, mac):
        """Borra una lámpara y la saca de cualquier grupo donde estuviera"""
        with self._lock:
            if mac not in self.lamps:
                return
            del self.lamps[mac]
            for lamp_macs in self.groups.values():
                if mac in lamp_macs:
                    lamp_macs.remove(mac)
            self._online.pop(mac, None)
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

    def get_lamp_targets(self):
        """Copia (mac, ip) para que el heartbeat recorra la lista sin carreras."""
        with self._lock:
            return [(mac, lamp.get("ip")) for mac, lamp in self.lamps.items()]

    def is_online(self, mac):
        return self._online.get(mac, True)

    def set_online(self, mac, online):
        """Marca el estado de red de una lámpara. True si cambió."""
        with self._lock:
            if mac not in self.lamps:
                return False
            changed = self._online.get(mac, True) != online
            self._online[mac] = online
            return changed

    def send_command(self, ip, command_params):
        """Envía un comando UDP reutilizando un único socket.

        Crear y cerrar un socket por comando era costoso al arrastrar un
        slider (varios comandos por segundo); reutilizarlo mantiene el
        movimiento fluido.

        Sigue siendo fire-and-forget a propósito: bloquear la UI esperando el
        ACK de cada comando congelaría el arrastre del slider. La lámpara que
        no responde se detecta con ``HeartbeatThread``.
        """
        sock = self._get_socket()
        if sock is None:
            return
        try:
            command_json = json.dumps(command_params).encode("utf-8")
            sock.sendto(command_json, (ip, 38899))
        except OSError as error:
            # El socket quedó inservible: se descarta y se recrea al próximo.
            _debug(f"No se pudo enviar el comando a {ip}: {error}")
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

    # La barra de temperatura va de cálido (izquierda, 2200K) a frío
    # (derecha, 6500K), igual que el ícono del termómetro. El blanco suave
    # del medio hace la transición natural, como en los selectores de iOS.
    TEMP_GRADIENT_STOPS = (
        (0.0, "#FF8A4C"),
        (0.5, "#F2EFEA"),
        (1.0, "#4FA8FF"),
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
        self._temperature_gradient = False
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

    def apply_appearance(self, settings, gradient=False, temperature=False):
        """Aplica los ajustes unificados de controles.

        El acento, el color de apagado y el de la perilla se comparten con el
        switch; el grosor y el tamaño del tirador también. Así un solo juego de
        controles modifica sliders y botones a la vez.

        ``gradient=True`` se usa para el slider de matiz (degradé arcoíris).
        ``temperature=True`` pinta la barra completa con el degradado
        cálido/frío, para ver el color al que se va a llegar antes de soltar."""
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
        self._temperature_gradient = bool(temperature)
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

        if self._gradient or self._temperature_gradient:
            # El matiz y la temperatura muestran toda la barra con su
            # degradado: así se ve el color final antes de parar el tirador.
            stops = (
                self.COLOR_STOPS if self._gradient else self.TEMP_GRADIENT_STOPS
            )
            gradient = QLinearGradient(groove.left(), 0, groove.right(), 0)
            for stop, color in stops:
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


class SliderIcon(QWidget):
    """Iconos dibujados para los sliders de brillo, temperatura y color.

    Reemplazan a los glifos unicode: un sol, un termómetro frío/caliente y
    un punto relleno con el color actual.
    """

    def __init__(self, kind, parent=None, size=16):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(size, size)
        self._value = 100 if kind == "brightness" else 50
        self._color = QColor("#ffffff")
        tooltips = {
            "brightness": "Brillo",
            "temperature": "Temperatura: fría (azul) ↔ cálida (naranja)",
            "color": "Color",
        }
        self.setToolTip(tooltips.get(kind, ""))

    def set_value(self, value):
        value = min(100, max(0, int(value)))
        if value == self._value:
            return
        self._value = value
        self.update()

    def set_color(self, color):
        color = QColor(color)
        if color.name() == self._color.name():
            return
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        if self.kind == "brightness":
            self._paint_brightness(painter, cx, cy, w)
        elif self.kind == "temperature":
            self._paint_temperature(painter, cx, cy, w, h)
        else:
            self._paint_color(painter, cx, cy, w, h)

    def _paint_brightness(self, painter, cx, cy, w):
        # Sol de línea (sun.max): círculo hueco y ocho rayos cortos.
        color = QColor("#D8D8D8")
        color.setAlphaF(0.7 + 0.3 * (self._value / 100.0))
        painter.setPen(
            QPen(color, max(1.0, w * 0.07), Qt.PenStyle.SolidLine,
                 Qt.PenCapStyle.RoundCap)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)

        radius = w * 0.13
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        inner, outer = w * 0.22, w * 0.34
        for index in range(8):
            angle = index * math.pi / 4.0
            dx, dy = math.cos(angle), math.sin(angle)
            painter.drawLine(
                QPointF(cx + dx * inner, cy + dy * inner),
                QPointF(cx + dx * outer, cy + dy * outer),
            )

    def _paint_temperature(self, painter, cx, cy, w, h):
        # Termómetro mínimo: una sola forma rellena, sin contorno interior.
        t = self._value / 100.0
        warm, cold = QColor("#FF8A4C"), QColor("#4FA8FF")
        liquid = QColor(
            round(warm.red() + (cold.red() - warm.red()) * t),
            round(warm.green() + (cold.green() - warm.green()) * t),
            round(warm.blue() + (cold.blue() - warm.blue()) * t),
        )

        tube = QRectF(cx - w * 0.095, h * 0.20, w * 0.19, h * 0.44)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(liquid)
        painter.drawRoundedRect(tube, w * 0.095, w * 0.095)
        painter.drawEllipse(QPointF(cx, h * 0.78), w * 0.16, w * 0.16)

    def _paint_color(self, painter, cx, cy, w, h):
        # Punto de color simple: reconocible al instante como "color" en
        # iOS/Android, sin formas decorativas que distraigan.
        radius = w * 0.30
        painter.setPen(QPen(QColor("#E0E0E0"), 0.9))
        painter.setBrush(self._color)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)


class UpdateIconButton(HoverButton):
    """Botón de actualización: círculo perfecto con una flecha, giratorio."""

    def __init__(self, parent=None):
        super().__init__("", parent, radius=6)
        self.setFixedSize(28, 28)
        self.setObjectName("updateButton")
        self.setToolTip("Buscar actualizaciones")
        self._angle = 0.0
        self._state = "idle"
        self._idle_color = QColor(DEFAULT_SETTINGS["update"]["color"])
        self._icon_size = DEFAULT_SETTINGS["update"]["size"]
        self._animation = QPropertyAnimation(self, b"angle")
        self._animation.setDuration(1400)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(360.0)
        self._animation.setLoopCount(-1)

    def get_angle(self):
        return self._angle

    def set_angle(self, value):
        self._angle = float(value)
        self.update()

    angle = pyqtProperty(float, get_angle, set_angle)

    def is_busy(self):
        return self._state == "busy"

    def set_color(self, color):
        """Color del ícono cuando no hay una actualización disponible."""
        self._idle_color = QColor(color)
        self.update()

    def set_size(self, size):
        """Tamaño del dibujo; el botón mantiene el área del engranaje."""
        size = min(UPDATE_ICON_SIZE_MAX, max(UPDATE_ICON_SIZE_MIN, int(size)))
        if size == self._icon_size:
            return
        self._icon_size = size
        self.update()

    def set_state(self, state):
        self._state = state
        tooltips = {
            "idle": "Buscar actualizaciones",
            "available": "Hay una versión nueva. Clic para actualizar WINWIZ.",
            "busy": "Instalando la actualización…",
        }
        self.setToolTip(tooltips.get(state, tooltips["idle"]))
        if state in ("available", "busy"):
            if self._animation.state() != QPropertyAnimation.State.Running:
                self._animation.start()
        else:
            self._animation.stop()
            self._angle = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._progress > 0.001:
            hover = QColor(self._hover_color)
            hover.setAlpha(round(hover.alpha() * self._progress))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover)
            painter.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)

        color = (
            current_accent(self)
            if self._state in ("available", "busy")
            else QColor("#FFFFFF" if self._progress > 0.001 else self._idle_color)
        )
        # El dibujo original mide 16 px; el resto de medidas escalan juntas
        # para que la flecha no se deforme al cambiar el tamaño.
        scale = self._icon_size / 16.0
        pen = QPen(
            color,
            max(1.2, 1.8 * scale),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )

        painter.save()
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        painter.rotate(self._angle)

        # Arco con un hueco arriba bien visible: así se distingue dónde
        # empieza y dónde termina la flecha. Se dibuja con drawArc (sin
        # QPainterPath) para evitar líneas rectas sobrantes, y está centrado
        # en el widget para que el giro no se desplace.
        radius = 6.5 * scale
        # Qt mide ángulos desde las 3 en sentido antihorario y con el eje Y
        # hacia abajo, al revés que math.cos/sin. Para que el arco vaya desde
        # 310° hasta 230° (en ángulos math) hay que usar:
        #   start_Qt = -310 = 50, span_Qt = -280.
        start_math = 310
        end_math = 230
        start_qt = (-start_math) % 360  # 50
        # El arco debe cubrir 280° en sentido antihorario-Qt (math creciente):
        # de 310° a 230° pasando por 0/90/180. Eso es start_math + 280.
        span_math = (end_math - start_math) % 360  # 280
        span_qt = -span_math  # -280
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(-radius, -radius, radius * 2, radius * 2),
            int(start_qt * 16),
            int(span_qt * 16),
        )

        # Punta triangular completamente adelante del extremo del arco, para
        # que quede claro que está en la punta y no en medio de la línea.
        end = math.radians(end_math)
        cx, cy = math.cos(end), math.sin(end)
        tx, ty = -cy, cx  # tangente en sentido horario
        px, py = cx * radius, cy * radius
        tip = QPointF(px + tx * 4.0 * scale, py + ty * 4.0 * scale)
        base_x, base_y = px + tx * 1.2 * scale, py + ty * 1.2 * scale
        head_half = 1.8 * scale
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        head = QPainterPath()
        head.moveTo(tip)
        head.lineTo(QPointF(base_x + cx * head_half, base_y + cy * head_half))
        head.lineTo(QPointF(base_x - cx * head_half, base_y - cy * head_half))
        head.closeSubpath()
        painter.drawPath(head)
        painter.restore()


class LampControl(QWidget):
    delete_requested = pyqtSignal(str)  # emite el mac de la lámpara a borrar

    def __init__(self, lamp_data, wiz_manager, parent=None):
        super().__init__(parent)
        self.mac = lamp_data["mac"]
        self.ip = lamp_data["ip"]
        self.name = lamp_data["name"]
        self.model = lamp_data.get("model")
        self.firmware = lamp_data.get("firmware")
        self.rssi = lamp_data.get("rssi")
        self.is_online = True
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
        # Refleja el estado que ya conoce el heartbeat (por si la tarjeta se
        # crea después de que la lámpara dejó de responder).
        self.set_online(self.wiz_manager.is_online(self.mac))

    def set_online(self, online):
        """Atenúa el nombre cuando la lámpara no responde en la red."""
        self.is_online = online
        self.name_label.setStyleSheet("" if online else "color: #9A9A9A;")
        self._update_name_tooltip()

    def _update_name_tooltip(self):
        """Datos para identificar la lámpara aunque se repita el nombre."""
        lines = [self.name, f"MAC: {self.mac}"]
        if self.ip and self.ip != "0.0.0.0":
            lines.append(f"IP: {self.ip}")
        if self.model:
            lines.append(f"Modelo: {self.model}")
        extras = []
        if self.firmware:
            extras.append(f"FW {self.firmware}")
        if self.rssi is not None:
            extras.append(f"{self.rssi} dBm")
        if extras:
            lines.append(" · ".join(extras))
        lines.append("En línea" if self.is_online else "Sin conexión")
        lines.append("Clic derecho para renombrar")
        self.name_label.setToolTip("\n".join(lines))

    def show_context_menu(self, position):
        menu = QMenu(self.window())
        apply_menu_theme(menu, current_accent(self))
        rename_action = menu.addAction("Renombrar…")
        menu.addSeparator()
        delete_action = menu.addAction("Eliminar")
        source = self.sender()
        if not isinstance(source, QWidget):
            source = self
        chosen = menu.exec(source.mapToGlobal(position))
        if chosen is rename_action:
            self.prompt_rename()
        elif chosen is delete_action:
            self.confirm_delete()

    def prompt_rename(self):
        """Pide un nombre nuevo y lo guarda sin reconstruir la tarjeta."""
        popup = self.window()
        if hasattr(popup, "pause_auto_hide"):
            popup.pause_auto_hide()
        try:
            dialog = RenameDialog(
                "Renombrar lámpara",
                "Nombre de la lámpara:",
                self.name,
                popup,
            )
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            if hasattr(popup, "resume_auto_hide"):
                popup.resume_auto_hide()
        if not accepted:
            return

        new_name = dialog.value()
        if self.wiz_manager.rename_lamp(self.mac, new_name):
            self.apply_name(new_name)

    def apply_name(self, new_name):
        """Actualiza el nombre en todas las tarjetas de la misma lámpara."""
        window = self.window()
        widgets = window.findChildren(LampControl) if window else []
        if self not in widgets:
            widgets.append(self)
        for widget in widgets:
            if widget is self or widget.mac == self.mac:
                widget.name = new_name
                widget.name_label.setText(new_name)
                widget._update_name_tooltip()

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
        self.name_label = name_label
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        # El clic derecho funciona en la tarjeta y en el nombre, sin cambiar
        # el clic izquierdo que ya enciende/apaga la lámpara.
        for widget in (self, header, name_label):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(self.show_context_menu)

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

        self.brightness_icon = SliderIcon("brightness", self)
        brightness_layout.addWidget(self.brightness_icon)

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

        self.temp_icon = SliderIcon("temperature", self)
        temp_layout.addWidget(self.temp_icon)

        self.temp_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setObjectName("tempSlider")
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

        self.color_icon = SliderIcon("color", self)
        self.color_icon.set_color(self.current_color)
        color_layout.addWidget(self.color_icon)

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
        self.color_icon.set_color(color)
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
        self.brightness_icon.set_value(value)

    def update_temp_label(self, slider_val):
        """Actualiza solo el label sin enviar comando"""
        kelvin = self.slider_to_kelvin(slider_val)
        self.temp_value.setText(f"{kelvin}K")
        self.temp_icon.set_value(slider_val)

    def update_color_preview_only(self, hue):
        """Actualiza solo el preview sin enviar comando"""
        self.current_hue = hue
        color = QColor.fromHsv(hue, 255, 255)
        self.color_icon.set_color(color)
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

        color = pick_color(self, self.current_color, "Elegir color exacto")

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
        if ask_confirmation(
            self.window(),
            "Borrar lámpara",
            f"¿Seguro que querés borrar '{self.name}'?",
        ):
            self.delete_requested.emit(self.mac)


class GroupControl(QWidget):
    """Control para un grupo de lámparas con expansión/colapso y controles completos"""

    delete_requested = pyqtSignal(str)       # emite el nombre del grupo a borrar
    lamp_delete_requested = pyqtSignal(str)  # reenvía el mac de una lámpara interna
    rename_requested = pyqtSignal(str, str)  # nombre viejo, nombre nuevo

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
        self.name_label = name_label
        name_label.setToolTip("Clic derecho para renombrar")
        name_layout.addWidget(name_label)
        header_layout.addWidget(name_row)

        # Renombrar desde el clic derecho, sin romper el clic izquierdo que
        # expande/colapsa el grupo.
        for widget in (self, header, name_row, name_label):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(self.show_context_menu)

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

        self.brightness_icon = SliderIcon("brightness", self)
        brightness_layout.addWidget(self.brightness_icon)

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

        self.temp_icon = SliderIcon("temperature", self)
        temp_layout.addWidget(self.temp_icon)

        self.temp_slider = ImprovedSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setObjectName("tempSlider")
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

        self.color_icon = SliderIcon("color", self)
        self.color_icon.set_color(self.current_color)
        color_layout.addWidget(self.color_icon)

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
        self.brightness_icon.set_value(value)

    def update_temp_label(self, slider_val):
        """Actualiza solo el label sin enviar comando"""
        kelvin = self.slider_to_kelvin(slider_val)
        self.temp_value.setText(f"{kelvin}K")
        self.temp_icon.set_value(slider_val)

    def update_color_preview_only(self, hue):
        """Actualiza solo el preview sin enviar comando"""
        color = QColor.fromHsv(hue, 255, 255)
        self.color_icon.set_color(color)
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
        self.color_icon.set_color(color)
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

        color = pick_color(self, self.current_color, "Elegir color exacto")

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

    def show_context_menu(self, position):
        menu = QMenu(self.window())
        apply_menu_theme(menu, current_accent(self))
        rename_action = menu.addAction("Renombrar…")
        menu.addSeparator()
        delete_action = menu.addAction("Eliminar")
        source = self.sender()
        if not isinstance(source, QWidget):
            source = self
        chosen = menu.exec(source.mapToGlobal(position))
        if chosen is rename_action:
            self.prompt_rename()
        elif chosen is delete_action:
            self.confirm_delete()

    def prompt_rename(self):
        """El renombre de un grupo lo aplica el panel, porque cambia su clave."""
        popup = self.window()
        if hasattr(popup, "pause_auto_hide"):
            popup.pause_auto_hide()
        try:
            taken = [
                name
                for name in self.wiz_manager.get_groups()
                if name != self.group_name
            ]
            dialog = RenameDialog(
                "Renombrar grupo",
                "Nombre del grupo:",
                self.group_name,
                popup,
                taken_names=taken,
            )
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            if hasattr(popup, "resume_auto_hide"):
                popup.resume_auto_hide()
        if accepted:
            self.rename_requested.emit(self.group_name, dialog.value())

    def confirm_delete(self):
        if ask_confirmation(
            self.window(),
            "Borrar grupo",
            f"¿Seguro que querés borrar el grupo '{self.group_name}'?\n"
            "Las lámparas no se borran, quedan sueltas.",
        ):
            self.delete_requested.emit(self.group_name)


class GroupDialog(AppDialog):
    """Diálogo para crear un grupo, con el mismo tema que el panel."""

    def __init__(self, wiz_manager, parent=None):
        super().__init__(parent, accent=current_accent(parent))
        self.wiz_manager = wiz_manager
        self.setWindowTitle("Crear grupo")
        self.setModal(True)
        self.setMinimumWidth(340)
        self.resize(340, 430)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("Nuevo grupo")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Elegí un nombre y marcá las luces que forman parte del grupo."
        )
        subtitle.setObjectName("hintLabel")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        root.addWidget(QLabel("Nombre del grupo:"))
        self.group_name_input = QLineEdit()
        self.group_name_input.setPlaceholderText("Ej.: Living")
        self.group_name_input.setClearButtonEnabled(True)
        root.addWidget(self.group_name_input)

        root.addWidget(QLabel("Seleccionar luces:"))
        self.lamp_list = QListWidget()
        for lamp in self.wiz_manager.get_lamps():
            item = QListWidgetItem(lamp["name"])
            item.setData(Qt.ItemDataRole.UserRole, lamp["mac"])
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lamp_list.addItem(item)
        root.addWidget(self.lamp_list, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        cancel_btn = QPushButton("Cancelar")
        save_btn = QPushButton("Guardar")
        save_btn.setObjectName("primaryButton")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save_group)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch(1)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        root.addLayout(btn_layout)

    def save_group(self):
        group_name = self.group_name_input.text().strip()
        if not group_name:
            show_warning(self, "Error", "Ingresá un nombre para el grupo")
            return
        if self.wiz_manager.group_name_exists(group_name):
            show_warning(self, "Error", "Ya existe un grupo con ese nombre")
            return

        selected_macs = []
        for i in range(self.lamp_list.count()):
            item = self.lamp_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_macs.append(item.data(Qt.ItemDataRole.UserRole))

        if not selected_macs:
            show_warning(self, "Error", "Seleccioná al menos una luz")
            return

        self.wiz_manager.add_group(group_name, selected_macs)
        self.accept()


class RenameDialog(AppDialog):
    """Diálogo chico para cambiar el nombre de una lámpara o un grupo."""

    def __init__(self, title, label, current, parent=None, taken_names=None):
        super().__init__(parent, accent=current_accent(parent))
        self._taken = {name.casefold() for name in (taken_names or ())}
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        root.addWidget(title_label)

        root.addWidget(QLabel(label))
        self.name_input = QLineEdit(current)
        self.name_input.setMaxLength(40)
        self.name_input.setClearButtonEnabled(True)
        self.name_input.selectAll()
        self.name_input.textChanged.connect(self._validate)
        self.name_input.returnPressed.connect(self._try_accept)
        root.addWidget(self.name_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("hintLabel")
        self.error_label.setStyleSheet("color: #FF9A9A;")
        self.error_label.hide()
        root.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        cancel_btn = QPushButton("Cancelar")
        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._try_accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self.save_button)
        root.addLayout(buttons)

        self._validate()
        self.name_input.setFocus()

    def _validate(self):
        name = self.name_input.text().strip()
        error = ""
        if not name:
            error = "El nombre no puede estar vacío."
        elif name.casefold() in self._taken:
            error = "Ya existe otro grupo con ese nombre."
        self.error_label.setText(error)
        self.error_label.setVisible(bool(error))
        self.save_button.setEnabled(not error)
        return not error

    def _try_accept(self):
        if self._validate():
            self.accept()

    def value(self):
        return self.name_input.text().strip()


class AddLampDialog(AppDialog):
    """Pide una IP concreta cuando el broadcast no llega a la lámpara."""

    def __init__(self, parent=None):
        super().__init__(parent, accent=current_accent(parent))
        self.setWindowTitle("Agregar lámpara por IP")
        self.setModal(True)
        self.setMinimumWidth(340)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("Agregar por IP")
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        hint = QLabel(
            "Si la lámpara no aparece con «Descubrir», escribí su IP. "
            "Podés verla en la app WiZ o en la lista de dispositivos del router."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(QLabel("IP de la lámpara:"))
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Ej.: 192.168.0.42")
        self.ip_input.setClearButtonEnabled(True)
        self.ip_input.textChanged.connect(self._validate)
        self.ip_input.returnPressed.connect(self._try_accept)
        root.addWidget(self.ip_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("hintLabel")
        self.error_label.setStyleSheet("color: #FF9A9A;")
        self.error_label.hide()
        root.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        cancel_btn = QPushButton("Cancelar")
        self.search_button = QPushButton("Buscar")
        self.search_button.setObjectName("primaryButton")
        self.search_button.setDefault(True)
        self.search_button.clicked.connect(self._try_accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self.search_button)
        root.addLayout(buttons)

        self.ip_input.setFocus()

    def _validate(self):
        text = self.ip_input.text().strip()
        error = ""
        if not text:
            error = "Ingresá la IP de la lámpara."
        else:
            try:
                address = ipaddress.ip_address(text)
            except ValueError:
                error = "Ingresá una IP válida, por ejemplo 192.168.0.42."
            else:
                if address.version != 4:
                    error = "Por ahora solo se admiten direcciones IPv4."
        self.error_label.setText(error)
        self.error_label.setVisible(bool(error))
        self.search_button.setEnabled(not error)
        return not error

    def _try_accept(self):
        if self._validate():
            self.accept()

    def value(self):
        return self.ip_input.text().strip()


class SettingsDialog(AppDialog):
    """Ajustes de apariencia con vista previa en vivo.

    Cada cambio emite ``preview`` con una copia de los ajustes; el popup los
    aplica al instante. Al cancelar se vuelve a los valores originales.
    """

    preview = pyqtSignal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent, accent=settings["sliders"]["accent"])
        self._original = copy.deepcopy(settings)
        self._tint_color = QColor(settings["glass"]["tint"])
        self._accent_color = QColor(settings["sliders"]["accent"])
        self._update_icon_color = QColor(settings["update"]["color"])

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

        # --- Temperatura ---------------------------------------------------
        temperature_group = QGroupBox("Barra de temperatura")
        temperature_grid = QGridLayout(temperature_group)
        temperature_grid.setContentsMargins(12, 18, 12, 12)
        temperature_grid.setHorizontalSpacing(10)
        temperature_grid.setVerticalSpacing(8)
        temperature_grid.setColumnStretch(1, 1)

        self.temp_gradient_check = QCheckBox(
            "Mostrar degradado frío/caliente en la barra"
        )
        self.temp_gradient_check.setChecked(
            settings["temperature"]["gradient"]
        )
        self.temp_gradient_check.setToolTip(
            "La barra completa va de cálido (izquierda) a frío (derecha)"
        )
        temperature_grid.addWidget(self.temp_gradient_check, 0, 0, 1, 3)

        self.temp_preview = ImprovedSlider(Qt.Orientation.Horizontal)
        self.temp_preview.setObjectName("tempPreviewSlider")
        self.temp_preview.setRange(0, 100)
        self.temp_preview.setValue(25)
        temperature_grid.addWidget(QLabel("Vista previa:"), 1, 0)
        temperature_grid.addWidget(self.temp_preview, 1, 1, 1, 2)

        temperature_hint = QLabel(
            "Con el degradado activo, la izquierda es cálida (2200 K) y la "
            "derecha fría (6500 K), igual que el color que recibe la lámpara. "
            "Si lo desactivás, la barra vuelve al color de acento de siempre."
        )
        temperature_hint.setObjectName("hintLabel")
        temperature_hint.setWordWrap(True)
        temperature_grid.addWidget(temperature_hint, 2, 0, 1, 3)

        root.addWidget(temperature_group)

        # --- Actualizaciones ----------------------------------------------
        update_group = QGroupBox("Actualizaciones")
        update_grid = QGridLayout(update_group)
        update_grid.setContentsMargins(12, 18, 12, 12)
        update_grid.setHorizontalSpacing(10)
        update_grid.setVerticalSpacing(8)
        update_grid.setColumnStretch(1, 1)

        self.update_swatch = QPushButton()
        self.update_swatch.setObjectName("colorSwatch")
        self.update_swatch.setFixedSize(64, 22)
        self.update_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_swatch.setToolTip("Elegir color del ícono de actualización")
        self.update_hex = QLabel()
        self.update_hex.setObjectName("settingValue")
        self._update_swatch(self.update_swatch, self._update_icon_color)
        update_grid.addWidget(QLabel("Color del ícono:"), 0, 0)
        update_grid.addWidget(
            self._color_control(self.update_swatch, self.update_hex), 0, 1, 1, 2
        )

        (
            self.update_size_slider,
            self.update_size_value,
            update_size_control,
        ) = self._make_slider_row(
            UPDATE_ICON_SIZE_MIN,
            UPDATE_ICON_SIZE_MAX,
            settings["update"]["size"],
            step=2,
        )
        update_grid.addWidget(QLabel("Tamaño del ícono:"), 1, 0)
        update_grid.addWidget(update_size_control, 1, 1, 1, 2)

        update_hint = QLabel(
            "El color y el tamaño se usan cuando no hay una versión nueva. "
            "Si hay actualización, el ícono gira y pasa al color de acento."
        )
        update_hint.setObjectName("hintLabel")
        update_hint.setWordWrap(True)
        update_grid.addWidget(update_hint, 2, 0, 1, 3)
        root.addWidget(update_group)

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
        self.update_swatch.clicked.connect(self._pick_update_color)
        self.update_size_slider.valueChanged.connect(self._refresh_state)
        self.temp_gradient_check.toggled.connect(self._refresh_state)
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
        self.update_hex.setText(self._update_icon_color.name().upper())
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
        self.update_size_value.setText(f"{self.update_size_slider.value()} px")

        self._update_preview_slider_appearance()
        self.temp_preview.apply_appearance(
            self.get_settings(),
            temperature=self.temp_gradient_check.isChecked(),
        )
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
        color = pick_color(
            self, self._tint_color, "Color del tinte del vidrio"
        )
        if color.isValid():
            self._tint_color = color
            self._update_swatch(self.tint_swatch, color)
            self._refresh_state()

    def _pick_accent(self):
        color = pick_color(
            self, self._accent_color, "Color de acento (sliders y botones)"
        )
        if color.isValid():
            self._accent_color = color
            self._update_swatch(self.accent_swatch, color)
            self._apply_dialog_style()
            self._refresh_state()

    def _pick_update_color(self):
        color = pick_color(
            self, self._update_icon_color, "Color del ícono de actualización"
        )
        if color.isValid():
            self._update_icon_color = color
            self._update_swatch(self.update_swatch, color)
            self._refresh_state()

    def _pick_toggle_color(self, key):
        titles = {
            "off": "Color de apagado (botón y riel del slider)",
            "knob": "Color del tirador y la perilla",
        }
        color = pick_color(
            self,
            self._toggle_colors[key],
            titles.get(key, "Color del botón"),
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
            self.update_size_slider,
            self.temp_gradient_check,
        )
        for widget in widgets:
            widget.blockSignals(True)

        self._tint_color = QColor(defaults["glass"]["tint"])
        self._accent_color = QColor(defaults["sliders"]["accent"])
        self._update_icon_color = QColor(defaults["update"]["color"])
        self._toggle_colors = {
            key: QColor(defaults["toggle"][key]) for key in ("off", "knob")
        }
        self._update_swatch(self.tint_swatch, self._tint_color)
        self._update_swatch(self.accent_swatch, self._accent_color)
        self._update_swatch(self.update_swatch, self._update_icon_color)
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
        self.update_size_slider.setValue(defaults["update"]["size"])
        self.temp_gradient_check.setChecked(defaults["temperature"]["gradient"])

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
                "update": {
                    "color": self._update_icon_color.name(),
                    "size": self.update_size_slider.value(),
                },
                "temperature": {
                    "gradient": self.temp_gradient_check.isChecked(),
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
        # Una sola hoja de estilos para todas las ventanas de la app. Se
        # reaplica al cambiar el acento para que la selección, el foco y el
        # botón principal sigan el color elegido.
        self.apply_theme(self._accent_color)


class PopupWindow(QWidget):
    appearance_changed = pyqtSignal(object)

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

        # Actualizaciones: chequeo silencioso al abrir la app por primera vez.
        self._update_net = QNetworkAccessManager(self)
        self._update_net.finished.connect(self._on_update_checked)
        self._update_reply = None
        self._update_branch = get_update_branch()
        self._local_commit = get_local_commit()
        self._remote_commit = None
        self._update_available = False
        self._manual_check = False

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

        # Si hay un diálogo modal abierto no se puede reconstruir la lista:
        # se borrarían las tarjetas detrás del diálogo. Se reintenta al cerrar.
        self._deferred_reload_timer = QTimer(self)
        self._deferred_reload_timer.setSingleShot(True)
        self._deferred_reload_timer.setInterval(250)
        self._deferred_reload_timer.timeout.connect(self.load_content)

        # Estado del descubrimiento: la barra inline reemplaza al modal.
        self._new_count = 0
        self._updated_count = 0
        self._discovery_cancelled = False
        self._discovery_running = False
        self._discovery_mode = "broadcast"
        self._manual_ip = None
        self._last_found_name = ""
        self._discovery_action = None
        self._discovery_status_base = ""
        self._discovery_error = ""
        self._found_total = 0
        self.discovery_thread = None
        self._discovery_dots = 0

        self._discovery_anim_timer = QTimer(self)
        self._discovery_anim_timer.setInterval(400)
        self._discovery_anim_timer.timeout.connect(self._tick_discovery_status)

        self._discovery_status_timer = QTimer(self)
        self._discovery_status_timer.setSingleShot(True)
        self._discovery_status_timer.timeout.connect(self._clear_discovery_message)

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
        QTimer.singleShot(1500, self.check_for_updates)

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
            or previous["temperature"] != self.settings["temperature"]
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
        # El ícono de actualización usa su propio color y tamaño en reposo.
        if previous["update"]["color"] != self.settings["update"]["color"]:
            self.update_button.set_color(self.settings["update"]["color"])
        if previous["update"]["size"] != self.settings["update"]["size"]:
            self.update_button.set_size(self.settings["update"]["size"])
        # El menú de la bandeja también sigue el acento elegido.
        if previous["sliders"].get("accent") != self.settings["sliders"].get(
            "accent"
        ):
            self.appearance_changed.emit(self.settings)

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

    # -- Actualizaciones ----------------------------------------------------

    def check_for_updates(self):
        """Consulta el último commit del branch instalado sin bloquear la UI."""
        if self._update_reply is not None:
            return
        url = UPDATE_CHECK_URL.format(repo=UPDATE_REPO, branch=self._update_branch)
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"WINWIZ-UpdateCheck")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        self._update_reply = self._update_net.get(request)

    def _on_update_checked(self, reply):
        if reply != self._update_reply:
            reply.deleteLater()
            return
        self._update_reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                _debug(f"No se pudo chequear actualizaciones: {reply.errorString()}")
                if self._manual_check:
                    self._show_update_message(
                        "No se pudo comprobar la versión. Revisá tu conexión.",
                        timeout=5000,
                    )
                return
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            sha = data.get("sha") if isinstance(data, dict) else None
            if not isinstance(sha, str) or len(sha) < 7:
                return
            self._remote_commit = sha
            if not self._local_commit:
                # Instalaciones anteriores no guardaban el commit: la primera
                # respuesta marca la base para no avisar falsamente.
                set_update_baseline(sha)
                self._local_commit = sha
                if self._manual_check:
                    self._show_update_message(
                        "Ya tenés la última versión.", timeout=4000
                    )
                return
            if sha != self._local_commit:
                self._update_available = True
                self.update_button.set_state("available")
                if self._manual_check:
                    self._show_update_message(
                        "Hay una versión nueva disponible.", timeout=5000
                    )
            elif self._manual_check:
                self._show_update_message("Ya tenés la última versión.", timeout=4000)
        except (ValueError, UnicodeDecodeError) as error:
            _debug(f"Respuesta de actualización inválida: {error}")
        finally:
            if self._manual_check:
                if not self._update_available:
                    self.update_button.set_state("idle")
                self._manual_check = False
            reply.deleteLater()

    def _show_update_message(self, text, timeout=None):
        """Reutiliza la barra inline para mostrar el estado de la actualización."""
        self.discovery_status.setText(text)
        self.discovery_action.hide()
        self.discovery_bar.show()
        self.pause_auto_hide()
        if timeout is not None:
            self._discovery_status_timer.start(timeout)

    def start_update(self):
        """Chequea manualmente o aplica la actualización ya detectada."""
        if self._discovery_running:
            show_warning(
                self, "Actualizar WINWIZ", "Terminá la búsqueda antes de actualizar."
            )
            return
        if self._update_reply is not None:
            return
        if not self._update_available or not self._remote_commit:
            self._manual_check = True
            self.update_button.set_state("busy")
            self._show_update_message("Buscando actualizaciones…")
            self.check_for_updates()
            return
        message = (
            "Se descargará e instalará la última versión desde GitHub. "
            "WINWIZ se cerrará y volverá a abrir solo al terminar.\n\n"
            f"Versión instalada: {self._local_commit[:7]}\n"
            f"Versión nueva: {self._remote_commit[:7]}"
        )
        if not ask_confirmation(self, "Actualizar WINWIZ", message):
            return
        self._run_update()

    def _run_update(self):
        """Lanza el instalador y cierra la app para que pueda reemplazar los archivos."""
        branch = self._update_branch
        args = ["-Branch", branch]
        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
            "Startup",
            "WINWIZ.lnk",
        )
        if os.path.exists(startup):
            args.append("-StartWithWindows")
        installer = UPDATE_INSTALLER_URL.format(repo=UPDATE_REPO, branch=branch)
        command = (
            f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue "
            f"-Timeout 20; $ErrorActionPreference='Stop'; "
            f"& ([scriptblock]::Create((irm '{installer}'))) {' '.join(args)}"
        )
        self.update_button.set_state("busy")
        self._show_update_message("Descargando e instalando la actualización…")
        self.wiz_manager.flush()
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ],
                creationflags=flags,
                close_fds=True,
            )
        except OSError as error:
            _debug(f"No se pudo lanzar el instalador: {error}")
            self.update_button.set_state("available")
            show_warning(
                self,
                "Actualizar WINWIZ",
                "No se pudo iniciar el instalador. Probá reinstalar manualmente.",
            )
            return
        QTimer.singleShot(300, QApplication.instance().quit)

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
        # Si la barra de descubrimiento sigue visible, el panel debe quedar
        # abierto aunque el mouse se aleje.
        if self._discovery_running:
            return
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

        self.update_button = UpdateIconButton(self)
        self.update_button.setObjectName("updateButton")
        self.update_button.set_color(self.settings["update"]["color"])
        self.update_button.set_size(self.settings["update"]["size"])
        self.update_button.clicked.connect(self.start_update)
        btn_row.addWidget(self.update_button)

        self.settings_button = HoverButton("⚙", radius=6)
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(28, 28)
        self.settings_button.setToolTip("Ajustes de apariencia")
        self.settings_button.clicked.connect(self.open_settings)
        btn_row.addWidget(self.settings_button)

        main_layout.addLayout(btn_row)

        # Barra de estado del descubrimiento: reemplaza al modal de fin de
        # búsqueda y queda a la vista mientras se busca.
        self.discovery_bar = QFrame()
        self.discovery_bar.setObjectName("discoveryBar")
        bar_layout = QHBoxLayout(self.discovery_bar)
        bar_layout.setContentsMargins(10, 6, 6, 6)
        bar_layout.setSpacing(8)

        self.discovery_status = QLabel("")
        self.discovery_status.setObjectName("discoveryStatus")
        self.discovery_status.setWordWrap(True)
        bar_layout.addWidget(self.discovery_status, 1)

        self.discovery_action = QPushButton("")
        self.discovery_action.setObjectName("discoveryAction")
        self.discovery_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discovery_action.clicked.connect(self._run_discovery_action)
        self.discovery_action.hide()
        bar_layout.addWidget(self.discovery_action)

        self.discovery_bar.hide()
        main_layout.addWidget(self.discovery_bar)

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
            QFrame#discoveryBar {
                background-color: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 5px;
            }
            QLabel#discoveryStatus {
                color: #D8D8D8;
                font-size: 11px;
            }
            QPushButton#discoveryAction {
                background-color: rgba(120, 170, 255, 0.18);
                border: 1px solid rgba(120, 170, 255, 0.28);
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 8px;
            }
            QPushButton#discoveryAction:hover {
                background-color: rgba(120, 170, 255, 0.30);
            }
            QPushButton#discoveryAction:disabled {
                color: #7A7A7A;
                background-color: rgba(255, 255, 255, 0.05);
                border-color: rgba(255, 255, 255, 0.08);
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
            name = slider.objectName()
            slider.apply_appearance(
                self.settings,
                gradient=name == "colorSlider",
                temperature=(
                    name == "tempSlider"
                    and self.settings["temperature"]["gradient"]
                ),
            )

    def load_content(self):
        """Carga grupos y lámparas no agrupadas"""
        if QApplication.activeModalWidget() is not None:
            # Reconstruir ahora borraría las tarjetas que sostienen al diálogo.
            self._deferred_reload_timer.start()
            return

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
            group_widget.rename_requested.connect(self.handle_rename_group)
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
            empty = QWidget()
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(0, 0, 0, 0)
            empty_layout.setSpacing(0)
            empty_label = QLabel(
                "No hay luces todavía.\n"
                "Usá «Descubrir» para buscar las de tu red WiZ."
            )
            empty_label.setObjectName("emptyState")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setWordWrap(True)
            empty_layout.addWidget(empty_label)

            add_button = QPushButton("Agregar por IP")
            add_button.setObjectName("discoveryAction")
            add_button.setCursor(Qt.CursorShape.PointingHandCursor)
            add_button.setFixedHeight(24)
            add_button.clicked.connect(self.open_add_lamp_dialog)
            empty_layout.addWidget(
                add_button, 0, Qt.AlignmentFlag.AlignHCenter
            )
            empty_layout.addSpacing(16)

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

    def handle_rename_group(self, old_name, new_name):
        """El nombre del grupo es la clave del diccionario: se recarga todo."""
        if self.wiz_manager.rename_group(old_name, new_name):
            self.load_content()

    def create_group(self):
        # Mientras el diálogo modal está abierto, el panel no debe cerrarse
        # solo: si se ocultara, el diálogo quedaría huérfano.
        self.pause_auto_hide()
        try:
            dialog = GroupDialog(self.wiz_manager, self)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self.resume_auto_hide()
        if accepted:
            self.load_content()

    def start_discovery(self):
        """«Descubrir» inicia la búsqueda; durante la búsqueda pasa a «Cancelar»."""
        if self._discovery_running:
            self.cancel_discovery()
            return

        self._discovery_mode = "broadcast"
        self._manual_ip = None
        self._start_discovery_thread(
            DiscoveryThread(), "Buscando lámparas en la red"
        )

    def _start_discovery_thread(self, thread, status_text):
        self._new_count = 0
        self._updated_count = 0
        self._found_total = 0
        self._last_found_name = ""
        self._discovery_cancelled = False
        self._discovery_error = ""
        self._discovery_dots = 0
        self._discovery_running = True

        self.discover_button.setText("Cancelar")
        self.discover_button.setEnabled(True)
        # Mientras se busca, el panel no se cierra solo.
        self.pause_auto_hide()

        self._show_discovery_message(status_text)
        self._discovery_anim_timer.start()

        self.discovery_thread = thread
        thread.lamp_found.connect(self.handle_lamp_found)
        thread.error.connect(self._handle_discovery_error)
        thread.finished.connect(self.discovery_finished)
        thread.start()

    def start_manual_discovery(self, ip):
        """Consulta una IP concreta cuando el broadcast no llega."""
        if self._discovery_running:
            return
        self._discovery_mode = "manual"
        self._manual_ip = ip
        self._start_discovery_thread(
            DiscoveryThread(targets=[ip], attempts=4, listen_time=4.0),
            f"Buscando {ip}",
        )

    def cancel_discovery(self):
        thread = self.discovery_thread
        if thread is None or not thread.isRunning():
            return
        self._discovery_cancelled = True
        self._discovery_anim_timer.stop()
        self._discovery_status_base = "Cancelando"
        self.discovery_status.setText("Cancelando…")
        self.discovery_action.hide()
        thread.requestInterruption()

    def _handle_discovery_error(self, message):
        self._discovery_error = message

    def _run_discovery_action(self):
        if self._discovery_action == "manual":
            self.open_add_lamp_dialog()

    def open_add_lamp_dialog(self):
        """Pide una IP y busca solo esa dirección."""
        if self._discovery_running:
            return
        self.pause_auto_hide()
        try:
            dialog = AddLampDialog(self)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            ip = dialog.value() if accepted else None
        finally:
            self.resume_auto_hide()
        if ip:
            self.start_manual_discovery(ip)

    def _show_discovery_message(
        self, text, action=None, action_text="", timeout=None
    ):
        self._discovery_status_base = text
        self.discovery_status.setText(text)
        self._discovery_action = action
        if action and action_text:
            self.discovery_action.setText(action_text)
            self.discovery_action.show()
        else:
            self.discovery_action.hide()
        self.discovery_bar.show()
        self._discovery_status_timer.stop()
        if timeout is not None:
            self._discovery_status_timer.start(timeout)

    def _tick_discovery_status(self):
        if not self._discovery_running:
            self._discovery_anim_timer.stop()
            return
        self._discovery_dots = (self._discovery_dots + 1) % 4
        dots = "." * self._discovery_dots
        self.discovery_status.setText(
            f"{self._discovery_status_base}{dots}"
        )

    def _update_discovery_progress(self):
        """Muestra cuántas lámparas van apareciendo mientras se busca."""
        total = self._new_count + self._updated_count
        if self._discovery_mode == "manual":
            base = f"Buscando {self._manual_ip}"
        else:
            base = "Buscando lámparas"
        if total:
            found = "encontrada" if total == 1 else "encontradas"
            base = f"{base}: {total} {found}"
        self._discovery_status_base = base
        dots = "." * self._discovery_dots
        self.discovery_status.setText(f"{base}{dots}")

    def _clear_discovery_message(self):
        if self._discovery_running:
            return
        self.discovery_bar.hide()
        self._discovery_action = None
        self._discovery_status_base = ""

    def _discovery_summary(self):
        parts = []
        if self._new_count:
            parts.append(
                f"{self._new_count} "
                f"{'nueva' if self._new_count == 1 else 'nuevas'}"
            )
        if self._updated_count:
            parts.append(
                f"{self._updated_count} "
                f"{'actualizada' if self._updated_count == 1 else 'actualizadas'}"
            )
        return " y ".join(parts)

    def handle_lamp_found(self, lamp_data):
        mac = lamp_data.get("mac")
        if not mac:
            return

        status = self.wiz_manager.add_lamp(
            mac,
            lamp_data.get("ip"),
            lamp_data.get("name"),
            model=lamp_data.get("model"),
            firmware=lamp_data.get("firmware"),
            rssi=lamp_data.get("rssi"),
        )
        self._found_total += 1
        self._last_found_name = lamp_data.get("name") or mac

        if status == "new":
            self._new_count += 1
        elif status == "updated":
            self._updated_count += 1
        if status is not None:
            # Si aparecen varias lámparas seguidas, se refresca una sola vez.
            self._reload_timer.start()

        # add_lamp ya la marcó en línea; force refresca la tarjeta si estaba
        # atenuada por el heartbeat.
        self.handle_lamp_status(mac, True, force=True)

        if self._discovery_running:
            self._update_discovery_progress()

    def handle_lamp_status(self, mac, online, force=False):
        """Aplica el resultado del heartbeat a todas las tarjetas de esa lámpara."""
        changed = self.wiz_manager.set_online(mac, online)
        if not changed and not force:
            return
        for widget in self.findChildren(LampControl):
            if widget.mac == mac:
                widget.set_online(online)

    def discovery_finished(self):
        self._discovery_anim_timer.stop()
        self._reload_timer.stop()
        thread = self.discovery_thread
        self.discovery_thread = None
        if thread is not None:
            thread.deleteLater()
        self._discovery_running = False
        self.discover_button.setText("Descubrir")
        self.discover_button.setEnabled(True)

        cancelled = self._discovery_cancelled
        error = self._discovery_error
        mode = self._discovery_mode
        manual_ip = self._manual_ip
        summary = self._discovery_summary()
        found = self._found_total > 0
        found_total = self._found_total
        last_name = self._last_found_name

        # Volver al modo normal antes de mostrar el resultado.
        self._discovery_mode = "broadcast"
        self._manual_ip = None
        self._discovery_cancelled = False
        self._discovery_error = ""
        self._discovery_dots = 0
        self._new_count = 0
        self._updated_count = 0
        self._found_total = 0
        self._last_found_name = ""

        self.load_content()
        # Si hay un diálogo abierto (por ejemplo, «Renombrar») no se reactiva
        # el auto-cierre: el diálogo se cerraría junto con el panel.
        if QApplication.activeModalWidget() is None:
            self.resume_auto_hide()

        if error:
            self._show_discovery_message(
                error, action="manual", action_text="Agregar por IP"
            )
        elif cancelled:
            text = "Búsqueda cancelada."
            if summary:
                text += f" {summary}."
            self._show_discovery_message(text, timeout=4000)
        elif mode == "manual":
            if found:
                self._show_discovery_message(
                    f"Lámpara agregada: {last_name}.", timeout=5000
                )
            else:
                self._show_discovery_message(
                    f"La IP {manual_ip} no respondió.",
                    action="manual",
                    action_text="Agregar por IP",
                )
        elif summary:
            self._show_discovery_message(f"Listo: {summary}.", timeout=6000)
        elif found_total:
            if found_total == 1:
                text = "Listo: la lámpara ya estaba agregada."
            else:
                text = f"Listo: {found_total} lámparas ya estaban agregadas."
            self._show_discovery_message(text, timeout=6000)
        else:
            self._show_discovery_message(
                "No se encontraron lámparas. Revisá que estén encendidas y en "
                "la misma red.",
                action="manual",
                action_text="Agregar por IP",
            )

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

        # Crear menú contextual. El tema se aplica después de crear la
        # ventana, cuando ya se conoce el acento guardado.
        self.menu = QMenu()
        show_action = QAction("Mostrar control", self.menu)
        exit_action = QAction("Salir", self.menu)
        self.menu.addAction(show_action)
        self.menu.addAction(exit_action)
        self.icon.setContextMenu(self.menu)

        # Mostrar ícono
        self.icon.setVisible(True)

        self.window = PopupWindow(self.wiz_manager)
        self._apply_menu_theme(self.window.settings)
        self.window.appearance_changed.connect(self._apply_menu_theme)

        # Detecta lámparas que dejaron de responder (o que volvieron).
        self.heartbeat = HeartbeatThread(self.wiz_manager)
        self.heartbeat.status_changed.connect(self.window.handle_lamp_status)
        self.heartbeat.start()
        self.app.aboutToQuit.connect(self.shutdown)

        # Conexiones
        self.icon.activated.connect(self.handle_icon_click)
        show_action.triggered.connect(self.show_window)
        exit_action.triggered.connect(self.app.quit)

    def shutdown(self):
        """Corta los hilos de red antes de que muera la aplicación."""
        self.heartbeat.requestInterruption()
        self.heartbeat.wait(3000)

        discovery = getattr(self.window, "discovery_thread", None)
        if discovery is not None and discovery.isRunning():
            discovery.requestInterruption()
            discovery.wait(2000)

    def _apply_menu_theme(self, settings):
        """Mantiene el menú de la bandeja igual de oscuro que el resto."""
        apply_menu_theme(self.menu, accent_color(settings))

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