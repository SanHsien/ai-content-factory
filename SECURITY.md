# 安全政策

> English: [SECURITY.en.md](SECURITY.en.md)

## 支援範圍

安全修正以本 fork 的最新 `main` 為主；上游版本的問題也會視需要回報原作者。
公開 v0.1.0 支援離線核心與零依賴 demo。即時 provider 與 publisher adapter 是實驗性、選配，或尚未包含。沒有任何文件授權帳號存取、遠端發布、瀏覽器自動化、憑證設定、付款或部署。

## 本機檢查

在專案根目錄執行：

```text
python -B -m unittest discover -s tests -p "test_*.py"
python -B scripts/security_scan.py --root . --brand-hash-file scripts/public_brand_hashes.sha256
python -B scripts/public_ci.py
pwsh -NoProfile -File tools\dev_check.ps1
```

編修後掃描會檢查憑證樣式的值、敏感檔名、私人絕對路徑，以及已設定的品牌 fingerprint。報告只含相對路徑、規則與 fingerprint。追蹤的品牌檔只有雜湊。

這些檢查降低意外洩漏風險，不是安全保證。二進位、編碼、新穎、被忽略或外部資料仍可能逃過。

## 私下回報

請使用 GitHub Security Advisories 的 **Report a vulnerability**
私下回報：<https://github.com/SanHsien/ai-content-factory/security/advisories/new>。
若該入口不可用，請透過 GitHub 個人檔案聯絡維護者，不要先建立公開 Issue。

回報請包含影響範圍、重現步驟、受影響版本與最小必要證據。請勿附上真實 API key、cookie、帳號、私人媒體或可識別個人的品牌設定。

若問題也存在於上游，維護者會視需要轉報 GitHub 上的原作者 repo。上游目前未公開專用安全信箱；不要在公開 Issue 放密鑰或 exploit 細節。

## 特別注意

- 永遠不要提交憑證、token、cookie、私鑰、瀏覽器設定檔、帳號匯出、私人媒體或正式設定。
- `.env.example` 只有名稱與空佔位符。
- 選配 adapter 讀取明確的行程範圍設定，錯誤與 log 必須編修。
- 公開測試只用生成的合成值與 fixture transport。
- 私人品牌層留在公開 repo 之外。
- `.gitignore` 已含 `output/`、`private/`、`.env*`、根目錄 `config/` 與根目錄 `brand.json`。公開 demo 品牌在 `examples/demo-brand/`，會被追蹤。不得用強制加入繞過。

## 發行閘門

公開候選由 `public_release_manifest.json` 組裝。allowlist 檢查、密鑰／品牌／路徑掃描、來源審查、依賴審查、乾淨 Stranger Test、ZIP 解壓或校驗比對失敗時停止。不要只為了拿到乾淨報告而加 ignore。

## 外部 adapter

啟用 adapter 前，審查驗證、網路目的地、資料保存、訓練政策、權利、成本、重試、速率限制、輸出完整性、依賴來源與操作者授權。本機 fixture 或介面不能證明外部服務安全或可用。
