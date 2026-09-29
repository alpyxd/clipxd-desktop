"""Apple (macOS) tarzı açık/koyu tema: renk jetonları, palet ve stil sayfası."""
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

LIGHT = {
    "window": "#F5F5F7", "sidebar": "#EBEBEF", "sidebar_sel": "#DCDCE1", "toolbar": "#F5F5F7",
    "card": "#FFFFFF", "card_border": "#E2E2E7", "sep": "#E5E5EA",
    "text": "#1D1D1F", "text2": "#6E6E73", "text3": "#AEAEB2",
    "accent": "#6E4BFF", "accent_hover": "#5E3BF2", "accent_pressed": "#4F2FDB",  # ClipXD moru
    "success": "#34C759", "danger": "#FF3B30", "warning": "#FF9500",
    "field": "#FFFFFF", "field_border": "#D2D2D7", "control": "#FFFFFF", "control_border": "#D1D1D6",
    "control_hover": "#F2F2F5", "segment_bg": "#E3E3E8", "segment_sel": "#FFFFFF", "toggle_off": "#E0E0E5",
    "addr": "#E6E6EA", "browser_bar": "#F6F6F8", "hover": (0, 0, 0, 0.055), "pressed": (0, 0, 0, 0.10),
    "tl_inactive": "#D6D6D9", "dim": (0, 0, 0, 0.22), "scroll": (0, 0, 0, 0.28),
}
DARK = {
    "window": "#1E1E20", "sidebar": "#29292C", "sidebar_sel": "#3B3B3F", "toolbar": "#1E1E20",
    "card": "#2A2A2D", "card_border": "#3A3A3D", "sep": "#3A3A3C",
    "text": "#F5F5F7", "text2": "#A1A1A6", "text3": "#68686D",
    "accent": "#7F5CFF", "accent_hover": "#9377FF", "accent_pressed": "#6A47F0",  # ClipXD moru
    "success": "#30D158", "danger": "#FF453A", "warning": "#FF9F0A",
    "field": "#1F1F21", "field_border": "#4A4A4D", "control": "#3A3A3D", "control_border": "#4B4B4F",
    "control_hover": "#444448", "segment_bg": "#1C1C1E", "segment_sel": "#5A5A5F", "toggle_off": "#3E3E42",
    "addr": "#3A3A3D", "browser_bar": "#2C2C2F", "hover": (255, 255, 255, 0.07), "pressed": (255, 255, 255, 0.12),
    "tl_inactive": "#4A4A4E", "dim": (0, 0, 0, 0.45), "scroll": (255, 255, 255, 0.28),
}

UI_FAMILIES = ["SF Pro Text", "Inter", "Segoe UI Variable Text", "Segoe UI"]
DISPLAY_FAMILIES = ["SF Pro Display", "Inter", "Segoe UI Variable Display", "Segoe UI"]
MONO_FAMILIES = ["SF Mono", "Cascadia Mono", "Consolas"]


def font(px: float, weight=QFont.Normal, display: bool = False, mono: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else DISPLAY_FAMILIES if display else UI_FAMILIES)
    f.setPixelSize(round(px))
    f.setWeight(weight)
    return f


def set_font(widget: QWidget, px: float, weight=QFont.Normal, display: bool = False):
    widget.setFont(font(px, weight, display))


