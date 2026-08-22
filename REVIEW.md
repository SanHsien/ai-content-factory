# Repository review（Windows-first）

- Review date: 2026-08-22
- Review baseline: `e99ae69b01955cfd48eaa219c3144f9629b3cb76`
- Upstream reviewed through: `d476f740af9c9a0b7f1c2d05c6e658a09ee9abb0`
- Primary environment: Windows 11、PowerShell、Python 3.14.7（本機）、CI Ubuntu/Windows 3.11–3.12（Windows gate 固定 3.12）
- Status: 維護骨架可用；離線產線契約未改寫；公開產品仍是上游 `ai-content-factory` v0.1.0

## 結論

這個 fork 適合作為 Windows 本機、給 Agent 維護的離線內容產線。預設路徑是 fixture、標準庫、不上網：`REMOTE_WRITE` 預設 `"0"`，publisher 只做本機 dry-run／manual，demo 證明編排與打包，不證明研究真實性或生成媒體品質。本機 `tools\dev_check.ps1` 與 GitHub Actions 在 `e99ae69` 全綠。

現階段的主要風險不是「預設會不會外連」，而是：

1. 公開安全掃描認得出 `api_key = "..."`，認不出 `OPENAI_API_KEY=` 賦值或供應商常用的金鑰前綴。
2. `render-video --no-network` 被解析後沒人讀；JSON 一律寫 `"network": "DISABLED"`，同意旗標是空的。
3. 繁中 README／`SECURITY.md` 已寫 fork 行為，英文鏡像與 gitignore 實際內容沒有對齊。

不把 fork 當成第二個官方產品 repo。CLI、fixture registry、`scripts/public_ci.py`、公開發行 allowlist 與 `docs/quickstart.md` 的可攜命令仍屬上游。公開品牌掃描禁止把上游 GitHub 帳號寫進追蹤檔；歸屬以 GitHub 的 Forked from、本機 `upstream` remote、Apache `NOTICE` 為準。

## 本輪實證

### 本機

```text
pwsh -NoProfile -File tools\dev_check.ps1
→ compileall / check_links / public_ci 全綠
→ WINDOWS DEV CHECK GREEN
→ 137 tests OK（1 skipped：POSIX-only venv bootstrap）
→ security scan: clean
→ demo SUCCEEDED，publisher mode=dry-run，remote_write=0，status=DRY_RUN_READY
→ validate complete=true，errors=[]，warnings=[]

python tools/check_upstream_updates.py
→ No new upstream commits.

python tools/check_links.py
→ 20 份維護文件，0 份斷掉的相對連結
```

抽查 `scripts/security_scan.py`（暫存目錄，不進 git）：

| 樣本 | 掃描結果 |
|---|---|
| `.env` 裡的 `OPENAI_API_KEY=` 加供應商金鑰前綴 | 0 finding |
| 純文字檔裡的裸供應商金鑰前綴 | 0 finding |
| Python 的 `api_key = "..."` 賦值 | 命中 `generic-secret-assignment` |

`git check-ignore`：`output/`、`.env`、`private/` 有擋；`config/foo.json` 與工作樹根目錄 `brand.json` **沒擋**。

### GitHub Actions（`e99ae69` push）

| Workflow | 結果 | 說明 |
|---|---|---|
| [public-fast-ci](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282596) | success | Ubuntu／Windows × Python 3.11、3.12 |
| [Windows development gate](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282645) | success | `tools\dev_check.ps1`，Python 3.12 |
| [CodeQL](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282593) | success | Python `security-extended` |
| [Upstream check](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282592) | success | 無未審查上游 commit |

`git ls-files` 142 檔。無 `.env`、金鑰、私人品牌、使用者 `output/`。`origin` 為 `SanHsien/ai-content-factory`；`upstream` remote 存在。Issues 已開；private vulnerability reporting 已啟用（API `enabled: true`）；secret scanning 與 push protection 已開。

## 開放 findings

