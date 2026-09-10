"""アニメのイベント・リバイバル上映情報を定期収集して通知するための小さなツール群。

収集経路は2つあり、どちらも同じ「候補(candidate)」形式に落としてから
ingest で突き合わせる。

  1. WebSearch 経路 … Claude が検索した結果を candidates JSON にして流し込む。
     ネットワーク許可が要らないので、この環境でそのまま動く。
  2. RSS 経路 … collect_rss が各社のフィードを直接読む。
     egress ポリシーで対象ドメインが許可されている必要がある。
"""

__all__ = ["normalize", "dates", "match", "store", "digest"]
