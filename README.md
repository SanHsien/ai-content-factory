<p align="center">
  <a href="README.md"><strong>繁體中文</strong></a> ·
  <a href="README.en.md">English</a>
</p>

# AI Content Factory

把一個主題變成可審查的內容包：文章、短影音腳本、分鏡、媒體計畫、品質報告，以及可發布的各平台文案。預設 demo **完全離線**：不需要 API key、帳號、GPU、私人素材或付費服務。

> 目前發行：v0.1.0。離線核心已公開可用；即時供應商與遠端發布仍是選配，或刻意不包含。

> **這是上游公開專案 `ai-content-factory` 的 Windows-first 維護型 fork**，沿用 Apache-2.0 與完整 Git 歷史。GitHub 頁面的 Forked from 即為原作者 repo。產品契約、離線 demo 與 provider 邊界跟隨上游；本維護線補上繁中入口、Windows 開發／驗收 gate，以及逐筆審查的上游追蹤。差異見 [`FORK.md`](FORK.md)，同步策略見 [`docs/UPSTREAM.md`](docs/UPSTREAM.md)。

## 這個 fork 額外提供什麼？

- **Windows-first 開發與驗收**：`tools/bootstrap_dev.ps1`、`tools/dev_check.ps1`，與上游 `scripts/public_ci.py` 同一套零依賴檢查。
- **繁中公開入口**：`README.md` 為繁中主檔，英文鏡像在 `README.en.md`。
- **AI 維護單一真相源**：[`AGENTS.md`](AGENTS.md)；`CLAUDE.md` 只補 Claude Code 入口。
- **上游追蹤**：每週檢查 `upstream/main` 未審查 commit，不盲目覆蓋 fork 修正。
- **CodeQL 與 Dependabot**：安全掃描與 GitHub Actions 依賴更新開 PR，不自動合併。

## 你會得到什麼

一條指令會在 `output/<run_id>/` 產出：

- fixture 研究資料、一篇文章、短影音腳本與分鏡；
- 供應商中立的圖片、影片、語音描述；
- 媒體 QA、綁定完整性的核准，以及防重複的套件清單；
- 七個常見社群平台的本機文案；以及
- `demo_preview.html`，可直接打開的單檔視覺摘要。

demo 證明的是編排與打包，不是事實研究或生成媒體品質。發布前請用經過審查的 provider 取代 fixture。

## 快速開始（Windows）

需求：Windows 10/11 與 Python 3.11 或更新。在本目錄執行：

```powershell
py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer required'; print(sys.version)"
py -3 -m venv .venv
.venv\Scripts\python -B scripts\bootstrap_offline.py
$result = .venv\Scripts\ai-content-factory demo --output output | ConvertFrom-Json
Invoke-Item $result.visible_artifact
```

No `pip install` or network access is needed for the base demo. 要用與公開發行相同的零依賴檢查驗證 checkout：

```powershell
.venv\Scripts\python -B scripts\public_ci.py
```

本 fork 的一鍵開發 gate（含連結檢查與 compile）：

```powershell
pwsh -NoProfile -File tools\bootstrap_dev.ps1
```

詳細指令、CMD／Linux、預期輸出、檢查與清除見 [完整 quickstart](docs/quickstart.md) 與 [開發環境](docs/DEVELOPMENT.md)。

## 需要付費 API 或 GPU 嗎？

| 能力 | 付費 API | GPU | 狀態 |
| --- | --- | --- | --- |
| 離線 demo 與 HTML 預覽 | 否 | 否 | 已包含並測試 |
| 本機平台套件 | 否 | 否 | 已包含；遠端寫入永遠為零 |
| 使用者提供的圖片轉動態 | 否 | 不需要專用 GPU | 選配；需要 HyperFrames 與 FFmpeg |
| 真實圖片生成 | 依供應商 | 依供應商 | 選配 adapter 邊界 |
| 本機生成影片 | 不需要託管 API | 通常需要 | 選配進階 provider 邊界；不含權重 |
| 遠端社群發布 | 依供應商 | 否 | v0.1 未包含 |

歷史圖片 API extra 不會被 demo 匯入，也絕不是自動後備。產品原生工具同樣是選配交接 adapter，不是公開核心的必要條件。

## 架構一覽

