"""macOS tarzı çerçevesiz pencere (Windows).

Windows başlık çubuğu kaldırılır ama pencere stili korunur; böylece yerel gölge,
Windows 11 yuvarlak köşeleri, kenara yaslama (Snap), küçültme/büyütme animasyonları
ve kenarlardan yeniden boyutlandırma çalışmaya devam eder. Diğer sistemlerde normal
pencere çerçevesi kullanılır.
"""
import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwm = ctypes.WinDLL("dwmapi")

    class _MARGINS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]

    class _NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class _MINMAXINFO(ctypes.Structure):
        _fields_ = [("ptReserved", wintypes.POINT), ("ptMaxSize", wintypes.POINT),
                    ("ptMaxPosition", wintypes.POINT), ("ptMinTrackSize", wintypes.POINT),
                    ("ptMaxTrackSize", wintypes.POINT)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    _user32.GetDpiForWindow.restype = wintypes.UINT
    _user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(_MARGINS)]
    _dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    _GWL_STYLE = -16
    _WS_CAPTION, _WS_THICKFRAME, _WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
    _WS_MINIMIZEBOX, _WS_MAXIMIZEBOX = 0x00020000, 0x00010000
    _SWP = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
    _WM_GETMINMAXINFO, _WM_NCCALCSIZE, _WM_NCHITTEST = 0x0024, 0x0083, 0x0084
    _HT = {"l": 10, "r": 11, "t": 12, "tl": 13, "tr": 14, "b": 15, "bl": 16, "br": 17}
    _DWMWA_DARK, _DWMWA_CORNER, _DWMWA_BORDER = 20, 33, 34

    def _monitor_info(hwnd):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        _user32.GetMonitorInfoW(_user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # 2 = EN YAKIN
        return info


class FramelessMixin:
    """QWidget/QDialog alt sınıflarına eklenir: class W(FramelessMixin, QWidget)."""

    RESIZE_BORDER = 6

    def init_frameless(self, resizable: bool = True):
        self._fl_resizable = resizable
        self._fl_applied = False
        if IS_WINDOWS:
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

    @property
    def is_frameless(self) -> bool:
        return IS_WINDOWS

    def _fl_apply(self):
        if not IS_WINDOWS:
            return
        hwnd = int(self.winId())
        style = _user32.GetWindowLongPtrW(hwnd, _GWL_STYLE)
        wanted = _WS_CAPTION | _WS_THICKFRAME | _WS_SYSMENU | _WS_MINIMIZEBOX
        if self._fl_resizable:
            wanted |= _WS_MAXIMIZEBOX
        if style & wanted != wanted:
            _user32.SetWindowLongPtrW(hwnd, _GWL_STYLE, style | wanted)
        if not self._fl_applied:
            margins = _MARGINS(-1, -1, -1, -1)  # gölge için DWM çerçevesini istemci alanına yay
            _dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
            corner = ctypes.c_int(2)  # DWMWCP_ROUND (Windows 11)
            _dwm.DwmSetWindowAttribute(hwnd, _DWMWA_CORNER, ctypes.byref(corner), 4)
            _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, _SWP)
            self._fl_applied = True

    def set_native_dark(self, dark: bool, border_hex: str | None = None):
        if not IS_WINDOWS or not self._fl_applied:
            return
        hwnd = int(self.winId())
        val = ctypes.c_int(1 if dark else 0)
        _dwm.DwmSetWindowAttribute(hwnd, _DWMWA_DARK, ctypes.byref(val), 4)
        if border_hex:
            h = border_hex.lstrip("#")
            colorref = ctypes.c_uint(int(h[4:6] + h[2:4] + h[0:2], 16))  # 0x00BBGGRR
            _dwm.DwmSetWindowAttribute(hwnd, _DWMWA_BORDER, ctypes.byref(colorref), 4)

    def toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def showEvent(self, event):
        super().showEvent(event)
        if IS_WINDOWS and not self._fl_applied:
            self._fl_apply()
            self._fl_theme_hook()

    def _fl_theme_hook(self):
        from clipxd.ui.theme import theme
        self._fl_sync_theme()
        theme.changed.connect(self._fl_sync_theme)  # bağlı metot: pencere silinince bağlantı da kalkar

    def _fl_sync_theme(self):
        from clipxd.ui.theme import theme
        self.set_native_dark(theme.dark, theme.t["card_border"])

    def changeEvent(self, event):
        super().changeEvent(event)
        if IS_WINDOWS and event.type() == QEvent.WindowStateChange and self._fl_applied:
            self._fl_apply()  # Qt bazı durum değişikliklerinde stili sıfırlayabilir

    def nativeEvent(self, event_type, message):
        if IS_WINDOWS and bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_GETMINMAXINFO:
                # Büyütülünce pencere tam olarak çalışma alanını (görev çubuğu hariç) kaplasın.
                # Bunu biz belirlemezsek konum bazen Windows'a (kenarlıklar ekran dışına taşar),
                # bazen Qt'ye kalır ve sonuç tutarsız olur.
                mon = _monitor_info(msg.hWnd)
                mmi = _MINMAXINFO.from_address(msg.lParam)
                work, full = mon.rcWork, mon.rcMonitor
                mmi.ptMaxPosition.x, mmi.ptMaxPosition.y = work.left - full.left, work.top - full.top
                mmi.ptMaxSize.x, mmi.ptMaxSize.y = work.right - work.left, work.bottom - work.top
                dpr = self.devicePixelRatioF()
                mmi.ptMinTrackSize.x = round(self.minimumWidth() * dpr)
                mmi.ptMinTrackSize.y = round(self.minimumHeight() * dpr)
                return True, 0
            if msg.message == _WM_NCCALCSIZE:
                if msg.wParam and _user32.IsZoomed(msg.hWnd):
                    # Güvenlik: pencere yine de ekran dışına taşarsa istemci alanını çalışma alanıyla sınırla
                    work = _monitor_info(msg.hWnd).rcWork
                    rect = _NCCALCSIZE_PARAMS.from_address(msg.lParam).rgrc[0]
                    rect.left, rect.top = max(rect.left, work.left), max(rect.top, work.top)
                    rect.right, rect.bottom = min(rect.right, work.right), min(rect.bottom, work.bottom)
                return True, 0  # başlık çubuğu yok: tüm pencere istemci alanı
            if msg.message == _WM_NCHITTEST and self._fl_resizable and not (self.isMaximized() or self.isFullScreen()):
                pos = QCursor.pos()
                x, y = pos.x() - self.x(), pos.y() - self.y()
                w, h, b = self.width(), self.height(), self.RESIZE_BORDER
                edge = ("t" if y < b else "b" if y >= h - b else "") + ("l" if x < b else "r" if x >= w - b else "")
                if edge:
                    return True, _HT[edge]
        return super().nativeEvent(event_type, message)


class DragFilter(QObject):
    """Boş alana basılı tutup sürükleyince pencereyi taşır, çift tıklayınca büyütür."""

    def __init__(self, window, widgets):
        super().__init__(window)
        self.window = window
        for w in widgets:
            w.installEventFilter(self)

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            handle = self.window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return True
        elif t == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            if getattr(self.window, "_fl_resizable", True):
                self.window.toggle_maximized()
            return True
        return False
