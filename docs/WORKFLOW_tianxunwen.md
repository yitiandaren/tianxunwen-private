# 天訊文完整自動工作流

從 **WhatsApp 完整對話原文** → **去重** → **分類** → **篩出天訊文** 的可重複流程。

---

## 一、目標

| 階段 | 產出 | 原則 |
|------|------|------|
| 原始保存 | `raw/whatsapp/*.txt` | 完整對話匯出，不改字 |
| 去重主檔 | `master/whatsapp/YYYY-MM-DD.md` | 只留一天大人；**一字不改**；TX-ID 到秒 |
| 分類／篩選 | `classify/pipeline_*.csv` `.md` | 功能粗標 + 開示細類 + 產出建議 |
| 公開典藏 | 公開 `tianxunwen` archive（另步） | 僅天訊文／金句等可公開層 |

---

## 二、天訊文判定規律（自動化依據）

### 強訊號

1. 含 **「示曰」**（或「言曰」）且成段論述 → **天訊文**
2. 有 **《標題》** 且長文（如《素行心經》《素語三百》）→ **天訊文**
3. 主題詞：素行、本元、太素、靜定、簡單、觀心、順隨、三愛、天印、三元…

### 依長短與格式

| 細類 | 特徵 | 產出 |
|------|------|------|
| **天訊文** | 示曰／成篇／可典藏 | 完整文案、公開 archive |
| **短開示** | 中長、完整意旨 | 文案；可拆圖卡 |
| **金句** | 短、可獨立成卡 | **圖卡** |
| **誓願文** | 開經偈、迴向偈、十二願等 | **編印** |
| **非開示** | 飲食、叫人、數字、SOP | 不進公開層 |

### 排除

- 任務口語開頭（中午、叫、拿、約…）且短
- 短視頻公式、園區公頃級 SOP（無示曰）
- 僅媒體占位

---

## 三、腳本與指令

### 1. 去重寫入 master

```bash
python scripts/process_whatsapp_tianxunwen.py raw/whatsapp/20260401_0531_chat.txt \
  --output-dir master/whatsapp \
  --source-name 20260401_0531_chat.txt
```

### 2. 只做天訊文篩選

```bash
python scripts/screen_tianxunwen.py raw/whatsapp/20260401_0531_chat.txt \
  --only 天訊文,金句,短開示,誓願文 \
  --csv classify/screen.csv \
  --md-report classify/screen.md
```

### 3. 一鍵完整管線（建議）

```bash
python scripts/run_tianxunwen_pipeline.py raw/whatsapp/20260401_0531_chat.txt
```

產出：

- 更新 `master/whatsapp/YYYY-MM-DD.md`
- `classify/pipeline_<檔名>_<日期>.csv`
- `classify/pipeline_<檔名>_<日期>.md`（天訊文清單、金句清單）

---

## 四、目錄

```
tianxunwen-private/
  raw/whatsapp/          # 原始匯出（不可改）
  master/whatsapp/       # 去重後一天大人原文
  classify/              # 分類與篩選報告
  scripts/
    process_whatsapp_tianxunwen.py   # 去重
    screen_tianxunwen.py             # 天訊文篩選
    run_tianxunwen_pipeline.py       # 一鍵管線
  docs/WORKFLOW_tianxunwen.md
  context/               # 高價值任務前因後果（人工）
```

---

## 五、人工必做邊界

1. **需前因後果**的短指令 → 對 raw 含一天行上一則
2. 長篇園區規劃是否公開 → 人工定層級
3. 《素語三百》是否拆條 → 目前整則為一則原文

---

## 六、與公開發布銜接

1. 從 pipeline 報告勾選 `開示細類=天訊文`
2. 套公開 archive YAML 範本
3. 推到公開 `yitiandaren/tianxunwen`（正文一字不改）

---

## 七、品質檢查

- [ ] master 原文與 WhatsApp 一致（抽查）
- [ ] 示曰長文皆入「天訊文」
- [ ] 金句無混入飲食指令
- [ ] 重複匯出再跑，新增為 0 或僅真新訊
- [ ] 公開前人工過天訊文清單
