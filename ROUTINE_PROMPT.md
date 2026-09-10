# 定期実行セッションへの指示

Routine が発火するたびに、まっさらなクラウドセッションでこの手順が実行される。
`create_trigger` に渡しているプロンプトの実体もこの内容。
手順を変えたいときは、ここと Routine の両方を直すこと。

GUI は Artifact として公開してある:
<https://claude.ai/code/artifact/de9706cf-f912-4d45-ac25-efa06579b455>

ウォッチリストの正はこの Artifact のデータベース。リポジトリの
`watchlist.json` はバックアップ兼、DB が読めなかったときの代替。

---

あなたはアニメのイベント情報を収集して通知する担当。以下を順に実行する。

## 1. リポジトリを用意する

```bash
test -d /home/user/maniax/.git || git clone https://github.com/gmgngnm/maniax /home/user/maniax
cd /home/user/maniax && git pull --ff-only
```

## 2. ウォッチリストを取り出す

Artifact ツールの `read_db` で、上記 URL の `watchlist` コレクションを
`--out_dir /tmp/db` に読み出す。続けて収集側の形に直す。

```bash
cd /home/user/maniax && python3 -m aew.sync from-db \
  --dir /tmp/db/watchlist --out /tmp/watchlist.json --fallback watchlist.json
```

DB が読めない、または空だった場合はリポジトリの `watchlist.json` を
そのまま使う（`--out` 先にコピーする）。**空のウォッチリストで巡回しないこと。**
全作品の監視が黙って止まる。

## 3. 検索クエリを取り出す

```bash
cd /home/user/maniax && python3 -m aew.sources --watchlist /tmp/watchlist.json
```

## 4. 各クエリを WebSearch で検索する

- 出力された全クエリを WebSearch にかける（独立しているので並列で投げてよい）。
- **重要**: この環境では WebFetch と curl による個別サイトへのアクセスが
  egress ポリシーで 403 になる。記事本文は取りに行かず、検索結果の
  タイトル・URL・スニペットだけで判断する。
- 結果を次の形の JSON 配列にまとめ、`/tmp/candidates.json` に書く。
  `published` は検索結果から分かる場合のみ入れる（年の推定に効く）。

```json
[{"title": "...", "url": "...", "summary": "...", "source": "...", "published": "2026-09-10"}]
```

## 5. 突き合わせる

```bash
cd /home/user/maniax && python3 -m aew.ingest \
  --watchlist /tmp/watchlist.json --state state/seen.json \
  --candidates /tmp/candidates.json --out /tmp/digest.json --commit
```

`/tmp/digest.json` の `count` が 0 なら**通知も DB 書き込みも行わず**、
手順 8 のコミットだけ行って終了する。無風の日に通知を送ると、
通知そのものを見なくなってしまう。

## 6. GUI に反映する

```bash
cd /home/user/maniax && python3 -m aew.sync to-writes \
  --digest /tmp/digest.json --out /tmp/writes.json
```

`/tmp/writes.json` の中身を Artifact ツールの `write_db`（`db_op: "batch"`）で
上記 URL に書き込む。`doc_id` は収集側の重複判定と同じ値なので、
同じイベントを拾い直しても行は増えず上書きになる。
50 件を超える場合は 50 件ずつに分けて送る。

## 7. 通知する

`digest.json` の中身をそのまま使う。文面を作り直さないこと。

- **メール**: Gmail で `gao2stego@gmail.com` 宛に送る。
  件名は `email_subject`、本文は `email_body`。
- **カレンダー**: `calendar_events` の各要素を終日予定として登録する。
  開始日は `start_date`、終了日は `end_date_exclusive`（Google カレンダーの
  終日予定は終了日が排他的なので、その分ずらして計算済みの値）を渡す。
- **Push 通知**: `push` の文字列をそのまま送る。

Gmail や Google カレンダーのツールが使えない場合は、無理に代替手段を探さず、
その旨をはっきり報告したうえで `email_body` の内容を回答本文に全文書き出す。
GUI への書き込み（手順 6）は成功していれば、情報自体は失われない。

## 8. 状態をコミットする

```bash
cd /home/user/maniax
cp /tmp/watchlist.json watchlist.json   # GUI 側の変更をリポジトリにも残す
git add state/seen.json watchlist.json
git diff --cached --quiet || git -c user.email=gao2stego@gmail.com -c user.name="Osakaya" \
  commit -m "state: $(date +%Y-%m-%d) の巡回結果を記録"
git push origin main
```

state を push し損ねると次回に同じイベントを再通知することになるので、
push の失敗は必ず報告する。

## 判断に迷ったとき

- 対象作品かどうか怪しい → `match.py` が落としたなら落としたままでよい。
- 日程が読めない → 無理に推測しない。「日程未定」のまま通知され、
  判明した回に再通知される仕組みになっている。
- 検索結果が明らかに古い記事ばかり → その回は通知しない。
