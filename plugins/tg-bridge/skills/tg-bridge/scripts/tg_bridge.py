#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram ⇆ Claude Code session 橋接(多 bot 版)。

一個 bot 管一個 session:每隻 bot 有自己嘅 token / chat_id / 綁定 session,
全部登記喺 ~/.claude/tg_bridge.json 嘅 bots 表,所以 Claude 隨時用 `bots`
命令睇返記住咗邊幾隻,按用戶選擇再 bind。

子命令([名] 可省略 — 得一隻 bot 時自動用佢):
  bots                  # 列出已登記 bot 同各自綁定狀態(JSON)
  setup <token> [名]    # 登記新 bot(預設用 bot username 做名);用戶要先同 bot 講過嘢
  bind [名]             # 將「呢個 project 最新活動嘅 session」綁去呢隻 bot
                        # 一 session 一 bot:會自動解除呢個 session 喺其他 bot 嘅綁定
  unbind [名]
  send [--bot 名] <text>
  poll [名]             # 長輪詢(俾 Monitor 用);一隻 bot 同時只可以有一個 poll
  hook                  # 俾 Stop / Notification hook 調用(按 session_id 自動搵 bot)

設定檔: ~/.claude/tg_bridge.json          {"bots": {名: {token, chat_id, session_id}}}
狀態檔: ~/.claude/tg_bridge_state.<名>.json   {offset}(每隻 bot 獨立嘅 poll 進度)
舊版單 bot config 會自動遷移。
"""
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.claude/tg_bridge.json")
TG_MSG_LIMIT = 3900  # TG 上限 4096,留返啲餘量


def state_path(name):
    return os.path.expanduser("~/.claude/tg_bridge_state.%s.json" % name)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(path, 0o600)  # 入面有 bot token


def api(token, method, **params):
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data, timeout=70) as resp:
        return json.load(resp)


def download_media(token, media):
    """下載 TG 媒體(video/document/photo)到 ~/Downloads/tg_bridge/,回傳本地路徑或錯誤描述。"""
    try:
        info = api(token, "getFile", file_id=media["file_id"]).get("result", {})
        fp = info.get("file_path")
        if not fp:
            return "file_id=%s(getFile 冇 file_path)" % media["file_id"]
        dest_dir = os.path.expanduser("~/Downloads/tg_bridge")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, media.get("file_name") or os.path.basename(fp))
        urllib.request.urlretrieve("https://api.telegram.org/file/bot%s/%s" % (token, fp), dest)
        return dest
    except Exception as exc:
        return "下載失敗(%s)— 檔案可能超過 Bot API 20MB 限制" % exc


def load_cfg():
    """讀 config,順手將舊版單 bot 格式遷移成 bots 表。"""
    cfg = load_json(CONFIG_PATH)
    if "token" in cfg:  # 舊版格式
        name = "default"
        try:
            name = api(cfg["token"], "getMe")["result"].get("username") or name
        except Exception:
            pass
        bot = {"token": cfg["token"]}
        for k in ("chat_id", "session_id"):
            if cfg.get(k) is not None:
                bot[k] = cfg[k]
        cfg = {"bots": {name: bot}}
        save_json(CONFIG_PATH, cfg)
        old_state = load_json(os.path.expanduser("~/.claude/tg_bridge_state.json"))
        if old_state:
            save_json(state_path(name), old_state)
        print("ℹ️ 已將舊版 config 遷移做多 bot 格式(bot 名: %s)" % name, file=sys.stderr)
    cfg.setdefault("bots", {})
    return cfg


def pick_bot(cfg, name=None, session_id=None):
    """揀一隻 bot:指名 > 得一隻 > 按綁定 session 配對。搵唔到就報錯收工。"""
    bots = cfg["bots"]
    if name:
        if name not in bots:
            print("❌ 冇叫 %r 嘅 bot,已登記: %s" % (name, ", ".join(bots) or "(冇)"))
            sys.exit(1)
        return name, bots[name]
    if len(bots) == 1:
        return next(iter(bots.items()))
    if session_id:
        for n, b in bots.items():
            if b.get("session_id") == session_id:
                return n, b
    print("❌ 有 %d 隻 bot,要指明用邊隻: %s" % (len(bots), ", ".join(bots) or "(冇)"))
    sys.exit(1)


def send_text(bot, text):
    """發送(超長自動分段)。失敗只印 stderr,唔好搞死 hook。"""
    text = text.strip()
    if not text:
        return
    for i in range(0, len(text), TG_MSG_LIMIT):
        try:
            api(bot["token"], "sendMessage", chat_id=bot["chat_id"], text=text[i:i + TG_MSG_LIMIT])
        except Exception as exc:
            print("tg_bridge: sendMessage 失敗: %s" % exc, file=sys.stderr)


def project_transcript_dir():
    # Claude Code 將 cwd 嘅 / . _ 全部換成 - 做 project 目錄名
    return os.path.expanduser("~/.claude/projects/") + os.getcwd().replace("/", "-").replace(".", "-").replace("_", "-")


def newest_session_id():
    files = glob.glob(project_transcript_dir() + "/*.jsonl")
    if not files:
        print("❌ 喺 %s 搵唔到 session transcript" % project_transcript_dir())
        sys.exit(1)
    return os.path.splitext(os.path.basename(max(files, key=os.path.getmtime)))[0]


# ---------- 子命令 ----------

def cmd_bots():
    cfg = load_cfg()
    out = []
    for name, b in cfg["bots"].items():
        out.append({
            "name": name,
            "chat_id": b.get("chat_id"),
            "session_id": b.get("session_id"),
            "bound": bool(b.get("session_id")),
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_setup(token, name=None):
    cfg = load_cfg()
    try:
        me = api(token, "getMe")["result"]
    except Exception as exc:
        print("❌ token 唔啱或者連唔到 TG: %s" % exc)
        sys.exit(1)
    name = name or me.get("username") or "default"
    # 同一個 token 重複 setup → 更新返原有嗰隻
    for n, b in cfg["bots"].items():
        if b["token"] == token:
            name = n
            break
    bot = cfg["bots"].setdefault(name, {})
    bot["token"] = token
    try:
        updates = api(token, "getUpdates", timeout=0).get("result", [])
    except Exception as exc:
        print("❌ getUpdates 失敗: %s" % exc)
        sys.exit(1)
    chat_id = None
    for u in updates:
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            chat_id = chat["id"]
    if chat_id is None:
        save_json(CONFIG_PATH, cfg)
        print("⚠️ token 已存低(bot 名: %s),但搵唔到你嘅 chat — 去 TG 同 @%s 講句嘢,再跑一次 setup"
              % (name, me.get("username")))
        sys.exit(1)
    bot["chat_id"] = chat_id
    save_json(CONFIG_PATH, cfg)
    # 將 offset 推到最尾,setup 前嘅舊訊息唔好當成指令
    if updates:
        save_json(state_path(name), {"offset": updates[-1]["update_id"] + 1})
    send_text(bot, "✅ Claude ⇆ TG 橋接已連接(bot: %s)。喺度回覆就可以繼續 Claude 嘅任務。" % name)
    print("✅ bot %r 已登記,chat_id=%s,並已發測試訊息" % (name, chat_id))


def cmd_bind(name=None):
    cfg = load_cfg()
    name, bot = pick_bot(cfg, name)
    sid = newest_session_id()
    old = bot.get("session_id")
    # 一 session 一 bot:解除呢個 session 喺其他 bot 嘅綁定
    for n, b in cfg["bots"].items():
        if n != name and b.get("session_id") == sid:
            b.pop("session_id", None)
            print("ℹ️ session 原本綁喺 bot %r,已解除嗰邊" % n)
    bot["session_id"] = sid
    save_json(CONFIG_PATH, cfg)
    if old and old != sid:
        print("⚠️ bot %r 原本綁住 session %s — 已切換,舊 session 嘅轉發即時停止" % (name, old[:8]))
    print("✅ bot %r 已綁定 session %s" % (name, sid))


def cmd_unbind(name=None):
    cfg = load_cfg()
    name, bot = pick_bot(cfg, name)
    bot.pop("session_id", None)
    save_json(CONFIG_PATH, cfg)
    print("✅ bot %r 已解除綁定" % name)


def cmd_send(text, name=None):
    cfg = load_cfg()
    if not cfg["bots"]:
        print("❌ 未登記任何 bot,先跑 setup")
        sys.exit(1)
    # 冇指名時:得一隻用嗰隻,否則用綁住「最新 session」嗰隻
    try:
        sid = None if name or len(cfg["bots"]) == 1 else newest_session_id()
    except SystemExit:
        sid = None
    name, bot = pick_bot(cfg, name, session_id=sid)
    if not bot.get("chat_id"):
        print("❌ bot %r 未完成 setup(冇 chat_id)" % name)
        sys.exit(1)
    send_text(bot, text)
    print("✅ 已經由 bot %r 發送" % name)


def cmd_poll(name=None):
    """長輪詢一隻 bot。每條入站訊息印一行(俾 Monitor 變成 session 事件)。"""
    cfg = load_cfg()
    name, bot = pick_bot(cfg, name)
    if not bot.get("chat_id"):
        print("tg_bridge: bot %r 未完成 setup,poll 退出" % name, file=sys.stderr)
        sys.exit(1)
    offset = load_json(state_path(name)).get("offset", 0)
    while True:
        try:
            updates = api(bot["token"], "getUpdates", offset=offset, timeout=50).get("result", [])
        except Exception:
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            save_json(state_path(name), {"offset": offset})
            msg = u.get("message") or {}
            # 只接受你本人嘅私聊訊息,陌生人搵到個 bot 都指揮唔到
            if (msg.get("chat") or {}).get("id") != bot["chat_id"]:
                continue
            text = (msg.get("text") or "").strip()
            if text:
                print("📩 TG 回覆: %s" % text, flush=True)
            media = msg.get("video") or msg.get("document") or (msg.get("photo") or [{}])[-1]
            if media.get("file_id"):
                dest = download_media(bot["token"], media)
                caption = (msg.get("caption") or "").strip()
                print("📎 TG 媒體已收: %s%s" % (dest, ("(caption: %s)" % caption) if caption else ""), flush=True)


def last_assistant_text(transcript_path):
    """由 transcript 尾部搵最後一條帶文字嘅 assistant 訊息。"""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    with open(transcript_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 512 * 1024))
        lines = f.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # tail 切斷嘅半行
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content") or []
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        if any(t.strip() for t in texts):
            return "\n".join(t for t in texts if t.strip())
    return ""


def cmd_hook():
    """Stop / Notification / PreToolUse hook 入口。任何情況都要靜靜地 exit 0,唔可以阻住 Claude。"""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    sid = payload.get("session_id")
    if not sid:
        return
    cfg = load_cfg()
    bot = next((b for b in cfg["bots"].values()
                if b.get("session_id") == sid and b.get("chat_id")), None)
    if not bot:
        return  # 呢個 session 冇 bot 認領 → 唔出聲
    event = payload.get("hook_event_name", "")
    if event == "PreToolUse":
        # AskUserQuestion 係 UI 彈窗:Stop hook 唔會 fire、TG 回覆又撳唔到佢,
        # 橋接緊嘅 session 會就咁卡死。擋走佢,叫 Claude 行返文字問答回路。
        if payload.get("tool_name") == "AskUserQuestion":
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "呢個 session 已橋接咗 Telegram,用戶可能唔喺電腦旁,彈窗式提問佢見唔到、"
                    "session 會卡死。請改用普通文字提問:列出所有選項並用 1/2/3 編號,"
                    "講明回覆數字即可,然後結束你嘅 turn — 問題會自動轉發去 TG,"
                    "用戶回覆會以「📩 TG 回覆」事件返嚟。唔好再調用 AskUserQuestion。"),
            }}, ensure_ascii=False))
        return
    if event == "Notification":
        msg = payload.get("message") or ""
        if "permission" in msg.lower():  # 只轉發授權請求,閒置提示唔好嘈
            send_text(bot, "⏸ %s" % msg)
        return
    send_text(bot, last_assistant_text(payload.get("transcript_path")))


def main():
    args = sys.argv[1:]
    # 抽走 --bot <名>(send 用)
    bot_flag = None
    if "--bot" in args:
        i = args.index("--bot")
        if i + 1 < len(args):
            bot_flag = args[i + 1]
            args = args[:i] + args[i + 2:]
    cmd = args[0] if args else ""
    rest = args[1:]
    if cmd == "bots":
        cmd_bots()
    elif cmd == "setup" and rest:
        cmd_setup(rest[0], rest[1] if len(rest) > 1 else None)
    elif cmd == "bind":
        cmd_bind(rest[0] if rest else None)
    elif cmd == "unbind":
        cmd_unbind(rest[0] if rest else None)
    elif cmd == "send":
        cmd_send(" ".join(rest) if rest else sys.stdin.read(), bot_flag)
    elif cmd == "poll":
        cmd_poll(rest[0] if rest else None)
    elif cmd == "hook":
        cmd_hook()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
