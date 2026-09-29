<p align="center">
  <img src="assets/logo.png" width="128" alt="ClipXD logo">
</p>

<h1 align="center">ClipXD Desktop</h1>

<p align="center">
  Social media video downloader &amp; media converter for Windows, with a macOS-style interface.<br>
  <sub>Sosyal medya video indirici ve medya dönüştürücü — Windows için, macOS tarzı arayüzle.</sub>
</p>

<p align="center">
  <a href="https://github.com/alpyxd/clipxd-desktop/releases/latest"><b>⬇ Download for Windows</b></a>
  &nbsp;·&nbsp; <b>English</b> &nbsp;·&nbsp; <a href="#türkçe">Türkçe</a>
</p>

<p align="center">
  <img src="assets/screenshots/indir-acik.png" width="49%" alt="Light theme">
  <img src="assets/screenshots/indir-koyu.png" width="49%" alt="Dark theme">
</p>

## English

> The app's interface is currently in **Turkish**.

### Features

- **Download** from YouTube, Instagram, TikTok, X (Twitter), Facebook, Reddit, Vimeo, Twitch, SoundCloud and
  [nearly 1,000 sites supported by yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) —
  as MP4 / MKV / WEBM video or MP3 / M4A / OPUS / FLAC / WAV audio, up to 4K, with embedded cover art,
  metadata and subtitles. A strip at the top shows the supported platforms; "+950 more sites" opens a
  searchable list of all of them.
- **Playlists:** playlist, channel or album links are scanned first; pick what you want from a checklist
  (search, select all, total duration). Files are saved into a folder named after the playlist.
- **Accounts:** add an account to download **private, followers-only or subscriber-only** content that the
  account can already see. The matching account is picked automatically from the link.
- **Convert:** *change container* (no re-encoding, lossless, takes seconds) or *re-encode* (H.264 / H.265 /
  VP9, quality, resolution, frame rate, audio bitrate, trimming, audio extraction, GIF).
- **Clean file names:** `Video Title.mp4`; existing files are never overwritten (`Video Title (1).mp4`).
- **Interface:** frameless window with traffic lights (native Windows shadow, rounded corners and Snap
  are kept), sidebar, card layout, Safari-style downloads list, in-window alerts and a Safari-like
  sign-in window. Automatic / light / dark theme.

### Download

