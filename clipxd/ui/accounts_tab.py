import html

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from clipxd import accounts as acc
from clipxd import secure_store
from clipxd.ui import icons
from clipxd.ui.common import fill_combo, hint_label
from clipxd.ui.platforms import platform_tile
from clipxd.ui.sheets import Sheet, alert, confirm
from clipxd.ui.theme import font, set_role, theme
from clipxd.ui.widgets import (Card, EmptyState, IconButton, PopupCombo, Segmented, Tile, label, safe_tooltip,
                                 section, styled)

METHOD_LABELS = {"login": "Uygulama içi giriş", "browser": "Tarayıcıdan aktarıldı", "file": "cookies.txt"}


def webengine_available() -> bool:
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
        return True
    except ImportError:
        return False


class PlatformButton(QAbstractButton):
    def __init__(self, platform: acc.Platform):
        super().__init__()
        self.platform = platform
        self.setCheckable(True)
        self.setFixedSize(70, 72)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(platform.name)
        self.tile = platform_tile(platform.key, 40)
        self.tile.setParent(self)
        self.tile.move(15, 6)
        self.tile.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.isChecked():
            p.setPen(QPen(theme.c("accent"), 2))
            p.setBrush(theme.c("accent", 0.08))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
        name = "Diğer" if self.platform.key == "custom" else self.platform.name.split(" (")[0]
        p.setPen(theme.c("text"))
        p.setFont(font(11, QFont.Medium if self.isChecked() else QFont.Normal))
        p.drawText(QRectF(0, 50, self.width(), 18), Qt.AlignCenter, name)


