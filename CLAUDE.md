# CLAUDE.md

請先完整閱讀並遵守 [`AGENTS.md`](AGENTS.md)。本檔只補充 Claude Code 的最小入口：

- 這是保留上游歷史的 fork；不要移除 `upstream`、原作者、Apache-2.0 或 `NOTICE`。
- 預設 runtime 是 Python 3.11+ 標準庫、離線；不要讓 demo 依賴 `pip install`。
- 修改產線或契約前，先跑對應 unittest；提交前跑
  `pwsh -NoProfile -File tools\dev_check.ps1`。
- 使用者產出、私人品牌、本機 `output/` 與憑證一律不可提交。
- 使用繁體中文，直接交付可驗證結果，避免冗長背景鋪陳。
