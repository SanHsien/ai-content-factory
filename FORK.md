# Fork 維護說明

本 repo fork 自 GitHub 上的公開專案 `ai-content-factory`，沿用 Apache-2.0 與完整 Git 歷史。
原作者 repo 以 GitHub 的 Forked from／本機 `upstream` remote 為準；公開品牌掃描禁止把上游帳號寫進追蹤檔。

## 為什麼維護 fork

- 保留原作者持續更新的離線內容產線、契約、fixture demo 與公開發行閘門。
- 採 Windows-first 維護：Windows 11 + PowerShell 是主要開發、除錯與完整驗收環境。
- 公開入口改以繁體中文為主，英文鏡像放 `README.en.md`。
- 建立可重現的 Windows 開發 gate、Windows CI job，以及逐筆審查的上游追蹤。
- 不把私人品牌、帳號、素材或即時供應商呼叫帶進公開核心。

**回貢判準：修的是上游的 bug 就送回去；這裡獨創的文件／Windows 維護骨架留在這裡。**

## 與上游的差異

| 項目 | 說明 |
|---|---|
| `README.md` | 繁中主檔；上游英文移到 `README.en.md` |
| `AGENTS.md` / `CLAUDE.md` | 本 fork 的 AI 維護單一真相源；上游英文在 `AGENTS.en.md` |
| `NOTICE.md` / `FORK.md` | 來源、授權與同步說明（Apache `NOTICE` 原文保留） |
| `tools/dev_check.ps1` | Windows 本機一鍵 gate，包住上游 `scripts/public_ci.py` |
| `.github/workflows/windows-dev-gate.yml` | Windows 跑同一套 canonical gate |
| `.github/workflows/upstream-check.yml` | 每週對 `upstream/main` 做未審查 commit 檢查 |
| `docs/DECISIONS.md`、`docs/UPSTREAM.md`、`docs/DEVELOPMENT.md` | fork 維護文件 |
| `scripts/security_scan.py` | fork 補 OpenAI 金鑰前綴與 `OPENAI_API_KEY=` 掃描（暫不回貢） |
| `render-video --no-network` | fork 改為必填確認；成功 JSON 標 `os_network_isolation: NOT_CLAIMED` |

產品 CLI、離線 demo、provider 契約、`scripts/public_ci.py` 與公開發行 allowlist 以上游為準，除非有已記錄的 fork 修正。

**不要從本 fork 組上游 v0.1.0 公開 RC。** `public_release_manifest.json` 仍收改寫後的 `README.md`／`AGENTS.md`，不含 `README.en.md` 與 `tools/`。產品發行候選以來源上游為準。

## 分支與 remote

- `origin/main`：SanHsien 維護線，也是唯一長期分支。
- 日常修改使用短期 branch，經 PR 與 CI 驗證後 squash merge 回 `main`。
- `upstream/main`：原作者 repo（本機 remote 名為 `upstream`），只追蹤、不推送。
- Dependabot 或外部 fork 的變更同樣走 PR，人工讀 diff 並通過 CI 後再合併。

不要 `git push upstream`。同步方式見 [`docs/UPSTREAM.md`](docs/UPSTREAM.md)。

上游更新英文 `README.md` 時，把新內容併進 `README.en.md`，再把對應段落翻進本 fork 的繁中 `README.md`。

## 換一台電腦怎麼開發

```powershell
git clone https://github.com/SanHsien/ai-content-factory.git
cd ai-content-factory
# `gh repo clone` 已會加上 `upstream` remote；若沒有，請用 GitHub 頁面 Forked from 的 clone URL：
# git remote add upstream <parent-clone-url>
pwsh -NoProfile -File tools\bootstrap_dev.ps1
```
