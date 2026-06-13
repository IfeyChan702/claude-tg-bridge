# claude-tg-bridge

[English](README.md) | 中文

**Telegram ⇆ Claude Code session 雙向橋接** — 人唔喺電腦旁邊,用 Telegram 繼續指揮 Claude Code 做嘢。

> **TL;DR (English)**: A two-way bridge between a Claude Code session and Telegram. Claude's replies are auto-pushed to your private TG bot via a Stop hook; anything you type in TG becomes a session event (via a long-polling Monitor) that wakes Claude to continue the task. Multi-bot support: register several bots, one bot drives one session, so multiple sessions can run in parallel from separate TG chats. Pure Python stdlib, zero dependencies, talks only to `api.telegram.org`. Install: `/plugin marketplace add IfeyChan702/claude-tg-bridge` → `/plugin install tg-bridge@claude-tg-bridge` → tell Claude "set up the telegram bridge".

---

## 呢個 plugin 解決咩問題

Claude Code 做緊長任務,你要出門 / 開會 / 瞓覺,但任務中途要你拍板、補資料、改方向。官方手機 app 可以鏈接 session,但如果你日常生活喺 Telegram,呢個 plugin 令你:

- 📲 Claude 每講完一輪,**自動推**最後嗰條回覆去你嘅 TG bot
- ⌨️ 你喺 TG 打嘅**每句嘢**,即時變成 session 事件,叫醒 Claude 繼續做
- 🔁 返到電腦直接喺 Claude Code 打字,兩邊無縫接力
- 🤖 **多 bot**:登記幾隻 bot,一隻 bot 管一個 session — 幾個 session 同時運行,TG 度幾個 chat 分開指揮,唔會撈亂

## 架構

```
┌─────────────────────────── 你部電腦 ───────────────────────────┐
│                                                                │
│  Claude Code session                                           │
│  ├── 出站:Stop / Notification hook(plugin 自動掛)            │
│  │     每輪結束 → tg_bridge.py hook → 讀 transcript 最後一條    │
│  │     assistant 訊息 → sendMessage 去你嘅 bot                  │
│  │                                                             │
│  └── 入站:Monitor 工具長跑 tg_bridge.py poll                   │
│        長輪詢 getUpdates → 每條 TG 訊息印一行 stdout             │
│        → 變成 session 事件 → 自動叫醒 Claude                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                              ▲ ▼ 只同 api.telegram.org 通訊
                        ┌──────────────┐
                        │ 你嘅 TG bot  │ ←→ 📱 你部手機
                        └──────────────┘
```

兩個方向都唔掂任何 LLM API — 出站係讀本地 transcript 檔,入站係標準 Telegram Bot API 長輪詢。

## 安裝

喺 Claude Code 入面:

```
/plugin marketplace add IfeyChan702/claude-tg-bridge
/plugin install tg-bridge@claude-tg-bridge
```

裝完**重開一個 session**(等 plugin hooks 載入),然後同 Claude 講:

> 裝 tg bridge

Claude 會跟住 skill 帶你行晒以下流程,你只需要做兩樣嘢:

1. 去 TG 搵 **@BotFather** → `/newbot` → 攞 token,貼俾 Claude
2. **同你個新 bot 講一句嘢**(咩都得 — 唔講嘢 Claude 偵測唔到你嘅 chat_id)

之後 Claude 自動完成:`setup`(寫 config + 認 chat_id)→ `bind`(綁定當前 session)→ 起監聽 → 雙向測試。

## 日常使用

| 情景 | 做法 |
|------|------|
| 開新 session 想接通 TG | 同 Claude 講「**開 TG bridge**」(佢會 bind + 起監聽) |
| 出門前 | 確認 bridge 開咗,直接走 — Claude 答完嘢會推去 TG |
| 喺 TG 指揮 | 直接打字,同喺電腦打無分別;長報告 Claude 會自動分段推送 |
| 返到電腦 | 直接喺 Claude Code 打字,唔使切換咩模式 |
| 停用 | 叫 Claude「停咗 TG bridge」(unbind + 停監聽) |

## Script 子命令參考

橋接核心係一個零依賴嘅 Python script(`skills/tg-bridge/scripts/tg_bridge.py`):

