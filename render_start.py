#!/usr/bin/env python3
"""
Render 部署入口 — 自动判断登录/监听
"""
import sys
from pathlib import Path

SESSION_FILE = Path("/opt/render/project/src/tg_session")

if not SESSION_FILE.exists():
    print("=" * 50)
    print("  ⚠️  未找到 Telegram 会话文件")
    print("=" * 50)
    print()
    print("  请通过 Render Shell 运行首次登录:")
    print("    python tg_code.py setup --phone +86XXXXXXXXX")
    print()
    print("  登录完成后重启服务即开始监听。")
    print("=" * 50)
else:
    # 导入 monitor（直接调用，不走 argparse）
    import tg_code
    tg_code.monitor(feishu_url="")
