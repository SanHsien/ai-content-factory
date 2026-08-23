# Repository review（Windows-first）

- Review date: 2026-08-22
- Review baseline: `e99ae69b01955cfd48eaa219c3144f9629b3cb76`
- Remediation: 同日 fork-local 修正（暫不回貢）
- Upstream reviewed through: `d476f740af9c9a0b7f1c2d05c6e658a09ee9abb0`
- Primary environment: Windows 11、PowerShell、Python 3.14.7（本機）；upstream CI 3.11／3.12；本 fork Windows gate 3.14
- Status: 維護骨架可用；R-01–R-06、R-08–R-10、R-12 已在本線修。R-07 接受（不改公開 allowlist）。R-11 接受：日常直接推 `main`。

## 結論

這個 fork 適合作為 Windows 本機、給 Agent 維護的離線內容產線。預設路徑是 fixture、標準庫、不上網：`REMOTE_WRITE` 預設 `"0"`，publisher 只做本機 dry-run／manual。

審查當下（`e99ae69`）的主要風險已在本線處理：OpenAI 金鑰形狀會被掃到、`render-video --no-network` 現在是必填確認、中英入口與安全政策對齊、私人品牌層真的進 `.gitignore`。公開產品仍是上游 `ai-content-factory` v0.1.0。本線不當上游 RC 來源。

不把 fork 當成第二個官方產品 repo。`scripts/public_ci.py`、公開發行 allowlist 與 `docs/quickstart.md` 的可攜命令仍屬上游契約。公開品牌掃描禁止把上游 GitHub 帳號寫進追蹤檔。

## 本輪實證

### 審查當下（`e99ae69`）

```text
pwsh -NoProfile -File tools\dev_check.ps1
→ WINDOWS DEV CHECK GREEN
→ 137 tests OK（1 skipped：POSIX-only venv bootstrap）
→ security scan: clean
→ demo SUCCEEDED，publisher mode=dry-run，remote_write=0
```

當時掃描器對 `OPENAI_API_KEY=` 加供應商金鑰前綴與裸金鑰前綴是 0 finding。GitHub Actions 全綠：
[public-fast-ci](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282596)、
[Windows gate](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282645)、
[CodeQL](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282593)、
[Upstream check](https://github.com/SanHsien/ai-content-factory/actions/runs/32554282592)。

### 修正後

以 `tests/test_security.py`、`tests/test_video_cli.py`、`tests/test_fork_docs.py` 鎖契約。完整 gate 見本 PR 的 `tools\dev_check.ps1`。

## 已修 findings

| ID | 嚴重度 | 做了什麼 |
|---|---|---|
| R-01 | P2 | `security_scan.py` 加 `openai-api-key-assignment` 與 `openai-secret-key-shaped`。空的 `OPENAI_API_KEY=` 仍允許。暫不回貢。 |
| R-02 | P2 | `render-video` 未加 `--no-network` 回 `NETWORK_ISOLATION_CONFIRMATION_REQUIRED`（exit 2）。成功 JSON 加 `os_network_isolation: NOT_CLAIMED`。 |
| R-03 | P2 | `README.en.md` 補 fork 段與 `tools\bootstrap_dev.ps1`。測試鎖中英都點名 `FORK.md`、bootstrap、`AGENTS.md`。 |
| R-04 | P2 | `.gitignore` 加根目錄 `/config/` 與 `/brand.json`。`SECURITY.md` 改寫成與實際忽略清單一致，不誤傷 `examples/demo-brand/brand.json`。 |
| R-05 | P2 | `SECURITY.en.md` 改為 GitHub Advisories 入口，與繁中同一條路。 |
| R-06 | P2 | Issue「上游」連結改 `docs/UPSTREAM.md`（本 repo blob URL）。about 仍指向 GitHub Forked from。 |
| R-08 | P3 | `check_links.py` 加 `ARCHITECTURE.md` 與 `docs/quickstart.md`。 |
| R-09 | P3 | Windows canonical gate 改 Python 3.14。不上游 `ci.yml` 矩陣。 |
| R-10 | P3 | README／`docs/DEVELOPMENT.md` 寫明 motion 是鏡頭運動、provenance 是聲明、不掃 `usage_rights`。不改 motion 產線行為。 |
| R-12 | P3 | fork 專屬句從 `test_oss_surface.py` 搬到 `test_fork_docs.py`。 |

## 接受、不改契約

| ID | 嚴重度 | 處理 |
|---|---|---|
| R-07 | P2 | **不改** `public_release_manifest.json`。`FORK.md`／`docs/DECISIONS.md` 寫明：不要從本 fork 組上游 v0.1.0 RC。 |
| R-11 | P3 | 已落地骨架不重寫歷史。之後一般修改直接推 `origin/main`，不開功能分支。 |

## 已檢查、不列為 finding

- `src/` 無 `os.system`、`shell=True`、`eval(`、`exec(`、`pickle`、`urllib.request`、`requests`、`httpx`。`subprocess.run` 只在 `local_voice.py` 與 `motion_render.py`，皆 argv 列表。
- 預設 demo／orchestrator／publisher 不開即時 API。Live OpenAI 需 `--provider openai-image`、`--allow-network`、`--confirm-live-call`、`--live-call-plan` 與行程內憑證；缺套件時失敗，不暗裡改走 fixture。
- Motion 預設 `npx --offline --yes hyperframes@0.7.106`；產線已標 `os_network_isolation: NOT_CLAIMED`。
- Publisher 只有本機 DryRun／Manual；`REMOTE_WRITE` 非 `"0"` 時產線拒絕。
- Apache-2.0：`LICENSE` 與上游 `NOTICE` 仍在。
- 公開品牌 denylist 讓追蹤檔不能寫上游帳號。`tools/upstream_baseline.json` 的 `"repo": "upstream"` 與此一致。
- Dependabot 不自動合併。公開 gate 零 pip 依賴。
- Fork 的 Windows gate／CodeQL／upstream-check 已 pin Actions SHA。上游 `ci.yml` 仍用浮動 tag。
- `public_ci.py` 會清掉子行程的即時憑證環境變數與 `REMOTE_WRITE`，再強制 `REMOTE_WRITE=0`。

## 尚未宣稱範圍

- **沒有**跑真實品牌、真實帳號、付費 OpenAI、HyperFrames／FFmpeg 實機出片，或任何社群平台上傳。
- **沒有**在未設 `PYTHONUTF8` 的互動 CP950 主控台證明所有 CLI 輸出都可印中文。
- **沒有**從本 fork 組 `scripts/build_release_candidate.py`；R-07 是刻意不組。
- **沒有**獨立評估 fixture 文章品質。
- `dev_check.ps1` **不含** CodeQL。
- **不宣稱** fork 有自己的 GitHub Release 或獨立版號。
- **不宣稱** 已把 `ARCHITECTURE.md`、`docs/quickstart.md` 翻成繁體。
- **不宣稱** `npx --offline` 等於主機沒有網路。
- **不宣稱** 已把 scanner／`--no-network` 修正送回上游。

## 建議下一步

1. 若要回貢 R-01／R-02，另開上游 PR；本輪不做。
2. 需要產品 RC 時用原作者 repo，不要用本 fork 的 allowlist。
3. 之後維護直接推 `origin/main`。