1. Get `ClipXD-Desktop-<version>-win64.zip` from the
   [latest release](https://github.com/alpyxd/clipxd-desktop/releases/latest).
2. Extract it anywhere and run `ClipXD\ClipXD.exe` (Python is not required).

The app is not code-signed yet, so Windows SmartScreen may warn on first launch: choose
**More info → Run anyway**. You can verify the download with the `.sha256` file attached to the release.

> **YouTube:** yt-dlp needs a JavaScript runtime for YouTube — install [Node.js](https://nodejs.org) or
> [Deno](https://deno.com).

### Run from source

Requirements: Windows 10/11 and [Python 3.11+](https://www.python.org/downloads/).

```bash
git clone https://github.com/alpyxd/clipxd-desktop.git
```

1. Double-click `kurulum.bat` (creates a virtual environment and installs the dependencies).
2. Start the app with `ClipXD.bat`.

ffmpeg is bundled through `imageio-ffmpeg`; a system-wide ffmpeg is used if present, and you can pick
another one in Settings. `exe_olustur.bat` builds the Windows package (`dist\ClipXD\ClipXD.exe` and the
release zip).

### Accounts

**Hesaplar (Accounts) → Hesap Ekle (Add Account)**, pick a platform, then one of three methods:

| Method | When |
|---|---|
| **In-app sign-in** (recommended) | A separate, private Safari-style window opens; sign in normally (2FA supported). |
| **From browser** | You are already signed in in your browser. Firefox works best; Chrome/Edge may be unreadable due to their newer cookie encryption and must be closed. |
| **cookies.txt** | A Netscape-format file exported with an extension such as "Get cookies.txt LOCALLY". |

Google may block YouTube sign-in inside embedded browsers — import from Firefox or use cookies.txt instead.

### Security & privacy

- **Your password is never stored.** In the in-app sign-in, it is only sent to the site's own page.
- Only the **session cookies** of the chosen platform's domains are stored, encrypted with **Windows DPAPI**
  (only your Windows account on this PC can decrypt them). During downloads they are used in memory and
  never written to disk in plain text.
- The proxy address (which may contain credentials) is encrypted too; custom site domains are validated.
- Only one ClipXD instance runs at a time, so account and settings files are never overwritten by another
  instance. A corrupted account list is backed up and reported, never deleted.
- Titles coming from the internet are turned into safe file/folder names and are never rendered as HTML.
- Data lives in `%APPDATA%\ClipXD`.

### Limitations

- **DRM-protected** content (Netflix, Disney+, Spotify, Apple Music, …) cannot be downloaded.
- Accounts only give access to content **that account can already see**.
- Only download content you have the right to download. Respecting the platforms' terms of service and
  copyright is the user's responsibility.

### Troubleshooting

| Problem | Fix |
|---|---|
| Downloads from a site suddenly fail | Sites change often: **Ayarlar (Settings) → yt-dlp → Güncelle (Update)** when running from source, or get the latest release. |
| "Content requires sign-in" | Add an account for that platform or refresh its session. |
| "YouTube asks to confirm you're not a bot" | Add a YouTube account. |
| Can't import from Chrome/Edge | Fully close the browser; otherwise use Firefox, in-app sign-in or cookies.txt. |
| "Codec can't be copied into this container" | Choose **Yeniden kodla (Re-encode)** in the Convert page. |
| Want detailed errors | Click the log icon next to the Downloads header. |

### Development

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe packaging\build_release.py
```

```
clipxd/
  app.py              Main window, single-instance guard
  downloader.py       yt-dlp download engine (Qt-free)
  converter.py        ffmpeg commands and progress tracking
  accounts.py         Account store, cookie filtering, platform list
  secure_store.py     Windows DPAPI encryption
  sites.py            Supported site list
  selftest.py         Headless package self-test (--self-test)
  ui/                 PySide6 pages, macOS-style widgets, theme, frameless window
packaging/            Release build script and third-party license texts
tests/                Unit, integration and security regression tests
```

### License

ClipXD Desktop's source code is released under the [MIT License](LICENSE). Bundled components keep their
own licenses (yt-dlp: Unlicense, PySide6/Qt: LGPL-3.0, FFmpeg: GPL-3.0, mutagen: GPL-2.0-or-later, …);
the Windows package ships their license texts and source links in `THIRD-PARTY-NOTICES.txt` and
`licenses/`.

Built with [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org) and
[Qt for Python (PySide6)](https://doc.qt.io/qtforpython/).

---

## Türkçe

<p align="right"><a href="#english">English</a> · <b>Türkçe</b></p>

### Özellikler

- **İndir:** YouTube, Instagram, TikTok, X (Twitter), Facebook, Reddit, Vimeo, Twitch, SoundCloud ve
  [yt-dlp'nin desteklediği 1000'e yakın site](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).
  MP4 / MKV / WEBM video veya MP3 / M4A / OPUS / FLAC / WAV ses; 4K'ya kadar kalite, kapak resmi, başlık
  bilgileri ve altyazı gömme. Üstteki şerit desteklenen platformları gösterir, "+950 site daha" tüm
  sitelerin aranabilir listesini açar.
- **Oynatma listeleri:** Liste, kanal veya albüm linkinde öğeler önce taranır; onay kutulu listeden
  (arama, tümünü seç, toplam süre) istediklerinizi seçersiniz. Dosyalar liste adıyla açılan klasöre iner.
- **Hesaplar:** Hesap ekleyerek o hesabın görebildiği **gizli / takipçilere özel / abonelere özel**
  içerikleri indirebilirsiniz. Linkin sitesine uygun hesap otomatik seçilir.
- **Dönüştür:** *Uzantı değiştir* (yeniden kodlamadan, kayıpsız, saniyeler içinde) veya *yeniden kodla*
  (H.264 / H.265 / VP9, kalite, çözünürlük, kare hızı, ses kalitesi, kırpma, sesi çıkarma, GIF).
- **Temiz dosya adları:** `Video Başlığı.mp4`; aynı ad varsa üzerine yazılmaz, `Video Başlığı (1).mp4` olur.
- **Arayüz:** Trafik ışıklı çerçevesiz pencere (Windows gölgesi, yuvarlak köşeler ve Snap korunur),
  kenar çubuğu, kart düzeni, Safari İndirilenler tarzı liste, pencere içi uyarılar ve Safari benzeri
  giriş penceresi. Otomatik / açık / koyu tema.

### İndirme

1. [Son sürümden](https://github.com/alpyxd/clipxd-desktop/releases/latest)
   `ClipXD-Desktop-<sürüm>-win64.zip` dosyasını indirin.
2. İstediğiniz yere çıkarın ve `ClipXD\ClipXD.exe` dosyasını çalıştırın (Python gerekmez).

Uygulama henüz dijital olarak imzalı olmadığı için Windows SmartScreen ilk açılışta uyarabilir:
**Ek bilgi → Yine de çalıştır** seçin. İndirdiğiniz dosyayı sürümdeki `.sha256` dosyasıyla doğrulayabilirsiniz.

> **YouTube:** yt-dlp, YouTube için bir JavaScript çalışma zamanına ihtiyaç duyar:
> [Node.js](https://nodejs.org) veya [Deno](https://deno.com) kurun.

### Kaynaktan çalıştırma

Gereksinim: Windows 10/11 ve [Python 3.11+](https://www.python.org/downloads/).

```bash
git clone https://github.com/alpyxd/clipxd-desktop.git
```

1. `kurulum.bat` dosyasına çift tıklayın (sanal ortamı oluşturur ve paketleri kurar).
2. Uygulamayı `ClipXD.bat` ile başlatın.

ffmpeg `imageio-ffmpeg` ile birlikte gelir; sisteminizde ffmpeg varsa o kullanılır, Ayarlar'dan farklı bir
konum da seçebilirsiniz. `exe_olustur.bat` Windows paketini (`dist\ClipXD\ClipXD.exe` ve sürüm zip'i) üretir.

### Hesap ekleme

**Hesaplar → Hesap Ekle** ile platformu seçin, ardından üç yöntemden birini kullanın:

| Yöntem | Ne zaman? |
|---|---|
| **Uygulama içi giriş** (önerilen) | Safari tarzı, ayrı ve gizli bir tarayıcı penceresi açılır; hesabınıza normal şekilde girersiniz (2FA dahil). |
| **Tarayıcıdan** | Siteye tarayıcınızda zaten giriş yaptıysanız. Firefox en sorunsuzudur; Chrome/Edge yeni çerez şifrelemesi nedeniyle okunamayabilir ve kapalı olmalıdır. |
| **cookies.txt** | "Get cookies.txt LOCALLY" gibi bir eklentiyle dışa aktarılmış Netscape biçimli dosya. |

Google, uygulama içi tarayıcıda YouTube girişini engelleyebilir; bu durumda Firefox'tan içe aktarın veya
cookies.txt kullanın. Aynı platforma birden fazla hesap eklenebilir; ★ ile işaretli **varsayılan** hesap
otomatik seçilir.

### Güvenlik ve gizlilik

- **Şifreniz hiçbir zaman saklanmaz.** Uygulama içi girişte şifre yalnızca sitenin kendi sayfasına gider.
- Yalnızca seçilen platformun alan adlarına ait **oturum çerezleri** saklanır ve **Windows DPAPI** ile
  şifrelenir (yalnızca bu bilgisayardaki Windows hesabınız çözebilir). İndirme sırasında çerezler bellekte
  kullanılır, diske düz metin yazılmaz.
- Proxy adresi (kullanıcı adı/şifre içerebilir) de şifreli saklanır; özel site alan adları doğrulanır.
- Aynı anda yalnızca bir ClipXD çalışır; hesap ve ayar dosyaları birbirinin üzerine yazılmaz. Bozuk bir
  hesap listesi silinmez, yedeklenip bildirilir.
- İnternetten gelen başlıklar güvenli dosya/klasör adlarına çevrilir ve arayüzde HTML olarak yorumlanmaz.
- Veriler: `%APPDATA%\ClipXD`. Eski adla (MedyaKit) kurulmuş veriler ilk açılışta otomatik taşınır.

### Sınırlamalar

- **DRM korumalı** içerikler (Netflix, Disney+, Spotify, Apple Music vb.) indirilemez.
- Hesaplar yalnızca **o hesabın zaten erişebildiği** içerikleri indirmenizi sağlar.
- Yalnızca indirme hakkınız olan içerikleri indirin. Platformların kullanım koşullarına ve telif
  haklarına uymak kullanıcının sorumluluğundadır.

### Sorun giderme

| Sorun | Çözüm |
|---|---|
| Bir sitede indirme birden bozuldu | Siteler sık değişir: kaynaktan çalıştırıyorsanız **Ayarlar → yt-dlp → Güncelle**, exe kullanıyorsanız son sürümü indirin. |
| "İçerik giriş gerektiriyor" | Hesaplar'dan o platform için hesap ekleyin veya oturumu yenileyin. |
| "YouTube bot doğrulaması istiyor" | Bir YouTube hesabı ekleyin. |
| Chrome/Edge'den içe aktarılamıyor | Tarayıcıyı tamamen kapatın; olmazsa Firefox, uygulama içi giriş veya cookies.txt kullanın. |
| "Codec bu kapsayıcıya kopyalanamıyor" | Dönüştür'de **Yeniden kodla** modunu seçin. |
| Ayrıntılı hata görmek | İndirmeler başlığının yanındaki günlük simgesine basın. |

### Geliştirme

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe packaging\build_release.py
```

Yeni bir platformu hesap listesine eklemek için `clipxd/accounts.py` içindeki `PLATFORMS` listesine giriş
sayfasını, alan adlarını ve oturum çerezi adını ekleyin. Klasör yapısı için İngilizce bölüme bakın.

### Lisans

ClipXD Desktop'ın kaynak kodu [MIT lisansı](LICENSE) ile yayımlanır. Pakete giren bileşenlerin kendi
lisansları vardır (yt-dlp: Unlicense, PySide6/Qt: LGPL-3.0, FFmpeg: GPL-3.0, mutagen: GPL-2.0 veya sonrası
vb.); Windows paketi bunların lisans metinlerini ve kaynak bağlantılarını `THIRD-PARTY-NOTICES.txt` ve
`licenses/` içinde taşır.
