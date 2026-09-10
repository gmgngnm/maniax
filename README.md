# maniax

アニメ作品のリバイバル上映・舞台挨拶・原画展・ライブ情報を定期的に集めて、
メール / Google カレンダー / スマホ通知に流すウォッチャー。

**GUI（スマホ可）**: <https://claude.ai/code/artifact/de9706cf-f912-4d45-ac25-efa06579b455>
— 予定の一覧、月カレンダー、監視リストの追加・削除。

「気づいたときには上映が終わっていた」を防ぐのが目的なので、
**通知しすぎないこと**を優先している。ウォッチリストに載っていない作品は
既定では通知しないし、日程が既に終わったイベントも落とす。

## 動く仕組み

Routine（定期トリガー）が毎回まっさらなクラウドセッションを起動し、
[ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) の手順を実行する。

```
        GUI（Artifact）
     ┌──── watchlist ────┐                    ┌──── events ────┐
     │  作品・監督の登録  │                    │   予定・カレンダー │
     └─────────┬─────────┘                    └────────▲────────┘
               │ read_db                               │ write_db
               ▼                                       │
        aew.sync from-db ──> aew.sources ──> 検索クエリ  │
                                                │       │
                                                ▼       │
                                    WebSearch（セッションが実行）
                                                │       │
                                                ▼ candidates.json
                                    aew.ingest ──> digest.json ──┤
                                                │                 │
                                                │                 └──> メール / カレンダー / Push
                                                ▼
                                    state/seen.json（git で永続化）
```

コンテナは実行のたびに消えるので、状態は 2 か所に外出ししている。
**ウォッチリストと表示用のイベント**は Artifact のデータベース（GUI が読み書きする正）、
**「通知済み」の重複判定**は `state/seen.json` を git で持ち回る。
`watchlist.json` は DB のバックアップ兼、DB が読めなかったときの代替。

## モジュール

| ファイル | 役割 |
|---|---|
| `aew/normalize.py` | 表記ゆれの吸収。『劇場版 少女☆歌劇 レヴュースタァライト』と『少女☆歌劇レヴュスタァライト』を同一視する |
| `aew/dates.py` | 「9月18日から1週間限定」→ 9/18〜9/24 のように会期を復元する |
| `aew/match.py` | ウォッチリスト照合と、4カテゴリ（リバイバル / 上映イベント / 展示 / ライブ）への分類 |
| `aew/store.py` | 重複排除。「前回は日程不明 → 今回判明」のときだけ再通知する |
| `aew/digest.py` | メール本文・Push 文言・カレンダー登録内容の組み立て |
| `aew/ingest.py` | 上記をつなぐ CLI |
| `aew/sources.py` | 情報源と検索クエリの定義 |
| `aew/sync.py` | GUI のデータベースと収集パイプラインの相互変換 |
| `aew/collect_rss.py` | RSS 直読み経路（下記の制約あり） |

## ウォッチリストを変える

**通常は GUI から**。「監視リスト」タブで作品・人物を追加／削除すれば、
次の朝の巡回から反映される。リポジトリを触る必要はない。

`watchlist.json` を直接編集して push しても動く（DB が読めなかったときの
代替として使われる）。書式は次のとおり。

```json
{
  "works":  [{ "title": "伝説巨神イデオン", "aliases": ["イデオン"] }],
  "people": [{ "name": "富野由悠季", "role": "監督", "aliases": ["富野喜幸", "井荻麟"] }]
}
```

`aliases` は略称・旧名義を入れておくと取りこぼしが減る。
人名は 3 文字未満だと誤爆しやすいので照合対象から外している。

### settings

| キー | 既定 | 意味 |
|---|---|---|
| `categories` | 4種すべて | 通知するイベント種別 |
| `include_unmatched` | `false` | ウォッチリスト外のイベントも通知するか |
| `drop_past_events` | `true` | 終了済みのイベントを落とすか |
| `max_queries` | `40` | 1 回の実行で投げる検索クエリの上限 |

作品数 × クエリテンプレート数で件数が増えるため、
`aew.sources` はテンプレート単位のラウンドロビンで並べる。
上限で打ち切っても、特定の作品だけ完全に無視されることはない。

## 収集経路が 2 つある理由

**WebSearch 経路（現在こちらで稼働）** — セッションが検索を実行し、
結果を候補として流し込む。追加設定なしで動く。
反面、検索インデックス経由なので数日のタイムラグがあり、
記事本文が読めないぶん日程を取り逃すことがある。

**RSS 経路（`aew/collect_rss.py`、現在は不通）** — 各社のフィードを直接読む。
速報性と精度は上だが、この環境の egress ポリシーが
natalie.mu / animeanime.jp / eiga.com などを 403 で塞いでいるため、
現状では全フィードが失敗する。

許可を広げるには、[Claude Code on the web の環境設定](https://code.claude.com/docs/en/claude-code-on-the-web)
でネットワークポリシーを変更し、`aew/sources.py` の `RSS_FEEDS` に
挙げたドメインを通す。許可が下りたら、手順 3 の WebSearch を

```bash
python3 -m aew.collect_rss --out /tmp/candidates.json
```

に差し替えるだけでよい。出力形式は揃えてある。

## 手で動かす

```bash
python3 -m aew.sources --watchlist watchlist.json      # 検索クエリを見る
python3 -m aew.ingest --candidates candidates.json     # --commit なしなら state を汚さない
python3 -m unittest discover -s tests -t .             # テスト
```

`--commit` を付けるまで `state/seen.json` は更新されない。
結果を確認してから記録する運用ができる。
