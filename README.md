# ADR Trend Screener · 趨勢效率動能榜（雲端網頁版）

把 Claude Code 的 `/adr-screener trend` skill 做成一個**公開、可上網**的網頁。

效率N = N日漲幅% ÷ (ADRN% × N)，衡量「真的在漲、漲得乾不乾淨」——補足 ADR 只看振幅不看方向的盲點。

## 五段輸出（與原 skill 一致）

1. **趨勢效率主表** — 效率3/5/10/20 + 5日漲% + 5日評分 + ADR + avg$Vol + Score + 單向性，依 Score 排序
2. **交叉過濾** — 全池 5日評分≥80 依 Score 排序，標 Top內/補進
3. **近期轉強排行 A** — 效率5 − 效率20（剛轉強）
4. **近期轉強排行 B** — 加權加速度（剛發動）
5. **兩表差異判讀** — 共同/僅A/僅B
6. **最早期點火榜** — 效率3，附 3vs5 / 3vs10 雙旗標

支援 5 個股票池：**tw150 / ndx100 / sp500 / sp400 / sp600**，網頁上分頁切換。

## 交叉訊號分頁

獨立主分頁，整理**全池每一檔**的 MA10×MA50 金叉/死叉狀態（同個股回測口徑），分三區塊：

- **🔥 最近剛觸發（≤3 天）** — `cross_days ≤ 3` 的新交叉，越新越上。
- **全部金叉 / 全部死叉** — 全池目前狀態清單（預設收起可展開），依「越新觸發越前、同天數 Score 大→前」排序。

欄位：代號·名稱／狀態／幾天前／5日漲%／5日評分／Score；代號可點進個股看完整波段回測。資料源自引擎 `compute_trend` 既有的全池交叉計算，匯出於每池 JSON 的 `cross_signals` 區塊（`engine/export_json.py` 的 `build_cross_signals`）。

## 架構

| 層 | 技術 | 角色 |
|---|---|---|
| 計算引擎 | Python + yfinance（`engine/adr_screen.py`，原 skill 引擎原封不動）| 抓日線、算效率/ADR/評分 |
| JSON 匯出 | `engine/export_json.py` | 重用引擎，把五段結果序列化成 JSON |
| 雲端執行 | GitHub Actions（`.github/workflows/`）| 定時/手動/按鈕觸發，跑引擎→部署 |
| 前端 | 純 HTML/CSS/JS（`web/index.html`，無建置步驟）| 讀 JSON 渲染五段表格 |
| 託管 | Cloudflare Pages | 公開靜態網頁 |

訪客看每日快照（不觸發抓取、不被 Yahoo 限流），需要最新時按「🔄 更新資料」觸發雲端重抓。

## 快速開始

見 **[DEPLOY.md](DEPLOY.md)** — 約 15 分鐘完成 GitHub + Cloudflare 設定。

本地預覽：
```bash
cd engine && PYTHONUTF8=1 python export_json.py ndx100 40
cd ../web && cp ../data/*.json data/ && python -m http.server 8899
# http://127.0.0.1:8899
```

## 口徑

- 效率：>0.4 單向強漲(趨勢盤)、0.15–0.4 震盪偏多、<0.15 高震盪沒淨幅、<0 回檔。
- Score = ADR20% × avg$Vol/1e6，**跨幣別不可比**。
- 來源 yfinance 日線快照，非全市場掃描，僅池內排序。
