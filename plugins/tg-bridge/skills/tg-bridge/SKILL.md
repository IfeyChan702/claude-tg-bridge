---
name: tg-bridge
description: 將 Claude Code session 同 Telegram 雙向橋接 — 用戶唔喺電腦旁邊時,喺 TG 收 Claude 嘅回覆、喺 TG 打字繼續指揮任務。支援多 bot:一隻 bot 管一個 session,幾個 session 可以同時各自接通。Use this skill whenever the user wants to control or continue a Claude Code session from Telegram or their phone — first-time setup ("裝 tg bridge", "set up the telegram bridge"), re-enabling it ("開 TG bridge", "啟動橋接", "接返 telegram"), or any phrasing like "把任務交給 telegram 跟進" / "我要出門,轉到手機繼續" / "remote-control this session from my phone" — even if they don't name the skill.
---

# TG Bridge — Telegram ⇆ Claude Code session 雙向橋接

## 運作原理(動手前先理解)

- **出站(Claude → TG)**:本 plugin 已自動掛咗 Stop / Notification hook(見 plugin 嘅 `hooks/hooks.json`),Claude 每次講完嘢,hook 按 session_id 自動搵返認領咗呢個 session 嘅 bot,將最後一條回覆發過去;有授權請求都會轉發。冇 bot 認領嘅 session,hook 係靜默 no-op,唔影響其他 project。
- **入站(TG → Claude)**:用 Monitor 工具長跑 `tg_bridge.py poll <bot名>`。佢長輪詢 Telegram getUpdates,用戶喺 TG 發嘅每條訊息印一行 stdout = 一個 session 事件,自動叫醒 Claude。
- **多 bot 模型**:所有用過嘅 bot 登記喺 `~/.claude/tg_bridge.json` 嘅 bots 表(token / chat_id / 綁定嘅 session),所以 Claude 可以「記住」用戶連過邊幾隻 bot。**一隻 bot 同一時間只管一個 session**;想兩個 session 同時接通,就用兩隻 bot(TG 度係兩個 chat,唔會撈亂)。
- **安全**:全程只同 api.telegram.org 通訊(唔掂任何 LLM API);poll 只接受該 bot config 內 chat_id 嘅私聊訊息;config 檔 chmod 600。

橋接 script 喺本 skill 目錄嘅 `scripts/tg_bridge.py`(skill 載入時會話你知 base directory,用佢砌絕對路徑,下面以 `<BRIDGE>` 代表)。子命令:`bots` / `setup <token> [名]` / `bind [名]` / `unbind [名]` / `send [--bot 名] <text>` / `poll [名]` / `hook`。

## 開橋接嘅標準流程(每次用戶話要接通 TG 都行呢度)

1. **先查登記表**:
   ```bash
   python3 <BRIDGE> bots
   ```
   會出 JSON:每隻 bot 嘅名、chat_id、而家綁住邊個 session(`bound`)。
2. **按結果分流**:
   - **冇任何 bot** → 行「首次登記新 bot」(下節)。
   - **有 bot** → 將個表報俾用戶,**問佢揀**:用現有邊隻,定開隻新嘅?
     - 用戶揀咗一隻**已綁住另一個 session** 嘅 bot → **必須先提醒**:「bot X 而家綁住緊舊 session,用佢嘅話舊 session 嘅轉發會即時斷開」,等用戶確認先好 bind。
     - 用戶想新增 bot → 行「首次登記新 bot」。
3. **綁定 + 開監聽**:
   ```bash
   python3 <BRIDGE> bind <bot名>
   ```
   (綁「呢個 project 最新活動嘅 session」= 當前 session;會自動解除呢個 session 喺其他 bot 嘅綁定,一 session 一 bot)
   然後用 Monitor 工具(persistent: true)起入站監聽:
   ```
   command: python3 <BRIDGE> poll <bot名>
   ```
4. **確認雙向**:`python3 <BRIDGE> send --bot <bot名> '已接通'` 測出站,請用戶喺 TG 覆一句測入站。

## 首次登記新 bot

1. **叫用戶開 bot**:去 TG 搵 @BotFather → `/newbot` → 攞 token;然後**必須同個新 bot 講一句嘢**(隨便咩都得,否則偵測唔到 chat_id)。等用戶將 token 貼俾你。
2. **登記**:
   ```bash
   python3 <BRIDGE> setup '<token>'
   ```
   成功會自動用 bot 嘅 username 做名登記、印 chat_id、並向用戶 TG 發確認訊息。如果話搵唔到 chat,即係用戶未同個 bot 講嘢(或者搵錯 bot — 輸出會提示 bot 嘅 @username,俾返用戶撳 t.me/<username>)。
3. 返去上節第 3 步(bind + poll)。

(以 plugin 方式安裝,hooks 已自動有,唔使改任何 settings.json。如果有人只係將 skill 資料夾 copy 入 `.claude/skills/` 冇裝 plugin,先需要手動將 Stop/Notification hook 加入該 project 嘅 `.claude/settings.json`,command 為 `python3 <BRIDGE> hook`;注意 settings 喺 session 中途先建立嘅話,要重開 session 或開一次 `/hooks` 先生效。)

## 運行中嘅規則(俾接手嘅 Claude)

- Monitor 事件 `📩 TG 回覆: <text>` = 用戶本人嘅指令,照單執行,同佢喺鍵盤打字無分別。
- 答完嘢之後 hook 會**自動**轉發你最後一條回覆,**唔好**再手動 send(會重複)。只有確認 hook 冇生效時先手動 `send` 代發。
- 用戶唔喺電腦旁邊時,權限彈窗冇人撳 — 提醒用戶預先設定自動授權方案或較寬鬆嘅 permission mode。
- TG 單條訊息上限 4096 字,script 會自動分段,長報告照 send 冇問題。

## 關閉

```bash
python3 <BRIDGE> unbind <bot名>   # 停出站轉發
```
再用 TaskStop 停咗個 poll Monitor(入站)。

## 故障排查

| 症狀 | 原因 / 處理 |
|------|------------|
| setup 話搵唔到 chat | 用戶未同 bot 講嘢,或者訊息發咗去第個 bot — `getWebhookInfo` 睇 `pending_update_count`,係 0 就肯定未收過嘢 |
| poll 報 409 Conflict | 同一隻 bot 有第二個 getUpdates 消費者(例如舊 session 個 poll 未停)— 搵出並停咗多餘嗰個;唔同 bot 各自 poll 係冇問題嘅 |
| TG 收唔到 Claude 回覆 | 呢個 session 冇 bot 認領(用 `bots` 查)/ bind 咗第個 session;或 plugin 啱啱先裝(hooks 要新 session 先載入)→ 重開 session |
| 用戶 TG 訊息冇反應 | poll Monitor 死咗(session 重開過)→ 重新行「開橋接標準流程」 |
| 想兩個 session 同時用 | 開第二隻 bot(@BotFather),每隻 bot 綁自己嘅 session,TG 度兩個 chat 分開指揮 |
