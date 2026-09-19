"""同じイベントを報じた複数の記事を 1 つにまとめる。

媒体ごとに 1 行ずつ出すと、同じ展覧会が 3 行並ぶ。それだけなら見苦しい
だけだが、**日付が食い違っているのに両方出す**のは実害がある。実際、
小田原の富野由悠季展が「11/3〜11/30」と「11/6〜12/6」の 2 行になり、
前者が誤りだった。

見出しの文字列だけでは判別できない。同じ展覧会を報じた 3 本の見出しの
類似度は 0.09〜0.17 しかなく、無関係な記事同士（0.05〜0.12）と重なる。
代わりに**固有名詞の共有**を見る。「小田原」「原点」のように、その
イベント固有の語が 2 つ以上重なれば同じ催しとみなす。
"""

import re
import unicodedata

from .normalize import normalize_loose

# どの記事にも出る語。共有されていても手がかりにならない。
GENERIC = {
    "展覧会", "展示", "開催", "決定", "上映", "公開", "記念", "全国", "劇場",
    "映画", "作品", "情報", "実施", "予定", "限定", "発表", "開始", "実行",
    "イベント", "アニメ", "アニメーション", "監督", "原作", "出演", "登壇",
    "販売", "発売", "商品", "版", "周年", "今年", "来年", "本日", "以降",
    "コメント", "到着", "解禁", "公式", "サイト", "ニュース", "特集",
    "チケット", "受付", "前売", "当日", "会場", "会期", "詳細",
}

# 2 文字以上の漢字・カタカナの連なりを固有名詞の候補とみなす。
# 形態素解析を入れずに済ませるための近似。
_TERM = re.compile(r"[一-龥]{2,}|[ァ-ヴー]{3,}|[A-Za-z]{3,}")

# これ以上見出しが似ていれば、固有名詞を数えるまでもなく同一とみなす
TITLE_SIMILARITY_STRONG = 0.45
# 固有名詞がこの数だけ重なれば同一とみなす
SHARED_TERMS_REQUIRED = 2


def _bigrams(text: str) -> set[str]:
    key = normalize_loose(text)
    return {key[i:i + 2] for i in range(len(key) - 1)} or {key}


def title_similarity(a: str, b: str) -> float:
    left, right = _bigrams(a), _bigrams(b)
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def distinctive_terms(title: str, exclude: set[str] | None = None) -> set[str]:
    """見出しから、そのイベントを特定しうる語を抜く。

    ウォッチリストで一致した語（作品名・人物名）は除く。どの記事にも
    出るので、共有されていても同じイベントの証拠にならない。
    """
    text = unicodedata.normalize("NFKC", title)
    found = set()
    for match in _TERM.finditer(text):
        term = match.group(0)
        if term in GENERIC or len(term) < 2:
            continue
        found.add(term)

    for label in exclude or set():
        key = unicodedata.normalize("NFKC", label)
        found = {t for t in found if t not in key and key not in t}
    return found


def related(a: str, b: str) -> bool:
    """2 つの語が同じものを指していそうか。

    見出しごとに語の切れ方が違う。「小田原城」と「小田原城天守閣」、
    「原点」と「原点辿」のように、完全一致では拾えない。包含関係か、
    3 文字以上の共通部分があれば同じものとみなす。
    """
    if a in b or b in a:
        return True
    return any(a[i:i + 3] in b for i in range(len(a) - 2))


def shared_term_count(terms_a: set[str], terms_b: set[str]) -> int:
    """重なる語の数。同じ語の言い換えを二重に数えない。"""
    return sum(1 for a in terms_a if any(related(a, b) for b in terms_b))


def _labels(item: dict) -> set[str]:
    return {m.get("label", "") for m in item.get("matches", []) if m.get("label")}


def _span(item: dict) -> tuple[str, str] | None:
    event = item.get("event") or {}
    if not event.get("start"):
        return None
    return event["start"], event.get("end") or event["start"]


