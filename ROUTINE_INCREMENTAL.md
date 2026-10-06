# 巡回（差分）の手順書

毎時 0 分（8 時台を除く。cron は UTC の `0 0-22 * * *`）に動く軽い巡回。
GUI から追加された項目と、再検索の予約だけを拾う。Routine ID は
`trig_01MvYdXHy9Kwf9iccvLTKJ8F`。

1 日 23 回動くので、**やることが無ければ DB を 2 つ読んだだけで終える**のが
設計の要。clone もしない。

**下の本文は Routine に渡しているプロンプトそのもの。** 手順を変えるときは
このファイルと `update_trigger` の両方を同じ文字列で直すこと。

メールは送らない。文面は `outbox` に積むだけで、送信は
[ROUTINE_DELIVERY.md](ROUTINE_DELIVERY.md) が引き受ける。

GUI: <https://claude.ai/code/artifact/de9706cf-f912-4d45-ac25-efa06579b455>

<!-- ここから下が Routine に渡している本文そのもの。差分が出ないよう、書き換えたら update_trigger にも同じ文字列を渡す。 -->

GUI から追加された作品・監督と、手動の再検索予約だけを拾う差分巡回です。**大半の回は何もせずに終わります。空振りを安く済ませるのが最優先です。**

GUI: https://claude.ai/code/artifact/de9706cf-f912-4d45-ac25-efa06579b455

## 0.1. 通知の鉄則（最優先）

端末に出してよいのは**新着イベントの箇条書きだけ**です。
この Routine は 1 日 23 回動くので、ここが崩れると端末が鳴り続けます。

- **新着 1 件以上** → 返答は `digest.json` の `push_bullets` を**そのまま貼るだけ**。
  前置きも、経過も、出典一覧も、所感も書かない。文面を自分で組み立てない。
- **やることが無い / 新着 0 件** → 「対象なし」または「新着なし」の 1 行だけ。
- **途中で失敗した** → **長い説明を書かない。**「巡回を中断しました」程度の
  1 行で終える。どのコマンドが拒否されたか、何をどこまでやったかを通知に
  出さないこと。詳細は手順 6 で `control/health` に記録します。その記録を
  別の Routine が拾って、利用者のチャットに静かに出します。

長い報告は、それだけで「報せるべきこと」と判断されて端末が鳴ります。
実際、権限で止まった回の顛末がそのまま通知され、利用者から苦情が出ました。

**メールは自分で送らないこと。** このセッションには Gmail が繋がりません
（組織の設定で、Routine が起こすセッションにはコネクタが渡らない）。
文面は手順 6-3 で DB の `outbox` に積むだけにします。毎朝 9:00 の配信
Routine が、溜まった分をまとめて 1 通で送ります。

## 0. 収集時の鉄則

**誤った日程を出すことは、何も出さないことより悪い。**

- `snippet` に検索結果の文面を**そのまま**入れる。**日付はここからしか読まれない**
- **要約に、出典が書いていない年を補わない**
- **曜日注記を勝手に足さない**（年の検算に使われる）
- `published` は分かれば入れ、分からなければ空にする。推測で埋めない
- **X の投稿は `published` を空でよい**（status ID から厳密に復元される）
- 半年より古い記事・投稿は候補に入れない

## 0.5. git について

**このセッションには、このリポジトリへの push 権限がありません。**
clone と pull は通ります（公開リポジトリなので）。**commit と push はしないこと。**

## 0.6. コマンドの出し方（これを守らないと止まる）

**1 回の Bash 呼び出しに複数の用事を詰め込むと、権限判定で拒否されて
巡回がそこで止まります。** 実際、`versions.json` の作成と `aew.sync` /
`aew.seen_db` / `aew.sources` を 1 回にまとめた呼び出しが拒否され、
2 件の作品が未検索のまま残りました。

- **1 回の Bash = 1 つのコマンド。** `&&` や `;` で無関係な処理をつながない
- **`/tmp/*.json` は Write ツールで書く。** ヒアドキュメントでシェルに書かせない
- 下のコード片が複数行あるときは、**1 行ずつ別の呼び出しで実行する**
- 拒否されたら、同じ処理の再実行や別の手段での回避はしない。手順 6 の
  health 記録だけ行って、1 行で終える

## 1. まず、やることがあるかだけ確かめる

**リポジトリを clone する前に**、Artifact ツールで次の 2 つを読みます。

- `read_db` (`db_op: "get"`, `collection: "control"`, `doc_id: "rescan"`)
- `read_db` (`db_op: "list"`, `collection: "watchlist"`)

判定はこれだけです。

- `control/rescan` の `requested` が `true` → **全件モード**
- watchlist に `searched` が `false` の項目がある → **差分モード**（その項目だけ）
- どちらでもない → **ここで終了**。clone も書き込みも通知も一切しない。
  health への記録も不要。「対象なし」の 1 行で終える。

## 2. リポジトリとデータを用意する（やることがある場合のみ）

```bash
test -d /home/user/maniax/.git || git clone https://github.com/gmgngnm/maniax /home/user/maniax
```
```bash
cd /home/user/maniax && git pull --ff-only
```

Artifact ツールで読みます。**いずれも `out_dir: "/tmp/db"` を付けること。**

- `watchlist` コレクション（`db_op: "list"`）
- `events` コレクション（`db_op: "list"`）
- `control/seen`（`db_op: "get"`, `collection: "control"`, `doc_id: "seen"`）

