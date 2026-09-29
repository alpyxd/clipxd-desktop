import os
import sys

from PySide6.QtCore import QCoreApplication, QThread, QTimer, Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout,
                               QWidget)

from clipxd import APP_NAME, __version__


def write_icon(path: str):
    """Paketleme için .ico dosyası üretir."""
    from pathlib import Path
    from clipxd.ui.icons import app_pixmap
    _app = QGuiApplication.instance() or QGuiApplication([])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    app_pixmap(256).save(path)


def _main_window_class():
    # Qt modülleri QApplication oluşturulduktan sonra içe aktarılsın diye fabrika içinde
    from clipxd.ui.accounts_tab import AccountsPage
    from clipxd.ui.convert_tab import ConvertPage
    from clipxd.ui.download_tab import DownloadPage
    from clipxd.ui.frameless import DragFilter, FramelessMixin
    from clipxd.ui.settings_tab import SettingsPage
    from clipxd.ui.sheets import confirm
    from clipxd.ui.theme import font, set_role, theme
    from clipxd.ui.widgets import Sidebar, TrafficLights, label, styled

    class MainWindow(FramelessMixin, QWidget):
        def __init__(self, ctx):
            super().__init__()
            self.init_frameless()
            self.ctx = ctx
            self.setWindowTitle(APP_NAME)
            self.resize(1200, 860)
            self.setMinimumSize(1000, 740)
            styled(self, "root")

            root = QHBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            self.sidebar = Sidebar()
            self.sidebar.add_brand()
            self.sidebar.add_header("Araçlar")
            self.sidebar.add_item("download", "İndir")
            self.sidebar.add_item("convert", "Dönüştür")
            self.sidebar.add_header("Kitaplık")
            self.sidebar.add_item("person", "Hesaplar")
            self.sidebar.add_stretch()
            self.sidebar.add_item("sliders", "Ayarlar")
            self.status_label = QLabel()
            self.status_label.setFont(font(11))
            set_role(self.status_label, "tertiary")
            self.status_label.setContentsMargins(10, 8, 0, 0)
            self.sidebar.add_bottom(self.status_label)
            root.addWidget(self.sidebar)

            self.lights = TrafficLights(self.sidebar)
            self.lights.move(18, 18)
            self.lights.close_clicked.connect(self.close)
            self.lights.minimize_clicked.connect(self.showMinimized)
            self.lights.zoom_clicked.connect(self.toggle_maximized)
            if not self.is_frameless:
                self.lights.hide()

            vsep = styled(QWidget(), "vsep")
            vsep.setFixedWidth(1)
            root.addWidget(vsep)

            content = styled(QWidget(), "content")
            cv = QVBoxLayout(content)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(0)
            toolbar = QWidget()
            toolbar.setFixedHeight(56)
            th = QHBoxLayout(toolbar)
            th.setContentsMargins(24, 6, 18, 0)
            # sayfa başlığı; bir sayfa kendi başlık widget'ını (header) verebilir
            self.headers = QStackedWidget()
            th.addWidget(self.headers)
            th.addStretch()
            self.actions = QStackedWidget()
            th.addWidget(self.actions)
            cv.addWidget(toolbar)
            self.stack = QStackedWidget()
            cv.addWidget(self.stack, 1)
            root.addWidget(content, 1)

            self.download_page = DownloadPage(ctx)
            self.convert_page = ConvertPage(ctx)
            self.accounts_page = AccountsPage(ctx)
            self.settings_page = SettingsPage(ctx, self._settings_saved)
            self.pages = [self.download_page, self.convert_page, self.accounts_page, self.settings_page]
            for page in self.pages:
                self.stack.addWidget(page)
                header = getattr(page, "header", None) or label(page.title, 20, QFont.Bold, display=True)
                self.headers.addWidget(header)
                holder = QWidget()  # butonlar araç çubuğu yüksekliğine yayılmasın
                hl = QHBoxLayout(holder)
                hl.setContentsMargins(0, 0, 0, 0)
                if page.actions is not None:
                    hl.addWidget(page.actions, 0, Qt.AlignVCenter)
                self.actions.addWidget(holder)
            self.sidebar.current_changed.connect(self._show_page)
            self.sidebar.set_current(0)

            # boş alanlardan pencere sürüklenebilsin (macOS başlık çubuğu davranışı)
            DragFilter(self, [toolbar, self.headers, self.sidebar])
            self._update_status()

        def _show_page(self, idx: int):
            self.stack.setCurrentIndex(idx)
            self.actions.setCurrentIndex(idx)
            self.headers.setCurrentIndex(idx)
            w = self.actions.currentWidget()
            self.actions.setFixedWidth(max(0, w.sizeHint().width()))

        def _update_status(self):
            from yt_dlp.version import __version__ as ytv
            ff = "ffmpeg hazır" if self.ctx.ffmpeg else "ffmpeg bulunamadı"
            color = theme.css("success" if self.ctx.ffmpeg else "danger")
            self.status_label.setText(f"<span style='color:{color}'>●</span> {ff}<br>yt-dlp {ytv} · v{__version__}")

        def _settings_saved(self):
            self._update_status()

        def closeEvent(self, event):
            active = self.download_page.active_count() + self.convert_page.active_count()
            if active and not confirm(self, "Çıkılsın mı?", f"{active} iş devam ediyor. Çıkarsanız iptal edilecek.",
                                      ok="Çık", destructive=True, kind="warning"):
                event.ignore()
                return
            self.ctx.download_pool.clear()  # henüz başlamamış işleri kuyruktan at
            self.ctx.convert_pool.clear()
            self.download_page.cancel_all()
            self.convert_page.cancel_all()
            for page in (self.download_page, self.convert_page):
                try:
                    page.shutdown()  # tercihleri kaydet; disk hatası çıkışı engellemesin
                except OSError as e:
                    print(f"Tercihler kaydedilemedi: {e}", file=sys.stderr)
            event.accept()
            if active:
                # iptal sinyali kısa sürede işlenir; takılan bir iş (ör. ffmpeg birleştirme) çıkışı engellemesin
                self.ctx.download_pool.waitForDone(4000)
                self.ctx.convert_pool.waitForDone(2000)
                if self.ctx.download_pool.activeThreadCount() or self.ctx.convert_pool.activeThreadCount():
                    os._exit(0)

    return MainWindow


