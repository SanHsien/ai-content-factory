# 開發環境

維護者與 AI 接手用的開發文件。產品使用方式在 [`README.md`](../README.md)；上游同步在 [`UPSTREAM.md`](UPSTREAM.md)；決策在 [`DECISIONS.md`](DECISIONS.md)。上游英文 quickstart 仍是產品契約：[`quickstart.md`](quickstart.md)。

## 架構

```text
主題
        │
        ▼
 ResearchProvider → TextProvider → 文章 / 短腳本
        │
        ▼
 分鏡與編輯契約
        │
        ▼
 Image / Video / Voice descriptors（預設 fixture）
        │
        ▼
 媒體 QA → 完整性核准 → 本機 DryRun / Manual publisher
        │
        ▼
 output/<run_id>/（含 demo_preview.html 與 platform-ready）
```

公開核心是編排與打包。fixture 不是事實研究，也不是生成媒體品質的證據。

## 本機開發（Windows）

```powershell
pwsh -NoProfile -File tools\bootstrap_dev.ps1
```

這會：

1. 確認 Python 3.11+
2. 建立 `.venv`
3. 用 `scripts/bootstrap_offline.py` 離線安裝（不跑 pip）
4. 跑 `tools/dev_check.ps1`

手動拆開：

```powershell
py -3 -c "import sys; assert sys.version_info >= (3, 11); print(sys.version)"
py -3 -m venv .venv
.venv\Scripts\python -B scripts\bootstrap_offline.py
pwsh -NoProfile -File tools\dev_check.ps1
```

跑一次離線 demo：

```powershell
$result = .venv\Scripts\ai-content-factory demo --output output | ConvertFrom-Json
Invoke-Item $result.visible_artifact
```

## Canonical gate

`tools\dev_check.ps1` 會依序：

1. `python -m compileall`（`src`、`tests`、`scripts`、`tools`）
2. `python tools/check_links.py`
3. `python -B scripts/public_ci.py`（unittest、安全掃描、demo、validate）

上游 GitHub Actions `public-fast-ci` 已在 Windows 與 Ubuntu、Python 3.11／3.12 跑 `public_ci.py`。本 fork 的 Windows canonical gate 跑 Python 3.14。

## 提交

直接推 `origin/main`，不開功能分支。提交前跑 `tools\dev_check.ps1`。

## 掃描涵蓋範圍

`security_scan.py` 的 finding 與「未掃描」分開回報：後者只表示覆蓋未完成，不表示已發現密鑰，也不表示安全。

- VCS metadata（含 worktree 的 `.git` 檔）不屬於掃描內容。
- `private`、`build`、`logs`、`cache`、`dist`、`output`、虛擬環境等略過目錄只回報目錄邊界，不列舉或讀取其私人內容；不能把一個目錄邊界當成一個已知未掃描檔案數量。
- 超過設定大小（預設 5,000,000 bytes）、含 NUL 的二進位／UTF-16 檔、無法讀取的檔案、symlink 與自訂排除會列出原因。單檔最多讀取上限加一 byte，不先整檔讀入。
- 文字輸出有 `[unscanned]`；有略過範圍時，JSON 增加 `unscanned: [{path, reason}]`。沒有略過範圍的既有 JSON 形狀不變。`run_checks()` 仍只回傳 findings；需要覆蓋資料的 Python 呼叫端可傳入 `unscanned=[]` 收集。
- 路徑本身若命中已設定的品牌 fingerprint，輸出改用路徑 SHA-256 遮罩，避免從檔名洩漏品牌；不輸出明文 denylist。
- 預設退出碼仍是 0（沒有 finding）、1（有 finding）、2（參數／掃描錯誤）；0 不保證未掃描區域沒有秘密。`--fail-on-unscanned` 另使未完整掃描回傳 2，有 finding 時優先回傳 1。

例如在指定的公開內容範圍做嚴格檢查：

```powershell
.venv\Scripts\python -B scripts\security_scan.py --root examples --fail-on-unscanned
```

現有 `public_ci.py` 與 workflow 不變：輸出會呈現覆蓋限制，預設不把 fixture PNG、快取等未掃描內容當成秘密 finding。需要全覆蓋的使用方必須明確採用嚴格旗標並選好檢查範圍；這不是公開發行核准。

## Motion render

`render-video` 把已有靜態圖做成鏡頭運動（`MOTION_RENDER`）。那不是合成主體動作，也不檢查 `usage_rights`。未給 `--provenance` 時，有 `--brand-config` 標 `PRIVATE_OWNED`，否則 `CHATGPT_HANDOFF`。必須加 `--no-network`。產線寫 `os_network_isolation: NOT_CLAIMED`：這是應用層離線，不是 OS 隔離。

## 不要做的事

- 不要讓公開 demo 依賴 `pip install`、API key 或 GPU。
- 不要提交 `output/`、根目錄 `config/`、根目錄 `brand.json`、憑證或使用者媒體。公開 demo 品牌在 `examples/demo-brand/`。
- 不要把 fixture 結果說成即時研究或已核准發布。
- 不要從本 fork 跑 `scripts/build_release_candidate.py` 當上游 v0.1.0 產品包。
- 不要為了讓 RC 通過而把私人路徑加進 ignore。
- 測試輸入必須是合成樣本，不能拿真實客戶文案或品牌。
