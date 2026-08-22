# 維護決策

## 2026-08-22：建立 Windows-first 維護型 fork

**決定**：fork 上游公開專案 `ai-content-factory`，保留 Apache-2.0、上游 `NOTICE` 與完整歷史，預設分支維持 `main` 以降低與上游同步摩擦。本線聚焦繁中公開入口、Windows 開發 gate、Windows CI，以及逐筆審查的上游追蹤。公開品牌掃描禁止把上游 GitHub 帳號寫進追蹤檔，因此文件只指向 GitHub 的 Forked from 與本機 `upstream` remote。

**理由**：上游離線產線、契約、fixture demo 與 `public_ci.py` 已經可用，符合「先把流程拆開，再交給 AI 一步一步做」的需求。缺的是 Windows 11 上可重現的開發／驗收骨架，以及繁中入口。直接用上游 repo 難以長期記錄 fork 取捨。

**限制**：

- 不把 fork 包裝成原創專案，不移除原作者、Apache-2.0 或 `NOTICE`。
- 產品 CLI、fixture registry、公開發行 allowlist 與 `docs/quickstart.md` 的可攜命令保持上游契約。
- `README.md` 改為繁中主檔；上游英文放 `README.en.md`。`tests/test_oss_surface.py` 改驗繁中入口，並另驗英文鏡像。
- 不把產品架構文件整批翻譯；`docs/quickstart.md` 與 `ARCHITECTURE.md` 等產品契約維持上游英文。
- 上游更新必須逐筆審查。

## 2026-08-22：開發 gate 不引入 pip 依賴

**決定**：`tools/dev_check.ps1` 只包 compileall、相對連結檢查與上游 `scripts/public_ci.py`。不把 pytest / ruff 變成公開檢查的必要條件。

**理由**：上游的產品不變式是「陌生人不用 `pip install` 也能跑 demo 與公開 CI」。fork 維護骨架不應打破這條線。

## 2026-08-22：不啟用 Dependabot 自動合併

**決定**：Dependabot 只開 PR；CI 與人工讀 diff 通過後才合併。

**理由**：預設 runtime 零依賴，GitHub Actions 與選配 extra 體積小，但自動合併仍會跳過「讀 diff」這一步。
