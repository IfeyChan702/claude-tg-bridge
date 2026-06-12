# claude-tg-bridge

**Telegram ⇆ Claude Code session 雙向橋接** — 人唔喺電腦旁邊,用 TG 繼續指揮 Claude Code。

Two-way bridge between a Claude Code session and Telegram: Claude's replies are pushed to your TG bot; whatever you type in TG wakes the session and continues the task.

## 安裝 Install

喺 Claude Code 入面:

```
/plugin marketplace add IfeyChan702/claude-tg-bridge
/plugin install tg-bridge@claude-tg-bridge
```

裝完同 Claude 講:**「裝 tg bridge」**,佢會帶你行晒成個流程(開 bot → 貼 token → 自動接通)。

## 點運作 How it works

| 方向 | 機制 |
|------|------|
| Claude → TG | Plugin 自帶 Stop / Notification hook:Claude 每講完一輪,自動將最後回覆發去你嘅 bot;權限請求都會通知 |
| TG → Claude | Claude 用 Monitor 工具長跑 `tg_bridge.py poll`(長輪詢 getUpdates),你每條 TG 訊息變成 session 事件,即時叫醒 Claude 繼續做嘢 |

- 純 Python 標準庫,零依賴;只同 `api.telegram.org` 通訊
- 只接受你本人 chat_id 嘅私聊訊息;bot token 淨係存喺本機 `~/.claude/tg_bridge.json`(chmod 600)
- 一次 setup,之後每個新 session 講聲「開 TG bridge」就接返通

## 要求 Requirements

- Claude Code(桌面 app 或 CLI,需有 Monitor 工具)
- macOS / Linux + Python 3
- 一個 Telegram bot(@BotFather 免費開,一分鐘)

## License

MIT
