## 2. Layer 1：Obsidian Vault 設計 任意

### 2-1. フォルダ構成

```
vault/
├── Journal/
│   ├── 20251202.md   ← 既存（プレーンテキスト）
│   ├── 20251203.md
│   └── ...
├── _Templates/
│   └── journal.md    ← 新テンプレート（以下参照）
└── _Archive/         ← 処理済みフラグ用（任意）
```

### 2-2. 日記テンプレート（新規ノート用）

```yaml
---
date: 2026-03-29
type: journal
mood:            # good / neutral / tired / 高揚 など自由に
energy:          # high / mid / low
context:         # 仕事 / 個人 / 登山 / 勉強
topics: []       # [診断士, DX, MI, 自分AI, 登山, 食, 思考] など
people: []       # 登場人物（社内は役職でもOK）
decisions: []    # この日に決めたこと・意図・方針（一言で）
status: raw      # raw / reviewed
---
```

```markdown
## 今日の文脈
<!-- 状況の背景を一言 -->

## 思ったこと・感じたこと
<!-- 完全自由記述 -->

## 気づき・学び
<!-- 任意 -->

## 次につながること
<!-- 任意 -->
```

**運用ルール**:
- `date`・`type`・`topics` の3つだけ必ず埋める
- 残りは空欄でも処理上は問題なし
- 既存ファイルにfrontmatterを後付けする必要はない（スクリプト側で対応）

---