#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""App Store Connect 操作 tool(唯讀為主) — 俾 Claude 調用,查 build / 審核 / TestFlight / 版本。

用官方 App Store Connect REST API,**完全唔掂你嘅登入密碼**:
你喺 ASC 自己生成一條 API 金鑰(.p8),呢個 tool 淨係攞嗰條金鑰簽 JWT request,
同登入帳戶兩回事(就好似 GitHub token / TG bot token 咁)。

子命令:
  apps                    # 列出你所有 app(攞 appId 用)
  builds   [appId] [-n N] # 最近 build + 處理狀態(PROCESSING/VALID/INVALID...)
  versions [appId]        # App Store 版本 + 審核狀態(WAITING_FOR_REVIEW/IN_REVIEW/...)
  review   [appId]        # 聚焦「進行中」嗰個版本嘅審核狀態
  testflight [appId]      # 最近 build 嘅 TestFlight beta 審核狀態
只得一個 app 時 appId 可省略。加 --json 出原始 JSON。

設定: ~/.claude/asc_config.json
  { "key_id": "XXXXXXXXXX",
    "issuer_id": "xxxxxxxx-xxxx-...",
    "p8_path": "/path/to/AuthKey_XXXXXXXXXX.p8" }

點攞金鑰(一次過,約兩分鐘):
  ASC → Users and Access → Integrations → App Store Connect API → Team Keys
  → Generate API Key(role 揀 App Manager 已夠)→ 下載 .p8(只可下載一次!)
  → 抄低 Key ID 同上面嘅 Issuer ID,連 .p8 路徑填入上面個 config。
"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt  # PyJWT

CONFIG_PATH = os.path.expanduser("~/.claude/asc_config.json")
API_BASE = "https://api.appstoreconnect.apple.com"

# Homebrew Python 唔用系統憑證庫,要明確指向 certifi 個 CA bundle,
# 否則 urlopen 會 CERTIFICATE_VERIFY_FAILED。
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


def die(msg, code=1):
    print(msg)
    sys.exit(code)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        die("❌ 未設定 — 整 %s,內容:\n"
            '  { "key_id": "...", "issuer_id": "...", "p8_path": "/path/AuthKey_XXX.p8" }\n'
            "金鑰喺 ASC → Users and Access → Integrations → App Store Connect API 生成。"
            % CONFIG_PATH)
    cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    # issuer_id 只有 Team Key 先有;Individual Key 唔需要
    for k in ("key_id", "p8_path"):
        if not cfg.get(k):
            die("❌ config 缺少 %r(喺 %s)" % (k, CONFIG_PATH))
    if not os.path.exists(os.path.expanduser(cfg["p8_path"])):
        die("❌ 搵唔到 .p8 金鑰檔: %s" % cfg["p8_path"])
    return cfg


