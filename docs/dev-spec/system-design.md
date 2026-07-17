# 智能商業與輿情分析服務系統設計文件

版本：v0.3  
最後更新日期：YYYY-MM-DD  
負責人：填寫組員姓名  
文件狀態：Draft / Review / Approved  

## 1. 文件目的

本文件說明智能商業與輿情分析服務的系統架構、模組分工、資料流、API 設計、n8n 自動化流程、AI / ML 分析流程、警示通知機制、錯誤處理、資料一致性、非同步任務設計、部署方式與未來擴充方向。

本系統的核心目標是讓店家透過 Line Bot 低門檻使用輿情分析服務。使用者只需要在 Line 中提出需求，系統即可透過 n8n 自動化流程建立服務任務，收集網路評論與社群討論，分析好評與負評，並提供警示通知與改善建議。

## 2. 系統定位

本系統不是單純的爬蟲工具，而是一套智能商業與輿情分析服務。爬蟲只是資料來源的一部分，真正的服務價值在於將非結構化的網路評論轉換成可行動的商業洞察。

MVP 階段主要完成「輿情分析」。系統需要能夠接收店家需求、建立爬蟲任務、收集貼文與留言、分析正負面內容、產生摘要與改善建議，並在發現高風險負評時通知客戶。

第二階段再完成「線上預約智能管理」。預約功能完成後，系統可以進一步結合預約數據與輿情數據，提供店家更深入的營運分析。

## 3. 系統整體架構

系統由七個主要部分組成，分別是 Line Bot、n8n Workflow、Backend API、Database、Crawler Service、AI / ML Analysis Service、Notification Service。

```text
Customer / Store Owner
        ↓
Line Bot
        ↓
n8n Workflow
        ↓
Backend API
        ↓
Database
        ↓
Crawler Service
        ↓
AI / ML Analysis Service
        ↓
Notification Service
        ↓
Line Bot Alert / Report