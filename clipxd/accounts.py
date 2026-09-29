"""Hesap yönetimi.

Şifreler hiçbir zaman saklanmaz. Bir hesap; platform bilgisi ve o platforma ait
oturum çerezlerinden oluşur. Çerezler secure_store ile şifrelenir ve indirme
sırasında yt-dlp'ye bellekte (diske düz metin yazmadan) verilir.
"""
import io
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp.cookies import YoutubeDLCookieJar

from clipxd import secure_store


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    login_url: str
    domains: tuple
    auth_cookies: tuple = ()
    note: str = ""


PLATFORMS = [
    Platform("youtube", "YouTube",
             "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F",
             ("youtube.com", "youtu.be"), ("SAPISID", "__Secure-3PAPISID", "LOGIN_INFO"),
             "Google, uygulama içi tarayıcıda girişi engelleyebilir. Sorun olursa "
             "'Tarayıcımdan içe aktar' (Firefox önerilir) veya cookies.txt yöntemini kullanın."),
    Platform("instagram", "Instagram", "https://www.instagram.com/accounts/login/",
             ("instagram.com",), ("sessionid",)),
    Platform("tiktok", "TikTok", "https://www.tiktok.com/login",
             ("tiktok.com",), ("sessionid", "sessionid_ss")),
    Platform("x", "X (Twitter)", "https://x.com/i/flow/login",
             ("x.com", "twitter.com"), ("auth_token",)),
    Platform("facebook", "Facebook", "https://www.facebook.com/login/",
             ("facebook.com", "fb.watch"), ("c_user", "xs")),
    Platform("reddit", "Reddit", "https://www.reddit.com/login/",
             ("reddit.com", "redd.it"), ("reddit_session", "token_v2")),
    Platform("vimeo", "Vimeo", "https://vimeo.com/log_in", ("vimeo.com",), ("vimeo",)),
    Platform("twitch", "Twitch", "https://www.twitch.tv/login", ("twitch.tv",), ("auth-token",)),
    Platform("linkedin", "LinkedIn", "https://www.linkedin.com/login", ("linkedin.com",), ("li_at",)),
    Platform("pinterest", "Pinterest", "https://www.pinterest.com/login/",
             ("pinterest.com", "pin.it"), ("_pinterest_sess",)),
    Platform("soundcloud", "SoundCloud", "https://soundcloud.com/signin",
             ("soundcloud.com",), ("oauth_token",)),
    Platform("dailymotion", "Dailymotion", "https://www.dailymotion.com/signin",
             ("dailymotion.com", "dai.ly"), ()),
    Platform("bilibili", "Bilibili", "https://passport.bilibili.com/login",
             ("bilibili.com", "b23.tv"), ("SESSDATA",)),
    Platform("custom", "Diğer (özel site)", "", (), ()),
]
PLATFORM_BY_KEY = {p.key: p for p in PLATFORMS}

# yt-dlp'nin çerez okuyabildiği tarayıcılar (görünen ad -> yt-dlp adı)
BROWSERS = {
    "Firefox": "firefox",
    "Google Chrome": "chrome",
    "Microsoft Edge": "edge",
    "Brave": "brave",
    "Opera": "opera",
    "Vivaldi": "vivaldi",
    "Chromium": "chromium",
}


def host_matches(host: str, domains) -> bool:
    host = (host or "").lower().lstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def url_host(url: str) -> str:
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except ValueError:
        return ""


def domains_from_url(url: str) -> list[str]:
    host = url_host(url)
    if host.startswith("www."):
        host = host[4:]
    return [host] if host else []


_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")
# Tek başına "alan adı" gibi görünen ama binlerce siteyi kapsayan ekler
_BROAD_SUFFIXES = {"co.uk", "org.uk", "com.tr", "net.tr", "org.tr", "gov.tr", "edu.tr", "com.br", "co.jp",
                   "com.au", "co.in", "com.cn", "com.mx", "github.io", "blogspot.com", "appspot.com"}


def normalize_domains(text: str) -> tuple[list[str], list[str]]:
    """Kullanıcının yazdığı alan adlarını temizler: (geçerliler, reddedilenler).

    'https://www.site.com/giris' -> 'site.com'. 'com' veya 'co.uk' gibi çok geniş ekler reddedilir;
    aksi halde tarayıcıdan içe aktarmada ilgisiz sitelerin çerezleri de alınırdı.
    """
    valid, rejected = [], []
    for raw in re.split(r"[,\s;]+", text or ""):
        d = raw.strip().lower()
        if not d:
            continue
        if "://" in d:
            d = url_host(d)
        d = d.split("/")[0].split(":")[0].lstrip("*.").removeprefix("www.")
        if _DOMAIN_RE.match(d) and d not in _BROAD_SUFFIXES:
            if d not in valid:
                valid.append(d)
        else:
            rejected.append(raw.strip())
    return valid, rejected