def _overlaps(a: dict, b: dict) -> bool:
    left, right = _span(a), _span(b)
    if not left or not right:
        return False
    return left[0] <= right[1] and right[0] <= left[1]


def same_event(a: dict, b: dict) -> bool:
    """2 件が同じ催しを指しているか。"""
    shared_labels = _labels(a) & _labels(b)
    if not shared_labels:
        return False

    if title_similarity(a.get("title", ""), b.get("title", "")) >= TITLE_SIMILARITY_STRONG:
        return True

    terms_a = distinctive_terms(a.get("title", ""), shared_labels)
    terms_b = distinctive_terms(b.get("title", ""), shared_labels)
    shared = shared_term_count(terms_a, terms_b)
    if shared >= SHARED_TERMS_REQUIRED:
        return True

    # 固有名詞が 1 つしか重ならなくても、同種の催しで会期が重なるなら同一とみなす
    if shared and _overlaps(a, b):
        if set(a.get("categories", [])) & set(b.get("categories", [])):
            return True
    return False


def group(items: list[dict]) -> list[list[dict]]:
    """同じイベントごとにまとめる。Union-Find で推移的に束ねる。"""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if same_event(items[i], items[j]):
                union(i, j)

    buckets: dict[int, list[dict]] = {}
    for index, item in enumerate(items):
        buckets.setdefault(find(index), []).append(item)
    return list(buckets.values())


def _trust(item: dict) -> tuple:
    """どの出典の日付を採るか。大きいほど信用できる。"""
    return (
        1 if item.get("date_confidence") == "confirmed" else 0,   # 本文で確認済み
        1 if item.get("published") else 0,                        # 公開日が分かる
        item.get("published", ""),                                # 新しい記事を優先
        1 if (item.get("event") or {}).get("year_explicit") else 0,
    )


def resolve(members: list[dict]) -> dict:
    """1 つの催しとしての代表値を組み立てる。

    日付が食い違う場合は、最も信用できる出典のものを採ったうえで、
    食い違いがあった事実と対立候補を残す。黙って片方を捨てない。
    """
    dated = [m for m in members if (m.get("event") or {}).get("start")]
    ranked = sorted(members, key=_trust, reverse=True)
    primary = sorted(dated, key=_trust, reverse=True)[0] if dated else ranked[0]

    starts = {m["event"]["start"] for m in dated}
    conflict = []
    if len(starts) > 1:
        chosen = primary["event"]["start"]
        for m in dated:
            if m["event"]["start"] != chosen:
                conflict.append({
                    "start": m["event"]["start"],
                    "end": m["event"].get("end"),
                    "source": m.get("source", ""),
                    "url": m.get("url", ""),
                })

    categories, matches, seen_labels = [], [], set()
    for m in members:
        for c in m.get("categories", []):
            if c not in categories:
                categories.append(c)
        for hit in m.get("matches", []):
            if hit.get("label") and hit["label"] not in seen_labels:
                seen_labels.add(hit["label"])
                matches.append(hit)

    return {
        "title": primary.get("title", ""),
        "url": primary.get("url", ""),
        "summary": primary.get("summary", ""),
        "source": primary.get("source", ""),
        "published": primary.get("published", ""),
        "categories": categories,
        "matches": matches,
        "event": primary.get("event"),
        "date_note": primary.get("date_note", ""),
        "date_hint": primary.get("date_hint", ""),
        "date_confidence": primary.get("date_confidence", ""),
        "date_conflict": conflict,
        "sources": [
            {"name": m.get("source", ""), "url": m.get("url", ""),
             "published": m.get("published", "")}
            for m in ranked
        ],
        "status": min((m.get("status", "known") for m in members),
                      key=lambda s: {"new": 0, "updated": 1, "known": 2}.get(s, 3)),
    }


def collapse(items: list[dict]) -> list[dict]:
    """まとめてから代表値にする。入口はこれ 1 つ。"""
    return [resolve(members) for members in group(items)]
