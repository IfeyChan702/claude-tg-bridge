# claude-tg-bridge

**Control Claude Code from your phone, through Telegram.**

English | [中文](README.zh.md)

A two-way bridge between a Claude Code session and Telegram: Claude's replies are pushed to your private TG bot the moment each turn ends, and anything you type in Telegram wakes the session and continues the task — as if you were typing at the keyboard.

Pure Python stdlib. Zero dependencies. Talks only to `api.telegram.org`.

## Why

Claude Code is running a long task, but you need to leave — a meeting, a commute, sleep. The task still needs you: to make a call, paste a token, change direction. With this plugin you just keep the conversation going from Telegram, and when you're back at the computer you type in Claude Code again. Seamless hand-off, both ways.

- 📲 Claude's final reply of every turn is **auto-pushed** to your private bot (permission requests too)
- ⌨️ Every message you send in TG becomes a **session event** that wakes Claude to continue
- 🔁 Walk back to the keyboard and just keep typing — no mode switching
- 🤖 **Multi-bot**: register several bots, one bot drives one session — run multiple sessions in parallel from separate TG chats

## How it works

```
┌────────────────────────── your machine ──────────────────────────┐
│                                                                   │
│  Claude Code session                                              │
│  ├── outbound: Stop / Notification hooks (auto-wired by plugin)   │
│  │     turn ends → tg_bridge.py hook → read the last assistant    │
│  │     message from the local transcript → sendMessage to bot     │
│  │                                                                │
│  └── inbound: a persistent Monitor runs tg_bridge.py poll         │
│        long-polls getUpdates → each TG message = one stdout line  │
│        → becomes a session event → wakes Claude                   │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                          ▲ ▼ only talks to api.telegram.org
                       ┌──────────────┐
                       │ your TG bot  │ ←→ 📱 your phone
                       └──────────────┘
```

Neither direction touches any LLM API — outbound reads the local transcript file, inbound is the standard Telegram Bot API long poll.

## Install

Inside Claude Code:

```
/plugin marketplace add IfeyChan702/claude-tg-bridge
/plugin install tg-bridge@claude-tg-bridge
```

Restart your session (so the plugin's hooks load), then tell Claude:

> set up the telegram bridge

Claude walks you through the rest. You only do two things:

1. Open **@BotFather** in Telegram → `/newbot` → paste the token to Claude
2. **Send your new bot any message** (otherwise your chat_id can't be detected)

Claude then runs `setup` (stores config, detects your chat_id) → `bind` (claims the current session) → starts the listener → tests both directions.

## Daily use

| Scenario | What to do |
|----------|-----------|
| New session, want TG connected | Tell Claude "**enable the tg bridge**" — it lists your registered bots, asks which to use, warns if that bot is bound to another session |
| Leaving the computer | Nothing — replies are already being pushed |
| Driving from TG | Just type; long reports are auto-split (4096-char limit handled) |
| Back at the keyboard | Just type in Claude Code |
| Two sessions in parallel | Create a second bot, bind one per session — two separate TG chats, zero crosstalk |
| Stop | Tell Claude "stop the tg bridge" |

## Command reference

The core is one zero-dependency script (`skills/tg-bridge/scripts/tg_bridge.py`):

| Command | What it does |
|---------|--------------|
| `bots` | List registered bots and which session each one is bound to (JSON) |
| `setup <token> [name]` | Register a bot (defaults to its username), detect your chat_id, send a confirmation |
| `bind [name]` | Bind the project's most recently active session to this bot (one session per bot; releases old bindings) |
| `unbind [name]` | Stop outbound forwarding |
| `send [--bot name] <text>` | Send a message manually (testing; auto-splits long text) |
| `poll [name]` | Long-poll getUpdates, print one line per inbound message (consumed by the Monitor) |
| `hook` | Called by the Stop/Notification hooks; routes by session_id to the owning bot |

`[name]` can be omitted when only one bot is registered. Files:

- `~/.claude/tg_bridge.json` — bot registry: token + chat_id + bound session per bot (chmod 600)
- `~/.claude/tg_bridge_state.<name>.json` — per-bot poll offset

## Security model

- **No secrets in this repo** — your bot token lives only in your local config
- **Allowlist** — the poller accepts private messages from your chat_id only; strangers who find your bot are ignored
- **Single-session forwarding** — hooks only forward the session a bot has explicitly claimed; on machines with no config they are a silent no-op
- **Network surface** — the script talks to `api.telegram.org` and nothing else
- ⚠️ Anyone holding your bot token can impersonate the bot — never paste it anywhere public

## FAQ

**How does a new session take over?**
Tell it "enable the tg bridge". Claude checks the registry (`bots`), asks which bot to use, and — if that bot is bound to an older session — warns you that the old session's forwarding will be cut before proceeding. Make sure the old session's poller is stopped: one bot supports exactly one long-poll connection.

**Can two sessions run at the same time?**
Yes — one bot per session. `/newbot` is free and takes a minute; each session gets its own TG chat.

**What if the session dies (reboot, app closed)?**
The inbound listener lives inside the session, so a dead session means nobody is reading TG. Re-ignite remotely with the official Claude mobile app: open a new session, tell it "enable the tg bridge". Official app as the igniter, TG as the daily channel.

**Claude asked for a permission while I was away?**
The Notification hook pushes permission requests to TG so you know, but approving happens at the computer. Before leaving, consider a more permissive permission mode.

**Why long-polling instead of a webhook?**
No public IP, no open ports, no TLS certs — works behind NAT and home networks out of the box.

**Group chats / multiple people?**
Deliberately unsupported. This is a single-operator remote-control channel.

## Requirements

- Claude Code (desktop app or CLI, with the Monitor tool)
- macOS / Linux with Python 3 (stdlib only, nothing to pip-install)
- A Telegram bot (free via @BotFather, takes a minute)

## Repo layout

```
claude-tg-bridge/
├── .claude-plugin/marketplace.json     # marketplace entry
├── plugins/tg-bridge/
│   ├── .claude-plugin/plugin.json      # plugin manifest
│   ├── hooks/hooks.json                # Stop/Notification hooks (auto-wired via ${CLAUDE_PLUGIN_ROOT})
│   └── skills/tg-bridge/
│       ├── SKILL.md                    # the full setup/re-enable/troubleshooting playbook for Claude
│       └── scripts/tg_bridge.py        # the bridge core (~250 lines, zero deps)
└── README.md
```

## License

MIT
