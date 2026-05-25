#!/usr/bin/env python3
"""
Telegram 验证码截获器
═══════════════════════
监听 Telegram 已登录设备的验证码消息，自动提取并展示。
支持 SOCKS5/HTTP 代理（中国区必备）。

用法:
  python tg_code.py setup --phone +8613800138000 --proxy socks5://192.168.1.100:10808
  python tg_code.py                          # 前台监听
  python tg_code.py --once                   # 单次检查
  python tg_code.py --feishu WEBHOOK_URL     # 同时推飞书
"""

import re
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
SESSION_FILE = PROJECT_DIR / "tg_session"
CONFIG_FILE = PROJECT_DIR / "config.json"
CODE_LOG_FILE = PROJECT_DIR / "codes.json"

BUILTIN_API_ID = 2040
BUILTIN_API_HASH = "b18441a1ff607e10a989891a5462e627"

logging.basicConfig(level=logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)

TELEGRAM_SERVICE_ID = 777000

CODE_PATTERNS = [
    re.compile(r"(?:login|confirmation|verification|auth(?:entication)?)\s*code\s*(?:is\s*)?(\d{4,6})", re.I),
    re.compile(r"(?:telegram|tg)\s*code\s*[:：\s]*(\d{4,6})", re.I),
    re.compile(r"(?:登录|验证|确认|安全)码\s*[:：\s]*(\d{4,6})"),
    re.compile(r"(?:your\s+)?code\s*[:：\s]*(\d{4,6})", re.I),
    re.compile(r"(?<![0-9])(\d{5})(?![0-9])"),
]

# ═══════════════════════════════════════
# 代理工具
# ═══════════════════════════════════════

def parse_proxy(proxy_str: str):
    """
    解析代理字符串，支持格式:
      socks5://127.0.0.1:10808
      socks5://user:pass@127.0.0.1:10808
      http://127.0.0.1:7890
    """
    import urllib.parse
    from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

    if not proxy_str:
        return None

    # MTProto 代理: mtproto://secret@host:port
    if proxy_str.startswith("mtproto://"):
        parsed = urllib.parse.urlparse(proxy_str)
        secret = parsed.username or ""
        if not secret:
            print("❌ MTProto 代理需要 secret，格式: mtproto://secret@host:port")
            sys.exit(1)
        return ("mtproto", parsed.hostname, int(parsed.port or 443), secret)

    # SOCKS5 / HTTP
    if "://" not in proxy_str:
        proxy_str = "socks5://" + proxy_str

    parsed = urllib.parse.urlparse(proxy_str)
    proto = parsed.scheme or "socks5"
    host = parsed.hostname
    port = int(parsed.port or (1080 if proto == "socks5" else 7890))
    username = parsed.username or None
    password = parsed.password or None

    return (proto, host, port, username, password)


def make_proxy_config(proxy_str: str):
    """
    从代理字符串创建 telethon 可用的代理配置。
    返回 (proxy_type, kwargs) 或 None。
    """
    parsed = parse_proxy(proxy_str)
    if not parsed:
        return None

    from telethon import ProxyType

    kind, *rest = parsed

    if kind == "mtproto":
        _, host, port, secret = rest
        from python_socks import ProxyType as PT
        # MTProto 代理在 telethon 中通过 TelegramClient 的 connection 参数设置
        return ("mtproto", {"host": host, "port": port, "secret": secret})

    _, host, port, username, password = rest

    if kind in ("socks5", "socks"):
        proxy_type = "socks5"
    elif kind in ("http", "https"):
        proxy_type = "http"
    else:
        print(f"❌ 不支持的代理类型: {kind}，支持 socks5/http/mtproto")
        sys.exit(1)

    return (proxy_type, {"host": host, "port": port, "username": username, "password": password})


# ═══════════════════════════════════════