| ID | 嚴重度 | Finding | 證據 | 建議 |
|---|---|---|---|---|
| R-01 | P2 | 公開密鑰掃描漏掉 OpenAI 常見寫法。選配 live image 路徑讀的是 `OPENAI_API_KEY`，掃描器卻只把 `api_key`／`api-key` 當 assignment。 | `scripts/security_scan.py` 186–195 行 `(?ix)\b(?:api[ _-]?key\|...)`；本機暫存檔：環境變數賦值與裸金鑰前綴 0 hit，`api_key = "..."` 1 hit | 加供應商金鑰前綴形狀與 `OPENAI_API_KEY=`。可回貢上游。不要為了綠燈加 ignore。 |
| R-02 | P2 | `render-video --no-network` 是死旗標。解析後 `_run_render_video` 從不讀 `args.no_network`，成功 JSON 永遠 `"network": "DISABLED"`。操作者以為有選擇，實際沒有同意面。 | `src/ai_content_factory/cli.py` 138 行；221–295 行無 `no_network`；291 行硬編碼 `"DISABLED"`；測試只 assert 預設 False | 要嘛拿掉旗標並在 help 寫「本路徑不連網、OS 隔離不宣稱」，要嘛讀旗標：未加 `--no-network` 就拒絕。Motion 產線已寫 `os_network_isolation: NOT_CLAIMED`。 |
| R-03 | P2 | 繁中 README 有 fork 專屬段（`tools\bootstrap_dev.ps1`、DEVELOPMENT／FORK／AGENTS）；`README.en.md` 只有四行橫幅，英文讀者看不到一鍵 gate。 | `README.md` 14–20、52–58 行；`README.en.md` 6–8 行後直接進上游產品本文 | 英文 README 補對等的 fork 段與 `tools\bootstrap_dev.ps1`。測試應鎖兩邊都點名 `FORK.md` 與 bootstrap。 |
| R-04 | P2 | `SECURITY.md` 寫 `config`、品牌 JSON、`output/` 與媒體已進 `.gitignore`。實際只有 `output/`、`private/`、`.env*`、憑證檔名；沒有 `config/`，也沒有通用 `brand.json`。 | `SECURITY.md` 42 行；`.gitignore` 11–29 行；`git check-ignore` 對 `config/foo.json`、根目錄 `brand.json` 無規則 | 文件改成只寫真正忽略的路徑；若要擋私人品牌，加 `config/` 與根目錄 `brand.json`，不要誤傷 `examples/demo-brand/brand.json`。 |
| R-05 | P2 | 中英安全政策互相打架。繁中要人走 GitHub Advisories；英文仍寫「private reporting 尚未啟用」。本 fork 的 Advisories 入口是開的。 | `SECURITY.md` 27–28 行；`SECURITY.en.md` 32–40 行；`GET .../private-vulnerability-reporting` → `{"enabled":true}` | 把 `SECURITY.en.md` 改成與繁中同一條回報路徑。這是 fork 文件，不必等上游。 |
| R-06 | P2 | Issue 樣板「上游原始專案」連到本 fork 自己。品牌掃描禁止把上游帳號寫進追蹤檔，所以用了自指 URL。標題卻像是原作者 repo。 | `.github/ISSUE_TEMPLATE/config.yml` 6–8 行 | 連結改指向 `docs/UPSTREAM.md`，about 維持「原作者見 GitHub Forked from」。不要為了修這個 finding 把上游帳號寫進追蹤檔。 |
| R-07 | P2 | 公開 RC allowlist 收的是改寫後的 `README.md`／`AGENTS.md`，不含 `README.en.md` 與 `tools/`。從本 fork 組 RC，陌生人拿到的會是繁中 fork 入口，不是上游英文產品包。 | `public_release_manifest.json` `include`：`README.md`、`AGENTS.md`；無 `README.en.md`、`FORK.md`、`tools/` | 本線不要當產品 RC 來源。若要從 fork 組包，allowlist 改收英文產品檔，或明確標成「fork 維護候選」而不是上游 v0.1.0。 |
| R-08 | P3 | `check_links.py` 只掃 20 份維護文件，不掃產品 `docs/quickstart.md`、`ARCHITECTURE.md`。那些仍是公開契約。 | `tools/check_links.py` `MAINTAINED_DOCUMENTS`；`tests/test_oss_surface.py` 另驗 quickstart 命令字串，不驗連結 | 現況可接受。若要防產品文件搬家，把 `docs/quickstart.md` 與 `ARCHITECTURE.md` 加進清單。 |
| R-09 | P3 | 本機 Python 3.14.7 全綠；CI 只到 3.12。Windows gate 沒跑 3.11 或 3.14。 | `python --version` → 3.14.7；`.github/workflows/ci.yml` 矩陣 3.11／3.12；`windows-dev-gate.yml` 固定 3.12 | 下次改 CI 時把 Windows 一格升到 3.14。非阻斷。 |
| R-10 | P3 | Motion render 不檢查 `usage_rights`。CLI 沒給 `--provenance` 時，有 `--brand-config` 就標 `PRIVATE_OWNED`，否則 `CHATGPT_HANDOFF`。Live image 路徑會拒絕 `UNKNOWN` 權利；這條不會。 | `cli.py` 238–247 行；`motion_render.py` 無 `usage_rights`；`providers/real_media.py` 94 行對 `UNKNOWN` 失敗 | 維持現況就在文件寫明：motion 只搬已有圖，權利是操作者的聲明，不是掃描結果。不要把靜態圖轉換說成合成主體動作。 |
| R-11 | P3 | `AGENTS.md` 要求一般修改走 branch → PR；維護骨架三筆 commit 直接進 `main`。 | `AGENTS.md` 開發原則；`git log`：`5502e9d`、`db1c309`、`e99ae69` 皆在 `main` | 之後的維護（含本 review 的後續修正）走 PR。已落地的骨架不必重寫歷史。 |
| R-12 | P3 | OSS surface 測試把 fork 身份鎖進產品 README（「Windows-first 維護型 fork」），但沒鎖中英 fork 段對齊。上游若改英文標題，繁中測試仍可能綠。 | `tests/test_oss_surface.py` 19–46 行；英文測試不含 `FORK.md`／bootstrap | 英文測試補 `FORK.md`；fork 專屬句留在 `tests/test_fork_docs.py`，不要繼續膨脹產品 OSS 測試。 |

