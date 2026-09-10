"""日本語まじりのタイトルを突き合わせるための正規化。

表記ゆれ（全角/半角、『』などの括弧、中黒、空白）を潰して、
同じイベントを別媒体が報じたときに同一視できるようにする。
"""

import hashlib
import re
import unicodedata

# 作品名を囲む括弧類。中身は残して括弧だけ落とす。
_BRACKETS = "『』「」【】《》〈〉[]()（）"
# 中黒・各種ダッシュ・空白は照合時に無視する。
# 長音符「ー」も意図的に含めている："レヴュースタァライト" と "レヴュスタァライト"
# のような長音のゆれを吸収するため。両辺に同じ処理がかかるので照合は壊れない。
_SEPARATORS = "・･:：;；,，、/／\\|｜-‐‑‒–—―ー~〜～_＿ 　\t"

_TRAILING_NOISE = re.compile(
    r"(?:\s*[-|｜]\s*(?:コミックナタリー|アニメイトタイムズ|映画\.com|"
    r"アニメ！アニメ！|MOVIE\s*WALKER\s*PRESS|リスアニ！|ファミ通\.com|"
    r"マイナビニュース|ORICON\s*NEWS|音楽ナタリー|映画ナタリー))+\s*$",
    re.IGNORECASE,
)


def strip_site_suffix(title: str) -> str:
    """「〜 - コミックナタリー」のような媒体名の接尾辞を落とす。"""
    return _TRAILING_NOISE.sub("", title).strip()


def normalize(text: str) -> str:
    """比較用のキー。NFKC したうえで括弧・区切り・空白を除去し小文字化する。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate({ord(c): None for c in _BRACKETS})
    text = text.translate({ord(c): None for c in _SEPARATORS})
    return text.casefold()


def normalize_loose(text: str) -> str:
    """normalize に加えて「劇場版」「TVアニメ」などの定型接頭辞も落とす。

    『劇場版 少女☆歌劇 レヴュースタァライト』と
    『少女☆歌劇 レヴュースタァライト』を同じ作品として扱いたいときに使う。
    """
    key = normalize(text)
    for prefix in (
        "劇場版総集編",
        "劇場版",
        "劇場アニメ",
        "アニメ映画",
        "tvアニメ",
        "テレビアニメ",
        "アニメ",
        "映画",
    ):
        if key.startswith(prefix) and len(key) > len(prefix) + 1:
            key = key[len(prefix) :]
            break
    return key


def canonical_url(url: str) -> str:
    """トラッキングパラメータとフラグメントを落とした URL。

    同じ記事が utm 付き/なしで二度流れてきても一件として数えるため。
    """
    if not url:
        return ""
    url = url.strip()
    url = re.sub(r"#.*$", "", url)
    url = re.sub(r"[?&](?:utm_[^=]+|fbclid|gclid|ref|ref_src|cmpid)=[^&]*", "", url)
    url = re.sub(r"\?&", "?", url)
    url = re.sub(r"[?&]+$", "", url)
    return re.sub(r"/+$", "", url)


def fingerprint(title: str, url: str = "") -> str:
    """重複判定に使う 16 桁のキー。

    URL があればそれを優先する（媒体内で最も確実な同一性）。
    無ければ正規化タイトルで代用する。
    """
    basis = canonical_url(url) or normalize_loose(strip_site_suffix(title))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
