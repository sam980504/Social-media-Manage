---
name: draft-posts
description: 依目前策略與冠軍/挑戰者提示詞產生社群貼文草稿並放入待核准佇列。使用者要「產今天/本週草稿」時使用。
---

0. 先確認要替哪個角色產草稿（代號 `<代號>`，不確定就先走 `start`）。以下檔案都在 `accounts/<代號>/`，指令都帶 `--account <代號>`。只讀該角色自己的資料。
1. 讀 `persona.md`（status 未確認就先改走 `set-persona`）、`platforms.md`（這個角色經營哪些平台）、`brand-guide.md`（語氣、禁用詞、範例）、`user.md`（審核與時段偏好）、`strategy.md`、`prompts/ACTIVE.md`，以及其中指定的 `prompts/<版本>.md`；標籤格式見根目錄 `rules.md`。
2. 若 `strategy.md` 的定位或風格還是空白，不要硬產草稿，先走 `set-persona` / `set-style`。
3. 依 ACTIVE.md 分流：有 challenger 時約 1/3 的草稿用 challenger 提示詞寫，其餘用 champion。
4. 每篇草稿先用 `prompts/rubric.md` 自評，<15 分重寫或丟棄（honesty 有疑慮直接丟）。極短貼文若 rubric 項目不適用，可只檢查 honesty 與 voice 並說明。
5. 通過者寫入佇列，時段依 `strategy.md` 第 4 節（空白就問使用者）。平台字數上限：threads 500、bluesky 300；`platforms.md` 沒填平台就先問使用者，不要猜。同一則內容要發多個平台、字數都放得下就直接 `add`（預設發到全部啟用平台，每個平台各存一篇、共用 group）；要依平台改寫（字數、語氣不同）就用 `--platform bluesky` 之類分開各 `add` 一篇，並依 `strategy.md` 的「平台」一節調整：
   `python3 tools/social.py --account <代號> add "<正文>" --tags "format:opinion,topic:X,hook:question,prompt:writer.v1" --strategy <目前版本> --at 2026-10-13T20:30:00+08:00`
6. 列出 `social.py --account <代號> list --status draft` 給使用者審核（每篇標明平台）。使用者明確同意才 `approve <id>`，Claude 不自行核准。佇列不能直接改草稿：要改就 `reject` 舊的、再 `add` 新的。
