# 每日情報整理管線(Daily Intel Pipeline) 設計文件 (spec)

- 日期: 2026-07-10
- 狀態: 已定案，待實作
- 專案: stockview1 (adr-trend-web)，Cloudflare Pages
- 範圍: Phase 1(引擎 MVP + stockview 分頁) + Phase 2(擴來源 + 推播)

## 1. 目的

使用者每天需要整理網路上的各種資料 —— 新聞、傳聞/小道消息、公司重大消息、行業內容、
投行與投信報告 —— 用途是三合一：**不漏重要動態**、**長期知識/追蹤**、**產出內容素材**。

現況：來源分散(新聞靠自己看、公司消息靠自己查、X 靠 x-summary skill、報告靠 kb-retriever)，
沒有一個每天固定產出的「情報彙整」。本專案要補上這一塊：一條自動管線，把全市場廣掃的雜訊
去噪、打分、分類，產出當天一頁看得完的情報，同時把資料沉澱下來供長期查閱。

## 2. 已定案決策

- **範圍**：全市場廣掃(不只追蹤清單)，靠引擎排序挑重點；「今日大事」用強模型嚴選少量、
  避免每天資訊過載。
- **引擎方案**：LLM 主導(方案 A)。預篩去重靠純程式(省成本)，批次標記用 Claude Haiku，
  當日精選/摘要用 Claude Sonnet。不做規則字典/向量去重的重投入(YAGNI，先驗證流程有沒有用)。
- **產出位置**：併入 stockview，新增「每日情報」主分頁，不做獨立網站/獨立 Skill 產出頁。
- **來源(Phase 1 先接)**：
  - 財經/產業新聞：重用 `_worker.js` 已接的鉅亨/Yahoo/CNBC RSS(擴充 feed 清單)
  - 台股公司重大消息：公開資訊觀測站「重大訊息」公告
  - 全市場池對照：重用既有 us5000/tw_all(供引擎判斷「這代號是誰、哪產業」)
- **來源(Phase 2 擴充)**：
  - X/社群傳聞：重用 `x-summary` skill 的抓取產出餵給引擎
  - 網路搜尋：鉅亨等站關鍵字搜尋，補 RSS 沒涵蓋的
  - 美股公司公告：SEC EDGAR 8-K/PR 摘要
- **重大事件推播(Phase 2)**：重用既有 Web Push 基礎設施(`PUSH_SUBS` KV + VAPID +
  digest 機制)，收盤後對高分事件發**一則彙整推播**，不逐則轟炸。
- **人工補件通道**：本次**不**做新 Skill/新 API 端點。小道消息/傳聞、投行 PDF 重點，
  使用者已有 kb-retriever + 既有 `/api/news/ingest` 可手動丟入；是否要專屬 Skill 留待
  Phase 1+2 上線、觀察實際使用痛點後再議(YAGNI)。
- **可信度標註**：傳聞/未證實類別的項目一律標 `credibility:"rumor"`，附原始來源連結，
  不與已證實消息混排；呼應使用者既有的「數字/ticker 先驗證再呈現」原則 —— 抽取結果
  是初篩,不是事實,UI 上要看得出來源以便人工核對。
- **成本控制**：每日進 LLM 的則數設上限(預設 300 則)，超過依預篩分數排序取前 300、
  其餘捨棄並在 log 記錄捨棄數量(不靜默截斷)。

## 3. 不做 (YAGNI)

- 不做規則/字典式去重打分(方案 B)、不做向量資料庫；先用 LLM 直接判斷，量大再優化。
- 不做「可寫題材一鍵匯出 Obsidian」自動化 —— 這屬於 Phase 3(長期沉澱)，本次先把
  `writeable` 分類產出到位，匯出動作先手動複製。
- 不做逐則即時推播 —— 只做收盤後一次彙整摘要推播。
- 不做新的操作台 Skill —— 沿用既有 kb-retriever / ingest 端點，觀察後再議。
- 不做多語言/多地區來源 —— 先台股+美股，中英文新聞皆可(LLM 直接處理，不用先翻譯)。
- 不做歷史回溯抓取 —— 上線後才開始累積，不補抓過去資料。