## 已檢查、不列為 finding

- `src/` 無 `os.system`、`shell=True`、`eval(`、`exec(`、`pickle`、`urllib.request`、`requests`、`httpx`。`subprocess.run` 只在 `local_voice.py` 與 `motion_render.py`，皆 argv 列表。
- 預設 demo／orchestrator／publisher 不開即時 API。Live OpenAI 需 `--provider openai-image`、`--allow-network`、`--confirm-live-call`、`--live-call-plan` 與 `OPENAI_API_KEY`；缺套件時失敗，不暗裡改走 fixture。
- Motion 預設 `npx --offline --yes hyperframes@0.7.106`；產線已標 `os_network_isolation: NOT_CLAIMED`。那是應用層離線，不是 OS 隔離。
- Publisher 只有本機 DryRun／Manual；`REMOTE_WRITE` 非 `"0"` 時產線拒絕。本輪 demo 的 `remote_write` 為 0。
- Apache-2.0：`LICENSE` 與上游 `NOTICE` 仍在。GitHub 帳號不是授權必要條件。
- 公開品牌 denylist 讓追蹤檔不能寫上游帳號。這是刻意約束，不是 attribution 缺失。`tools/upstream_baseline.json` 的 `"repo": "upstream"` 與此一致。
- Dependabot 不自動合併（`docs/DECISIONS.md`），合理。公開 gate 零 pip 依賴，不引入 pytest／ruff。
- Fork 的 Windows gate／CodeQL／upstream-check 已 pin Actions SHA。上游 `ci.yml` 仍用浮動 `checkout@v4`／`setup-python@v5`；不為了格式去改上游產品 workflow。
- `public_ci.py` 會清掉子行程的 `OPENAI_API_KEY` 與 `REMOTE_WRITE`，再強制 `REMOTE_WRITE=0`。
- CodeQL 與 secret scanning 通過，只證明這次 checkout 的靜態面，不是即時 provider、權利或公開發行核准。

## 尚未宣稱範圍

- **沒有**跑真實品牌、真實帳號、付費 OpenAI、HyperFrames／FFmpeg 實機出片，或任何社群平台上傳。
- **沒有**在未設 `PYTHONUTF8` 的互動 CP950 主控台證明所有 CLI 輸出都可印中文；本輪 gate 有設 `PYTHONUTF8=1`。
- **沒有**從本 fork 組 `scripts/build_release_candidate.py` 並做 Stranger Test；R-07 是 allowlist 閱讀結論，不是 RC 實測失敗。
- **沒有**獨立評估 fixture 文章品質、媒體 QA 分數對真實素材的意義。
- `dev_check.ps1` **不含** CodeQL。CodeQL 只在 GitHub。
- **不宣稱** fork 有自己的 GitHub Release 或獨立版號；產品版本仍是上游 v0.1.0。
- **不宣稱** 已把 `ARCHITECTURE.md`、`docs/quickstart.md` 等產品架構文件翻成繁體。那是刻意不做。
- **不宣稱** `npx --offline` 等於主機沒有網路。

## 建議下一步（未動手）

1. 補 OpenAI 密鑰形狀到 `security_scan.py`（R-01），並加一條「`OPENAI_API_KEY=` 加供應商金鑰前綴必須失敗」的測試。這是最值得回貢上游的掃描洞。
2. 處理 `render-video --no-network`（R-02）：刪或真正強制。同時在 help 重申 OS 網路隔離不宣稱。
3. 對齊文件：英文 README 的 fork 段（R-03）、`SECURITY.md` 的 gitignore 句子（R-04）、`SECURITY.en.md` 的 Advisories 入口（R-05）、Issue 上游連結改 `docs/UPSTREAM.md`（R-06）。
4. 之後的程式與文件變更走 PR（R-11），不要再直接推 `main`。
5. 不要從本 fork 當上游 v0.1.0 的 RC 來源，除非先改 allowlist（R-07）。
