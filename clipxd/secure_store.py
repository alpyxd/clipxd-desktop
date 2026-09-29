"""Hesap çerezlerini diskte şifreli saklar.

Windows'ta DPAPI (CryptProtectData) kullanılır: veri yalnızca aynı Windows
kullanıcısı tarafından, aynı bilgisayarda çözülebilir. Diğer sistemlerde dosya
yalnızca sahibinin okuyabileceği izinlerle düz metin olarak yazılır.
"""
import os
from pathlib import Path

_DPAPI_MAGIC = b"MKDP1\n"
_PLAIN_MAGIC = b"MKPT1\n"
# Uygulamanın eski adını içerir ama DEĞİŞTİRİLMEMELİ: şifreli dosyalar bu değerle çözülür,
# değişirse daha önce eklenmiş hesapların çerezleri okunamaz.
_ENTROPY = b"MedyaKit-cookie-store-v1"

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _blob_p = ctypes.POINTER(_DataBlob)
    _crypt32.CryptProtectData.argtypes = [_blob_p, wintypes.LPCWSTR, _blob_p, ctypes.c_void_p,
                                          ctypes.c_void_p, wintypes.DWORD, _blob_p]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [_blob_p, ctypes.c_void_p, _blob_p, ctypes.c_void_p,
                                            ctypes.c_void_p, wintypes.DWORD, _blob_p]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def _to_blob(data: bytes):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data) if data else (ctypes.c_ubyte * 1)()
        return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))), buf

    def _dpapi(func, data: bytes) -> bytes:
        inp, _keep1 = _to_blob(data)
        ent, _keep2 = _to_blob(_ENTROPY)
        out = _DataBlob()
        if func is _crypt32.CryptProtectData:
            ok = func(ctypes.byref(inp), "ClipXD", ctypes.byref(ent), None, None,
                      _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
        else:
            ok = func(ctypes.byref(inp), None, ctypes.byref(ent), None, None,
                      _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out))
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))

    def protect(data: bytes) -> bytes:
        return _DPAPI_MAGIC + _dpapi(_crypt32.CryptProtectData, data)

    def unprotect(blob: bytes) -> bytes:
        if blob.startswith(_DPAPI_MAGIC):
            return _dpapi(_crypt32.CryptUnprotectData, blob[len(_DPAPI_MAGIC):])
        if blob.startswith(_PLAIN_MAGIC):
            return blob[len(_PLAIN_MAGIC):]
        raise ValueError("Tanınmayan şifreli dosya biçimi")

    ENCRYPTED = True
else:
    def protect(data: bytes) -> bytes:
        return _PLAIN_MAGIC + data

    def unprotect(blob: bytes) -> bytes:
        if blob.startswith(_PLAIN_MAGIC):
            return blob[len(_PLAIN_MAGIC):]
        raise ValueError("Bu dosya başka bir işletim sisteminde şifrelenmiş")

    ENCRYPTED = False


def write_secret(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(protect(text.encode("utf-8")))
    os.replace(tmp, path)


def read_secret(path: Path) -> str:
    return unprotect(path.read_bytes()).decode("utf-8")