| 命令 | 作用 |
|------|------|
| `bots` | 列出登記咗嘅 bot 同各自綁住邊個 session(JSON) |
| `setup <token> [名]` | 登記新 bot(預設用 bot username 做名)、自動偵測你嘅 chat_id、發確認訊息 |
| `bind [名]` | 將「當前 project 最新活動嘅 session」綁去呢隻 bot(一 session 一 bot,自動解除舊綁定) |
| `unbind [名]` | 解除綁定(出站即停) |
| `send [--bot 名] <text>` | 手動發訊息去 TG(測試用;超長自動分段) |
| `poll [名]` | 長輪詢 getUpdates,每條入站訊息印一行(俾 Monitor 用) |
| `hook` | 俾 Stop / Notification / PreToolUse hook 調用(按 session_id 自動搵返認領嘅 bot) |

`[名]` 喺只登記咗一隻 bot 時可以省略。檔案位置:

- `~/.claude/tg_bridge.json` — bots 表:每隻 bot 嘅 token + chat_id + 綁定 session(chmod 600)
- `~/.claude/tg_bridge_state.<bot名>.json` — 每隻 bot 自己嘅 poll 進度(getUpdates offset)

## 安全模型

- **Token 唔入 repo**:bot token 只存喺你本機 config,plugin 本身冇任何秘密
- **白名單**:poll 只接受 config 入面你本人 chat_id 嘅**私聊**訊息 — 陌生人就算搵到你個 bot,講咩都會被忽略
- **單 session 轉發**:hook 只轉發已綁定嗰一個 session,唔會將你其他 project 嘅嘢推出去;未 setup 嘅機器上 hook 係靜默 no-op
- **網絡面**:全程只同 `api.telegram.org` 通訊
- ⚠️ 記住:邊個攞到你 bot token 就可以扮你個 bot,唔好將 token 貼上任何公開地方

## 常見問題

**Q: 新 session 點接手?**
A: 喺新 session 講「開 TG bridge」— Claude 會用 `bots` 查返你登記過嘅 bot 俾你揀。揀咗一隻已綁住舊 session 嘅 bot,Claude 會先提醒你「會斷開舊 session 嘅轉發」等你確認。注意舊 session 嘅監聽要停咗(閂咗舊 session 或者叫佢停),同一隻 bot 只可以有一個 poll。

**Q: 兩個 session 可唔可以同時運行?**
A: 可以 — 開兩隻 bot(@BotFather 度 `/newbot` 多一次),每隻 bot 綁自己嘅 session。TG 度係兩個獨立 chat,邊個 chat 指揮邊個 session,清清楚楚。Bot 數量冇上限,Telegram 開 bot 免費。

**Q: session 死咗(電腦重啓 / app 閂咗)點算?**
A: 入站監聽寄生喺 session 入面,session 冇咗 TG 訊息就冇人接。遙距重生:用 Claude 官方手機 app 嘅 remote 功能開個新 session,叫佢「開 TG bridge」接手。官方鏈接做點火器,TG 做日常通道。

**Q: 我唔喺電腦旁,Claude 要權限批准點算?**
A: Notification hook 會將授權請求推去 TG 通知你,但「批准」要喺電腦發生 — 出門前建議用較寬鬆嘅 permission mode,或者配合自動授權方案。

**Q: 我唔喺電腦旁,Claude 想彈選擇題問我點算?**
A: 選項彈窗(AskUserQuestion)喺 TG 度撳唔到,所以有個同步 PreToolUse hook 會幫已橋接嘅 session 擋走佢,叫 Claude 改用文字列 1/2/3 選項提問 — 問題會照常轉發去 TG,你回覆數字就得。冇橋接嘅 session 彈窗照常。

**Q: 點解唔直接用 webhook?**
A: 長輪詢唔使公網 IP / 開 port / HTTPS 證書,喺住宅網絡同 NAT 後面都即裝即用。

**Q: 支唔支援群組 / 多人?**
A: 唔支援(刻意)。呢個係單人遙控通道,只認你本人嘅私聊。

## 要求

- Claude Code(桌面 app 或 CLI,需有 Monitor 工具)
- macOS / Linux + Python 3(純標準庫,冇任何 pip 依賴)
- 一個 Telegram bot(@BotFather 免費開,一分鐘)

## Repo 結構

```
claude-tg-bridge/
├── .claude-plugin/marketplace.json     # marketplace 入口
├── plugins/tg-bridge/
│   ├── .claude-plugin/plugin.json      # plugin manifest
│   ├── hooks/hooks.json                # Stop/Notification/PreToolUse hook(自動掛,用 ${CLAUDE_PLUGIN_ROOT})
│   └── skills/tg-bridge/
│       ├── SKILL.md                    # 教 Claude 安裝/開啓/排障嘅完整流程
│       └── scripts/tg_bridge.py        # 橋接核心(~220 行,零依賴)
└── README.md
```

## License

MIT
