# inbox — 手元の PC から渡す収集結果の置き場

巡回が動くクラウド環境は、egress ポリシーで X も Yahoo! リアルタイム検索も
塞がれている。手元の PC にはその制限が無いので、**検索だけを手元でやり、
結果をここに置いて push する**と、次の巡回が拾って通常の結果と一緒に扱う。

```bash
python3 -m aew.collect_x --watchlist watchlist.json
git add inbox && git commit -m "x: 収集" && git push
```

取り込まれたファイルは巡回側が削除するので、置きっぱなしで構わない。

手で作っても構わない。形式は候補 JSON の配列。

```json
[{"title": "投稿本文をそのまま", "url": "https://x.com/user/status/123...",
  "snippet": "投稿本文をそのまま", "source": "X (@user)", "published": ""}]
```

`published` は空でよい。X の URL なら status ID から投稿日時が厳密に復元される。
**年を自分で書き足さないこと。** 出典に無い年を補うと、終わったイベントが
未来の予定に化ける。
