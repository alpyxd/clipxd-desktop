"""yt-dlp'nin desteklediği sitelerin listesi (Qt'den bağımsız)."""
import functools

# Açıklaması bu kadar kısa olanlar görünen ad olarak kullanılır
_MAX_DESC_AS_NAME = 32

NICE_NAMES = {
    "youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok", "twitter": "X (Twitter)",
    "facebook": "Facebook", "reddit": "Reddit", "vimeo": "Vimeo", "twitch": "Twitch", "soundcloud": "SoundCloud",
    "dailymotion": "Dailymotion", "pinterest": "Pinterest", "linkedin": "LinkedIn", "bilibili": "Bilibili",
    "bluesky": "Bluesky", "kick": "Kick", "niconico": "Niconico", "vk": "VK",
}

# yt-dlp testlerinden biri +18 olduğu için "yetişkin" işaretlenen ama genel amaçlı platformlar
_GENERAL_BUT_FLAGGED = {
    "youtube", "twitter", "reddit", "dailymotion", "niconico", "niconicochannelplus", "kick", "bluesky",
    "newgrounds", "vevo", "yandexvideo", "ondemandkorea", "cda", "mxplayer", "picarto", "goodgame", "mave",
}
_ADULT_WORDS = ("porn", "xxx", "sex", "hentai", "xhamster", "nsfw", "fap", "tube8")


@functools.lru_cache(maxsize=1)
def supported_sites() -> tuple:
    """(görünen ad, açıklama) listesi; alfabetik, site başına tek satır.

    Çalışmayan (_WORKING=False), gizli (IE_DESC=False) ve genel amaçlı çıkarıcılar ile yetişkin
    siteler listede gösterilmez (yetişkin siteler yine de indirilebilir).
    """
    from yt_dlp.extractor import gen_extractor_classes

    groups: dict[str, list] = {}
    flagged: set[str] = set()
    for ie in gen_extractor_classes():
        name = ie.IE_NAME
        if name == "generic" or ie.IE_DESC is False or not getattr(ie, "_WORKING", True):
            continue
        base = name.split(":")[0].lower()
        groups.setdefault(base, []).append(ie)
        if (getattr(ie, "age_limit", 0) or 0) >= 18:
            flagged.add(base)

    # "soundcloudembed", "facebookpluginsvideo" gibi yan girişleri ana sitenin altında topla
    for base in sorted(groups, key=len):
        if base not in groups:
            continue
        for other in [b for b in groups if b != base and len(base) >= 5 and b.startswith(base)]:
            groups[base].extend(groups.pop(other))
            if other in flagged:
                flagged.add(base)

    for base in list(groups):
        if (base in flagged and base not in _GENERAL_BUT_FLAGGED) or any(w in base for w in _ADULT_WORDS):
            del groups[base]

    sites = []
    for base, ies in groups.items():
        display = NICE_NAMES.get(base)
        if display is None:
            short = [ie.IE_DESC for ie in ies if ie.IE_NAME.lower() == base and isinstance(ie.IE_DESC, str)
                     and len(ie.IE_DESC) <= _MAX_DESC_AS_NAME and ";" not in ie.IE_DESC]
            raw = next((ie.IE_NAME for ie in ies if ie.IE_NAME.lower() == base), ies[0].IE_NAME).split(":")[0]
            display = short[0] if short else raw[:1].upper() + raw[1:]
        extras = sorted({ie.IE_DESC for ie in ies if isinstance(ie.IE_DESC, str) and ie.IE_DESC != display})
        sites.append((display, "; ".join(extras[:4])))
    sites.sort(key=lambda s: s[0].casefold())
    return tuple(sites)
