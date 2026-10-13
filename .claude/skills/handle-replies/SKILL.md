---
name: handle-replies
description: 抓取貼文留言、依回覆策略擬草稿並待使用者核准後送出。使用者要「處理留言/回覆」時使用。
---

先確認是哪個角色（`<代號>`，不確定走 `start`）；以下指令都帶 `--account <代號>`，檔案在 `accounts/<代號>/`。

1. `python3 tools/social.py --account <代號> pull-replies`，再 `social.py --account <代號> replies --status new`。
2. 依 `accounts/<代號>/strategy.md` 第 5 節分類（空白就先訪談使用者定回覆策略）：值得回 / 忽略 / 需使用者決定（攻擊、敏感、個資）。
3. 值得回者：`social.py draft-reply <key> "<≤2句回覆>"`；忽略者 `approve-reply <key> --ignore`（`<key>` 是 `replies` 輸出的 key，例如 `bluesky__at___…`，每則留言屬於一個平台，回覆會回到同一平台，字數上限依平台）。
4. 把草稿列給使用者；使用者同意後 `approve-reply <key...>`，再 `send-replies`。
5. 回覆的成效（對方是否再回）可在下次 review 時用來調整回覆風格。
