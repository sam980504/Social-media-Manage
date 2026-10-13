# 社群帳號經營（Threads、Bluesky）：Claude 作為大腦（多角色多平台版）

## 起點
先走 skill `start`：列出現有角色、選一個繼續，或建立新角色（訪談角色與風格，不提供現成範本）。

## 多角色與獨立性
- 每個角色一個資料夾 `accounts/<代號>/`，裡面是它自己的一切：`persona.md`、`brand-guide.md`、`user.md`、`platforms.md`、`strategy.md`、`learnings.md`、`changelog.md`、`prompts/`、`research/`、`posts/`、`metrics/`、`replies/`、`.env`（token）。
- **角色之間完全獨立**：不得讀 A 角色的設定、風格、成效、研究去用在 B 角色；切換角色時重新讀該角色的檔案。
- 共用的只有：`tools/social.py`、`.claude/skills/`、`templates/account/`（空白模板）、`rules.md`（紅線與標籤格式）。
- 工具的每個指令都要明確帶 `--account <代號>`，沒有「目前選中的角色」。不確定是哪個角色就先問使用者。

## 運作閉環
草稿 → 人工核准 → 發佈 → 同步成效 → 檢討 → 改策略 → 下一輪草稿

| 步驟 | 做法 |
|---|---|
| 起點／選角色 | skill `start`，先看 `social.py overview`（所有角色一張表）；新角色用 `social.py init-account <代號>` 建空白資料夾 |
| 看總覽／核准 | `social.py overview` 看所有角色；草稿的核准／退回在對話裡由使用者明確說可以，才跑 `approve`／`reject <id> --note "理由"` |
| 設角色 | skill `set-persona`（聊天訪談，一次一題），寫入 `accounts/<代號>/persona.md` |
| 定風格 | skill `set-style`，使用者三選一：指定帳號／先海巡社群／直接寫草稿來回調 |
| 研究 | skill `research-topics`，讀 `accounts/<代號>/research/watchlist.md` |
| 產草稿 | skill `draft-posts`，寫入佇列（status=draft）。一個角色可經營多個平台：`add` 預設發到全部啟用平台，每個平台各存一篇（共用 group）；依平台改寫用 `--platform` |
| 核准 | 使用者說可以，才跑 `social.py --account <代號> approve <id>` |
| 發佈 | `python3 tools/social.py --account <代號> publish-due`（只發 approved 且到時間者；不會自己定時跑）。所有角色一次：`social.py publish-due --all`（各用各自的 token 與檔案） |
| 成效 | `social.py --account <代號> sync` 然後 `report`（沒有 token 時會跳過） |
| 檢討 | skill `review-performance` |
| 進化 | skill `improve-strategy`，修改該角色的 `strategy.md` 並記入 changelog |
| 留言 | skill `handle-replies` |

## 規則
- 所有工具呼叫：`python3 tools/social.py --account <代號> <cmd>`，輸出為 JSON。某平台沒有憑證時，該平台自動 dry-run。
- 發文與回覆一律須使用者明確核准，Claude 不得自行 approve。
- 每篇草稿必須帶 tags 與 `--strategy <該角色目前版本>`，格式見 `rules.md`。
- 角色身分、受眾、邊界的唯一來源是 `accounts/<代號>/persona.md`；角色未確認前不得排程。
- 角色經營哪些平台，唯一來源是 `accounts/<代號>/platforms.md` 的 `platforms:`（threads／bluesky，沒有預設值）。每篇貼文、留言、成效都屬於單一平台，核准、發佈、檢討都按平台分開；不同平台的指標不可直接比（Bluesky 沒有瀏覽數）。
- 聲音（語氣、禁用詞、範例貼文）的唯一來源是 `accounts/<代號>/brand-guide.md`。
- 操作者偏好（審核習慣、方便審核的時段）記在 `accounts/<代號>/user.md`，只放偏好，不放策略；與 strategy.md 衝突時以 strategy.md 為準。
- `learnings.md` 是學到的規律。`posts/`、`metrics/`、`replies/` 是系統資料（純文字檔，git 即歷史），草稿與狀態一律用 `social.py` 改，不要手改。
- 若推上 GitHub，儲存庫必須是**私有**的（內含角色設定與貼文）。憑證只放在各角色自己的 `.env`（`THREADS_ACCESS_TOKEN`、`THREADS_USER_ID`、`BLUESKY_HANDLE`、`BLUESKY_APP_PASSWORD`），Bluesky 一律用 App Password、不用主密碼，不得進 repo。
- 策略的唯一來源是 `accounts/<代號>/strategy.md`；風格、排程、回覆規則都在那裡改，不要散落在別處。
- `rules.md` 的硬性紅線不可被任何角色的自我改進修改。
- 新角色沒有任何預設風格、配比、排程；全部由訪談與成效決定。
- 爬文只用於找主題靈感，不複製原文。
- 時間一律台北時間 (+08:00)。
- 需要 Python 3（macOS 通常已有；Windows 需自行安裝）。

## 目錄
- `rules.md` 共用紅線與標籤格式
- `tools/social.py` CLI（佇列、發佈、成效、回覆、`accounts`、`overview`、`init-account`）
- `templates/account/` 新角色的空白模板
- `accounts/<代號>/` 各角色資料（`.env` 不入版控）
- `.claude/skills/` 流程 skill
