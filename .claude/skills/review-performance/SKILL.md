---
name: review-performance
description: 同步各平台成效並產出檢討報告（依 tag、提示詞版本、時段比較）。使用者要「看成效/週報/檢討」時使用。
---

先確認是哪個角色（`<代號>`，不確定走 `start`），只分析該角色自己的成效，不跨角色合併。

1. `python3 tools/social.py --account <代號> sync --days 14`，再 `python3 tools/social.py --account <代號> report --days 14`。沒有 token 時 sync 會跳過、report 為空，如實告知使用者。
2. `report` 按平台分開輸出（`platforms.<平台>.by_tag`）。**不同平台的指標不可直接比**：Threads 有瀏覽數所以看互動率，Bluesky 沒有瀏覽數只能比平均互動數；一律分平台分析，不要把兩個平台的樣本混在一起。分析 `by_tag`：format、topic、hook、hour，特別是 `prompt:*` 的 champion vs challenger。
3. 誠實規則：n<5 的組別只能說「假設」；兩組差距小於約 20% 且樣本少時，判定「無明顯差異」。
4. 輸出：(a) 表現最好/最差 3 篇與可能原因；(b) 各 tag 比較表；(c) 提示詞 A/B 目前戰況；(d) 建議交給 `improve-strategy` 的 1–3 個實驗。
5. 把有證據的結論追加到 `accounts/<代號>/learnings.md`（標明狀態與樣本數）。
