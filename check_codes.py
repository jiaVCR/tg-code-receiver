#!/usr/bin/env python3
"""
GitHub Actions 模式 — 定时检查验证码
运行在 GitHub Actions 美国服务器，能直连 Telegram。
每次运行从仓库 secret 加载会话，检查新消息后退回。
"""
import re
import json
import base64
import os
import sys
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
SESSION_SECRET_NAME = "TG_SESSION"  # GitHub Actions secret 名
FEISHU_SECRET_NAME = "FEISHU_WEBHOOK"  # 飞书 webhook（可选）


def extract_code(text: str) -> str | None:
    for pat in CODE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def main():
    from telethon import TelegramClient, events

    api_id = 2040
    api_hash = "b18441a1ff607e10a989891a5462e627"

    # 从环境变量加载会话（GitHub Secret，base64 编码）
    session_b64 = os.environ.get(SESSION_SECRET_NAME, "")
    if session_b64:
        print("[INFO] 从 TG_SESSION secret 加载会话...")
        SESSION_FILE.write_bytes(base64.b64decode(session_b64))
    else:
        print("[WARN] TG_SESSION secret 为空，需要先完成首次登录")
        print("       在本地运行: python tg_code.py setup --phone +86XXXXXXXXX")
        print("       然后把 tg_session.session base64 编码后存入 GitHub Secret")
        sys.exit(0)

    feishu_url = os.environ.get(FEISHU_SECRET_NAME, "")

    client = TelegramClient(str(SESSION_FILE), api_id, api_hash)
    codes_found = []

    @client.on(events.NewMessage)
    async def handler(event):
        message = event.message
        sender = await message.get_sender()
        sender_id = getattr(sender, "id", None)
        sender_name = (getattr(sender, "first_name", "") or "").lower()

        is_official = (
            sender_id == TELEGRAM_SERVICE_ID
            or sender_name == "telegram"
        )
        text = message.text or ""
        if not is_official and not any(
            kw in text.lower() for kw in
            ["login code", "verification code", "telegram code", "your code", "验证码"]
        ):
            return

        code = extract_code(text)
        if code:
            print(f"[CODE] {code} | {text[:80]}")
            codes_found.append(code)

            if feishu_url:
                try:
                    import urllib.request
                    payload = json.dumps({
                        "msg_type": "text",
                        "content": {"text": f"🔐 Telegram 验证码: {code}"},
                    }).encode()
                    req = urllib.request.Request(feishu_url, data=payload,
                        headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=5)
                except Exception:
                    pass

    async def run():
        await client.start()
        me = await client.get_me()
        print(f"[INFO] 已登录: {me.first_name}")

        # 等待几秒接收新消息
        await asyncio.sleep(8)

        if codes_found:
            print(f"[OK] 找到 {len(codes_found)} 个验证码")
        else:
            print("[OK] 无新验证码")

        # 保存更新后的会话（base64 输出，手动存入 secret）
        await client.disconnect()
        if SESSION_FILE.exists():
            new_b64 = base64.b64encode(SESSION_FILE.read_bytes()).decode()
            print(f"[SESSION] 会话已更新 (长度: {len(new_b64)})")
            # 输出到 GitHub Actions output
            with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
                f.write(f"session={new_b64}\n")
                f.write(f"codes={'|'.join(codes_found)}\n")

    import asyncio
    with client:
        client.loop.run_until_complete(run())


if __name__ == "__main__":
    main()
