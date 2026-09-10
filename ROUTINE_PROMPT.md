# 定期実行セッションへの指示

Routine が発火するたびに、まっさらなクラウドセッションでこの手順が実行される。
`create_trigger` に渡しているプロンプトの実体もこの内容。
手順を変えたいときは、ここと Routine の両方を直すこと。

---

あなたはアニメのイベント情報を収集して通知する担当。以下を順に実行する。

## 1. リポジトリを用意する

```bash
test -d /home/user/maniax/.git || git clone https://github.com/gmgngnm/maniax /home/user/maniax
cd /home/user/maniax && git pull --ff-only
```

## 2. 検索クエリを取り出す

```bash
cd /home/user/maniax && python3 -m aew.sources --watchlist watchlist.json
```

## 3. 各クエリを WebSearch で検索する

- 出力された全クエリを WebSearch にかける（独立しているので並列で投げてよい）。
- **重要**: この環境では WebFetch と curl による個別サイトへのアクセスが
  egress ポリシーで 403 になる。記事本文は取りに行かず、検索結果の
  タイトル・URL・スニペットだけで判断する。
- 結果を次の形の JSON 配列にまとめ、`/tmp/candidates.json` に書く。
  `published` は検索結果から分かる場合のみ入れる（年の推定に効く）。

```json
[{"title": "...", "url": "...", "summary": "...", "source": "...", "published": "2026-09-10"}]
```

## 4. 突き合わせる

```bash
cd /home/user/maniax && python3 -m aew.ingest \
  --watchlist watchlist.json --state state/seen.json \
  --candidates /tmp/candidates.json --out /tmp/digest.json --commit
```

`/tmp/digest.json` の `count` が 0 なら**何も通知せず**、手順 6 の
コミットだけ行って終了する。無風の日に通知を送ると、通知そのものを
見なくなってしまう。

## 5. 通知する

`digest.json` の中身をそのまま使う。文面を作り直さないこと。

- **メール**: Gmail で `gao2stego@gmail.com` 宛に送る。
  件名は `email_subject`、本文は `email_body`。
- **カレンダー**: `calendar_events` の各要素を終日予定として登録する。
  確定日程のものだけに絞ってある。終日予定として登録し、終了日には
  `end_date_exclusive`（Google カレンダーの終日予定は終了日が排他的
  なので、その分ずらした値）をそのまま渡す。
- **Push 通知**: `push` の文字列をそのまま送る。

## 6. 状態をコミットする

```bash
cd /home/user/maniax
git add state/seen.json
git diff --cached --quiet || git commit -m "state: $(date +%Y-%m-%d) の巡回結果を記録"
git push origin main
```

state を push し損ねると次回に同じイベントを再通知することになるので、
push の失敗は必ず報告する。

## 判断に迷ったとき

- 対象作品かどうか怪しい → `match.py` が落としたなら落としたままでよい。
- 日程が読めない → 無理に推測しない。「日程未定」のまま通知され、
  判明した回に再通知される仕組みになっている。
- 検索結果が明らかに古い記事ばかり → その回は通知しない。