class PlatformPicker(QWidget):
    changed = Signal(str)

    def __init__(self, columns: int = 7):
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        self.buttons: dict[str, PlatformButton] = {}
        for i, p in enumerate(acc.PLATFORMS):
            b = PlatformButton(p)
            b.clicked.connect(lambda _=False, k=p.key: self.select(k))
            grid.addWidget(b, i // columns, i % columns)
            self.buttons[p.key] = b
        self._current = None
        self.select(acc.PLATFORMS[0].key)

    def select(self, key: str):
        self._current = key
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        self.changed.emit(key)

    def value(self) -> str:
        return self._current

    def lock(self):
        for k, b in self.buttons.items():
            b.setEnabled(k == self._current)
            b.setVisible(k == self._current)


class AddAccountSheet(Sheet):
    """Yeni hesap ekler veya mevcut hesabın oturumunu yeniler (account verilirse)."""

    def __init__(self, host, account: acc.Account | None = None):
        super().__init__(host, width=600)
        self.account = account
        self.result_data = None
        b = self.body
        b.setSpacing(10)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Oturumu Yenile" if account else "Hesap Ekle", 17, QFont.Bold, display=True))
        titles.addWidget(label("Şifreniz saklanmaz; yalnızca oturum çerezleri şifrelenerek bu bilgisayarda tutulur.",
                               12, role="secondary", wrap=True))
        head.addLayout(titles, 1)
        b.addLayout(head)

        self.picker = PlatformPicker()
        b.addWidget(self.picker)

        form = Card()
        self.name_edit = QLineEdit()
        self.name_edit.setFixedWidth(280)
        self.name_edit.setPlaceholderText("Örn: Kişisel Instagram")
        form.add_row("Hesap adı", self.name_edit)
        self.login_url_edit = QLineEdit()
        self.login_url_edit.setFixedWidth(280)
        self.login_url_edit.setPlaceholderText("https://site.com/login")
        self.row_login_url = form.add_row("Giriş sayfası", self.login_url_edit)
        self.domains_edit = QLineEdit()
        self.domains_edit.setFixedWidth(280)
        self.domains_edit.setPlaceholderText("site.com, cdn.site.com")
        self.row_domains = form.add_row("Alan adları", self.domains_edit)
        self.form = form
        b.addWidget(form)

        self.note = label("", 11.5, role="warning", wrap=True)
        b.addWidget(self.note)

        mrow = QHBoxLayout()
        mrow.addWidget(label("Giriş yöntemi", 13, QFont.DemiBold))
        mrow.addStretch()
        self.method = Segmented([("login", "Uygulama içi giriş"), ("browser", "Tarayıcıdan"),
                                 ("file", "cookies.txt")], min_segment=96)
        mrow.addWidget(self.method)
        b.addLayout(mrow)

        self.method_stack = QStackedWidget()
        # uygulama içi
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(2, 0, 2, 0)
        l1.addWidget(hint_label("Safari benzeri güvenli bir pencere açılır; hesabınıza normal şekilde giriş yaparsınız "
                                "(iki adımlı doğrulama dahil). Geçmiş ve çerezler diske yazılmaz.", 540))
        l1.addStretch()
        self.method_stack.addWidget(p1)
        # tarayıcı
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(2, 0, 2, 0)
        l2.setSpacing(8)
        r2 = QHBoxLayout()
        self.browser_combo = PopupCombo(min_width=170)
        fill_combo(self.browser_combo, [(v, k) for k, v in acc.BROWSERS.items()])
        self.profile_edit = QLineEdit()
        self.profile_edit.setPlaceholderText("Profil (boş = varsayılan)")
        r2.addWidget(self.browser_combo)
        r2.addWidget(self.profile_edit, 1)
        l2.addLayout(r2)
        l2.addWidget(hint_label("O tarayıcıda siteye giriş yapmış olmalısınız. Firefox en sorunsuz sonucu verir; "
                                "Chrome/Edge yeni şifreleme nedeniyle okunamayabilir ve kapalı olmalıdır. Yalnızca "
                                "seçilen platformun çerezleri alınır.", 540))
        self.method_stack.addWidget(p2)
        # dosya
        p3 = QWidget()
        l3 = QVBoxLayout(p3)
        l3.setContentsMargins(2, 0, 2, 0)
        l3.setSpacing(8)
        r3 = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("cookies.txt yolu")
        pick = QPushButton("Seç…")
        pick.clicked.connect(self._browse_file)
        r3.addWidget(self.file_edit, 1)
        r3.addWidget(pick)
        l3.addLayout(r3)
        l3.addWidget(hint_label("\"Get cookies.txt LOCALLY\" gibi bir eklentiyle dışa aktarılmış Netscape biçimli dosya. "
                                "İçe aktardıktan sonra orijinal dosyayı silmeniz önerilir.", 540))
        self.method_stack.addWidget(p3)
        self.method_stack.setFixedHeight(76)
        b.addWidget(self.method_stack)

        self.add_buttons([("Vazgeç", None, None), ("Devam", "go", "primary")])
        # Devam butonu doğrudan kapatmasın: doğrulama gerekiyor
        self.default_button.clicked.disconnect()
        self.default_button.clicked.connect(self._go)

        if not webengine_available():
            self.method.set_item_enabled(0, False)
            self.method.set_value("browser")
        self.picker.changed.connect(self._platform_changed)
        self.method.changed.connect(lambda _: self.method_stack.setCurrentIndex(self.method.index()))
        self.name_edit.textEdited.connect(lambda _: self.name_edit.setProperty("auto", False))

        if account:
            self.picker.select(account.platform)
            self.picker.lock()
            self.name_edit.setText(account.name)
            self.name_edit.setEnabled(False)
            self.domains_edit.setText(", ".join(account.domains))
            self.login_url_edit.setText(account.login_url)
        self._platform_changed(self.picker.value())
        self.method_stack.setCurrentIndex(self.method.index())

    def _platform(self) -> acc.Platform:
        base = acc.PLATFORM_BY_KEY[self.picker.value()]
        if base.key != "custom":
            return base
        domains, _ = acc.normalize_domains(self.domains_edit.text())
        return acc.Platform("custom", "Özel site", self.login_url_edit.text().strip(), tuple(domains))

    def _platform_changed(self, key: str):
        p = acc.PLATFORM_BY_KEY[key]
        custom = key == "custom"
        self.form.set_row_visible(self.row_login_url, custom)
        self.form.set_row_visible(self.row_domains, custom)
        self.note.setText(p.note)
        self.note.setVisible(bool(p.note))
        if not self.account and (not self.name_edit.text() or self.name_edit.property("auto")):
            self.name_edit.setText("" if custom else f"{p.name} hesabım")
            self.name_edit.setProperty("auto", True)
        self._place()

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), "cookies.txt seç", "",
                                              "Çerez dosyası (*.txt);;Tüm dosyalar (*)")
        if path:
            self.file_edit.setText(path)

    def _go(self):
        platform = self._platform()
        name = self.name_edit.text().strip()
        method = self.method.value()
        if not name:
            alert(self, "Hesap adı gerekli", "Lütfen hesap için bir ad girin.")
            return
        if platform.key == "custom":
            _, rejected = acc.normalize_domains(self.domains_edit.text())
            if rejected:
                alert(self, "Geçersiz alan adı", "Şunlar geçerli bir site alan adı değil veya çok geniş: "
                      + ", ".join(rejected[:5]) + "\nÖrnek: site.com, video.site.com", kind="warning")
                return
            if not platform.domains and platform.login_url:
                derived, _ = acc.normalize_domains(platform.login_url)
                platform = acc.Platform("custom", "Özel site", platform.login_url, tuple(derived))
            if not platform.domains:
                alert(self, "Alan adı gerekli", "Özel site için geçerli bir giriş sayfası veya alan adı girin.")
                return
            if method == "login" and not platform.login_url.startswith(("http://", "https://")):
                alert(self, "Giriş sayfası gerekli", "Geçerli bir giriş sayfası adresi girin (https://…).")
                return

        if method == "login":
            from clipxd.ui.login_dialog import BrowserWindow
            win = BrowserWindow(platform, self.window())
            if win.exec() != BrowserWindow.Accepted or win.jar is None:
                return
            jar = win.jar
        else:
            QGuiApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                if method == "browser":
                    jar = acc.jar_from_browser(self.browser_combo.currentData(), self.profile_edit.text().strip(),
                                               platform.domains)
                else:
                    path = self.file_edit.text().strip()
                    if not path:
                        raise ValueError("Lütfen bir cookies.txt dosyası seçin.")
                    jar = acc.jar_from_file(path, platform.domains)
            except Exception as e:
                QGuiApplication.restoreOverrideCursor()
                alert(self, "İçe aktarılamadı", self._import_error_text(str(e)), kind="error")
                return
            QGuiApplication.restoreOverrideCursor()
            if not len(jar):
                alert(self, "Çerez bulunamadı", f"{', '.join(platform.domains)} için hiç çerez bulunamadı. Bu siteye "
                                                "giriş yapılmış olduğundan emin olun.", kind="warning")
                return
            ok, text = acc.auth_cookie_status(jar, platform)
            if ok is False and not confirm(self, "Oturum algılanmadı", f"{text}. {len(jar)} çerez bulundu. "
                                           "Yine de kaydedilsin mi?", ok="Kaydet", kind="warning"):
                return

        self.result_data = {"name": name, "platform": platform.key, "domains": list(platform.domains),
                            "jar": jar, "method": method,
                            "login_url": platform.login_url if platform.key == "custom" else ""}
        self.done("ok")

    @staticmethod
    def _import_error_text(msg: str) -> str:
        low = msg.lower()
        hint = ""
        if "could not copy" in low or "permission" in low or "locked" in low:
            hint = "\n\nTarayıcıyı tamamen kapatıp tekrar deneyin."
        elif "decrypt" in low or "dpapi" in low or "v20" in low or "app-bound" in low:
            hint = ("\n\nBu tarayıcının yeni çerez şifrelemesi okunamıyor. Firefox'u, uygulama içi girişi veya "
                    "cookies.txt yöntemini kullanın.")
        elif "could not find" in low or "not found" in low:
            hint = "\n\nTarayıcı veya profil bulunamadı. Profil adını kontrol edin ya da boş bırakın."
        return msg[:500] + hint


