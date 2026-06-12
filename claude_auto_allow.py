#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自動點擊 Claude 視窗嘅「Always allow」按鈕,
以及 macOS 系統權限彈窗(「"claude" wants access to control "Google Chrome"」)嘅「OK」。

用法:
  python3 claude_auto_allow.py           # 每 10 秒掃描一次,搵到就點擊
  python3 claude_auto_allow.py --once    # 只掃描一次(調試用)
  python3 claude_auto_allow.py --dump    # 印出成棵 UI tree(搵按鈕真實名稱用)

前提:運行佢嘅 app(PyCharm / Terminal)要喺
  系統設定 → 私隱與保安 → 輔助使用 入面剔選
"""
import sys
import time

# pyobjc 嘅符號係運行時動態生成,PyCharm 靜態分析睇唔到 — 下面兩行係叫佢收聲
# noinspection PyUnresolvedReferences
from AppKit import NSWorkspace
# noinspection PyUnresolvedReferences
from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementCopyActionNames,
    AXUIElementSetAttributeValue,
    AXUIElementPerformAction,
)

TARGET_APP = "Claude"
# 比對 AXTitle + AXDescription;英文唔分大小寫,中文直接子串比對
TARGET_TEXTS = ["always allow", "allow always", "一律允許", "始終允許", "总是允许","Always"]

# --- macOS 系統 TCC 權限彈窗(「"claude" wants access to control "Google Chrome"」)---
# 呢類彈窗唔屬於 Claude app,係由系統進程顯示,所以要另外掃
SYSTEM_DIALOG_APPS = {"UserNotificationCenter", "CoreServicesUIAgent"}
PERMISSION_SOURCE = "claude"  # 只有 claude 發起嘅權限請求先自動允許
PERMISSION_TEXTS = ["wants access to control", "想要控制", "想控制"]
OK_LABELS = {"ok", "好", "允許", "允许", "allow"}  # 整個 label 完全等於先算(唔會撞 Don't Allow)
# 只點擊互動角色,避免誤點聊天內容入面嘅普通文字
CLICK_ROLES = {"AXButton", "AXRadioButton", "AXCheckBox", "AXMenuItem",
               "AXLink", "AXPopUpButton", "AXMenuButton"}
SCAN_INTERVAL = 10
MAX_DEPTH = 60

_seen_labels = set()  # 已見過嘅互動元素標籤(只印新出現嘅,方便睇到彈窗按鈕真名)


def ax_get(elem, attr):
    err, value = AXUIElementCopyAttributeValue(elem, attr, None)
    return value if err == 0 else None


def ax_actions(elem):
    err, names = AXUIElementCopyActionNames(elem, None)
    return list(names) if err == 0 and names else []


def find_claude_pids():
    return [
        app.processIdentifier()
        for app in NSWorkspace.sharedWorkspace().runningApplications()
        if app.localizedName() == TARGET_APP
    ]


def app_element(pid):
    app = AXUIElementCreateApplication(pid)
    # Electron app 必須設呢個,先會暴露 web 內容嘅 accessibility tree
    AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
    return app


def walk(elem, depth=0):
    """遞歸走 UI tree,yield (elem, role, title, desc, depth)。"""
    if depth > MAX_DEPTH:
        return
    role = ax_get(elem, "AXRole") or ""
    title = ax_get(elem, "AXTitle") or ""
    desc = ax_get(elem, "AXDescription") or ""
    yield elem, role, title, desc, depth
    for child in ax_get(elem, "AXChildren") or []:
        for item in walk(child, depth + 1):
            yield item


def label_matches(label):
    low = label.lower()
    return any(t in low for t in TARGET_TEXTS)


def scan_permission_dialogs(verbose=False):
    """掃系統權限彈窗:「"claude" wants access to control ...」→ 撳 OK。"""
    clicked = False
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.localizedName() not in SYSTEM_DIALOG_APPS:
            continue
        app_elem = AXUIElementCreateApplication(app.processIdentifier())
        for win in ax_get(app_elem, "AXWindows") or []:
            texts, buttons = [], []
            for elem, role, title, desc, _ in walk(win):
                if role == "AXStaticText":
                    texts.append(str(ax_get(elem, "AXValue") or title or desc))
                elif role == "AXButton":
                    buttons.append((elem, (title or desc).strip()))
            blob = " ".join(t for t in texts if t).lower()
            matched = (PERMISSION_SOURCE in blob
                       and any(t.lower() in blob for t in PERMISSION_TEXTS))
            if verbose and blob and blob not in _seen_labels:
                _seen_labels.add(blob)
                print("  🪟 系統彈窗(%s): %r" % (app.localizedName(), blob[:90]))
            if not matched:
                continue
            for elem, label in buttons:
                if label.lower() not in OK_LABELS:
                    continue
                err = AXUIElementPerformAction(elem, "AXPress")
                if err == 0:
                    print("✅ 已喺權限彈窗撳 %r: %r" % (label, blob[:80]))
                    clicked = True
                else:
                    print("⚠️ 權限彈窗撳 %r 失敗 (AXError %d)" % (label, err))
                break
    return clicked


def scan_and_click(verbose=False):
    dialog_clicked = scan_permission_dialogs(verbose=verbose)
    pids = find_claude_pids()
    if not pids:
        print("Claude 未運行")
        return dialog_clicked
    clicked = False
    for pid in pids:
        count = 0
        for elem, role, title, desc, _ in walk(app_element(pid)):
            count += 1
            if role not in CLICK_ROLES:
                continue
            label = (title + " " + desc).strip()
            if verbose and label and label not in _seen_labels:
                _seen_labels.add(label)
                print("  🆕 %s: %r" % (role, label[:90]))
            if not clicked and label and label_matches(label):
                actions = ax_actions(elem)
                if "AXPress" in actions:
                    err = AXUIElementPerformAction(elem, "AXPress")
                    if err == 0:
                        print("✅ 已點擊 %s: %r" % (role, label))
                        clicked = True
                    else:
                        print("⚠️ 搵到目標但點擊失敗 (AXError %d): %r" % (err, label))
                else:
                    print("⚠️ 目標唔支援 AXPress (actions=%s): %r" % (actions, label))
        if verbose:
            print("pid %d: 掃描咗 %d 個元素%s" % (pid, count, ",已點擊 ✅" if clicked else ""))
    return clicked or dialog_clicked


def dump():
    """印出 UI tree,用嚟搵按鈕嘅真實名稱。"""
    pids = find_claude_pids()
    if not pids:
        print("Claude 未運行")
        return
    for pid in pids:
        print("=== Claude pid %d ===" % pid)
        app = app_element(pid)
        time.sleep(0.5)  # 俾時間 Electron 起 accessibility tree
        for elem, role, title, desc, depth in walk(app):
            label = " ".join(x for x in (title, desc) if x)
            if label or role in CLICK_ROLES or role == "AXWindow":
                extra = ""
                if role in CLICK_ROLES:
                    extra = "  actions=%s" % ax_actions(elem)
                print("%s%-14s %r%s" % ("  " * depth, role, label[:80], extra))


def main():
    if not AXIsProcessTrusted():
        print("❌ 冇輔助使用權限!")
        print("   去 系統設定 → 私隱與保安 → 輔助使用,")
        print("   加入並剔選你運行呢個 script 嘅 app(PyCharm / Terminal)。")
        print("   剔咗之後要完全退出嗰個 app(Cmd+Q)再重開先生效。")
        sys.exit(1)

    if "--dump" in sys.argv:
        dump()
        return
    if "--once" in sys.argv:
        scan_and_click(verbose=True)
        return

    print("開始監控 Claude(每 %d 秒掃一次,Ctrl+C 停止)..." % SCAN_INTERVAL)
    print("(🆕 = 新出現嘅互動元素 — 彈窗一出就會見到佢啲按鈕真名)")
    while True:
        try:
            scan_and_click(verbose=True)
        except Exception as exc:
            print("發生錯誤: %s" % exc)
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