def extract_code(text: str) -> str | None:
    for pat in CODE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def save_code(code: str, source: str, raw_text: str):
    CODE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = []
    if CODE_LOG_FILE.exists():
        try:
            records = json.loads(CODE_LOG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    records.append({
        "code": code,
        "source": source,
        "text": raw_text[:200],
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    records = records[-50:]
    CODE_LOG_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def send_to_feishu(webhook_url: str, code: str, text: str):
    try:
        import urllib.request
        payload = json.dumps({
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"Telegram 验证码: {code}"},
                    "template": "blue",
                },
                "elements": [{
                    "tag": "markdown",
                    "content": f"**验证码:** `{code}`\n**消息:** {text[:200]}\n---\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                }],
            },
        }).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def get_proxy_arg():
    """从命令行参数中提取 --proxy"""
    for i, arg in enumerate(sys.argv):
        if arg == "--proxy" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def get_phone_arg():
    for i, arg in enumerate(sys.argv):
        if arg == "--phone" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def build_client(config: dict):
    """构造带代理的 TelegramClient"""
    from telethon import TelegramClient

    proxy_cfg = config.get("proxy")
    if proxy_cfg:
        proxy_type, kwargs = proxy_cfg
        print(f"🔗 使用代理: {proxy_type}://{kwargs.get('host')}:{kwargs.get('port')}")

        if proxy_type == "mtproto":
            # MTProto 代理
            from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
            client = TelegramClient(
                str(SESSION_FILE),
                config["api_id"],
                config["api_hash"],
                connection=ConnectionTcpMTProxyRandomizedIntermediate,
                proxy=(kwargs["host"], kwargs["port"], kwargs["secret"]),
            )
            return client

        if proxy_type == "socks5":
            import socks
            proxy = (socks.SOCKS5, kwargs["host"], kwargs["port"],
                     bool(kwargs.get("username")),
                     kwargs.get("username"), kwargs.get("password"))
        elif proxy_type == "http":
            proxy = (socks.HTTP, kwargs["host"], kwargs["port"],
                     bool(kwargs.get("username")),
                     kwargs.get("username"), kwargs.get("password"))
        else:
            print(f"❌ 不支持的代理类型: {proxy_type}")
            sys.exit(1)

        client = TelegramClient(str(SESSION_FILE), config["api_id"], config["api_hash"], proxy=proxy)
        return client
    else:
        return TelegramClient(str(SESSION_FILE), config["api_id"], config["api_hash"])


def setup():
    proxy_str = get_proxy_arg()
    phone_str = get_phone_arg()

    print("=" * 55)
    print("  Telegram 验证码截获器 — 首次配置")
    print("=" * 55)
    print(f"  API: 内置 (api_id={BUILTIN_API_ID})")

    if proxy_str:
        proxy_cfg = make_proxy_config(proxy_str)
        print(f"  代理: {proxy_str}")
    else:
        proxy_cfg = None
        print("  代理: 直连（如被墙请加 --proxy socks5://IP:端口）")

    print()

    if phone_str:
        phone = phone_str
        print(f"  手机号: {phone}")
    else:
        phone = input("  输入 Telegram 手机号 (如 +8613800138000): ").strip()

    if not phone:
        print("❌ 手机号不能为空")
        sys.exit(1)

    config = {
        "api_id": BUILTIN_API_ID,
        "api_hash": BUILTIN_API_HASH,
        "phone": phone,
        "proxy": proxy_cfg,
    }
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({
        "api_id": config["api_id"],
        "api_hash": config["api_hash"],
        "phone": config["phone"],
        "proxy_str": proxy_str,
    }, indent=2))

    print()
    print("  正在请求验证码...")
    print("  Telegram 会将验证码发送到你的已登录设备")
    print()

    _do_login(config, is_setup=True)


def _do_login(config: dict, is_setup: bool = False):
    client = build_client(config)

    async def login():
        await client.start()
        me = await client.get_me()
        print(f"\n✅ 登录成功! {me.first_name} (@{me.username or 'N/A'})")
        print(f"   会话: {SESSION_FILE}")
        if is_setup:
            print()
            print("=" * 55)
            print("  配置完成! 运行 python tg_code.py 开始监听")
            print("=" * 55)

    with client:
        client.loop.run_until_complete(login())


def monitor(feishu_url: str = "", once: bool = False):
    if not SESSION_FILE.exists():
        print("❌ 未找到会话，请先运行: python tg_code.py setup --phone +8613xxxxx --proxy socks5://IP:端口")
        sys.exit(1)

    raw_config = json.loads(CONFIG_FILE.read_text())
    proxy_str = raw_config.get("proxy_str", "")

    # 重建 proxy 配置
    if proxy_str:
        proxy_cfg = make_proxy_config(proxy_str)
    else:
        proxy_cfg = None

    config = {
        "api_id": raw_config["api_id"],
        "api_hash": raw_config["api_hash"],
        "proxy": proxy_cfg,
    }

    from telethon import TelegramClient, events

    client = build_client(config)
    latest_code_found = {}

    @client.on(events.NewMessage)
    async def handler(event):
        message = event.message
        sender = await message.get_sender()
        sender_id = getattr(sender, "id", None)
        sender_name = (getattr(sender, "first_name", "") or "").lower()

        is_official = (
            sender_id == TELEGRAM_SERVICE_ID
            or sender_name == "telegram"
            or (hasattr(sender, "username") and sender.username == "Telegram")
        )

        text = message.text or ""
        if not is_official:
            if not any(kw in text.lower() for kw in
                       ["login code", "verification code", "telegram code", "your code",
                        "登录验证码", "验证码"]):
                return

        code = extract_code(text)
        if code:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n{'='*55}")
            print(f"  🔐 验证码: {code}")
            print(f"  ⏰ {now}")
            print(f"  💬 {text[:100]}")
            print(f"{'='*55}")

            save_code(code, getattr(sender, "first_name", "Telegram"), text)
            latest_code_found["code"] = code

            if feishu_url:
                send_to_feishu(feishu_url, code, text)

            if once:
                await client.disconnect()

    async def run():
        await client.start()
        me = await client.get_me()
        print(f"✅ {me.first_name} | 监听中...")
        print()

        if once:
            await asyncio.sleep(10)
            c = latest_code_found.get("code")
            if c:
                print(f"✅ {c}")
            else:
                print("⏳ 10秒内未收到验证码")
            await client.disconnect()
        else:
            await client.run_until_disconnected()

    import asyncio
    with client:
        client.loop.run_until_complete(run())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram 验证码截获器")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="首次配置")
    p_run = sub.add_parser("run", help="启动监听")
    p_run.add_argument("--once", action="store_true")
    p_run.add_argument("--feishu", type=str, default="")

    # 顶层参数（放在子命令前面，如 --phone --proxy）
    parser.add_argument("--phone", type=str, default="")
    parser.add_argument("--proxy", type=str, default="")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--feishu", type=str, default="")

    args = parser.parse_args()

    feishu = getattr(args, "feishu", "") or ""
    once = getattr(args, "once", False)

    if args.command == "setup":
        setup()
    else:
        monitor(feishu_url=feishu, once=once)
