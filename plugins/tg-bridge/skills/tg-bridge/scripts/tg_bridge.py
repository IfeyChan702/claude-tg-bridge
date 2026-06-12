#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram ⇆ Claude Code session 橋接。

出站:Claude Code Stop hook 調用 `hook` 模式 → 將最後一條 Claude 回覆發去 TG
入站:session 入面起一個 Monitor 跑 `poll` 模式 → 你喺 TG 嘅回覆變成 session 事件,
      Claude 收到就繼續做嘢

子命令:
  setup <bot_token>   # 一次性設定:寫低 token,自動偵測你嘅 chat_id(要先喺 TG 同 bot 講過嘢)
  bind                # 將「呢個 project 最新活動嗰個 session」綁定為橋接對象
  unbind              # 解除綁定(出站即停)
  send <text>         # 手動發訊息去 TG(測試用;冇 argv 就讀 stdin)
  poll                # 長輪詢 TG(俾 Monitor 用),每條入站訊息印一行
  hook                # 俾 Claude Code Stop / Notification hook 調用(stdin 收 JSON)

設定檔: ~/.claude/tg_bridge.json   {token, chat_id, session_id}
狀態檔: ~/.claude/tg_bridge_state.json   {offset}(poll 進度,分開存避免互相覆寫)
"""
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.claude/tg_bridge.json")
STATE_PATH = os.path.expanduser("~/.claude/tg_bridge_state.json")
TG_MSG_LIMIT = 3900  # TG 上限 4096,留返啲餘量


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


def send_text(cfg, text):
    """發送(超長自動分段)。失敗只印 stderr,唔好搞死 hook。"""
    text = text.strip()
    if not text:
        return
    chunks = [text[i:i + TG_MSG_LIMIT] for i in range(0, len(text), TG_MSG_LIMIT)]
    for chunk in chunks:
        try:
            api(cfg["token"], "sendMessage", chat_id=cfg["chat_id"], text=chunk)
        except Exception as exc:
            print("tg_bridge: sendMessage 失敗: %s" % exc, file=sys.stderr)


# ---------- 子命令 ----------

def cmd_setup(token):
    cfg = load_json(CONFIG_PATH)
    cfg["token"] = token
    try:
        updates = api(token, "getUpdates", timeout=0).get("result", [])
    except Exception as exc:
        print("❌ token 唔啱或者連唔到 TG: %s" % exc)
        sys.exit(1)
    # 搵最後一個私聊 chat 做 chat_id
    chat_id = None
    for u in updates:
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            chat_id = chat["id"]
    if chat_id is None:
        save_json(CONFIG_PATH, cfg)
        print("⚠️ token 已存低,但搵唔到你嘅 chat — 去 TG 同個 bot 講句嘢(咩都得),再跑一次 setup")
        sys.exit(1)
    cfg["chat_id"] = chat_id
    save_json(CONFIG_PATH, cfg)
    # 將 offset 推到最尾,setup 前嘅舊訊息唔好當成指令
    if updates:
        save_json(STATE_PATH, {"offset": updates[-1]["update_id"] + 1})
    send_text(cfg, "✅ Claude ⇆ TG 橋接已連接。喺度回覆就可以繼續 Claude 嘅任務。")
    print("✅ chat_id=%s 已寫入 %s,並已發測試訊息" % (chat_id, CONFIG_PATH))


def project_transcript_dir():
    # Claude Code 將 cwd 嘅 / 換成 - 做 project 目錄名
    return os.path.expanduser("~/.claude/projects/") + os.getcwd().replace("/", "-")


def cmd_bind():
    files = glob.glob(project_transcript_dir() + "/*.jsonl")
    if not files:
        print("❌ 喺 %s 搵唔到 session transcript" % project_transcript_dir())
        sys.exit(1)
    newest = max(files, key=os.path.getmtime)
    sid = os.path.splitext(os.path.basename(newest))[0]
    cfg = load_json(CONFIG_PATH)
    cfg["session_id"] = sid
    save_json(CONFIG_PATH, cfg)
    print("✅ 已綁定 session %s" % sid)


def cmd_unbind():
    cfg = load_json(CONFIG_PATH)
    cfg.pop("session_id", None)
    save_json(CONFIG_PATH, cfg)
    print("✅ 已解除綁定")


def cmd_send(text):
    cfg = load_json(CONFIG_PATH)
    if not cfg.get("token") or not cfg.get("chat_id"):
        print("❌ 未 setup(冇 token / chat_id)")
        sys.exit(1)
    send_text(cfg, text)
    print("✅ 已發送")


def cmd_poll():
    """長輪詢 TG。每條入站訊息印一行(俾 Monitor 變成 session 事件)。"""
    cfg = load_json(CONFIG_PATH)
    if not cfg.get("token") or not cfg.get("chat_id"):
        print("tg_bridge: 未 setup,poll 退出", file=sys.stderr)
        sys.exit(1)
    offset = load_json(STATE_PATH).get("offset", 0)
    while True:
        try:
            updates = api(cfg["token"], "getUpdates", offset=offset, timeout=50).get("result", [])
        except Exception:
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            save_json(STATE_PATH, {"offset": offset})
            msg = u.get("message") or {}
            # 只接受你本人嘅私聊訊息,陌生人搵到個 bot 都指揮唔到
            if (msg.get("chat") or {}).get("id") != cfg["chat_id"]:
                continue
            text = (msg.get("text") or "").strip()
            if text:
                print("📩 TG 回覆: %s" % text, flush=True)


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
    """Stop / Notification hook 入口。任何情況都要靜靜地 exit 0,唔可以阻住 Claude。"""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    cfg = load_json(CONFIG_PATH)
    if not cfg.get("token") or not cfg.get("chat_id") or not cfg.get("session_id"):
        return  # 未 setup / 未 bind → 唔出聲
    if payload.get("session_id") != cfg["session_id"]:
        return  # 唔係綁定嗰個 session
    event = payload.get("hook_event_name", "")
    if event == "Notification":
        msg = payload.get("message") or ""
        if "permission" in msg.lower():  # 只轉發授權請求,閒置提示唔好嘈
            send_text(cfg, "⏸ %s" % msg)
        return
    # Stop:轉發最後一條回覆
    send_text(cfg, last_assistant_text(payload.get("transcript_path")))


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "setup" and len(args) > 1:
        cmd_setup(args[1])
    elif cmd == "bind":
        cmd_bind()
    elif cmd == "unbind":
        cmd_unbind()
    elif cmd == "send":
        cmd_send(" ".join(args[1:]) if len(args) > 1 else sys.stdin.read())
    elif cmd == "poll":
        cmd_poll()
    elif cmd == "hook":
        cmd_hook()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