# ---------------------------------------------------------------- çerez yardımcıları

def new_jar() -> YoutubeDLCookieJar:
    return YoutubeDLCookieJar()


def jar_to_text(jar: YoutubeDLCookieJar) -> str:
    buf = io.StringIO()
    jar.save(buf)
    return buf.getvalue().lstrip("\x00")


def text_to_jar(text: str) -> YoutubeDLCookieJar:
    jar = YoutubeDLCookieJar(io.StringIO(text))
    jar.load()
    return jar


def filter_jar(jar, domains) -> YoutubeDLCookieJar:
    """Yalnızca verilen alan adlarına ait çerezleri döndürür. Alan adı yoksa hiçbir çerez alınmaz
    (tarayıcıdaki tüm oturumların yanlışlıkla içe aktarılmasını önler)."""
    out = new_jar()
    if not domains:
        return out
    for cookie in jar:
        if host_matches(cookie.domain, domains):
            out.set_cookie(cookie)
    return out


def make_cookie(domain: str, name: str, value: str, path: str = "/", secure: bool = True,
                expires: int | None = None, http_only: bool = False) -> Cookie:
    return Cookie(
        version=0, name=name, value=value, port=None, port_specified=False,
        domain=domain, domain_specified=bool(domain), domain_initial_dot=domain.startswith("."),
        path=path or "/", path_specified=True, secure=secure, expires=expires, discard=expires is None,
        comment=None, comment_url=None, rest={"HttpOnly": ""} if http_only else {},
    )


def jar_from_file(path: str, domains=None) -> YoutubeDLCookieJar:
    jar = YoutubeDLCookieJar(path)
    jar.load()
    return filter_jar(jar, domains)


def jar_from_browser(browser: str, profile: str | None, domains) -> YoutubeDLCookieJar:
    """Yüklü bir tarayıcıdan yalnızca ilgili alan adlarının çerezlerini okur."""
    from yt_dlp.cookies import extract_cookies_from_browser

    messages = []

    class _Log:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg, only_once=False): messages.append(msg)
        def error(self, msg): messages.append(msg)

    jar = extract_cookies_from_browser(browser, profile or None, _Log())
    filtered = filter_jar(jar, domains)
    if not len(filtered) and messages:
        raise RuntimeError("\n".join(messages[-3:]))
    return filtered


def auth_cookie_status(jar, platform: Platform) -> tuple[bool | None, str]:
    """Oturum çerezinin varlığını ve süresini kontrol eder.

    Dönüş: (True=bulundu / False=bulunamadı / None=bilinmiyor, açıklama)
    """
    if not platform.auth_cookies:
        return (None, f"{len(jar)} çerez") if len(jar) else (False, "Çerez yok")
    now = time.time()
    found = [c for c in jar if c.name in platform.auth_cookies and host_matches(c.domain, platform.domains)]
    if not found:
        return False, "Oturum çerezi yok (giriş tamamlanmamış olabilir)"
    valid = [c for c in found if not c.expires or c.expires > now]
    if not valid:
        return False, "Oturumun süresi dolmuş, yeniden giriş yapın"
    expiries = [c.expires for c in valid if c.expires]
    if expiries:
        return True, "Oturum açık (bitiş: " + datetime.fromtimestamp(min(expiries)).strftime("%d.%m.%Y") + ")"
    return True, "Oturum açık"


# ---------------------------------------------------------------- hesap deposu

_ID_RE = re.compile(r"^[0-9a-f]{8,32}$")


@dataclass
class Account:
    id: str
    name: str
    platform: str
    domains: list = field(default_factory=list)
    method: str = ""
    created: str = ""
    default: bool = False
    cookie_count: int = 0
    login_url: str = ""           # yalnızca özel siteler için

    @property
    def platform_obj(self) -> Platform:
        base = PLATFORM_BY_KEY.get(self.platform, PLATFORM_BY_KEY["custom"])
        if self.platform == "custom" or tuple(self.domains) != base.domains:
            return Platform(base.key, base.name, self.login_url or base.login_url, tuple(self.domains),
                            base.auth_cookies, base.note)
        return base

    @property
    def platform_name(self) -> str:
        return PLATFORM_BY_KEY.get(self.platform, PLATFORM_BY_KEY["custom"]).name

    def matches(self, url: str) -> bool:
        return host_matches(url_host(url), self.domains)


