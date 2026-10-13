---
name: improve-strategy
description: 提示詞優化循環：根據成效報告提出挑戰者提示詞、A/B 測試、擇優升級，並同步修改策略與排程。每週一次或使用者要求「優化/進化」時使用。
---

先確認是哪個角色（`<代號>`），檔案都在 `accounts/<代號>/`，指令都帶 `--account <代號>`。只用該角色自己的成效與學習，不借用其他角色的結論。

## 循環（每輪約一週）
1. **診斷**：執行 `review-performance` 取得報告與 learnings。
2. **裁決上一輪**：若 ACTIVE.md 有 challenger 且雙方各 ≥8 篇、已過 48 小時成效穩定：
   - challenger 的 eng_rate 與平均 views 均明顯較佳（>20%）→ 升級為 champion
   - 差不多 → 保留 champion，捨棄 challenger（簡單者勝）
   - 較差 → 捨棄並在 learnings 記為「已推翻」
   樣本不足 → 不裁決，繼續測。
3. **提出新挑戰者**：只改**一個變因**（例如鉤子寫法、長度、結尾方式、語氣），複製 champion 為 `accounts/<代號>/prompts/writer.v<N+1>.md`，在檔頭註明「與上一版差異」與「假設」。可參考表現最好的貼文作為正例、最差的作為反例（只提取手法，不貼原文）。
4. **離線預篩**：用 rubric 對新舊提示詞各產 5 篇測試草稿評分並比較；若 challenger 明顯更差就別上線，回到步驟 3。
5. **上線**：更新 `accounts/<代號>/prompts/ACTIVE.md` 的 challenger。
6. **同步調整其他旋鈕**（一次只動一到兩個）：排程時段、format 配比、回覆策略，寫入 `accounts/<代號>/strategy.md` 並把 version 遞增。
7. **記錄**：在 `accounts/<代號>/changelog.md` 追加：版本、依據數據、改了什麼、預期效果、驗證日期。

## 護欄
- 根目錄 `rules.md` 的硬性紅線不可修改；提示詞不得放寬核准與誠實規則。
- 不因單篇爆紅或單篇慘敗改策略；結論需有樣本數。
- 每輪最多一個 challenger，避免變因混雜。
- 優化目標以 eng_rate 為主、views 為輔，不得以標題黨或爭議話題換取數字。
