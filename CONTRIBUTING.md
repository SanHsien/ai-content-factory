# 貢獻指南

> English: [CONTRIBUTING.en.md](CONTRIBUTING.en.md)

歡迎能保住離線核心與 provider 邊界、而且方便審查的小改動。

## 開始前

1. 先讀 [`AGENTS.md`](AGENTS.md)、[`FORK.md`](FORK.md) 與 [`README.md`](README.md)。
2. 確認問題在最新 `main` 仍可重現，並查過既有 Issues。
3. 產品契約或離線 demo 的實質變更，優先考慮回報或回貢上游原始專案（GitHub 的 Forked from）。
4. 不要附上私人品牌、素材、帳號或任何憑證。

## 本機開發

```powershell
pwsh -NoProfile -File tools\bootstrap_dev.ps1
```

等價拆開：

```powershell
python -m venv .venv
.venv\Scripts\python -B scripts\bootstrap_offline.py
.venv\Scripts\python -B scripts\public_ci.py
```

非 Windows 請改用該平台的 venv 路徑。基礎 runtime 沒有第三方依賴。

## 變更規則

- 不提交密鑰、個人資料、私人品牌、私人路徑、帳號識別碼、瀏覽器狀態、模型權重、快取或生成輸出。
- 把廠商 import 與網路行為留在明確的選配 adapter 內。
- 補失敗路徑測試；不要削弱離線、核准、防重複或遠端寫入斷言。
- 行為、依賴、複製材料、授權或公開／私有邊界變更時，更新文件與 `PROVENANCE_LEDGER.md`。
- 依賴保持精簡。每一個直接依賴都要記錄來源、版本、授權、用途、網路行為與密鑰需求。

## Provider 與 publisher 貢獻

說明能力、API 或 runtime 假設、來源／授權、網路與密鑰行為、成本／重試上限、權利／隱私限制、錯誤對應，以及人工審查邊界。附上合成 fixture。即時測試必須分開且 opt-in；公開 CI 不能需要憑證、帳號或 GPU。

## 提交與 PR

1. 從最新 `main` 建立短期 branch。
2. 修改完成後跑 `pwsh -NoProfile -File tools\dev_check.ps1`。
3. 開 PR，讓既有 CI／安全檢查完成後再合併。
4. 通過 review 與 gate 後 squash merge 回 `main`；不要直接把日常修改推進 `main`。

- Bug 修正先附失敗測試；新行為需涵蓋成功、邊界與錯誤路徑。
- 修改使用方式時同步更新 `README.md` 與 `README.en.md`。
- PR 說明需交代是否來自 upstream、是否改動公開 CLI／quickstart，以及實際跑過哪些指令。
- 提交訊息建議使用 `fix:`、`feat:`、`docs:`、`test:`、`chore:`。
- 本機測過綠燈，不是即時 provider 可用或可以對外發布的證據。
- Dependabot 與外部 fork 的變更同樣走 PR；人工讀 diff 後再合併。
