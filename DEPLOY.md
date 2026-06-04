# 部署說明 · ADR Trend Screener 雲端網頁

把 `/adr-screener trend` 做成公開網頁。架構：

```
GitHub Actions（雲端跑 Python 引擎）──產生 5 池 JSON──▶ Cloudflare Pages（公開靜態網頁）
        ▲                                                          │
        └──────── 網頁「🔄 更新資料」按鈕 透過 GitHub API 觸發 ◀────┘
```

- **訪客**看的是每日定時更新的快照 → 不觸發抓取、**不會被 Yahoo 限流**。
- **你**想要最新時按「更新資料」→ 觸發 GitHub Actions 雲端重抓 → 約 3–8 分鐘後自動部署。
- 你的電腦**完全不用開機**，全部在雲端、全免費額度內。

---

## 一次性設定（約 15 分鐘）

### 步驟 1 — 建 GitHub repo 並上傳

```bash
cd ~/adr-trend-web
git init
git add .
git commit -m "init: ADR trend screener web"
# 在 github.com 建一個新 repo（例 adr-trend-web），然後：
git remote add origin https://github.com/<你的帳號>/adr-trend-web.git
git branch -M main
git push -u origin main
```

> `.gitignore` 已排除 `data/*.json`（資料由 CI 產生）。引擎 `engine/adr_screen.py`、5 個 universe 清單、前端 `web/index.html`、workflow 都會上傳。

### 步驟 2 — 開一個 Cloudflare Pages 專案

1. 登入 [Cloudflare Dashboard](https://dash.cloudflare.com) →左側 **Workers & Pages** → **Create** → **Pages** → **Connect to Git**。
2. 選剛才的 repo。建置設定：
   - **Framework preset**：`None`
   - **Build command**：留空
   - **Build output directory**：`web`
3. 按 **Save and Deploy**。第一次會部署 `web/`（此時還沒有 data，網頁會顯示「載入失敗」提示，正常，步驟 4 跑完就好）。
4. 記下你的 Pages 專案名稱（例 `adr-trend`）與網址（`https://adr-trend.pages.dev`）。

> 之後實際的「產生資料 + 部署」由 GitHub Actions 用 wrangler 直接 push（步驟 3），所以這裡 Git 連動只是用來開專案；也可以選 **Direct Upload** 模式建立空專案。

### 步驟 3 — 設定 GitHub Actions 的 Cloudflare 金鑰

到 GitHub repo → **Settings** → **Secrets and variables** → **Actions**：

**Secrets**（New repository secret）：
| 名稱 | 值 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → Create Token → 用 **"Edit Cloudflare Workers"** 範本，或自訂含 **Account › Cloudflare Pages › Edit** 權限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Dashboard 右側欄、或 Workers & Pages 頁網址裡的 Account ID |

**Variables**（Variables 分頁 → New repository variable）：
| 名稱 | 值 |
|---|---|
| `CF_PAGES_PROJECT` | 你的 Pages 專案名稱（例 `adr-trend`） |

### 步驟 4 — 跑第一次

GitHub repo → **Actions** 分頁 → 左側 **export-and-deploy** → 右上 **Run workflow** → **Run**。

約 3–8 分鐘後完成，打開 `https://<專案>.pages.dev` 就能看到五池資料。✅

之後它會**每個工作日自動更新兩次**（台股收盤後、美股收盤後，見 workflow 的 cron）。

---

## 啟用網頁「🔄 更新資料」按鈕（可選）

預設按鈕只會提示「請到 Actions 手動跑」。要讓它真的一鍵觸發雲端重抓，需要一個能呼叫 GitHub API 的 token。

### ⚠️ 先讀這個安全提醒

這是**公開網頁**。任何寫進 `web/index.html` 的 token 都會被所有訪客看到 = 等於公開那個 token。所以：

- **絕對不要**用你的個人 GitHub token 或任何有寫入權限的 token。
- 只能用**權限最小**的 fine-grained token：**只對這一個 repo、只給 `Contents: Read` 之外的 `Metadata: Read` + 觸發 workflow 所需的最小權限**。最壞情況下別人也只能「幫你多觸發幾次重抓」，無法改你的程式或資料。
- 觸發頻率本身受 GitHub Actions 免費額度保護；真的被濫用就把 token 撤銷即可。

### 設定方式

1. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token。
   - **Resource owner**：你自己
   - **Repository access**：Only select repositories → 選 `adr-trend-web`
   - **Permissions** → Repository permissions → **Contents: Read and write**（`repository_dispatch` 需要）。其餘全部 No access。
   - 產生後複製 token（`github_pat_...`）。
2. 編輯 `web/index.html` 最上方的設定區：
   ```js
   const GH_OWNER = "你的帳號";
   const GH_REPO  = "adr-trend-web";
   const GH_DISPATCH_TOKEN = "github_pat_xxx";   // 最小權限 token
   ```
3. commit + push。下次部署後，按鈕就能一鍵觸發了。

> **不想承擔公開 token 風險？** 就維持預設（留空）。需要最新資料時，自己到 GitHub Actions 按一下 **Run workflow** 即可，效果一樣，零風險。這是推薦做法。

---

## 常見問題

**Q：為什麼不是「打開網頁當下即時抓」？**
Cloudflare 跑不了 Python+yfinance；而且公開站若每位訪客都即時抓 500+ 檔，會被 Yahoo 限流。改用「每日快照 + 手動觸發」根治限流，且 trend 用日線、收盤才定案，每天更新一次即足夠。

**Q：資料多久更新？**
每個工作日自動兩次（cron 可改）；或任何時候手動觸發。標題列「更新」會顯示該池資料的產生時間（UTC 轉本地）。

**Q：想改 TopN 或加減股票池？**
- TopN：改 workflow 裡 `python export_json.py all 50` 的數字。
- 股票池：editor `engine/export_json.py` 的 `POOLS` 清單；池清單檔在 `engine/universe/*.txt`。
- 前端分頁：改 `web/index.html` 的 `const POOLS`。

**Q：本地預覽？**
```bash
cd engine && PYTHONUTF8=1 python export_json.py ndx100 40   # 產生 data/ndx100.json
cd ../web && cp ../data/*.json data/ && python -m http.server 8899
# 開 http://127.0.0.1:8899
```

**Q：中文趨勢字串變亂碼？**
務必帶 `PYTHONUTF8=1`（workflow 已設）。這是 Windows/Python 讀原始碼編碼的已知問題，UTF-8 模式可解。

---

## 口徑與限制（同原 skill）

- 效率N = N日漲幅% / (ADRN% × N)；5日評分 = 漲幅40% + 效率5(35%) + 加速25%。
- Score = ADR20% × avg$Vol/1e6，**跨幣別不可比**（美股 USD / 台股 TWD）。
- 來源 yfinance 日線。**非真·全市場掃描**，只在股票池清單內排序。下市/改名代號列入 [失敗]，不中斷。
- 台股權值股快照（tw150）會過時，需手動更新清單。
