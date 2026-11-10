# 運作原理：從 RSS 到單字卡

本文說明每天自動抓新聞、整理單字的完整流程。對應程式：[`main.py`](main.py)、[`config.yaml`](config.yaml)、[`.github/workflows/daily-news.yml`](.github/workflows/daily-news.yml)。

## 1. 整體流程

```mermaid
flowchart TD
    A([⏰ GitHub Actions 排程<br/>每天 UTC 23:00 = 台灣 07:00<br/>或手動 workflow_dispatch]) --> B[checkout + 安裝 Python 套件]
    B --> C[python main.py<br/>讀取 config.yaml / GEMINI_API_KEY]
    C --> D[抓取 RSS 並挑選 5 則新聞]
    D --> E[組成一個 prompt<br/>一次呼叫 Gemini]
    E --> F[驗證 JSON 結構]
    F --> G[轉成 Markdown / Anki CSV / README]
    G --> H{有檔案變動?}
    H -- 是 --> I[git commit + push<br/>github-actions bot]
    H -- 否 --> J([結束])
    I --> J
```

## 2. 抓新聞與挑選 5 則

```mermaid
flowchart TD
    S([開始]) --> L[讀取 config.yaml 的 feeds 清單]
    L --> F1[BBC World]
    L --> F2[The Guardian World]
    L --> F3[NPR News]
    L --> F4[Reuters via Google News]
    F1 & F2 & F3 & F4 --> P{單一來源<br/>抓取失敗?}
    P -- 是 --> SK[印出警告並跳過<br/>不中斷流程]
    P -- 否 --> T[只保留過去 24 小時內的文章<br/>去 HTML、清理標題]
    SK --> M
    T --> M[合併所有文章]
    M --> U{不同主題數 &lt; 5?}
    U -- 是 --> FB[加入 Google News 備援 RSS]
    U -- 否 --> D1
    FB --> D1[依連結去重]
    D1 --> CL[依標題相似度聚類成「主題」]
    CL --> RK[排序主題]
    RK --> PK[每個主題取摘要最長的一篇<br/>取前 5 個主題]
    PK --> Z{一則都沒有?}
    Z -- 是 --> ERR([報錯結束])
    Z -- 否 --> OK([得到 5 則新聞])
```

### 如何判斷「重要」與「避免重複」

| 步驟 | 作法 |
| --- | --- |
| 相似標題 | 標題轉小寫、去掉停用字後取關鍵詞集合；兩篇的重疊比例 ≥ 0.5 視為同一主題 |
| 重要程度 | 報導該主題的**不同媒體數**越多越重要 |
| 同分排序 | 取該主題在各來源 RSS 中的**最前面名次**（媒體通常把重要新聞排前面） |
| 代表文章 | 同一主題中挑摘要最長的，讓 Gemini 有較多內容可用 |

## 3. 呼叫 Gemini（一次處理 5 則）

```mermaid
flowchart TD
    A[5 則新聞的 標題 + 摘要] --> B[組成單一 prompt<br/>含學習者程度與輸出規則]
    B --> C[取得候選模型清單<br/>config 主模型 + fallback_models<br/>+ API 查到的 flash 模型]
    C --> D[用第一個模型呼叫 generate_content<br/>要求 JSON，並附上結構 schema]
    D --> R{結果?}
    R -- 成功 --> V[解析成 DailyResult]
    R -- 429 / 503 --> W{已重試 3 次?}
    W -- 否 --> WT[等待 60 秒] --> D
    W -- 是 --> N
    R -- 其他錯誤<br/>404 / 504 / JSON 無法解析 --> N{還有下一個模型?}
    N -- 是 --> D2[換下一個模型] --> D
    N -- 否 --> X([失敗：workflow 標示紅燈])
    V --> OUT([回傳結構化資料])
```

要點：

- **一次請求**處理 5 則，節省免費額度。
- 每次呼叫有 120 秒逾時，避免卡死。
- Gemini 必須回傳固定 JSON 結構，Markdown 由程式自己產生，格式才穩定。

### Gemini 回傳的資料結構

```mermaid
classDiagram
    class DailyResult {
        items: NewsItem[]
    }
    class NewsItem {
        index
        title_en / title_zh
        summary_zh
        why_important_zh
        vocab: Vocab[]
    }
    class Vocab {
        word
        pos
        kk
        meaning_zh
        sentence_en / sentence_zh
        synonyms 1-2 個
        collocations 1-2 個
        toeic_common
    }
    DailyResult "1" --> "5" NewsItem
    NewsItem "1" --> "3-5" Vocab
```

## 4. 輸出與發佈

```mermaid
flowchart LR
    R[DailyResult] --> M[news/YYYY-MM-DD.md<br/>日報]
    R --> A[anki/YYYY-MM-DD.csv<br/>單字;中文意思;例句]
    R --> RD[README.md<br/>最新一期 + 歷史清單]
    M & A & RD --> G[git add / commit / push]
    G --> REPO[(GitHub repo)]
```

- 檔名日期使用台灣時間（`timezone_offset: 8`）。
- Anki CSV 會依單字去重；匯入 Anki 時分隔符號選「分號」。
- 同一天重跑會覆蓋當天檔案，不會產生重複。

## 5. 錯誤處理一覽

| 狀況 | 處理 |
| --- | --- |
| 某個 RSS 失敗或無內容 | 跳過該來源，其他照常 |
| 新聞不足 5 則 | 改用 Google News RSS 補足 |
| 所有來源都沒新聞 | 報錯，workflow 失敗 |
| Gemini 429 / 503 | 等 60 秒重試，最多 3 次 |
| 主模型仍失敗、模型下架或 JSON 無法解析 | 自動換下一個候選模型 |
| 全部模型都失敗 | 不寫入檔案，workflow 失敗，可在 Actions 頁面看日誌 |
| 沒有檔案變動 | 不 commit |

## 6. 常用調整

| 想做的事 | 修改位置 |
| --- | --- |
| 新增 / 移除新聞來源 | `config.yaml` → `feeds` |
| 改新聞數量、時間範圍 | `config.yaml` → `news_count`、`lookback_hours` |
| 換 Gemini 模型 | `config.yaml` → `gemini.model` / `fallback_models` |
| 改執行時間 | `.github/workflows/daily-news.yml` → `cron`（UTC，台灣時間減 8 小時） |
| 暫停排程 | GitHub → Actions → Daily News → ⋯ → Disable workflow |