## 4. 架構與資料流

```
擷取層 fetch_intel.py              引擎 intel_engine.py                產出 export_intel.py
──────────────────           ──────────────────────────         ─────────────────────
新聞 RSS(鉅亨/Yahoo/CNBC)                                          data/intel.json
台股重大訊息(公開資訊觀測站)   1. 正規化 + 預篩去重(標題近似   →   → stockview「每日情報」分頁
X摘要(x-summary 產出,Phase2)     /URL,純程式,不進 LLM)              → 高分事件 → web push 摘要
網路搜尋(Phase2)             2. 批次標記(Claude Haiku):            (重用既有 digest 機制)
美股 8-K/PR(Phase2)             抽 tickers[]/industry/
                                 一句摘要/重要性分數(0-100)/
                                 分類(大事/公司/產業/傳聞)
                              3. 聚類:同一事件多來源併一則
                              4. 當日精選(Claude Sonnet,少量):
                                 today_top_events + writeable
                                 (含 why,2-3句)
```

跑在既有 `export-and-deploy.yml` cron 新增一組 job，**一天 1 跑**(收盤後，比照 PI/FSI/TIPS
的 `|| echo 失敗,沿用線上` 容錯模式)。`ANTHROPIC_API_KEY` 需新增為 GitHub secret。

## 5. 資料結構 `data/intel.json`

```jsonc
{
  "as_of": "2026-07-10T13:30:00+08:00",
  "generated_at": "...",
  "source_counts": {"news": 812, "disclosure": 45, "x": 0, "search": 0},  // Phase2欄位先留null
  "llm_processed": 300, "llm_dropped": 340,   // 成本上限追蹤,對應「不靜默截斷」
  "top_events": [        // 今日大事(Sonnet 嚴選,含 why,建議 <=15 則)
    {
      "id": "...", "title": "...", "summary": "...", "why": "...",
      "score": 92, "category": "major",           // major/company/industry/rumor
      "credibility": "confirmed",                  // confirmed/rumor
      "tickers": ["2327"], "industry": "被動元件",
      "sources": [{"src": "鉅亨網", "url": "...", "time": "..."}]
    }
  ],
  "by_industry": { "半導體": [ /* item 同上結構 */ ], "被動元件": [ ... ] },
  "company":  [ /* item,含 tickers,可點進 stockview 個股詳情 */ ],
  "rumor":    [ /* item,credibility 一律 "rumor" */ ],
  "writeable":[ /* item + "angle"(建議切入角度) */ ]
}
```

抓取/LLM 全失敗 → 不覆寫(沿用線上 last-good)，與 fsi/pi/tips/yieldcurve 一致的容錯模式。

## 6. 前端「每日情報」分頁

新增主分頁(比照現有 macro/趨勢動能榜 的分頁列)：

- 頂部：**今日大事**卡片流 —— 標題 + 一句摘要 + why + 重要性色條(依 score) +
  來源連結 + 關聯 `[代號]` 可點進 stockview 個股詳情頁
- 中段：**分產業**摺疊區塊(點產業展開當日該產業消息，比照既有台股主題摺疊 UI)
- 下段：**公司公告** / **傳聞**(標「未證實」樣式，如淡色/虛線框) / **可寫題材**
- 右上：日期切換(看前 N 天的 `intel.json` 快照，需 export 端保留歷史 —— 見 §8)、
  分類篩選 chip
- 風格：沿用現有分頁的精簡卡片+摺疊模式，繁體中文，不新增設計系統

## 7. 重大事件推播(Phase 2)

- 收盤後 workflow 內，篩 `top_events` 中 `score >= 80`(預設門檻，可調)
- 彙整成**一則**摘要推播(標題:"今日重大情報 N 則" + 前 3 則標題)，重用
  `push_golden_cross.py` 已驗證的 pywebpush 發送邏輯與 `PUSH_SUBS` KV 訂閱清單