class AccountStore:
    def __init__(self, root: Path):
        self.root = root
        self.index_path = root / "accounts.json"
        self.cookie_dir = root / "cookies"
        self._lock = threading.RLock()
        self._accounts: list[Account] = []
        self.listeners = []
        self.load_error = ""
        self._load()

    def _load(self):
        if not self.index_path.exists():
            return
        known = {f.name for f in fields(Account)}
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("beklenmeyen biçim")
        except (OSError, ValueError) as e:
            # Bozuk dosyayı ezmeden yedekle; aksi halde bir sonraki kayıtta tüm hesaplar kaybolurdu
            backup = self.index_path.with_name(f"accounts.bozuk-{int(time.time())}.json")
            try:
                self.index_path.replace(backup)
            except OSError:
                pass
            self.load_error = f"Hesap listesi okunamadı ({e}); dosya yedeklendi: {backup.name}"
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            data = {k: v for k, v in item.items() if k in known}  # yeni sürümden kalan alanları yok say
            if not _ID_RE.match(str(data.get("id", ""))) or "name" not in data or "platform" not in data:
                continue  # dosya yolunda kullanılan kimlik yalnızca onaltılık olabilir
            try:
                self._accounts.append(Account(**data))
            except TypeError:
                continue

    def _save_index(self):
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(a) for a in self._accounts], indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.index_path)

    def _notify(self):
        for cb in list(self.listeners):
            cb()

    def _cookie_path(self, account_id: str) -> Path:
        return self.cookie_dir / f"{account_id}.bin"

    # --- sorgular
    def all(self) -> list[Account]:
        with self._lock:
            return list(self._accounts)

    def get(self, account_id: str) -> Account | None:
        with self._lock:
            return next((a for a in self._accounts if a.id == account_id), None)

    def find_for_url(self, url: str) -> Account | None:
        matches = [a for a in self.all() if a.matches(url)]
        if not matches:
            return None
        return next((a for a in matches if a.default), matches[0])

    # --- değişiklikler
    def add(self, name: str, platform: str, domains, jar, method: str, login_url: str = "") -> Account:
        with self._lock:
            has_default = any(a.default and a.platform == platform and a.domains == list(domains)
                              for a in self._accounts)
            account = Account(
                id=uuid.uuid4().hex[:12], name=name, platform=platform, domains=list(domains),
                method=method, created=datetime.now().strftime("%d.%m.%Y %H:%M"),
                default=not has_default, cookie_count=len(jar), login_url=login_url,
            )
            secure_store.write_secret(self._cookie_path(account.id), jar_to_text(jar))
            self._accounts.append(account)
            self._save_index()
        self._notify()
        return account

    def replace_cookies(self, account_id: str, jar, method: str | None = None):
        with self._lock:
            account = self.get(account_id)
            if account is None:
                return
            secure_store.write_secret(self._cookie_path(account_id), jar_to_text(jar))
            account.cookie_count = len(jar)
            if method:
                account.method = method
            self._save_index()
        self._notify()

    def remove(self, account_id: str):
        with self._lock:
            self._accounts = [a for a in self._accounts if a.id != account_id]
            self._save_index()
            try:
                self._cookie_path(account_id).unlink(missing_ok=True)
            except OSError:
                pass  # dosya kilitliyse bile hesap listeden kalkmış olur; kimse okuyamaz (DPAPI)
        self._notify()

    def set_default(self, account_id: str):
        with self._lock:
            target = self.get(account_id)
            if target is None:
                return
            for a in self._accounts:
                if a.platform == target.platform and a.domains == target.domains:
                    a.default = a.id == account_id
            self._save_index()
        self._notify()

    # --- çerezler
    def load_cookie_text(self, account_id: str) -> str:
        with self._lock:
            return secure_store.read_secret(self._cookie_path(account_id))

    def load_jar(self, account_id: str) -> YoutubeDLCookieJar:
        return text_to_jar(self.load_cookie_text(account_id))

    def store_jar_after_use(self, account_id: str, jar):
        """İndirme sonrası yenilenen çerezleri geri yazar (arka plan iş parçacığından çağrılır)."""
        with self._lock:
            account = self.get(account_id)
            if account is None or not len(jar):
                return
            secure_store.write_secret(self._cookie_path(account_id), jar_to_text(jar))
            account.cookie_count = len(jar)
            self._save_index()

    def status(self, account: Account) -> tuple[bool | None, str]:
        try:
            jar = self.load_jar(account.id)
        except Exception as e:  # dosya silinmiş / başka kullanıcıda şifrelenmiş
            return False, f"Çerezler okunamadı: {e}"
        return auth_cookie_status(jar, account.platform_obj)
