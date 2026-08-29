# 維護決策

## 2026-08-23：複查上游，維持 baseline

**決定**：`reviewed_date` 推進到 2026-08-23，`reviewed_through` 不動。

**理由**：上游預設分支自 `d476f74` 起 0 個新 commit，遠端只有一條分支，open PR／issue 仍為 0。
唯一的 PR 是本 fork 端誤開後關閉的那一個，不是上游的變更。

**同時記下一個取捨**：追蹤檔刻意不寫上游 slug（見 `docs/UPSTREAM.md`），因此 PR／issue 這兩個
面向沒有自動化，只能人工盤點。這是取捨不是缺口，寫下來避免下次被當成漏做而重建工具。

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

## 2026-08-22：審查可修項先在 fork 落地，暫不回貢

**決定**：REVIEW.md R-01–R-06、R-08–R-10、R-12 在本線修。R-07 不改 `public_release_manifest.json`。R-11 當時用 PR 消化審查修正，不重寫已進 `main` 的骨架歷史。暫不把 scanner／CLI 修正送回上游。

**理由**：維護者要求先修本線能修的部分。公開 allowlist 是產品契約，改了會讓本 fork 組出的包不再是上游產品提取。scanner 與 `--no-network` 是行為修正，記在 fork 差異表，之後若要回貢另開。

**限制**：

- `public_release_manifest.json`、`scripts/public_ci.py`、fixture registry、`REMOTE_WRITE=0` 不改。
- Windows canonical gate 改跑 Python 3.14；上游 `public-fast-ci` 矩陣仍是 3.11／3.12。
- Motion 路徑仍不掃描 `usage_rights`；只在 README／開發文件寫明那是操作者聲明。

## 2026-08-22：不從本 fork 組上游產品 RC

**決定**：本維護線不當上游 v0.1.0 的 RC 來源。需要公開產品包時，用原作者 repo 或另外定義 fork 維護候選。

**理由**：allowlist 會帶出繁中 `README.md` 與 fork `AGENTS.md`，不含 `README.en.md` 與 `tools/`。那不是陌生人該拿到的上游產品形狀。

## 2026-08-22：日常維護直接推 `main`

**決定**：之後一般修改直接推 `origin/main`，不開功能分支、不開維護 PR。提交前跑 `pwsh -NoProfile -File tools\dev_check.ps1`。Dependabot 仍開 PR，人工讀 diff 後合併。不推 `upstream`。

**理由**：維護者明確要求。本線是單人維護 fork，branch → PR 摩擦大於收益。GitHub 仍接受外人 PR 與 Dependabot PR。

## 2026-08-29：上游檢查補上 PR 與 issue 兩個面向

**決定**：`check_upstream_updates.py` 補上以 `--state all` 收集上游 PR／issue 的邏輯，
`upstream-check.yml` 補 `GH_TOKEN: ${{ github.token }}`，新增 `tests/test_upstream_updates.py`。
Baseline 既有的水位不動。

**理由**：`docs/UPSTREAM.md` 早就寫著「四個面向都要看」，`upstream_baseline.json` 也記著
`reviewed_pr_through` 與 `reviewed_issue_through`——但**沒有任何程式讀那兩個欄位**，檢查器只比對
commit 水位。那兩個面向不是「查過沒發現」，是根本沒查，而每週的排程報告長得跟查過一樣綠。
這是艦隊層級的問題：24 個 fork 裡 21 個都這樣（`SanHsien/repo-fleet-ops` 的 `docs/INCIDENTS.md`
第十條）。參考實作是 `SanHsien/harness-guard`。

三個性質，缺一不可：

- **`--state all`**：只查 `open` 看不到「開了又關、沒有合併」的 PR，而那正是「上游拒收、但可能對
  本 fork 有價值」的一類——已合併的遲早會經由 commit 抵達，被關掉的永遠不會。
- **`gh` 失敗時回 `None` 不回 `[]`**，報告寫 `Not checked` 並 **fail closed**（exit 2）。
  「沒查到」和「沒有」在綠色報告裡長得一樣，只有一個是真的。
- **`GH_TOKEN`**：`gh` 在 Actions 裡沒有憑證就列舉不到，配上 fail closed 會讓紅燈的意思變成
  「檢查器壞了」而不是「上游有東西」。

**證據**：落地後實跑 `python tools/check_upstream_updates.py`，三個面向都印出水位與待辦數；
本 repo 的 gate 全綠。

**已知代價**：水位以上真的有東西時，每週的 upstream-check 會回 exit 1。那是它該做的事——先前的
綠燈不是「沒有待辦」，是沒有人看。

**觸發條件**：報告列出項目時逐筆讀 diff、把採用／略過理由寫進本檔，然後才推進 baseline 的水位。