def make_token(cfg):
    """簽一個 20 分鐘有效嘅 ES256 JWT(ASC 上限 20 分鐘)。

    Team Key:有 issuer_id → 用 iss claim。
    Individual Key:冇 issuer_id → 用 sub="user"(Apple 規定)。
    """
    private_key = open(os.path.expanduser(cfg["p8_path"])).read()
    now = int(time.time())
    issuer = cfg.get("issuer_id", "").strip()
    placeholder = (not issuer) or issuer.startswith("貼你")
    claims = {"iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}
    if placeholder:
        claims["sub"] = "user"          # Individual Key
    else:
        claims["iss"] = issuer          # Team Key
    return jwt.encode(claims, private_key, algorithm="ES256",
                      headers={"kid": cfg["key_id"], "typ": "JWT"})


def api_get(token, path, **params):
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        hint = {401: "(金鑰/issuer 唔啱,或 JWT 過期)",
                403: "(金鑰權限唔夠 — 喺 ASC 將 key role 調高)",
                404: "(搵唔到資源,核對 appId)"}.get(e.code, "")
        try:
            detail = json.loads(body)["errors"][0].get("detail", body)
        except Exception:
            detail = body[:300]
        die("❌ API %d %s: %s" % (e.code, hint, detail))


def get_apps(token):
    return api_get(token, "/v1/apps", limit=200,
                   **{"fields[apps]": "name,bundleId,sku"})["data"]


def resolve_app_id(token, args):
    """攞命令列 appId;省略且只得一個 app 就自動用佢。"""
    explicit = next((a for a in args if not a.startswith("-")), None)
    if explicit:
        return explicit
    apps = get_apps(token)
    if len(apps) == 1:
        return apps[0]["id"]
    if not apps:
        die("❌ 帳戶冇任何 app")
    listing = "\n".join("  %s  %s (%s)" % (a["id"], a["attributes"]["name"],
                                           a["attributes"]["bundleId"]) for a in apps)
    die("有 %d 個 app,請指明 appId:\n%s" % (len(apps), listing))


def out(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return True
    return False


# ---------- 子命令 ----------

def cmd_apps(token, args, as_json):
    apps = get_apps(token)
    if out(apps, as_json):
        return
    if not apps:
        print("(冇 app)")
        return
    print("App Store Connect — %d 個 app:" % len(apps))
    for a in apps:
        at = a["attributes"]
        print("  • %s  (%s)\n    appId=%s  sku=%s"
              % (at["name"], at["bundleId"], a["id"], at.get("sku", "-")))


def cmd_builds(token, args, as_json):
    app_id = resolve_app_id(token, args)
    n = 10
    if "-n" in args:
        i = args.index("-n")
        if i + 1 < len(args):
            n = int(args[i + 1])
    data = api_get(token, "/v1/builds", limit=n, sort="-uploadedDate",
                   **{"filter[app]": app_id,
                      "fields[builds]": "version,processingState,uploadedDate,expired"})["data"]
    if out(data, as_json):
        return
    if not data:
        print("(冇 build)")
        return
    print("最近 %d 個 build:" % len(data))
    for b in data:
        at = b["attributes"]
        flag = " ⛔expired" if at.get("expired") else ""
        print("  build %s — %s%s  (%s)"
              % (at.get("version", "?"), at.get("processingState", "?"),
                 flag, at.get("uploadedDate", "")[:19]))


def _versions(token, app_id, n=10):
    return api_get(token, "/v1/apps/%s/appStoreVersions" % app_id, limit=n,
                   **{"fields[appStoreVersions]":
                      "versionString,appStoreState,platform,createdDate"})["data"]


def cmd_versions(token, args, as_json):
    app_id = resolve_app_id(token, args)
    data = _versions(token, app_id)
    if out(data, as_json):
        return
    if not data:
        print("(冇版本)")
        return
    print("App Store 版本:")
    for v in data:
        at = v["attributes"]
        print("  v%s [%s] — %s"
              % (at.get("versionString", "?"), at.get("platform", "?"),
                 at.get("appStoreState", "?")))


# 審核中嘅狀態(非「已上架/可開發」嘅穩定態)
IN_FLIGHT = {"PREPARE_FOR_SUBMISSION", "WAITING_FOR_REVIEW", "IN_REVIEW",
             "PENDING_DEVELOPER_RELEASE", "PENDING_APPLE_RELEASE",
             "PROCESSING_FOR_APP_STORE", "METADATA_REJECTED", "REJECTED",
             "DEVELOPER_REJECTED", "INVALID_BINARY"}


def cmd_review(token, args, as_json):
    app_id = resolve_app_id(token, args)
    data = _versions(token, app_id)
    flying = [v for v in data if v["attributes"].get("appStoreState") in IN_FLIGHT]
    if out(flying or data[:1], as_json):
        return
    if not flying:
        latest = data[0]["attributes"] if data else {}
        print("✅ 冇進行中嘅審核。最新版本 v%s — %s"
              % (latest.get("versionString", "?"), latest.get("appStoreState", "?")))
        return
    print("🔎 進行中嘅審核:")
    for v in flying:
        at = v["attributes"]
        print("  v%s — %s" % (at.get("versionString", "?"), at.get("appStoreState", "?")))


def cmd_testflight(token, args, as_json):
    app_id = resolve_app_id(token, args)
    data = api_get(token, "/v1/builds", limit=10, sort="-uploadedDate",
                   **{"filter[app]": app_id,
                      "fields[builds]": "version,processingState,uploadedDate",
                      "include": "betaAppReviewSubmission",
                      "fields[betaAppReviewSubmissions]": "betaReviewState"})
    if out(data, as_json):
        return
    subs = {x["id"]: x["attributes"].get("betaReviewState")
            for x in data.get("included", []) if x["type"] == "betaAppReviewSubmissions"}
    builds = data["data"]
    if not builds:
        print("(冇 build)")
        return
    print("TestFlight — 最近 build 嘅 beta 審核狀態:")
    for b in builds:
        at = b["attributes"]
        rel = (b.get("relationships", {}).get("betaAppReviewSubmission", {})
               .get("data") or {})
        state = subs.get(rel.get("id"), "—(未提交 beta 審核)")
        print("  build %s — 處理:%s  beta審核:%s"
              % (at.get("version", "?"), at.get("processingState", "?"), state))


COMMANDS = {
    "apps": cmd_apps, "builds": cmd_builds, "versions": cmd_versions,
    "review": cmd_review, "testflight": cmd_testflight,
}


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    cmd = args[0] if args else ""
    if cmd not in COMMANDS:
        die(__doc__, 0 if cmd in ("-h", "--help", "") else 1)
    token = make_token(load_config())
    COMMANDS[cmd](token, args[1:], as_json)


if __name__ == "__main__":
    main()