**events の各行の version を、Write ツールで `/tmp/versions.json` に
`{"doc_id": version}` の形で書いてください。** 手順 5 で必要です。

```bash
cd /home/user/maniax && python3 -m aew.sync from-db --dir /tmp/db/watchlist --out /tmp/watchlist.json
```
差分モードなら末尾に `--pending-only` を付ける。続けて別の呼び出しで:

```bash
cd /home/user/maniax && python3 -m aew.seen_db pull --dir /tmp/db/control --out /tmp/seen.json
```

## 3. X と通常検索の両方を引く

```bash
cd /home/user/maniax && python3 -m aew.sources --watchlist /tmp/watchlist.json --x
```
```bash
cd /home/user/maniax && python3 -m aew.sources --watchlist /tmp/watchlist.json
```

X 用は WebSearch の `allowed_domains` に `["x.com", "twitter.com"]` を指定。投稿本文を `title` と `snippet` の両方に入れます。通常のクエリはドメイン指定なし。

**両方の結果を Write ツールで `/tmp/candidates.json` に書きます。**
`snippet` には検索結果の文面をそのまま入れること。**日付はここからしか読まれません。**

```json
[{"title": "...", "url": "...", "snippet": "検索結果の文面をそのまま", "summary": "...", "source": "...", "published": ""}]
```

## 4. 突き合わせと本文照合

```bash
cd /home/user/maniax && python3 -m aew.ingest --watchlist /tmp/watchlist.json --state /tmp/seen.json --candidates /tmp/candidates.json --out /tmp/digest.json --commit
```
```bash
cd /home/user/maniax && python3 -m aew.confirm --digest /tmp/digest.json --out /tmp/digest.json
```

**通知とメールの文面は、必ず `confirm` のあとの `digest.json` から取ること。**
照合で日付が訂正され、同じ催しがまとまって件数が変わります。

## 5. 反映して印をつける — **必ず merge-existing を使う**

新着が 0 件でも、**印の更新と手順 6 の書き戻しは必ず行ってください**。飛ばすと同じ項目を毎時間検索し続けます。

```bash
cd /home/user/maniax && python3 -m aew.sync merge-existing --existing-dir /tmp/db/events --versions /tmp/versions.json --digest /tmp/digest.json --out /tmp/writes.json
```
```bash
cd /home/user/maniax && python3 -m aew.sync mark-searched --dir /tmp/db/watchlist --out /tmp/marks.json
```
全件モードなら `mark-searched` に `--all` を付ける。

**`to-writes` は使わないでください。** 別の日に別の媒体が同じ催しを報じると GUI に 2 行目・3 行目ができます（実際に小田原の展覧会が 3 行になりました）。

`write_db`（`db_op: "batch"`）で書き込みます。

- `/tmp/writes.json`（`if_version` は merge-existing が埋めてある）
- `/tmp/marks.json`（対象が GUI から削除済みで失敗したらその項目は飛ばす）
- `control/rescan` を `set` で `{"requested": false, "lastRunAt": "<現在時刻のISO8601>"}`

## 6. 記録を書き戻し、必要なときだけ通知する

### 6-1. 通知済みの記録（成功したときのみ）

`write_db`: `db_op: "set"`, `collection: "control"`, `doc_id: "seen"`, `file_path: "/tmp/seen.json"`

新着が 0 件でもこれは必ず行う。

### 6-2. 巡回の記録（**手順 2 まで進んだ回は、成功しても失敗しても必ず**）

まず現在時刻を 1 回の Bash で取ります。

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
```

`write_db`: `db_op: "update"`（`set` ではなく `update`。日次巡回と同じ
ドキュメントを共有しているので、上書きすると相手の記録が消えます）
`collection: "control"`, `doc_id: "health"`

```json
{"lastDiffRunAt": "<上のコマンドの出力をそのまま>", "lastDiffError": ""}
```

**時刻を丸めないこと**（見張り側の判定が狂います）。

**途中で失敗したときは `lastDiffError` に短く理由を書く**（例
`"aew.sources の実行が権限判定で拒否された"`）。通知には出しません。

手順 1 で「対象なし」として終わった回は、この記録も不要です。

### 6-3. メールの文面を outbox に積む（新着 1 件以上のときのみ）

**自分でメールを送ろうとしないこと**（手順 0.1）。文面を作り直させない
ために、digest から運ぶ CLI を用意してあります。

```bash
cd /home/user/maniax && python3 -m aew.outbox --digest /tmp/digest.json --out /tmp/outbox.json --kind diff
```

`skip:` と表示されたら（新着なし）何もせず手順 6-4 へ。
`doc_id:` が表示されたら、その値を使って書き込みます。

`write_db`: `db_op: "set"`, `collection: "outbox"`,
`doc_id: "<表示された doc_id>"`, `file_path: "/tmp/outbox.json"`

**outbox の行は自分で消さないこと。** 送った配信 Routine が消します。

### 6-4. 返答（＝端末に出るもの）

- やることが無い / `count` が 0 → **1 行だけ**
- `count` が 1 件以上 → **`digest.json` の `push_bullets` をそのまま貼るだけ**
- 失敗した → **「巡回を中断しました」程度の 1 行だけ**（手順 0.1）

カレンダーには登録しない（毎朝 9:00 の配信 Routine が担当）。
**git の commit と push はしないこと。**
