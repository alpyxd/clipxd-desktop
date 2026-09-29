"""Safari tarzı uygulama içi giriş penceresi.

Gizli (off-the-record) bir QtWebEngine profili kullanır: çerezler, geçmiş ve önbellek
diske yazılmaz. Kullanıcı normal şekilde giriş yapar, oturum çerezleri yakalanır ve
yalnızca platformun alan adlarına ait olanlar hesap olarak saklanır. Şifre hiçbir
zaman uygulamaya ulaşmaz; sadece sitenin kendi sayfasına yazılır.
"""
import re

import shiboken6
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QToolTip,
                               QVBoxLayout, QWidget)

from clipxd import accounts as acc
from clipxd.ui import icons
from clipxd.ui.frameless import DragFilter, FramelessMixin
from clipxd.ui.sheets import confirm, alert
from clipxd.ui.theme import font, set_role, theme
from clipxd.ui.widgets import IconButton, TrafficLights, label, safe_tooltip, styled


class _Page(QWebEnginePage):
    def createWindow(self, _type):
        # "Google ile giriş" gibi açılır pencereleri aynı görünümde aç
        return self


class AddressField(QWidget):
    """Safari'nin akıllı arama alanı: ortada kilit + alan adı, altta yükleme çubuğu."""

    navigate = Signal(str)
    reload_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setMinimumWidth(300)
        self.setMaximumWidth(680)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.IBeamCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._url = QUrl()
        self._progress = 100
        self.editing = False
        self.edit = QLineEdit(self)
        self.edit.setObjectName("bare")
        self.edit.setFont(font(13))
        self.edit.hide()
        self.edit.returnPressed.connect(self._submit)
        self.edit.installEventFilter(self)
        self.btn = IconButton("retry", "Sayfayı yeniden yükle", 24, 13, parent=self)
        self.btn.clicked.connect(self._btn_clicked)

    def set_url(self, url: QUrl):
        self._url = url
        self.setToolTip(safe_tooltip(url.toString()))
        self.update()

    def set_progress(self, p: int):
        self._progress = p
        loading = p < 100
        self.btn.set_icon("xmark" if loading else "retry")
        self.btn.setToolTip("Yüklemeyi durdur" if loading else "Sayfayı yeniden yükle")
        self.update()

    def _btn_clicked(self):
        (self.stop_requested if self._progress < 100 else self.reload_requested).emit()

    def resizeEvent(self, e):
        self.btn.move(self.width() - 28, 4)
        self.edit.setGeometry(10, 3, self.width() - 42, 26)

    def mousePressEvent(self, e):
        if not self.editing:
            self.editing = True
            self.edit.setText(self._url.toString())
            self.edit.show()
            self.edit.setFocus()
            self.edit.selectAll()
            self.update()

    def _end_edit(self):
        self.editing = False
        self.edit.hide()
        self.update()

    def _submit(self):
        text = self.edit.text().strip()
        if text and "://" not in text:
            text = "https://" + text
        url = QUrl(text)
        if url.isValid() and url.scheme() in ("http", "https"):
            self.navigate.emit(url.toString())
        self._end_edit()

    def eventFilter(self, obj, e):
        if obj is self.edit:
            if e.type() == QEvent.FocusOut:
                self._end_edit()
            elif e.type() == QEvent.KeyPress and e.key() == Qt.Key_Escape:
                self._end_edit()
                return True
        return False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        if self.editing:
            p.setPen(QPen(theme.c("accent"), 2))
            p.setBrush(theme.c("field"))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 7, 7)
            return
        p.setPen(Qt.NoPen)
        base = theme.c("addr")
        if self.underMouse():
            base = base.darker(104) if not theme.dark else base.lighter(112)
        p.setBrush(base)
        p.drawPath(path)
        if 0 < self._progress < 100:
            p.save()
            p.setClipPath(path)
            p.setBrush(theme.c("accent"))
            p.drawRect(QRectF(0, r.bottom() - 2.5, r.width() * self._progress / 100, 3))
            p.restore()
        host = self._url.host().removeprefix("www.")
        secure = self._url.scheme() == "https"
        text = host or self._url.toString() or "Yükleniyor…"
        f = font(13, QFont.Medium)
        fm = QFontMetrics(f)
        max_w = int(r.width() - 80)
        text = fm.elidedText(text, Qt.ElideMiddle, max_w)
        icon_w = 14 if secure else 0
        total = icon_w + (5 if secure else 0) + fm.horizontalAdvance(text)
        x = (r.width() - total) / 2
        if secure:
            icons.paint(p, "lock", QRectF(x, (r.height() - 13) / 2, 13, 13), theme.c("text2"), 1.8)
            x += icon_w + 5
        p.setFont(f)
        p.setPen(theme.c("text"))
        p.drawText(QRectF(x, 0, r.width() - x, r.height()), Qt.AlignVCenter | Qt.AlignLeft, text)


