# 路線圖

> 本 repo 後續工作的單一真相源。做完一項，就在同一個 commit 刪掉那一列；新工作只加在這裡。
> 現況段的數字是 2026-10-29 依 `main` `cfa0e9606ca9` 查的快照，開工前先重查 GitHub。

## 現況

`kafidog/ai-content-factory` 的 Windows-first 維護 fork（離線優先、供應商中立的 AI 內容產線；public，GitHub 上無 fork 上層，上游以本機 `upstream` remote 與 repo 變數 `UPSTREAM_CLONE_URL` 追蹤）。健康：`CodeQL`、`Upstream check`、`Windows development gate`、`public-fast-ci` 預設分支最近一次皆 success（2026-10-27），`Dependency freshness` success（2026-10-25 手動觸發）；open issue 0 筆、open PR 0 筆；Dependabot 與 Code scanning 告警 0 筆；無 release。上游 main 為 `77d6950`，已審到底（`tools/upstream_baseline.json`）。openai 依賴目前以 deferral 延後，下次複審 2026-11-25。

## 近期：可以直接動手
| 項目 | 為什麼 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 決定 `security_scan` 對「未掃描」檔案的處理 | 預設略過任何深度的 `private`、`build`、`logs`、`cache`、`dist`、`output` 等目錄，超過 5MB 或含 NUL（含 UTF-16）的檔案靜默略過且不回報；若這些位置有被追蹤的檔案，金鑰不會被抓到。把「未掃描」列為 finding 會影響 CI，所以要先由維護者決定要不要 | 維護者回覆採用／不採用；採用則由後續工作先寫重現測試（被追蹤的略過目錄內含金鑰樣式，修前掃描無輸出、修後有「未掃描」finding），`python -m pytest` 與 `scripts/public_ci.py` 在乾淨 checkout 綠；不採用則在 `docs/DECISIONS.md` 記理由並刪此列 | 維護者 | `scripts/security_scan.py:26,36-48`；深掃報告（2026-10-26）「需要維護者決定」 |
| `approval.py` 的參照檢查改用 `media/qa.py` 的 `_is_safe_local_reference` | POSIX 上原生 `Path` 會接受含反斜線的檔名，與 qa 新 helper 的規則不一致；目前因要求單一路徑段而不構成漏洞，屬一致性補強 | 測試：含反斜線、`..`、磁碟代號的參照在 approval 與 qa 得到相同拒絕結果（修前至少一項失敗）；`python -m pytest` 綠 | Claude Sonnet | `src/ai_content_factory/pipeline/approval.py:133`；`src/ai_content_factory/media/qa.py:30`；深掃報告（2026-10-26） |

## 中期：等條件成立再做
| 項目 | 觸發條件 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 升 openai pin（現值見 `pyproject.toml` 的 `openai-image`）並更新 deferral | 維護者有金鑰環境可手動跑 `tests/test_real_provider.py` live 模式；或日期到 2026-11-25（`revisit`），或 `Dependency freshness`（每月 1 日）因 PyPI 又超過 `deferredLatest` 轉紅 | live 測試通過後才改 pin；`OpenAI(api_key, max_retries)` 與 `images.edit(...)` 簽章仍相符；`.github/dependency-deferrals.json` 的 openai 條目刪除或更新 `deferredLatest`／`reviewed`／`revisit`；`Dependency freshness` 綠 | 維護者 | `.github/dependency-deferrals.json`；`src/ai_content_factory/providers/openai_image.py`；接續開發報告（2026-10-25） |
| 上游新提交審查 | `Upstream check`（每週一 03:00 UTC）轉 failure，或 `git fetch upstream main` 後 `python tools/check_upstream_updates.py --strict` 非零；failure 代表有未審項目，不是工具壞 | 依 `docs/UPSTREAM.md` 審查清冊逐項判決寫進 `docs/DECISIONS.md`；`pwsh -NoProfile -File tools\dev_check.ps1` 綠；baseline 推進到完整 SHA | Claude Sonnet | `docs/UPSTREAM.md`；`.github/workflows/upstream-check.yml:11` |

## 刻意不做
| 不做什麼 | 理由 | 什麼情況下重新考慮 |
| --- | --- | --- |
| 從本 fork 組上游 v0.1.0 release candidate | 本 fork 的公開 allowlist 不對應上游；`REVIEW.md` R-07 已接受不改 `public_release_manifest.json` | 需要產品 RC 時改用原作者 repo，不在這裡做 |
| 接上真實遠端 provider／publisher 或瀏覽器自動化 | 現階段是離線 staging 邊界；能力狀態與所需證據由 [`docs/skills-roadmap.md`](docs/skills-roadmap.md) 定義（該檔只描述能力狀態，不是工作清單） | 維護者明確變更範圍並完成該檔列出的威脅模型、授權與權利審查 |
| 把 `.venv`、`output/` 等本機忽略檔納入追蹤或清理 | 屬本機環境產物 | 不重新考慮 |
| 修改上游 `ci.yml` 的測試矩陣 | `REVIEW.md` R-09 決定 Windows canonical gate 用 Python 3.14，不改上游矩陣 | 上游矩陣造成本線無法驗證時 |
| 回貢上游（含 R-01／R-02） | 預設只打本 repo；回貢須維護者在當次對話明確同意 | 維護者在當次對話明說要回貢某個修正 |

## 維護方式

上游：每週一 `Upstream check`，failure 才動手；判決見 [`docs/DECISIONS.md`](docs/DECISIONS.md)、[`docs/UPSTREAM.md`](docs/UPSTREAM.md)。依賴：每月 `Dependency freshness`；deferral 一律帶 `revisit` 日期，openai 更版很密，每月可能需更新 `deferredLatest`。日常維護直接推 `origin/main`。