def set_role(widget: QWidget, role: str):
    """QSS'te QLabel[role=...] ile renklendirme (secondary, tertiary, danger, success, accent)."""
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode = "system"
        self.dark = False
        self.t = LIGHT
        self._listening = False
        self.cache_dir: Path | None = None

    # --- renk erişimi
    def c(self, key: str, alpha: float | None = None) -> QColor:
        v = self.t[key]
        if isinstance(v, tuple):
            col = QColor(v[0], v[1], v[2])
            col.setAlphaF(v[3])
        else:
            col = QColor(v)
        if alpha is not None:
            col.setAlphaF(alpha)
        return col

    def css(self, key: str, alpha: float | None = None) -> str:
        col = self.c(key, alpha)
        return f"rgba({col.red()},{col.green()},{col.blue()},{col.alphaF():.3f})"

    # --- uygulama
    def apply(self, mode: str):
        self.mode = mode
        app = QApplication.instance()
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "setColorScheme"):  # Qt 6.8+: web içeriği ve yerel diyaloglar da uyum sağlar
            scheme = {"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}.get(mode, Qt.ColorScheme.Unknown)
            hints.setColorScheme(scheme)
        if not self._listening:
            hints.colorSchemeChanged.connect(self._system_changed)
            self._listening = True
        self.dark = mode == "dark" or (mode == "system" and hints.colorScheme() == Qt.ColorScheme.Dark)
        self.t = DARK if self.dark else LIGHT
        app.setPalette(self._palette())
        app.setStyleSheet(self._qss())
        self.changed.emit()
        for w in app.allWidgets():
            w.update()

    def _system_changed(self, *_):
        if self.mode == "system":
            dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
            if dark != self.dark:
                self.apply("system")

    def _palette(self) -> QPalette:
        p = QPalette()
        roles = {
            QPalette.Window: "window", QPalette.WindowText: "text", QPalette.Base: "field",
            QPalette.AlternateBase: "window", QPalette.Text: "text", QPalette.Button: "control",
            QPalette.ButtonText: "text", QPalette.Highlight: "accent", QPalette.ToolTipBase: "card",
            QPalette.ToolTipText: "text", QPalette.PlaceholderText: "text3", QPalette.Link: "accent",
            QPalette.Mid: "sep", QPalette.Midlight: "sep", QPalette.Light: "card", QPalette.Dark: "control_border",
        }
        for role, key in roles.items():
            p.setColor(role, self.c(key))
        p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            p.setColor(QPalette.Disabled, role, self.c("text3"))
        return p

    def _icon_file(self, name: str, color: str) -> str:
        from clipxd.ui import icons
        from clipxd.paths import data_dir
        folder = self.cache_dir or data_dir() / "cache"
        path = folder / f"{name}_{color.strip('#')}.svg"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(icons.svg(name, color, 2.2), encoding="utf-8")
        except OSError:
            return ""  # klasör yazılamıyorsa açılır menü oku olmadan devam et (çökme yerine)
        return path.as_posix()

    def _qss(self) -> str:
        c = lambda k, a=None: self.css(k, a)  # noqa: E731
        chevrons = self._icon_file("chevrons_updown", self.t["text2"])
        chevrons_off = self._icon_file("chevrons_updown", self.t["text3"])
        return f"""
* {{ outline: none; }}
QWidget {{ color: {c('text')}; }}
QWidget#root, QDialog#browser {{ background: {c('window')}; }}
QWidget#sidebar {{ background: {c('sidebar')}; }}
QWidget#content, QWidget#page {{ background: {c('window')}; }}
QWidget#vsep {{ background: {c('card_border')}; }}
QWidget#sep {{ background: {c('sep')}; }}
QFrame#card {{ background: {c('card')}; border: 1px solid {c('card_border')}; border-radius: 12px; }}
QFrame#sheet {{ background: {c('card')}; border: 1px solid {c('card_border')}; border-radius: 14px; }}
QFrame#dropZone {{ background: transparent; border: 2px dashed {c('field_border')}; border-radius: 14px; }}
QFrame#dropZone[active="true"] {{ border-color: {c('accent')}; background: {c('accent', 0.06)}; }}
QFrame#urlCard {{ background: {c('card')}; border: 1px solid {c('card_border')}; border-radius: 14px; }}
QFrame#urlCard[focus="true"] {{ border: 1px solid {c('accent')}; }}
QWidget#browserBar {{ background: {c('browser_bar')}; border-bottom: 1px solid {c('sep')}; }}
QWidget#browserFooter {{ background: {c('browser_bar')}; border-top: 1px solid {c('sep')}; }}

QLabel[role="secondary"] {{ color: {c('text2')}; }}
QLabel[role="tertiary"] {{ color: {c('text3')}; }}
QLabel[role="danger"] {{ color: {c('danger')}; }}
QLabel[role="success"] {{ color: {c('success')}; }}
QLabel[role="accent"] {{ color: {c('accent')}; }}
QLabel[role="warning"] {{ color: {c('warning')}; }}
QLabel:disabled {{ color: {c('text3')}; }}

QLineEdit, QPlainTextEdit {{
    background: {c('field')}; border: 1px solid {c('field_border')}; border-radius: 7px;
    padding: 5px 8px; selection-background-color: {c('accent')}; selection-color: #FFFFFF;
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {c('accent')}; }}
QLineEdit:disabled {{ color: {c('text3')}; background: {c('window')}; }}
QPlainTextEdit#bare, QLineEdit#bare {{ background: transparent; border: none; padding: 2px; }}
QPlainTextEdit#log {{ background: {c('card')}; border: 1px solid {c('card_border')}; border-radius: 10px;
    padding: 8px; color: {c('text2')}; }}

QComboBox {{
    background: {c('control')}; border: 1px solid {c('control_border')}; border-radius: 6px;
    padding: 3px 24px 3px 10px; min-height: 20px;
}}
QComboBox:hover {{ background: {c('control_hover')}; }}
QComboBox:disabled {{ color: {c('text3')}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }}
QComboBox::down-arrow {{ image: url("{chevrons}"); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled {{ image: url("{chevrons_off}"); }}
QComboBox QAbstractItemView {{
    background: {c('card')}; border: 1px solid {c('card_border')}; padding: 4px;
    selection-background-color: {c('accent')}; selection-color: #FFFFFF; outline: none;
}}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 0 8px; border-radius: 5px; }}
QComboBox QAbstractItemView::item:disabled {{ color: {c('text3')}; }}

QPushButton {{
    background: {c('control')}; border: 1px solid {c('control_border')}; border-radius: 6px;
    padding: 4px 14px; min-height: 20px;
}}
QPushButton:hover {{ background: {c('control_hover')}; }}
QPushButton:pressed {{ background: {c('pressed')}; }}
QPushButton:disabled {{ color: {c('text3')}; }}
QPushButton#primary {{
    background: {c('accent')}; color: #FFFFFF; border: none; border-radius: 7px; padding: 5px 16px;
}}
QPushButton#primary:hover {{ background: {c('accent_hover')}; }}
QPushButton#primary:pressed {{ background: {c('accent_pressed')}; }}
QPushButton#primary:disabled {{ background: {c('control')}; color: {c('text3')}; }}
QPushButton#pill {{
    background: {c('accent')}; color: #FFFFFF; border: none; border-radius: 17px;
    padding: 7px 22px; min-height: 20px;
}}
QPushButton#pill:hover {{ background: {c('accent_hover')}; }}
QPushButton#pill:pressed {{ background: {c('accent_pressed')}; }}
QPushButton#pill:disabled {{ background: {c('control')}; color: {c('text3')}; }}
QPushButton#link {{ background: transparent; border: none; color: {c('accent')}; padding: 2px 4px; }}
QPushButton#link:hover {{ color: {c('accent_hover')}; }}
QPushButton#link:disabled {{ color: {c('text3')}; }}
QPushButton#destructive {{ color: {c('danger')}; }}

QProgressBar {{ background: {c('sep')}; border: none; border-radius: 2px; min-height: 4px; max-height: 4px; }}
QProgressBar::chunk {{ background: {c('accent')}; border-radius: 2px; }}

QListWidget#entries {{ background: transparent; border: none; outline: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget#scrollBody {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px 2px 2px 0; }}
QScrollBar::handle:vertical {{ background: {c('scroll')}; border-radius: 3px; min-height: 32px; margin: 0 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0 2px 2px 2px; }}
QScrollBar::handle:horizontal {{ background: {c('scroll')}; border-radius: 3px; min-width: 32px; margin: 2px 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QToolTip {{ background: {c('card')}; color: {c('text')}; border: 1px solid {c('card_border')};
    border-radius: 6px; padding: 4px 8px; }}
QMenu {{ background: {c('card')}; border: 1px solid {c('card_border')}; border-radius: 9px; padding: 5px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c('accent')}; color: #FFFFFF; }}
QMenu::item:disabled {{ color: {c('text3')}; }}
QMenu::separator {{ height: 1px; background: {c('sep')}; margin: 4px 8px; }}
"""


theme = ThemeManager()
