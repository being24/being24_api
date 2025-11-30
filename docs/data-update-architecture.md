# データ更新アーキテクチャ設計書

## 目次
- [概要](#概要)
- [現状の課題](#現状の課題)
- [新アーキテクチャ](#新アーキテクチャ)
- [データフロー](#データフロー)
- [実装計画](#実装計画)
- [技術仕様](#技術仕様)
- [考慮事項](#考慮事項)

## 概要

ページデータの更新処理を2段階に分離し、レスポンス速度を向上させつつ、最終的には完全なデータを取得する仕組みを構築する。

### 設計の目的
- **レスポンス速度の改善**: Wikidot APIの遅延をユーザーに見せない
- **スケーラビリティの向上**: 全データを毎日走査する必要をなくす
- **リソース効率化**: 必要なデータのみを更新
- **データ鮮度の維持**: リクエストされたデータは迅速に更新

## 現状の課題

### 問題点
1. **全データスキャンの限界**: 毎日全データを走査するのはスケールしない
2. **Wikidot APIの遅さ**: レスポンスタイムが長く、ユーザー体験が悪化
3. **無駄なリクエスト**: アクセスされないデータも更新している

### パフォーマンス比較
```
Wikidot + Crom API: ~X秒/ページ
Crom APIのみ:      ~Y秒/ページ (約Z倍高速)
```

## 新アーキテクチャ

### 2段階更新モデル

```
┌─────────────┐
│ユーザー     │
│リクエスト   │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────┐
│ 第1段階: 即時レスポンス (Crom APIのみ)│
├──────────────────────────────────────┤
│ 1. Crom APIから投票履歴取得          │
│ 2. rating/dateフィールドのみDB更新   │
│ 3. 即座にレスポンス返却              │
│ 4. 更新キューにページIDを追加        │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│ 第2段階: バックグラウンド完全更新    │
├──────────────────────────────────────┤
│ 1. キューから未完了ページIDを取得   │
│ 2. Wikidot APIで完全データ取得       │
│ 3. Crom APIで投票履歴取得            │
│ 4. DBを完全データで更新              │
│ 5. キューから削除                    │
└──────────────────────────────────────┘
```

### データ状態管理

#### 部分更新戦略 (Cromのみ)
- **取得元**: Crom API
- **更新対象フィールド**:
  - `date` (日付)
  - `rating` (各日付のrating値)
  - `metatitle` (Cromから取得)
  - `tags` (Cromから取得)
- **更新方法**: 既存ドキュメントの該当フィールドのみを上書き (`$set`操作)
- **保持されるデータ**:
  - `created_at`, `updated_at`, `commented_at`
  - `created_by`, `updated_by`, `commented_by`
  - `comments`, `size`, `revisions`, `rating_votes`
  - `fullname`, `title`
  - その他すべての既存フィールド

**利点**: 既存データを消失させるリスクがない。Wikidotから取得済みのデータはそのまま保持される。

#### 完全更新 (Wikidot + Crom)
- **取得元**: Wikidot API + Crom API
- **更新方法**: ドキュメント全体を新しいデータで置き換え
- **すべてのフィールド**が最新の正確な値になる

## データフロー

### 即時レスポンスフロー
```
[リクエスト] → [Crom API] → [DB部分更新(rating/date/tags)] → [レスポンス]
                    ↓
              [キュー追加]
```

### バックグラウンド処理フロー
```
[定時実行] → [キュー取得] → [Wikidot API] → [Crom API] → [DB完全更新(全フィールド)] → [キューから削除]
```

## 実装計画

### Phase 1: 基盤実装
- [ ] 更新キュー管理モジュール作成 (`app/internal/update_queue.py`)
- [ ] 部分更新用のDB操作関数作成 (rating/date/metatitle/tagsのみ`$set`)
- [ ] 既存の`get_date_pages_by_id`関数の統合

### Phase 2: 即時レスポンス層
- [ ] 高速更新エンドポイント作成/修正
- [ ] Crom APIのみでのDB部分更新ロジック (既存データ保持)
- [ ] キューへのページID追加処理

### Phase 3: バックグラウンド処理層
- [ ] バックグラウンドワーカー作成 (`app/workers/wikidot_updater.py`)
- [ ] 定時実行スクリプト作成
- [ ] エラーハンドリングとリトライロジック

### Phase 4: 運用・最適化
- [ ] モニタリング・ロギング強化
- [ ] キュー優先度制御
- [ ] レート制限対応
- [ ] パフォーマンスチューニング

## 技術仕様

### 更新キュー設計

#### MongoDBコレクション: `update_queue`
```javascript
{
  _id: ObjectId,
  page_id: Number,           // Wikidot ID
  requested_at: ISODate,     // 最初にリクエストされた日時
  last_requested_at: ISODate,// 最後にリクエストされた日時
  request_count: Number,     // リクエスト回数（優先度判定に使用）
  status: String,            // "pending" | "processing" | "completed" | "failed"
  priority: Number,          // 優先度 (request_countベース)
  retry_count: Number,       // リトライ回数
  last_error: String,        // 最後のエラーメッセージ
  updated_at: ISODate        // 最終更新日時
}
```

#### インデックス
```javascript
{ page_id: 1 }                    // ユニーク制約
{ status: 1, priority: -1 }       // キュー処理用
{ status: 1, updated_at: 1 }      // タイムアウト検出用
```

### DB更新戦略

#### 部分更新 (Crom APIのみ)
MongoDBの`$set`演算子を使用して、特定フィールドのみを更新:
```python
# rating/dateフィールドのみ更新
db.ayame_date_pages.update_many(
  {"id": page_id},
  {
    "$set": {
      "date": date_value,
      "rating": rating_value,
      "metatitle": metatitle_value,
      "tags": tags_value
    }
  }
)
```

**重要**: 既存のドキュメントが存在しない場合は、部分更新ではなく新規作成が必要。
その場合は一時的にダミー値を使用してドキュメントを作成し、キューに追加。

#### 完全更新 (Wikidot + Crom)
ドキュメント全体を置き換え:
```python
# 全フィールドを新しいデータで置き換え
db.ayame_date_pages.replace_one(
  {"id": page_id, "date": date_value},
  new_complete_document
)
```

### APIエンドポイント

#### 新規/修正エンドポイント
```
POST /api/pages/{page_id}/update-fast
- Crom APIのみで即座に更新
- レスポンス: { status: "updated", fields: ["rating", "date", "metatitle", "tags"] }
```

### `/data/pageid` エンドポイント現在仕様

ユーザーが `GET /data/pageid?pageid={id}` を呼び出した際の挙動を以下に定義する。

#### フロー概要
```
1. クエリ `pageid` を取得
2. MongoDB `collection_search` / `collection_data` に対象IDの最新ドキュメントがあるか確認
3. あれば既存データを返却（必要に応じて rating 履歴も別取得）
4. なければ Crom API を問い合わせ
   4-1. Cromに存在する → 部分データ生成 (rating/date/metatitle/tags) を保存しレスポンス、キューへ投入
   4-2. Cromに存在しない → 404同等の意味合いで `{ "page_id": id, "found": false }` を返却
```

#### 状態判定ロジック
| ケース | DBに既存 | Crom存在 | レスポンス `data_state` | キュー投入 | 備考 |
|--------|----------|----------|-------------------------|------------|------|
| A 初回アクセス | なし | あり | partial | する | ダミー作成 + 部分更新 |
| B 初回アクセス | なし | なし | none | しない | 存在しない通知 |
| C 既存 complete | あり | - | complete | 条件付き | TTL超過なら再enqueue |
| D 既存 partial | あり | - | partial | 条件付き | 完全更新待ち |

#### 部分更新生成フィールド
```
{
  "id": <page_id>,
  "fullname": <URL末尾 or 推定値>,
  "title": null (不明時は metatitle 同値),
  "metatitle": <Crom.wikidotInfo.title>,
  "tags": <Crom.wikidotInfo.tags>,
  "date": <当日 or 各投票日>,
  "rating": <各日付時点rating>,
  "data_state": "partial"
}
```

#### 代表的レスポンス例
既存完全データ:
```json
{
  "page_id": 123456,
  "data_state": "complete",
  "latest": {
    "date": "2025-11-30",
    "rating": 42,
    "metatitle": "SCP-XXX-JP",
    "tags": ["scp", "jp"]
  },
  "queued_for_full": false
}
```

初回アクセスでCromから部分取得:
```json
{
  "page_id": 987654,
  "data_state": "partial",
  "latest": {
    "date": "2025-11-30",
    "rating": 3,
    "metatitle": "SCP-YYY-JP",
    "tags": ["scp", "jp", "tale"]
  },
  "queued_for_full": true
}
```

存在しないID:
```json
{
  "page_id": 11111111,
  "found": false
}
```

#### キュー投入条件 (暫定)
- ドキュメント未存在かつ Crom に存在 → 直ちに enqueue
- `data_state=partial` で最終完全更新時刻が未設定 → enqueue 維持
- `data_state=complete` かつ 最終完全更新時刻が TTL(例: 30分) 超過 → 再 enqueue
- 最近 enqueue 済み (`last_enqueued_at < MIN_INTERVAL`) の場合はスキップ

#### 失敗時の扱い
- Crom問い合わせ失敗（ネットワーク等）: レスポンスは既存DB（なければ `found:false`）、内部でリトライ用に軽度ログ
- 連続失敗はキュー `retry_count` 増加で監視対象

#### 返却メタ情報（案）
| フィールド | 意味 |
|------------|------|
| `data_state` | `partial` / `complete` / `none` |
| `queued_for_full` | 完全更新キュー投入済みか |
| `last_partial_at` | 部分更新最終時刻 |
| `last_complete_at` | 完全更新最終時刻 |
| `found` | ページ存在判定（存在しない時のみ false） |

将来的に `/system/update_partial?pageid=` で強制部分更新、`/system/update_full?pageid=` で即時完全更新を追加可能。


### バックグラウンドワーカー

#### 実行頻度
- **初期案**: 1時間ごと
- **動的調整**: キューサイズに応じて実行頻度を変更

#### 処理フロー
```python
1. キューから優先度順にN件取得 (status="pending")
2. 各ページIDについて:
   a. status="processing"に更新
   b. Wikidot API + Crom APIでデータ取得
  c. DB完全更新 (全フィールド)
   d. status="completed"に更新
3. エラー時:
   a. retry_count++
   b. status="failed" (retry_count > MAX_RETRY)
   c. status="pending" (それ以外)
```

#### レート制限対策
- Wikidot API: X req/min → sleep制御
- Crom API: Y req/min → 並列度制限

### エラーハンドリング

#### リトライ戦略
```python
MAX_RETRY = 3
RETRY_DELAYS = [60, 300, 3600]  # 秒単位
```

#### エラー種別
- **一時的エラー**: ネットワーク、API障害 → リトライ
- **永続的エラー**: ページ削除、ID不正 → failed状態で停止

## 考慮事項

### データ整合性
- **部分更新の安全性**: 既存フィールドを上書きしないため、データ消失リスクなし
- **新規ページの扱い**: 初回は一時的にダミー値でドキュメント作成、すぐキュー追加
- **更新中の読み取り**: rating/dateは最新、その他フィールドは既存値を使用

### パフォーマンス
- **キューサイズ監視**: 溜まりすぎたら警告
- **処理スループット**: 1時間あたりN件処理可能
- **DB負荷**: 更新頻度によるインデックス最適化

### 運用
- **モニタリング項目**:
  - キューサイズ (pending, processing, failed)
  - 平均処理時間
  - エラー率
  - 最終完全更新からの経過時間

- **アラート条件**:
  - pending > X件
  - failed > Y件
  - processing状態が1時間以上

### スケーリング
- **水平スケール**: ワーカーを複数起動 (分散ロック必要)
- **優先度制御**: アクセス頻度の高いページを優先

### 移行戦略
1. **Phase 1**: 新システムと並行運用
2. **Phase 2**: 徐々に新システムへ切り替え
3. **Phase 3**: 旧システム停止、全データcomplete化

## 次のステップ

### 優先実装項目
1. ✅ `get_date_pages_by_id`関数 (完了)
2. ✅ `update_queue.py` モジュール (完了)
3. ✅ 高速更新エンドポイント `/data/pageid` (完了)
4. ✅ バックグラウンドワーカー `process_partial_queue` (完了)
5. ✅ 定時実行統合 `main.py` の `periodic_update` (完了)

### 実装状況

#### Phase 1: 基盤実装 ✅
- ✅ 更新キュー管理モジュール作成 (`app/internal/update_queue.py`)
- ✅ 部分更新用のDB操作関数作成 (rating/date/metatitle/tagsのみ`$set`)
- ✅ 既存の`get_date_pages_by_id`関数の統合

#### Phase 2: 即時レスポンス層 ✅
- ✅ `/data/pageid` エンドポイント拡張
  - 今日のデータなし時にCrom APIから即座に取得
  - レスポンス返却後、バックグラウンドでキュー投入 (`asyncio.create_task`)
- ✅ Crom APIのみでのDB部分更新ロジック (`partial_update_from_crom`)
- ✅ キューへのページID追加処理 (`update_queue.enqueue`)

#### Phase 3: バックグラウンド処理層 ✅
- ✅ バックグラウンドワーカー作成 (`process_partial_queue`)
- ✅ 定時実行統合 (`main.py` の `periodic_update` に組み込み、3時間ごと実行)
- ⬜ エラーハンドリングとリトライロジック (基本実装済み、監視は未)

#### Phase 4: 運用・最適化 🔄
- ⬜ モニタリング・ロギング強化
- ⬜ キュー優先度制御の調整
- ⬜ レート制限対応
- ⬜ パフォーマンスチューニング

### 定時実行の実装

`main.py` の `periodic_update` 関数にて3時間ごとに実行:

```python
async def periodic_update():
    # 1. フル更新（直近4時間更新ページ: Wikidot + Crom）
    await ayame_update.update_database()
    
    # 2. キュー処理（pending状態のpage_id: Cromのみ部分更新）
    result = await ayame_update.process_partial_queue(batch_size=50)
```

**実行順序:**
1. 最近更新されたページの完全データ取得 (Wikidot + Crom)
2. ユーザーリクエストでキューに入ったページの部分更新 (Crom のみ)

### 検証項目
- ✅ 部分更新後のデータでフロントエンドが正常動作するか (rating/date/tags/metatitleのみ更新)
- ✅ 既存フィールドが意図せず消失していないか確認 (`$set`操作で安全)
- ⬜ キュー処理のスループット測定
- ⬜ エラーケースの網羅的テスト
