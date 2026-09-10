"""ウォッチリスト照合と、イベント種別の分類。

「拾いすぎない」ことを優先している。通知が多いと結局読まなくなり、
見逃し防止という当初の目的が達成できないため。
"""

from .normalize import normalize, normalize_loose, strip_site_suffix

# イベント種別。watchlist.json の categories でオン/オフする。
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "revival": (
        "リバイバル上映", "リバイバル", "再上映", "復活上映", "復刻上映",
        "アンコール上映", "4kリマスター", "リマスター版", "リマスター上映",
        "期間限定上映", "特別上映", "凱旋上映", "再映",
        "周年記念上映", "記念上映", "デジタルリマスター",
    ),
    "screening_event": (
        "舞台挨拶", "応援上映", "爆音上映", "絶叫上映", "発声可能上映",
        "ライブ上映", "先行上映", "トークショー", "トークイベント",
        "見逃し上映", "同時上映", "プレミア上映", "完成披露",
        "上映会", "特典上映",
    ),
    "exhibition": (
        "原画展", "展示会", "展覧会", "企画展", "設定資料展",
        "コラボカフェ", "コラボレーションカフェ", "ポップアップストア",
        "ポップアップショップ", "期間限定ショップ", "常設展",
        "ミュージアム", "アニメ展", "作品展", "巡回展",
        # 「富野由悠季展の開催」のように、固有名＋「展」で書かれる形。
        # 「展」単独だと「展開」「発展」に当たるので、後続の語まで含めて見る。
        "展の開催", "展が開催", "展を開催", "展開催", "展の詳細",
    ),
    "concert": (
        "オーケストラコンサート", "オーケストラ", "交響", "シンフォニー",
        "コンサート", "単独公演", "ライブイベント", "音楽祭",
        "スペシャルライブ", "アニsoン", "ライブツアー", "フェス出演",
        "生演奏上映", "シネマコンサート",
    ),
}

# 「上映」だけでは新作公開の話と区別がつかないので、単独では採用しない。
# ただし下の語と一緒に出てきたらイベント性ありとみなす。
_EVENT_HINTS = ("決定", "開催", "実施", "限定", "追加", "チケット", "受付", "発売")

# 明らかにイベントではないものを落とす
_EXCLUDE = (
    "blu-ray", "dvd", "円盤", "配信開始", "配信決定", "グッズ発売",
    "アニメイト通販", "予約受付中のグッズ", "ゲーム化", "アプリ",
)


def classify(text: str, enabled: set[str] | None = None) -> list[str]:
    """テキストから該当するイベント種別を返す。空リストなら「イベントではない」。"""
    key = normalize(text)
    if any(normalize(word) in key for word in _EXCLUDE):
        return []
    hits = []
    for category, words in CATEGORY_KEYWORDS.items():
        if enabled is not None and category not in enabled:
            continue
        if any(normalize(word) in key for word in words):
            hits.append(category)
    return hits


def _entry_terms(entry: dict) -> list[str]:
    """1エントリが持つ照合語（正式名＋別名）を集める。"""
    terms = [entry.get("title") or entry.get("name") or ""]
    terms += entry.get("aliases", [])
    return [t for t in terms if t]


def match_watchlist(text: str, watchlist: dict) -> list[dict]:
    """ウォッチリストのどの項目に当たったかを返す。

    作品は「劇場版」などを外した緩いキーでも照合するが、
    人物（作者・監督）は姓名がそのまま出るので通常の正規化のみで足りる。
    """
    haystack = normalize(text)
    haystack_loose = normalize_loose(text)
    matched = []
    for work in watchlist.get("works", []):
        for term in _entry_terms(work):
            if normalize(term) in haystack or normalize_loose(term) in haystack_loose:
                matched.append({"kind": "work", "label": work.get("title", term)})
                break
    for person in watchlist.get("people", []):
        for term in _entry_terms(person):
            # 3文字未満の人名は誤爆しやすいので採らない
            if len(normalize(term)) >= 3 and normalize(term) in haystack:
                matched.append(
                    {
                        "kind": "person",
                        "label": person.get("name", term),
                        "role": person.get("role", ""),
                    }
                )
                break
    return matched


def evaluate(candidate: dict, watchlist: dict) -> dict | None:
    """候補1件を評価する。通知に値しなければ None。

    candidate: {"title", "url", "summary", "source", "published"}
    """
    settings = watchlist.get("settings", {})
    enabled = set(settings.get("categories", CATEGORY_KEYWORDS.keys()))

    title = strip_site_suffix(candidate.get("title", ""))
    text = " ".join(
        filter(None, [title, candidate.get("summary", ""), candidate.get("url", "")])
    )

    categories = classify(text, enabled)
    if not categories and _looks_like_event(text, enabled):
        categories = ["screening_event"]
    if not categories:
        return None

    matches = match_watchlist(text, watchlist)
    if not matches and not settings.get("include_unmatched", False):
        return None

    return {
        "title": title,
        "url": candidate.get("url", ""),
        "summary": candidate.get("summary", ""),
        "source": candidate.get("source", ""),
        "published": candidate.get("published", ""),
        "categories": categories,
        "matches": matches,
        "watched": bool(matches),
    }


def _looks_like_event(text: str, enabled: set[str]) -> bool:
    """「上映」＋イベントらしさのヒント語、という弱いシグナル。"""
    if "screening_event" not in enabled and "revival" not in enabled:
        return False
    key = normalize(text)
    return "上映" in key and any(normalize(h) in key for h in _EVENT_HINTS)