class AccountRow(QWidget):
    def __init__(self, page, account: acc.Account, status):
        super().__init__()
        self.page, self.account = page, account
        ok, text = status
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 10, 10)
        h.setSpacing(12)
        h.addWidget(platform_tile(account.platform, 36))
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(account.name, 13, QFont.DemiBold))
        platform = account.platform_name if account.platform != "custom" else ", ".join(account.domains)
        dot = {True: "success", False: "danger"}.get(ok, "text3")
        col = theme.css(dot)
        sub = QLabel(f"{html.escape(platform)} · <span style='color:{col}'>●</span> {html.escape(text)}")
        sub.setTextFormat(Qt.RichText)
        sub.setFont(font(11.5))
        set_role(sub, "secondary")
        sub.setToolTip(safe_tooltip(f"Alan adları: {', '.join(account.domains)}\n"
                                    f"Yöntem: {METHOD_LABELS.get(account.method, account.method)}\n"
                                    f"Eklenme: {account.created}"))
        texts.addWidget(sub)
        h.addLayout(texts, 1)
        star = IconButton("star_fill" if account.default else "star",
                          "Varsayılan hesap" if account.default else "Varsayılan yap", 28, 16,
                          color_key="warning" if account.default else "text2")
        star.clicked.connect(lambda: page.ctx.accounts.set_default(account.id))
        refresh = IconButton("retry", "Oturumu yenile", 28, 16)
        refresh.clicked.connect(lambda: page.refresh_session(account))
        trash = IconButton("trash", "Hesabı sil", 28, 16, danger_hover=True)
        trash.clicked.connect(lambda: page.remove(account))
        for w in (star, refresh, trash):
            h.addWidget(w)