def _setup_logging():
    """pythonw / paketlenmiş sürümde stdout-stderr yoktur; çıktıları günlük dosyasına yönlendir."""
    import traceback
    from clipxd.paths import data_dir

    if sys.stdout is None or sys.stderr is None:
        log_path = data_dir() / "clipxd.log"
        try:
            if log_path.exists() and log_path.stat().st_size > 1_000_000:
                log_path.unlink()
            log = open(log_path, "a", encoding="utf-8", buffering=1)
        except OSError:
            log = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        print(text, file=sys.stderr)
        app = QApplication.instance()
        # Pencere yalnızca ana iş parçacığında açılabilir; arka plandan açmak uygulamayı çökertir
        if app is not None and QThread.currentThread() is app.thread():
            QMessageBox.critical(None, "Beklenmeyen hata", text[-2000:])

    sys.excepthook = excepthook


def create_app(argv=None) -> QApplication:
    if os.name == "nt":
        try:  # görev çubuğunda Python yerine uygulama simgesi görünsün
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ClipXD.Desktop")
        except Exception:
            pass
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401  (QApplication'dan önce yüklenmeli)
    except ImportError:
        pass
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    from clipxd.ui.icons import app_icon
    from clipxd.ui.theme import font
    app.setFont(font(13))
    app.setWindowIcon(app_icon())
    return app


def build_main_window(ctx):
    from clipxd.ui.theme import theme
    theme.apply(ctx.settings["theme"])
    return _main_window_class()(ctx)


def _single_instance():
    """İkinci kopya açılırsa ilkini öne getirip kapanır.

    İki kopya aynı anda çalışırsa hesap ve ayar dosyalarını birbirinin üzerine yazıp
    eklenen hesapları kaybettirebilir. Dönüş: sunucu (ilk kopya) veya None (zaten açık).
    """
    import hashlib
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from clipxd.paths import data_dir

    name = "ClipXD-" + hashlib.sha1(str(data_dir()).lower().encode("utf-8")).hexdigest()[:16]
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return None
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)  # yalnızca aynı Windows kullanıcısı
    QLocalServer.removeServer(name)
    server.listen(name)
    return server


def main():
    _setup_logging()
    if "--self-test" in sys.argv:  # arayüzsüz paket doğrulaması (bkz. clipxd/selftest.py)
        from clipxd.selftest import run
        sys.exit(run(sys.argv))
    app = create_app()
    server = _single_instance()
    if server is None:
        sys.exit(0)
    from clipxd.context import AppContext
    ctx = AppContext()
    win = build_main_window(ctx)

    def bring_to_front():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        if win.isMinimized():
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()

    server.newConnection.connect(bring_to_front)
    win.show()
    if ctx.accounts.load_error:
        from clipxd.ui.sheets import alert
        QTimer.singleShot(400, lambda: alert(win, "Hesap listesi okunamadı", ctx.accounts.load_error,
                                             kind="warning"))
    sys.exit(app.exec())