class BrowserWindow(FramelessMixin, QDialog):
    def __init__(self, platform: acc.Platform, parent=None):
        super().__init__(parent)
        self.init_frameless()
        self.setObjectName("browser")
        self.platform = platform
        self.jar = None
        self._cookies = {}
        self._torn_down = False
        self.setWindowTitle(f"{platform.name} — Giriş")
        self.resize(1100, 800)
        self.setMinimumSize(780, 560)

        self.profile = QWebEngineProfile()  # isimsiz profil = gizli mod, diske yazmaz
        ua = self.profile.httpUserAgent()
        self.profile.setHttpUserAgent(re.sub(r"\s*QtWebEngine/\S+", "", ua))
        store = self.profile.cookieStore()
        store.cookieAdded.connect(self._cookie_added)
        store.cookieRemoved.connect(self._cookie_removed)
        self.view = QWebEngineView()
        self.page = _Page(self.profile, self.view)
        self.view.setPage(self.page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Safari araç çubuğu
        bar = styled(QWidget(), "browserBar")
        bar.setFixedHeight(52)
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(18, 0, 14, 0)
        bh.setSpacing(4)
        lights = TrafficLights(bar)
        lights.close_clicked.connect(self.reject)
        lights.minimize_clicked.connect(self.showMinimized)
        lights.zoom_clicked.connect(self.toggle_maximized)
        if not self.is_frameless:
            lights.hide()
        bh.addWidget(lights)
        bh.addSpacing(16)
        self.back_btn = IconButton("chevron_left", "Geri", 30, 18, color_key="text")
        self.fwd_btn = IconButton("chevron_right", "İleri", 30, 18, color_key="text")
        self.back_btn.clicked.connect(self.view.back)
        self.fwd_btn.clicked.connect(self.view.forward)
        bh.addWidget(self.back_btn)
        bh.addWidget(self.fwd_btn)
        bh.addStretch(1)
        self.address = AddressField()
        self.address.navigate.connect(lambda u: self.view.load(QUrl(u)))
        self.address.reload_requested.connect(self.view.reload)
        self.address.stop_requested.connect(self.view.stop)
        bh.addWidget(self.address, 5)
        bh.addStretch(1)
        share = IconButton("share", "Bağlantıyı kopyala", 30, 18, color_key="text")
        share.clicked.connect(self._copy_link)
        bh.addWidget(share)
        layout.addWidget(bar)
        DragFilter(self, [bar])

        layout.addWidget(self.view, 1)

        # --- alt bilgi çubuğu
        footer = styled(QWidget(), "browserFooter")
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(18, 10, 16, 10)
        fh.setSpacing(12)
        self.shield = QLabel()
        fh.addWidget(self.shield)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(label(f"{platform.name} hesabınıza giriş yapın", 13, QFont.DemiBold))
        domain = platform.domains[0] if platform.domains else "site"
        texts.addWidget(label(f"Şifreniz yalnızca {domain} adresine gönderilir; ClipXD şifrenizi görmez ve "
                              "saklamaz. İki adımlı doğrulama desteklenir.", 11.5, role="secondary"))
        fh.addLayout(texts, 1)
        self.status = QLabel()
        self.status.setFont(font(12, QFont.Medium))
        fh.addWidget(self.status)
        fh.addSpacing(6)
        cancel = QPushButton("Vazgeç")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self.finish_btn = QPushButton("Girişi Tamamladım")
        self.finish_btn.setObjectName("primary")
        self.finish_btn.setCursor(Qt.PointingHandCursor)
        self.finish_btn.clicked.connect(self._finish)
        fh.addWidget(cancel)
        fh.addWidget(self.finish_btn)
        layout.addWidget(footer)

        self.view.urlChanged.connect(self._url_changed)
        self.view.loadStarted.connect(lambda: self.address.set_progress(1))
        self.view.loadProgress.connect(lambda v: self.address.set_progress(max(1, min(99, v))))
        self.view.loadFinished.connect(lambda _: (self.address.set_progress(100), self._update_nav()))
        self.view.titleChanged.connect(lambda t: self.setWindowTitle(t or platform.name))
        self._paint_icons()
        theme.changed.connect(self._paint_icons)
        self._update_status()
        self._update_nav()
        self.address.set_url(QUrl(platform.login_url))
        self.view.load(QUrl(platform.login_url))

    def _paint_icons(self):
        if not self._torn_down:
            self.shield.setPixmap(icons.pixmap("shield", theme.c("accent"), 26, 1.6))

    def _url_changed(self, url: QUrl):
        self.address.set_url(url)
        self._update_nav()

    def _update_nav(self):
        if self._torn_down:
            return
        h = self.view.history()
        self.back_btn.setEnabled(h.canGoBack())
        self.fwd_btn.setEnabled(h.canGoForward())

    def _copy_link(self):
        QGuiApplication.clipboard().setText(self.view.url().toString())
        QToolTip.showText(QCursor.pos(), "Bağlantı kopyalandı", self)

    # --- çerez takibi
    @staticmethod
    def _key(c):
        return c.domain(), c.path(), bytes(c.name()).decode("utf-8", "replace")

    def _cookie_added(self, cookie):
        self._cookies[self._key(cookie)] = type(cookie)(cookie)  # kopya sakla
        self._update_status()

    def _cookie_removed(self, cookie):
        self._cookies.pop(self._key(cookie), None)
        self._update_status()

    def _build_jar(self):
        jar = acc.new_jar()
        for c in self._cookies.values():
            domain = c.domain()
            if not domain:
                continue
            expires = None if c.isSessionCookie() else int(c.expirationDate().toSecsSinceEpoch())
            jar.set_cookie(acc.make_cookie(
                domain, bytes(c.name()).decode("utf-8", "replace"), bytes(c.value()).decode("utf-8", "replace"),
                c.path() or "/", c.isSecure(), expires, c.isHttpOnly()))
        return acc.filter_jar(jar, self.platform.domains)

    def _update_status(self):
        if self._torn_down:
            return
        ok, text = acc.auth_cookie_status(self._build_jar(), self.platform)
        if ok:
            self.status.setText("✓ Oturum algılandı")
            set_role(self.status, "success")
        elif ok is None:
            self.status.setText(text)
            set_role(self.status, "secondary")
        else:
            self.status.setText("Giriş bekleniyor…")
            set_role(self.status, "tertiary")

    def _finish(self):
        jar = self._build_jar()
        ok, text = acc.auth_cookie_status(jar, self.platform)
        if not len(jar):
            alert(self, "Çerez alınamadı", "Bu siteden hiç çerez alınamadı. Giriş yaptığınızdan emin olun.",
                  kind="warning")
            return
        if ok is False and not confirm(self, "Oturum algılanmadı",
                                       f"{text}. Giriş tamamlanmadıysa gizli içerikler indirilemez. Yine de "
                                       "kaydedilsin mi?", ok="Kaydet", kind="warning"):
            return
        self.jar = jar
        self.accept()

    def done(self, result):
        self._teardown()
        super().done(result)

    def _teardown(self):
        # Sayfa, profilden önce silinmeli; aksi halde QtWebEngine uyarı verir / çökebilir.
        if self._torn_down:
            return
        self._torn_down = True
        try:
            theme.changed.disconnect(self._paint_icons)
        except (RuntimeError, TypeError):
            pass
        self.view.stop()
        if shiboken6.isValid(self.view):
            shiboken6.delete(self.view)  # sayfayı da siler (sayfanın ebeveyni görünüm)
        if shiboken6.isValid(self.profile):
            shiboken6.delete(self.profile)
        self._cookies.clear()


# geriye dönük uyumluluk
LoginDialog = BrowserWindow
