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

## Motion render

`render-video` 把已有靜態圖做成鏡頭運動（`MOTION_RENDER`）。那不是合成主體動作，也不檢查 `usage_rights`。未給 `--provenance` 時，有 `--brand-config` 標 `PRIVATE_OWNED`，否則 `CHATGPT_HANDOFF`。必須加 `--no-network`。產線寫 `os_network_isolation: NOT_CLAIMED`：這是應用層離線，不是 OS 隔離。

## 不要做的事

- 不要讓公開 demo 依賴 `pip install`、API key 或 GPU。
- 不要提交 `output/`、根目錄 `config/`、根目錄 `brand.json`、憑證或使用者媒體。公開 demo 品牌在 `examples/demo-brand/`。
- 不要把 fixture 結果說成即時研究或已核准發布。
- 不要從本 fork 跑 `scripts/build_release_candidate.py` 當上游 v0.1.0 產品包。
- 不要為了讓 RC 通過而把私人路徑加進 ignore。
- 測試輸入必須是合成樣本，不能拿真實客戶文案或品牌。
