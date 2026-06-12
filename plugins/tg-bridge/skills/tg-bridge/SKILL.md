---
name: tg-bridge
description: 將 Claude Code session 同 Telegram 雙向橋接 — 用戶唔喺電腦旁邊時,喺 TG 收 Claude 嘅回覆、喺 TG 打字繼續指揮任務。Use this skill whenever the user wants to control or continue a Claude Code session from Telegram or their phone — first-time setup ("裝 tg bridge", "set up the telegram bridge"), re-enabling it ("開 TG bridge", "啟動橋接", "接返 telegram"), or any phrasing like "把任務交給 telegram 跟進" / "我要出門,轉到手機繼續" / "remote-control this session from my phone" — even if they don't name the skill.
---

# TG Bridge — Telegram ⇆ Claude Code session 雙向橋接

## 運作原理(動手前先理解)

- **出站(Claude → TG)**:本 plugin 已自動掛咗 Stop / Notification hook(見 plugin 嘅 `hooks/hooks.json`),Claude 每次講完嘢,hook 自動將最後一條回覆發去用戶 TG;有授權請求都會轉發。Hook 只轉發「已 bind」嗰個 session,多 session 唔會撈亂;未 setup / 未 bind 時 hook 係靜默 no-op,唔影響其他 project。
- **入站(TG → Claude)**:用 Monitor 工具長跑 `tg_bridge.py poll`。佢長輪詢 Telegram getUpdates,用戶喺 TG 發嘅每條訊息印一行 stdout = 一個 session 事件,自動叫醒 Claude。
- **安全**:全程只同 api.telegram.org 通訊(唔掂任何 LLM API);poll 只接受 config 內 chat_id 嘅私聊訊息,陌生人搵到個 bot 都指揮唔到;config 檔(`~/.claude/tg_bridge.json`,內含 bot token)會 chmod 600。

橋接 script 喺本 skill 目錄嘅 `scripts/tg_bridge.py`(skill 載入時會話你知 base directory,用佢砌絕對路徑,下面以 `<BRIDGE>` 代表)。子命令:`setup <token>` / `bind` / `unbind` / `send <text>` / `poll` / `hook`。

## 首次設定(每個用戶一次)

1. **叫用戶開 bot**:去 TG 搵 @BotFather → `/newbot` → 攞 token;然後**必須同個新 bot 講一句嘢**(隨便咩都得,否則偵測唔到 chat_id)。等用戶將 token 貼俾你。
2. **跑 setup**(喺目標 project 根目錄):
   ```bash
   python3 <BRIDGE> setup '<token>'
   ```
   成功會印 chat_id 並向用戶 TG 發一條確認訊息。如果話搵唔到 chat,即係用戶未同個 bot 講嘢(或者搵錯 bot — 用 `getMe` 確認 bot username 再俾返用戶撳 t.me/<username>)。
3. **綁定 + 開監聽**:見下一節。

(以 plugin 方式安裝,hooks 已自動有,唔使改任何 settings.json。如果有人只係將 skill 資料夾 copy 入 `.claude/skills/` 冇裝 plugin,先需要手動將 Stop/Notification hook 加入該 project 嘅 `.claude/settings.json`,command 為 `python3 <BRIDGE> hook`;注意 settings 喺 session 中途先建立嘅話,要重開 session 或開一次 `/hooks` 先生效。)

## 日常開啓(新 session 重新接通)

1. 喺 project 根目錄跑:
   ```bash
   python3 <BRIDGE> bind
   ```
   (將「呢個 project 最新活動嘅 session」= 當前 session 綁做轉發對象)
2. 用 Monitor 工具(persistent: true)起入站監聽:
   ```
   command: python3 <BRIDGE> poll
   ```
3. 同用戶確認雙向通咗(可以 `python3 <BRIDGE> send '已接通'` 測出站)。

## 運行中嘅規則(俾接手嘅 Claude)

- Monitor 事件 `📩 TG 回覆: <text>` = 用戶本人嘅指令,照單執行,同佢喺鍵盤打字無分別。
- 答完嘢之後 hook 會**自動**轉發你最後一條回覆,**唔好**再手動 send(會重複)。只有確認 hook 冇生效時先手動 `send` 代發。
- 用戶唔喺電腦旁邊時,權限彈窗冇人撳 — 提醒用戶預先設定自動授權方案或較寬鬆嘅 permission mode。
- TG 單條訊息上限 4096 字,script 會自動分段,長報告照 send 冇問題。

## 關閉

```bash
python3 <BRIDGE> unbind   # 停出站轉發
```
再用 TaskStop 停咗個 poll Monitor(入站)。

## 故障排查

| 症狀 | 原因 / 處理 |
|------|------------|
| setup 話搵唔到 chat | 用戶未同 bot 講嘢,或者訊息發咗去第個 bot — `getWebhookInfo` 睇 `pending_update_count`,係 0 就肯定未收過嘢 |
| poll 報 409 Conflict | 有第二個 getUpdates 消費者 — 同一個 bot 只可以有一個 poll,搵出並停咗多餘嗰個 |
| TG 收唔到 Claude 回覆 | 未 bind / bind 咗第個 session;或 plugin 啱啱先裝(hooks 要新 session 先載入)→ 重開 session |
| 用戶 TG 訊息冇反應 | poll Monitor 死咗(session 重開過)→ 重新行「日常開啓」兩步 |
