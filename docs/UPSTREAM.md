# 上游維護

## Remote

- Fork：`origin` → `https://github.com/SanHsien/ai-content-factory.git`
- 原作者：本機 git remote `upstream`（GitHub Forked from；不要把上游帳號寫進追蹤檔）
- 追蹤分支：`main`

## 檢查新提交

```powershell
git fetch upstream main
python tools\check_upstream_updates.py --strict
```

工具以 `tools/upstream_baseline.json` 的 `reviewed_through` 為起點，列出所有未審查提交。
有新提交或檢查失敗時，`--strict` 回傳非零；排程 workflow 也會因此明確失敗。

## 審查清冊

每次只做一次批次審查：

1. 讀 commit 主旨與變更檔案。
2. 判斷是否與繁中 README、Windows gate 或測試衝突。
3. 可直接同步的提交用 merge；只需要部分修正時 cherry-pick 或最小重做。
4. 跑 `pwsh -NoProfile -File tools\dev_check.ps1`。
5. 在 `docs/DECISIONS.md` 記錄採用／略過理由。
6. 驗證完成後才把 baseline 推進到已審查的完整 40 字元 SHA。

Baseline 代表「已審查」，不代表「全部已合併」。

README 衝突的解法：上游新英文內容併進 `README.en.md`，再把對應段落翻進 `README.md`。

## 2026-08-22：fork 起點

本 fork 自上游 `main` `d476f740af9c9a0b7f1c2d05c6e658a09ee9abb0`
（`docs: update public security reporting status`）建立。此 SHA 設為第一個 `reviewed_through`。
之後的上游 commit 才需要進入審查清冊。

## 2026-08-22：上游 PR、issue、分支盤點

上游當時 **0 個 open PR、0 個 open issue、1 個分支**（只有預設分支）。沒有可引用的項目。

記下來是為了下次不必重推：這個上游不用 PR 流程，改動直接進預設分支，所以本 fork 的審查單位
就是 commit；issue 若日後出現，判準是「只有會改變本 fork 要驗什麼的才追」（Windows 行為、
授權、隱私），純功能請求隨 commit 進來。

### 分支

已逐一與上游預設分支比對（不是只數數量）：**沒有任何分支帶著獨佔 commit**——上游的分支都是
open PR 的 head，或已完全併回預設分支。所以分支這個面向本輪沒有可引用的東西。

### 水位
- PR、issue 皆為 **0**（盤點日 2026-08-22），記在 `tools/upstream_baseline.json`。

## 2026-08-23：複查

`d476f74` 之後上游預設分支 **0 個新 commit**；遠端仍只有預設分支一條，沒有其他分支可比。
PR 與 issue 面向：上游現有一個**已關閉**的 PR，是本 fork 端誤開到上游後立刻關掉的那一個
（詳見 `FORK.md` 的「只對本 fork 開 PR」條），不是上游自己的變更，沒有可引用的內容；
open PR 與 open issue 仍為 0。**水位仍要推進**：`--state all` 的最大 PR 編號是 #1，記 0 表示「還沒看過 #1」，下次檢查會把它再列一次。改記 `reviewed_pr_through: 1`。

**這裡有一個刻意的取捨要寫清楚**：本檔開頭規定不把上游帳號寫進追蹤檔，所以
`tools/upstream_baseline.json` 的 `repo` 是本機 remote 名稱 `upstream` 而不是 slug。代價是
`tools/check_upstream_updates.py` 只能追 commit，**無法自動查 PR／issue**——這兩個面向要靠人工
盤點（像今天這樣）。這是為了追蹤檔不外洩上游身分而付的代價，不是漏做；若日後改變取捨，
把 slug 放進去就能比照其他 fork 自動收 PR／issue。