class AccountsPage(QWidget):
    title = "Hesaplar"

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        styled(self, "page")
        self.ctx = ctx
        self.actions = QPushButton("Hesap Ekle")
        self.actions.setObjectName("primary")
        self.actions.setCursor(Qt.PointingHandCursor)
        self.actions.setIcon(icons.icon("plus", "#FFFFFF", 14))
        self.actions.clicked.connect(self.add)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 4, 24, 20)
        root.setSpacing(12)

        info = Card()
        storage = ("Windows DPAPI ile şifrelenir; yalnızca sizin Windows hesabınız bu bilgisayarda açabilir"
                   if secure_store.ENCRYPTED else "yalnızca bu bilgisayarda saklanır")
        iw = QWidget()
        ih = QHBoxLayout(iw)
        ih.setContentsMargins(0, 0, 0, 0)
        ih.setSpacing(14)
        self.shield = QLabel()
        ih.addWidget(self.shield, 0, Qt.AlignTop)
        it = QVBoxLayout()
        it.setSpacing(3)
        it.addWidget(label("Şifreniz asla saklanmaz", 13, QFont.DemiBold))
        it.addWidget(label(f"Yalnızca oturum çerezleri tutulur ve {storage}. İndirirken linke uygun hesap otomatik "
                           "seçilir; böylece o hesabın görebildiği gizli, takipçilere özel veya abonelere özel "
                           "içerikler de indirilebilir. DRM korumalı içerikler desteklenmez.", 12, role="secondary",
                           wrap=True))
        ih.addLayout(it, 1)
        info.add_widget(iw, margins=(16, 14, 16, 14))
        root.addWidget(info)

        root.addWidget(section("Hesaplar"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollBody")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 4, 0)
        self.body_layout.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._paint_icons()
        theme.changed.connect(self._paint_icons)
        self.ctx.accounts.listeners.append(self.refresh)
        self.refresh()

    def _paint_icons(self):
        self.shield.setPixmap(icons.pixmap("shield", theme.c("accent"), 30, 1.6))

    def refresh(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        accounts = self.ctx.accounts.all()
        if not accounts:
            empty = EmptyState("person", "Henüz hesap yok",
                               "Herkese açık içerikler için hesap gerekmez. Gizli veya hesaba özel içerikleri "
                               "indirmek için sağ üstten hesap ekleyin.")
            self.body_layout.addWidget(empty)
            self.body_layout.addStretch()
            return
        card = Card()
        for a in accounts:
            card.add_widget(AccountRow(self, a, self.ctx.accounts.status(a)), margins=(0, 0, 0, 0))
        self.body_layout.addWidget(card)
        self.body_layout.addStretch()

    def add(self):
        sheet = AddAccountSheet(self)
        if sheet.exec() == "ok" and sheet.result_data:
            d = sheet.result_data
            self.ctx.accounts.add(d["name"], d["platform"], d["domains"], d["jar"], d["method"], d["login_url"])

    def refresh_session(self, account: acc.Account):
        sheet = AddAccountSheet(self, account=account)
        if sheet.exec() == "ok" and sheet.result_data:
            self.ctx.accounts.replace_cookies(account.id, sheet.result_data["jar"], sheet.result_data["method"])

    def remove(self, account: acc.Account):
        if confirm(self, f"“{account.name}” silinsin mi?", "Hesap ve kayıtlı oturum bilgileri bu bilgisayardan "
                   "kalıcı olarak silinir.", ok="Sil", destructive=True, kind="warning"):
            self.ctx.accounts.remove(account.id)