- 沿用 `handleNewsIngest`/digest 的模式：推播內文連結指到分頁內對應區塊(用 hash 錨點)

## 8. 歷史保留與長期知識

- `data/intel.json` 只存**當日**快照(比照 macro.json 模式)；額外每日 append 一筆精簡
  索引到 `data/intel_history.json`(僅 `as_of` + `top_events` 的 title/score/tickers，
  裁切保留最近 90 天，避免檔案無限成長)供分頁「日期切換」與未來個股時間軸串接。
- 個股詳情頁(現有 stockfull)未來可關聯此索引顯示「近期情報」，本次先不做串接，只確保
  `tickers[]` 欄位到位、資料可被後續串接，不做多餘設計。

## 9. 測試與防呆(沿用既有已驗證模式)

- `engine/fetch_intel.py`：抓取函式，網路失敗回 None，不拋例外(比照 `fetch_pi.py`)
- `engine/intel_engine.py`：**純函式**(去重比對、分數解析、聚類、上限截斷邏輯)，
  可用合成資料在 CI 跑單元測試，不需真實 LLM/網路
- `engine/export_intel.py`：組裝 + 容錯落盤，比照 `export_tips.py`/`export_yieldcurve.py`
- `engine/test_intel_engine.py`：pytest，涵蓋去重/分數/聚類/上限/傳聞標記，跑進既有
  CI(`test.yml` 的 python job)
- `web/test_intel_dom.mjs`：render 邏輯測試(比照 `test_tips_dom.mjs`)
- 若前端有 ECharts 圖表(如「近期情報密度」小圖，非必要 MVP)，需經
  `test_echarts_smoke.mjs` 真渲染驗證(避開 piecewise visualMap 崩潰雷)
- `intel` 加入 `pull_live_data.py` TOP 清單(`test_data_pull_sync.mjs` 會強制擋，
  沒加會直接讓 CI 紅——這正是本次要延續的三類防呆之一)
- 部署後驗證步驟(`export-and-deploy.yml` 的 curl 檢查清單)加入 `intel`
- **人工抽查**：Phase 1 上線後前幾天，使用者需抽查 `top_events`/`tickers` 抽取準確度
  (呼應 `verify-counts-and-data-before-presenting` 記憶)；此為流程要求，非自動化項目

## 10. 成本與風險

**Token/成本估算**(一天 1 跑、預篩去重後進 LLM 上限 300 則；Claude Haiku 4.5 $1/$5 每
MTok、Claude Sonnet 5 $3/$15 每 MTok，2026-08-31 前 intro 價 $2/$10)：

| 階段 | 用途 | 每日估算 |
|---|---|---|
| Haiku 批次標記 | 300 則 ÷ 15/批 = 20 批，抽 ticker/產業/摘要/分數/分類 | input ~83K、output ~30K tokens |
| Sonnet 當日精選 | 從高分池(~80則)選 top_events(≤15) + writeable(~10)，寫 why | input ~10K、output ~3.75K tokens |

月成本(30 天)：Haiku 約 $7、Sonnet 約 $2.6(intro 價約 $1.7)，**合計約 $9–10/月**
(intro 期間約 $8–9/月)。此為 Phase 1+2 上線初期(300 則/天上限、未含 Phase 2 新增
X/搜尋來源前)的粗估基準；Phase 2 來源擴充後原始量會增加，但進 LLM 仍受同一上限控制，
估算量級大致不變。正式用量以實際帳單為準，此處僅供抓量級與抓上限是否合理的參考。

- 風險：新聞來源可能重複率高(同事件多家報導) → 依賴 §4 步驟 3 聚類，若聚類效果不佳
  需追加調整(留待實作後依實際資料調參，不在此 spec 預先過度設計)
- 風險：LLM 抽取 ticker 錯誤 → §9 人工抽查 + UI 標示來源連結供核對，缺乏自動化事實查核
  (不做，超出本次範圍)
