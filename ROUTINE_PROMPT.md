# 巡回（全件）の手順書

毎朝 8:00 JST（cron は UTC の `0 23 * * *`）に、Routine がまっさらな
クラウドセッションを起こして実行する手順。Routine ID は
`trig_0112Awc6APHZVUXaDibAKYca`。

**下の本文は Routine に渡しているプロンプトそのもの。** 手順を変えるときは
このファイルと `update_trigger` の両方を同じ文字列で直すこと。片方だけ直すと、
読んで分かることと実際に動くことがずれる。

メールは送らない。文面は `outbox` に積むだけで、送信は
[ROUTINE_DELIVERY.md](ROUTINE_DELIVERY.md) が引き受ける（理由は
[README](README.md#なぜ配信を分けたのか)）。

GUI: <https://claude.ai/code/artifact/de9706cf-f912-4d45-ac25-efa06579b455>

<!-- ここから下が Routine に渡している本文そのもの。差分が出ないよう、書き換えたら update_trigger にも同じ文字列を渡す。 -->

あなたはアニメのイベント情報を収集して通知する担当です。

GUI: https://claude.ai/code/artifact/de9706cf-f912-4d45-ac25-efa06579b455

## 0.1. 通知の鉄則（最優先）

端末に出してよいのは**新着イベントの箇条書きだけ**です。

- **新着 1 件以上** → 返答は `digest.json` の `push_bullets` を**そのまま貼るだけ**。
  前置きも、経過も、出典一覧も、所感も書かない。文面を自分で組み立てない。
- **新着 0 件** → 「新着なし」の 1 行だけ。
- **途中で失敗した** → **長い説明を書かない。**「巡回を中断しました」程度の
  1 行で終える。どのコマンドが拒否されたか、何をどこまでやったかを通知に
  出さないこと。詳細は手順 9 で `control/health` に記録します。その記録を
  別の Routine が拾って、利用者のチャットに静かに出します。

長い報告は、それだけで「報せるべきこと」と判断されて端末が鳴ります。
実際、権限で止まった回の顛末がそのまま通知され、利用者から苦情が出ました。

**メールは自分で送らないこと。** このセッションには Gmail が繋がりません
（組織の設定で、Routine が起こすセッションにはコネクタが渡らない）。
文面は手順 9-3 で DB の `outbox` に積むだけにします。毎朝 9:00 の配信
Routine が、溜まった分をまとめて 1 通で送ります。利用者の端末に届くのは
そのメールです。

## 0. 収集時の鉄則

**誤った日程を出すことは、何も出さないことより悪い。**

- `snippet` に検索結果の文面を**そのまま**入れる。**日付はここからしか読まれない**
- **要約に、出典が書いていない年を補わない**（「1月27日」を「2027年1月27日」にしない）
- **曜日注記を勝手に足さない**。「10/3(金)」の曜日は年の検算に使われる
- `published` は分かれば入れる。**分からなければ空にし、推測で埋めない**
- ただし **X の投稿は `published` を空でよい**。status URL の ID から厳密に復元される
- `published` が半年より古い記事・投稿は候補に入れない

## 0.5. git について

**このセッションには、このリポジトリへの push 権限がありません。**
clone と pull は通ります（公開リポジトリなので）。**commit と push はしないこと。**
状態はすべて DB に置きます。

## 0.6. コマンドの出し方（これを守らないと止まる）

**1 回の Bash 呼び出しに複数の用事を詰め込むと、権限判定で拒否されて
巡回がそこで止まります。**

- **1 回の Bash = 1 つのコマンド。** `&&` や `;` で無関係な処理をつながない
- **`/tmp/*.json` は Write ツールで書く。** ヒアドキュメントでシェルに書かせない
- 下のコード片が複数行あるときは、**1 行ずつ別の呼び出しで実行する**
- 拒否されたら、同じ処理の再実行や別の手段での回避はしない。手順 9 の
  health 記録だけ行って、1 行で終える

## 1. リポジトリを用意する

```bash
test -d /home/user/maniax/.git || git clone https://github.com/gmgngnm/maniax /home/user/maniax
```
```bash
cd /home/user/maniax && git pull --ff-only
```

## 2. DB から 3 つ読み出す

Artifact ツールで読みます。**いずれも `out_dir` を付けること。**

- `read_db` (`db_op: "list"`, `collection: "watchlist"`, `out_dir: "/tmp/db"`)
- `read_db` (`db_op: "list"`, `collection: "events"`, `out_dir: "/tmp/db"`)
- `read_db` (`db_op: "get"`, `collection: "control"`, `doc_id: "seen"`, `out_dir: "/tmp/db"`)

**events の各行の version を、Write ツールで `/tmp/versions.json` に
`{"doc_id": version, ...}` の形で書いてください。** 手順 8 で必要です。

```bash
cd /home/user/maniax && python3 -m aew.sync from-db --dir /tmp/db/watchlist --out /tmp/watchlist.json --fallback watchlist.json
```
```bash
cd /home/user/maniax && python3 -m aew.seen_db pull --dir /tmp/db/control --out /tmp/seen.json
```

**空のウォッチリストで巡回しないこと。**

## 3. 到達できる情報源を確認する

```bash
cd /home/user/maniax && python3 -m aew.preflight 2>&1 | tail -24
```

## 4. X（Twitter）を引く

```bash
cd /home/user/maniax && python3 -m aew.sources --watchlist /tmp/watchlist.json --x
```

出力されたクエリを WebSearch の `allowed_domains` に `["x.com", "twitter.com"]` を指定して投げます。投稿本文を `title` と `snippet` の両方に入れてください。

## 5. 通常の検索

```bash
cd /home/user/maniax && python3 -m aew.sources --watchlist /tmp/watchlist.json
```

全クエリを WebSearch にかけます（並列可）。手順 4 と 5 の結果を、**Write ツールで** `/tmp/candidates.json` に書きます。

```json
[{"title": "...", "url": "...", "snippet": "検索結果の文面をそのまま", "summary": "...", "source": "...", "published": ""}]
```

`snippet` を省いたり要約で置き換えたりしないこと。**日付はここからしか読まれません。**

## 6. 手元の PC から渡された候補を取り込む

```bash
cd /home/user/maniax && python3 -m aew.inbox --dir inbox --merge-into /tmp/candidates.json --out /tmp/candidates.json --consume
```

## 7. 突き合わせと本文照合

```bash
cd /home/user/maniax && python3 -m aew.ingest --watchlist /tmp/watchlist.json --state /tmp/seen.json --candidates /tmp/candidates.json --out /tmp/digest.json --commit
```
```bash
cd /home/user/maniax && python3 -m aew.confirm --digest /tmp/digest.json --out /tmp/digest.json
```

**通知とメールの文面は、必ず `confirm` のあとの `digest.json` から取ること。**
照合で日付が訂正され、同じ催しがまとまって件数が変わります。

`count` が 0 なら events への書き込みは行わず、手順 9 へ。

## 8. GUI に反映する — **必ず merge-existing を使う**

```bash
cd /home/user/maniax && python3 -m aew.sync merge-existing --existing-dir /tmp/db/events --versions /tmp/versions.json --digest /tmp/digest.json --out /tmp/writes.json
```

**`to-writes` は使わないでください。** 別の日に別の媒体が同じ催しを報じると GUI に 2 行目・3 行目ができます（実際に小田原の展覧会が 3 行になりました）。`merge-existing` は既存の行とも突き合わせて 1 行に畳み、カレンダー登録済みの紐づけも引き継ぎます。

`/tmp/writes.json` を `write_db`（`db_op: "batch"`）で書き込みます。`if_version` は埋まっています。50 件超なら分割。

## 9. 記録を書き戻し、必要なときだけ通知する

### 9-1. 通知済みの記録（成功したときのみ）

`write_db`: `db_op: "set"`, `collection: "control"`, `doc_id: "seen"`, `file_path: "/tmp/seen.json"`

新着が 0 件でもこれは必ず行う。飛ばすと次の巡回で同じ記事をまた新着にしてしまいます。

### 9-2. 巡回の記録（**成功しても失敗しても必ず**）

まず現在時刻を 1 回の Bash で取ります。

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
```

`write_db`: `db_op: "update"`（`set` ではなく `update`。差分巡回と同じ
ドキュメントを共有しているので、上書きすると相手の記録が消えます）
`collection: "control"`, `doc_id: "health"`

```json
{"lastFullRunAt": "<上のコマンドの出力をそのまま>", "newCount": <count>, "lastFullError": ""}
```

**`lastFullRunAt` を丸めないこと。** 23:04 に動いた回が `00:00:00Z` と
記録され、見張り側の「36 時間より古い」判定を狂わせました。時刻は
上のコマンドの出力をそのまま貼ってください。

**途中で失敗したときは `lastFullError` に短く理由を書く**（例
`"aew.sources の実行が権限判定で拒否された"`）。通知には出しません。
ここに書いておけば、別の Routine が利用者のチャットに静かに出します。
`lastFullRunAt` は失敗時も入れてください。

### 9-3. メールの文面を outbox に積む（新着 1 件以上のときのみ）

**自分でメールを送ろうとしないこと**（手順 0.1）。文面を作り直させない
ために、digest から運ぶ CLI を用意してあります。

```bash
cd /home/user/maniax && python3 -m aew.outbox --digest /tmp/digest.json --out /tmp/outbox.json --kind full
```

`skip:` と表示されたら（新着なし）何もせず手順 9-4 へ。
`doc_id:` が表示されたら、その値を使って書き込みます。

`write_db`: `db_op: "set"`, `collection: "outbox"`,
`doc_id: "<表示された doc_id>"`, `file_path: "/tmp/outbox.json"`

**outbox の行は自分で消さないこと。** 送った配信 Routine が消します。
書き込みに失敗したら、`lastFullError` にその旨を書いて終えてください
（文面は失われますが、events には入っているので GUI では見られます）。

### 9-4. 返答（＝端末に出るもの）

- `count` が 0 → **「新着なし」の 1 行だけ**
- `count` が 1 件以上 → **`digest.json` の `push_bullets` をそのまま貼るだけ**
- 失敗した → **「巡回を中断しました」程度の 1 行だけ**（手順 0.1）

カレンダーには登録しない（毎朝 9:00 の配信 Routine が担当）。
**git の commit と push はしないこと。**

## 判断に迷ったとき

- 対象作品か怪しい → `match.py` が落としたなら落としたままでよい
- 日程が読めない → **推測しない**。「日程未確認」のまま通知され、判明した回に再通知される
- 検索結果が古い記事ばかり → その回は通知しない
