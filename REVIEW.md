# Project Review 2026-08-22

## 結論

`SanHsien/ai-content-factory` 已從上游公開專案 `ai-content-factory` fork，並補上與其他維護型 fork 相同的開發環境與治理檔。離線 CLI、fixture demo、`scripts/public_ci.py` 與公開發行 allowlist 未改寫產品行為。

這是維護骨架落地，**不是**內容產線重寫。發行仍以上游 v0.1.0 為準，直到有 fork-only 修正需要獨立版本。

## 本輪落地

| 項目 | 狀態 |
| --- | --- |
| 公開 fork `SanHsien/ai-content-factory` | 完成 |
| 繁中 `README.md` + 英文 `README.en.md` | 完成 |
| `AGENTS.md` / `CLAUDE.md` / `FORK.md` / `NOTICE.md` | 完成 |
| `docs/DECISIONS.md` / `UPSTREAM.md` / `DEVELOPMENT.md` | 完成 |
| Windows gate `tools/dev_check.ps1` + CI Windows job | 完成 |
| `upstream-check` + CodeQL + Dependabot | 完成 |
| 上游產品契約（`public_ci.py`、quickstart 命令） | 保留 |

## 尚未通過 / 後續

- 本機驗證（2026-08-22）：`pwsh -NoProfile -File tools\dev_check.ps1` → `WINDOWS DEV CHECK GREEN`；`public_ci.py` 137 tests OK（1 skipped），security scan clean，offline demo `SUCCEEDED`。
- 本 fork 尚無自己的 GitHub Release；陌生人仍可依 README 離線 bootstrap。
- 即時 provider、遠端發布與 macOS 實機驗證仍依上游聲明：未包含或未驗證。
