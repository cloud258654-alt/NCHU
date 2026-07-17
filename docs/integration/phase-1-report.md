# Phase 1 Report: 安全工作區與 Git 基準

## 執行日期

2026-07-17 15:18:41 +08:00

## 來源與目標路徑

- 來源專案 A：D:\group-project-V2-main
- 來源專案 B：D:\BI-RMP-main
- 目標工作區：D:\BI-RMP-V2
- 備份根目錄：D:\project-backups
- 備份目錄：D:\project-backups\20260717-151840

## 備份 ZIP

| 專案 | ZIP 路徑 | 大小 bytes | entries | 驗證 |
|---|---:|---:|---:|---|
| A | D:\project-backups\20260717-151840\group-project-V2-main.zip | 187299 | 42 | readable |
| B | D:\project-backups\20260717-151840\BI-RMP-main.zip | 4078242 | 182 | readable |

## Git 初始化結果

- .git exists: True
- initial branch/status recorded after commit in validation section

## .gitignore 檢查結果

- .env ignored: True
- check-ignore output:

`	ext
.gitignore:1:.env	.env
`

## 來源專案異動檢查

只對來源專案執行讀取與壓縮備份；未對來源專案執行寫入、刪除、移動、重新命名或 Git 操作。

| 專案 | before file count | after file count | before latest write UTC | after latest write UTC | 結果 |
|---|---:|---:|---|---|---|
| A | 42 | 42 | 07/17/2026 05:04:49 | 07/17/2026 05:04:49 | unchanged |
| B | 182 | 182 | 07/17/2026 05:05:12 | 07/17/2026 05:05:12 | unchanged |

## Warning

- 備份程序依安全限制排除 .git、常見 build/cache 目錄，以及真實 .env / .env.* secret files；本次未發現真實 .env 檔名。
- 未執行套件安裝、服務啟動、資料庫 SQL、migration 或 git push。

## 結論

PASS
