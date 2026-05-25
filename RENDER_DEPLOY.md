# Render.com 免费部署指南

## 架构

```
Telegram 服务器 ←── Render 免费服务器 (美国) ──→ 飞书推送
                         │
                    监听验证码消息
                    自动提取 5 位数字
                    推送到你的飞书群
```

Render 免费额度：750 小时/月（刚好够 24/7 运行），服务器在美国，直连 Telegram 无墙。

## 第一步：准备代码

在本地创建 Git 仓库：

```bash
cd /home/cjq/ai/telegram_code_receiver
git init
git add tg_code.py render_start.py requirements.txt
git commit -m "init"
```

推送到 GitHub（需要先建个 repo）：
```bash
git remote add origin https://github.com/你的用户名/tg-code-receiver.git
git push -u origin main
```

> 如果 GitHub 打不开，用镜像推送：
> ```bash
> git remote add origin https://ghproxy.com/https://github.com/你的用户名/tg-code-receiver.git
> ```

## 第二步：Render 部署

1. 用手机 VPN 开浏览器，打开 https://render.com
2. GitHub 注册/登录
3. 点 **New +** → **Background Worker**
4. 连接 GitHub，选刚推的仓库
5. 配置：
   ```
   Name:          tg-code-receiver
   Runtime:       Python 3
   Build Command: pip install -r requirements.txt
   Start Command: python render_start.py
   ```
6. 点 **Create Background Worker**

## 第三步：首次登录 Telegram

1. Render Dashboard → 点进刚创建的服务 → **Shell** 标签
2. 在 Shell 中运行：
   ```bash
   python tg_code.py setup --phone +8618242807155
   ```
3. Telegram 验证码会发到你手机上（手机开着 VPN 能收到）
4. 输入验证码 → 登录成功 → 会话文件保存到 Render 磁盘

## 第四步：启动监听

回到 Render Dashboard → **Manual Deploy** → **Restart service**

之后验证码自动推送飞书。在脚本中加上飞书 webhook：
```bash
# 修改 render_start.py 最后一行的 feishu_url
tg_code.monitor(feishu_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
```

---

**每月费用：0 元**
