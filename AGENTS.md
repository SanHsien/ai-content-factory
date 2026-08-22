# AGENTS.md

給 Codex、Claude Code、Cursor 與其他自動化代理在本專案工作時的指引。產品與使用方式先讀 [`README.md`](README.md)；開發與驗收細節見 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)。上游英文原文在 [`AGENTS.en.md`](AGENTS.en.md)。

## 專案定位

這是上游公開專案 `ai-content-factory` 的 Apache-2.0 fork。GitHub 頁面的 Forked from 即為原作者 repo。
核心價值是把「找資料 → 寫文章 → 短影音腳本 → 分鏡 → 媒體計畫 → 檢查 → 平台文案」拆成可審查的離線產線，而不是一次亂生全部。

`origin` 是 `SanHsien/ai-content-factory`，`upstream` 是原作者 repo，預設分支皆為 `main`。
保留上游作者、Apache-2.0、`NOTICE`、公開發行 allowlist 與離線 demo。本 fork 的維護差異記在 [`FORK.md`](FORK.md) 與 [`docs/DECISIONS.md`](docs/DECISIONS.md)。

主要開發與完整驗收環境是 **Windows 11 + PowerShell**；上游 CI 的 Ubuntu job 補跨平台相容性。

## 硬性邊界

- 預設執行環境維持 **Python 3.11+、標準庫、離線**。不要為了本機開發 gate 讓 demo 依賴 `pip install`。
- 不執行即時 API、遠端發布、瀏覽器自動化、憑證設定、付款、部署或發行，除非有另外一份明確授權。
- v0.1.0 已公開；之後的發行與公開發布動作仍需另外授權。
- 不提交真實密鑰、私人路徑、私人素材、個人資料、帳號識別碼或私人品牌名稱。
- 不推送到 `upstream`。上游同步先跑 `python tools/check_upstream_updates.py`，逐筆審查後再 merge / cherry-pick；不盲目覆蓋 fork 文件與 Windows gate。
- 不要覆寫產品契約：`scripts/public_ci.py`、`public_release_manifest.json`、fixture registry、`REMOTE_WRITE=0`。
- 不要把靜態圖轉換說成合成主體動作；那叫 `MOTION_RENDER`。
- 權利不明的匯入媒體不得物化進審查套件。
- 模型權重、快取、瀏覽器狀態與私人媒體永遠不進 source release candidate。
- 保留無關的 worktree 變更。不要 reset、clean、stash 或覆寫其他貢獻者的工作。

## 技術與資料流

- Python 3.11+；預設 runtime 零第三方依賴。
- `src/ai_content_factory/`：核心契約、編排、媒體 QA、providers、publishers、CLI。
- `fixtures/synthetic/`：公開安全的確定性 demo 輸入。
- `scripts/`：離線 bootstrap、公開 CI、安全掃描、RC 建置。
- `tools/`：fork 維護工具（Windows gate、上游檢查、相對連結檢查）。
- `tests/`：`unittest`，零依賴。
- fixture registry 是預設。選配 adapter 必須被明確選取，不得變成隱藏後備。
- 品牌素材與正式設定屬於外部私有層，不得複製進本 repo。

## 開發原則

- 一般修改使用短期分支：**branch → PR → CI → squash merge**。`main` 是唯一長期分支，不直接拿它當日常工作區。
- 修 bug 先補可重現失敗測試，再做最小修正。
- 上游公開 CLI、README quickstart 指令與 `docs/quickstart.md` 的可攜命令視為相容性契約。
- 不為了套格式而大改上游程式；不要引入必須的 pytest / ruff 才能跑公開檢查。
- 使用繁體中文回覆；使用者文件以繁中為主，公開入口同步維護 `README.en.md`。
- 上游更新英文 `README.md` 時：把新內容併進 `README.en.md`，再翻進繁中 `README.md`。
- 掃描輸出保持編修；私人品牌 denylist 只存 SHA-256 fingerprint。
- 非瑣碎的來源、依賴與設計決策記在 `PROVENANCE_LEDGER.md`。
- 本機掃描或 fixture 測試只證明該邊界，不是即時 provider、權利、品質或公開發行核准的證據。
- 公開候選只准用 `public_release_manifest.json` 與 `scripts/build_release_candidate.py` 組裝；不要複製整個 worktree。
- `REVIEW.md` 是風險快照，不是每個一般 bug 的流水帳。

## 上游處理

1. `git fetch upstream main`
2. `python tools/check_upstream_updates.py --strict`
3. 逐筆判斷是否與繁中 README、Windows gate 或測試衝突。
4. 可同步的提交用 merge；只需要部分修正時 cherry-pick 或最小重做。
5. 跑 `pwsh -NoProfile -File tools\dev_check.ps1`
6. 採用／略過寫進 `docs/DECISIONS.md`，驗證後才推進 `tools/upstream_baseline.json`

Baseline 代表「已審查」，不代表「全部已合併」。

## 依賴新鮮度

每月的 `Dependency freshness` workflow 跑 `tools/check_dependency_freshness.py`，
只比對 `pyproject.toml` 的宣告與 PyPI 現行版，不看已安裝環境、不改檔。
比對深度跟著宣告走：`>=6` 只比主版，`>=1.26` 比到次版。

紅燈只有兩種正當出口，兩種都要留下理由：

- **維持宣告**：在宣告那一行加 `# freshness-hold: <理由>`。用於「這個下限就是我們要的」
  的長期政策（例：建置後端只需要 PEP 621 支援）。
- **已延後**：在 `.github/dependency-deferrals.json` 加一筆
  `{"deferredLatest": "<當時看到的版本>", "reason": "<為什麼這次不升>"}`。
  PyPI 一超過該版本，延後自動失效、報告恢復提醒——所以不會變成永久靜音。

不要用調高下限的方式讓紅燈消失：宣告是相容性承諾，不是消音鍵。

## 驗證

```powershell
pwsh -NoProfile -File tools\bootstrap_dev.ps1
```

等價拆開：

```powershell
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/public_ci.py
python -B scripts/security_scan.py --root . --brand-hash-file scripts/public_brand_hashes.sha256
python -B -m ai_content_factory demo --output output
python -B -m ai_content_factory inspect --output output
python -B -m ai_content_factory validate --output output
python tools/check_links.py
```

沒有實際跑過 `public_ci.py` 與 Windows gate，不要宣稱本機開發環境已可用。

## 文件責任

- `README.md` / `README.en.md`：公開產品與 fork 入口。
- `FORK.md`：與上游的關係、差異、同步方式。
- `NOTICE`：上游 Apache 聲明；`NOTICE.md`：本 fork 的 attribution。
- `docs/UPSTREAM.md`：upstream remote 與審查清冊。
- `docs/DEVELOPMENT.md`：本機開發與驗收指令。
- `docs/DECISIONS.md`：長期取捨。
- `CHANGELOG.md`：產品變更；fork 骨架可加 Unreleased 段，不要改寫上游歷史。
- `CONTRIBUTING.md` / `SECURITY.md`：本 fork 的貢獻與安全回報流程。
