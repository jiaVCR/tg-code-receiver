#!/usr/bin/env python3
"""GitHub Actions - Telegram code monitor with Feishu REST API push."""
import re, json, base64, os, sys
from datetime import datetime
from pathlib import Path

CODE_PATTERNS = [
    re.compile(r"(?:login|confirmation|verification|auth(?:entication)?)\s*code\s*(?:is\s*)?(\d{4,6})", re.I),
    re.compile(r"(?:telegram|tg)\s*code\s*[:：\s]*(\d{4,6})", re.I),
    re.compile(r"(?:登录|验证|确认|安全)码\s*[:：\s]*(\d{4,6})"),
    re.compile(r"(?:your\s+)?code\s*[:：\s]*(\d{4,6})", re.I),
]
TELEGRAM_SERVICE_ID = 777000
SESSION_FILE = Path("tg_session.session")

def extract_code(text):
    for pat in CODE_PATTERNS:
        m = pat.search(text)
        if m: return m.group(1)
    return None

def feishu_send(code, text):
    app_id = os.environ.get("FEISHU_APP_ID","")
    app_secret = os.environ.get("FEISHU_APP_SECRET","")
    chat_id = os.environ.get("FEISHU_CHAT_ID","")
    if not all([app_id, app_secret, chat_id]):
        print("[WARN] Feishu creds missing, skip push")
        return
    try:
        import urllib.request as ur
        tb = json.dumps({"app_id":app_id,"app_secret":app_secret}).encode()
        req = ur.Request("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=tb, headers={"Content-Type":"application/json"})
        tk = json.loads(ur.urlopen(req,timeout=10).read()).get("tenant_access_token","")
        if not tk:
            print("[ERR] Feishu token failed")
            return
        cnt = {"zh_cn":{"title":f"Telegram验证码: {code}","content":[[
            {"tag":"text","text":f"验证码: {code}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{text[:150]}"}
        ]]}}
        mb = json.dumps({"receive_id":chat_id,"msg_type":"post","content":json.dumps(cnt)}).encode()
        req2 = ur.Request(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            data=mb, headers={"Authorization":f"Bearer {tk}","Content-Type":"application/json"})
        r = json.loads(ur.urlopen(req2,timeout=10).read())
        print(f"[FEISHU] code={r.get('code')} msg={r.get('msg','')}")
    except Exception as e:
        print(f"[FEISHU] Error: {e}")

def main():
    from telethon import TelegramClient, events
    api_id, api_hash = 2040, "b18441a1ff607e10a989891a5462e627"
    session_b64 = os.environ.get("TG_SESSION","")
    if session_b64:
        print("[INFO] Loading TG_SESSION...")
        SESSION_FILE.write_bytes(base64.b64decode(session_b64))
    else:
        print("[WARN] TG_SESSION empty. Run setup via Codespaces first.")
        sys.exit(0)
    client = TelegramClient(str(SESSION_FILE), api_id, api_hash)
    codes = []
    @client.on(events.NewMessage)
    async def h(event):
        m = event.message; s = await m.get_sender()
        sid = getattr(s,"id",None); sn = (getattr(s,"first_name","") or "").lower()
        official = sid==TELEGRAM_SERVICE_ID or sn=="telegram"
        t = m.text or ""
        if not official and not any(k in t.lower() for k in
            ["login code","verification code","telegram code","your code","验证码"]):
            return
        c = extract_code(t)
        if c:
            print(f"[CODE] {c} | {t[:80]}")
            codes.append(c); feishu_send(c, t)
    async def run():
        await client.start()
        print(f"[INFO] {getattr(await client.get_me(),'first_name','?')}")
        await asyncio.sleep(10)
        print(f"[OK] {'codes:'+str(codes) if codes else 'no new codes'}")
        await client.disconnect()
        if SESSION_FILE.exists():
            nb = base64.b64encode(SESSION_FILE.read_bytes()).decode()
            print(f"[SESSION] {len(nb)} chars")
            o = os.environ.get("GITHUB_OUTPUT","/dev/null")
            if o != "/dev/null":
                with open(o,"a") as f: f.write(f"session={nb}\ncodes={'|'.join(codes)}\n")
    import asyncio
    with client: client.loop.run_until_complete(run())

if __name__ == "__main__":
    main()