```text
Topic
  -> ResearchProvider
  -> TextProvider
  -> storyboard and editorial contracts
  -> ImageProvider / VideoProvider / VoiceProvider
  -> media QA
  -> integrity-bound approval
  -> local DryRunPublisher / ManualPublisher
  -> visual preview and platform-ready package
```

核心編排只認契約，不認廠商 SDK。私人品牌從 repo 外提供設定與素材。選配 adapter 可以增加網路、模型或工具需求，但預設登錄檔仍是 fixture-only、離線。新增 adapter 前請讀 [ARCHITECTURE.md](ARCHITECTURE.md) 與 [provider 文件](docs/providers.md)。

## 常用指令

```powershell
# 列出所有指令
.venv\Scripts\ai-content-factory --help

# 用確定性 fixture 跑另一個主題
.venv\Scripts\ai-content-factory run `
  --topic "How can a creator plan one useful short video?" `
  --output output-custom

# 檢查或驗證，不改產物
.venv\Scripts\ai-content-factory inspect --output output-custom
.venv\Scripts\ai-content-factory validate --output output-custom

# 只跑公開測試
.venv\Scripts\python -B -m unittest discover -s tests -p "test_*.py"

# 用公開 denylist fingerprint 跑編修後掃描
.venv\Scripts\python -B scripts\security_scan.py `
  --root . `
  --brand-hash-file scripts\public_brand_hashes.sha256
```

`run` 可用 `--brand` 接受 repo 外的通用 JSON 品牌設定。它本身不會啟用即時 provider 或 publisher。

## 安全模型

- 離線發布階段強制 `REMOTE_WRITE=0`。
- 已核准產物被改動後，核准失效。
- 重跑相同套件會重用邏輯身分，不會產生第二次發布意圖。
- 具網路能力的 adapter 需要明確指令與同意旗標。
- 密鑰、瀏覽器設定檔、模型權重、快取、私人路徑與私人媒體被發行清單與編修掃描排除。
- fixture 聲明有明確標記，需要人工審查。

本專案在 v0.1 **不**儲存憑證、不自動登入、不發布到社群帳號。

## 專案結構

```text
src/ai_content_factory/   核心、產線、媒體、providers、publishers、CLI
fixtures/synthetic/       確定性、公開安全的 demo 輸入
examples/demo-brand/      通用外部品牌設定範例
tests/                    零依賴公開測試套件
scripts/                  離線 bootstrap、掃描、CI、RC 建置
tools/                    本 fork 的 Windows gate 與上游檢查
docs/                     架構、providers、安全、疑難排解、fork 維護
```

## 擴充

1. 實作 `providers/contracts.py` 或 `publishers/base.py` 的其中一個 protocol。
2. 把廠商 import 留在 adapter 內。
3. 宣告網路、密鑰、成本、權利與授權行為。
4. 加上淨化過的 fixture 與失敗路徑測試。
5. 明確登錄 adapter；不要做成隱藏後備。

從 [providers](docs/providers.md)、[編輯引擎](docs/editorial-engine.md) 與 [公開／私有分離](docs/public-private-separation.md) 開始。

## 文件

- [Quickstart](docs/quickstart.md)
- [開發環境](docs/DEVELOPMENT.md)
- [Architecture](ARCHITECTURE.md)
- [Pipeline](docs/pipeline.md)
- [Provider 模型](docs/providers.md)
- [圖片 providers](docs/image-providers.md)
- [影片 providers](docs/video-providers.md)
- [語音 providers](docs/voice-providers.md)
- [編輯引擎](docs/editorial-engine.md)
- [隱私與安全](docs/privacy.md)
- [疑難排解](docs/troubleshooting.md)
- [Fork 維護](FORK.md)
- [貢獻指南](CONTRIBUTING.md)
- [安全政策](SECURITY.md)
- [AI／agent 指引](AGENTS.md)

## 授權

核心原始碼採 Apache-2.0。外部工具、provider SDK、模型權重、字型與使用者素材保留各自授權。本 repo 不重新授權、也不打包它們；見 [NOTICE](NOTICE)、[fork 聲明](NOTICE.md)、[依賴清冊](docs/dependency-inventory.md) 與 [來源帳本](PROVENANCE_LEDGER.md)。
