---
name: app-store-connect
description: 查 App Store Connect 嘅狀態 — build 處理進度、App Store 審核狀態、TestFlight beta 審核、版本資訊。用官方 ASC REST API(唯讀),唔掂登入密碼。Use this skill WHENEVER the user asks about anything on App Store Connect / the App Store for their iOS app — "個 app 審核到邊", "build 上咗未", "TestFlight 過咗未", "上架狀態", "幾時可以 release", "version 1.2 審核點", "App Store 拒咗未", "check my app review status", "is my build processed", "what's on TestFlight" — even if they don't name App Store Connect or this skill. For READING status only; submitting / releasing / rejecting are user actions, never automate them.
---

# App Store Connect 狀態查詢

## 做乜 / 唔做乜

呢個 skill 用官方 **App Store Connect REST API** 查狀態,**完全唔掂登入帳戶 / 密碼** —— 靠用戶喺 ASC 自己生成嘅 API 金鑰(.p8)簽 JWT,同 tg_bridge 用 bot token 同一道理。

- ✅ **做**:唯讀查詢 —— app 列表、build 處理狀態、App Store 版本同審核狀態、TestFlight beta 審核。
- ❌ **唔做**:任何寫入 / 對外動作 —— 提交審核、release、回應拒審、改 metadata。呢啲係用戶嘅決定,就算 API 做得到都**唔好自動做**;要做先明確問用戶逐個確認。本 tool 亦冇實作呢啲。

## Tool 位置同命令

工具係 `scripts/asc.py`(本 repo 內 = 根目錄 `asc.py`,用 venv python 跑):

```bash
.venv/bin/python3 asc.py <命令> [appId] [--json]
```

| 命令 | 查乜 |
|------|------|
| `apps` | 所有 app + appId(其他命令要用 appId;只得一個 app 時可省略) |
| `builds [appId] [-n N]` | 最近 N 個 build + 處理狀態 |
| `versions [appId]` | App Store 版本 + 審核狀態 |
| `review [appId]` | 只列「進行中」嗰個版本嘅審核狀態 |
| `testflight [appId]` | 最近 build 嘅 TestFlight beta 審核狀態 |

加 `--json` 出原始 JSON(要進一步處理時用),預設出人類可讀摘要。

## 典型用法

- 用戶問「審核到邊」→ 跑 `asc.py review`,將狀態翻譯成人話報俾佢。
- 用戶問「build 上咗未 / 處理好未」→ `asc.py builds`。
- 唔知 appId、又多過一個 app → 先 `asc.py apps`,同用戶確認邊個。
- 報告時用埋下面嘅狀態對照,唔好淨係讀英文 enum。

## 狀態解讀(翻譯成人話)

**App Store 版本狀態(appStoreState)** —— 常見:
- `PREPARE_FOR_SUBMISSION` 準備中(未提交)
- `WAITING_FOR_REVIEW` 排緊隊等審
- `IN_REVIEW` 審緊
- `PENDING_DEVELOPER_RELEASE` 過咗,等你撳 release
- `PENDING_APPLE_RELEASE` 過咗,等 Apple 按排程放
- `READY_FOR_SALE` 已上架
- `REJECTED` / `DEVELOPER_REJECTED` / `METADATA_REJECTED` 被拒(分別:Apple 拒 / 你自己撤 / metadata 問題)
- `INVALID_BINARY` binary 有問題

**Build 處理狀態(processingState)**:`PROCESSING` 處理中 / `VALID` 可用 / `INVALID` 無效 / `FAILED` 失敗。

## 首次設定(未設定先做)

如果跑命令出「❌ 未設定」,即係未有金鑰。指導用戶:

1. ASC → **Users and Access → Integrations → App Store Connect API → Team Keys**
2. **Generate API Key**(role 揀 **App Manager** 已足夠查嘢)→ 下載 `.p8`(**只可下載一次**)→ 放去 `~/.claude/`
3. 抄低該 key 嘅 **Key ID** 同頂部嘅 **Issuer ID**
4. 整 `~/.claude/asc_config.json`:
   ```json
   { "key_id": "XXXXXXXXXX", "issuer_id": "xxxx-...", "p8_path": "~/.claude/AuthKey_XXXXXX.p8" }
   ```
   - **Team Key**(預設,Admin 生成):`issuer_id` 喺 ASC API 頁面**頂部**(從來唔喺 `.p8` 檔內)。
   - **Individual Key**(個人金鑰):**冇** `issuer_id` —— config 留空或唔寫嗰行,tool 會自動改用 `sub:"user"`。
5. 跑 `asc.py apps` 驗證 —— 見到真實 app 列表就成。

金鑰同 config 喺 `~/.claude/`(repo 外),`.gitignore` 已封 `*.p8` / `asc_config.json`,唔會公開。

## 故障排查

| 症狀 | 處理 |
|------|------|
| ❌ 未設定 | 行上面首次設定 |
| API 401 | key_id / issuer_id 唔啱,或 .p8 同 Key ID 對唔上;Team Key 漏咗 issuer_id 亦會 401 |
| API 403 | 金鑰權限唔夠 → 喺 ASC 將 key role 調高 |
| CERTIFICATE_VERIFY_FAILED | Homebrew Python 唔用系統憑證 → 已靠 certifi 解決;缺就 `pip install certifi` |
| 缺 PyJWT/cryptography/certifi | `.venv/bin/python3 -m pip install pyjwt cryptography certifi` |
