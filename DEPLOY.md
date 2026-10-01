# 服务器部署步骤（Ubuntu 22.04）

> 从「创建文件夹」开始，一步一步完成部署。所有命令均以 Ubuntu 22.04 + 普通用户（非 root）为准。
> 下文命令中的 `你的用户名`、`服务器IP` 请替换成你的真实值。

---

## 第 1 步：把项目文件上传到服务器

项目文件清单（本地 `B:\WorkBuddy\daily-checkin\`）：

```
checkin.py      主脚本（已填好站点信息）
.env            环境变量（已填 SENDKEY，账号密码待你填）
.env.example    环境变量示例（可选，可不传）
README.md       使用说明（可选）
```

**方式 A：图形工具（推荐新手）**

用 WinSCP / FileZilla，把整个 `daily-checkin` 文件夹上传到服务器 `/home/你的用户名/` 下，上传后得到 `/home/你的用户名/daily-checkin/`。

**方式 B：scp 命令（在本地 Git Bash 里执行）**

```bash
scp -r "B:/WorkBuddy/daily-checkin" 你的用户名@服务器IP:/home/你的用户名/checkin
```

> 执行后服务器上会得到 `/home/你的用户名/checkin/` 目录，里面就是项目文件。

---

## 第 2 步：登录服务器，创建并进入项目文件夹

```bash
ssh 你的用户名@服务器IP
```

如果上面 scp 已经直接建好了 `/home/你的用户名/checkin`，跳过 mkdir，直接进入：

```bash
cd ~/checkin && ls -la
```

如果还没建文件夹，手动创建：

```bash
mkdir -p ~/checkin
cd ~/checkin
```

---

## 第 3 步：安装依赖（Python + Playwright + Chromium）

```bash
# 更新软件源并安装 Python 与 pip
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# (推荐) 创建独立虚拟环境，避免污染系统
python3 -m venv venv
source venv/bin/activate

# 安装 Python 依赖 (国内服务器建议加清华镜像加速)
pip3 install playwright requests -i https://pypi.tuna.tsinghua.edu.cn/simple

# 关键: 解决 Chromium 下载的网络问题 (腾讯云等服务器无 IPv6)
#   1) 强制 Node 走 IPv4, 否则报 ENETUNREACH 2603:...:443
#   2) 用国内镜像下载 Chromium, 默认 CDN 在国内经常超时
export NODE_OPTIONS="--dns-result-order=ipv4first"
export PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"

# 安装 Chromium 浏览器本体 (在 venv 内执行, 不要加 sudo!)
python3 -m playwright install chromium

# 安装 Chromium 所需系统库 (需要 sudo, 必须用 venv 的 python 完整路径,
# 否则 sudo 会调用系统 python 报 "No module named playwright")
sudo /home/你的用户名/checkin/venv/bin/python3 -m playwright install-deps
```

> ⚠️ 两个易错点:
> 1. 不要在 `sudo` 后面直接写 `python3` —— sudo 用的是系统 Python (`/usr/bin/python3`),
>    而 playwright 装在 venv 里, 会报 `No module named playwright`。要么不加 sudo,
>    要么用 venv 的完整路径: `sudo /home/你的用户名/checkin/venv/bin/python3 -m playwright install-deps`
> 2. 下载浏览器时若报 `ENETUNREACH 2603:...` (IPv6 不可达), 就是没设 `NODE_OPTIONS`
>    强制 IPv4 导致的, 重新 export 后再执行。

**验证安装**：

```bash
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

---

## 第 4 步：配置环境变量（填账号密码）

```bash
cd ~/checkin

# 用 nano 或 vim 打开 .env，填入账号密码
nano .env
```

把下面两行填上真实值（SENDKEY 已经填好了，不用动）：

```
CHECKIN_USER=你的账号
CHECKIN_PASS=你的密码
```

保存退出后，**限制文件权限**（防止其他用户读取密码）：

```bash
chmod 600 ~/checkin/.env
```

> ⚠️ 账号密码只写在 `.env` 里，绝不写进 `checkin.py`。`.env` 不要提交到 Git。

---

## 第 5 步：手动测试（必须先做！）

```bash
cd ~/checkin

# 如果用了虚拟环境
source venv/bin/activate

python3 checkin.py
```

观察：
- 控制台是否输出「打卡成功」
- 微信是否收到「每日打卡成功」通知
- 若失败，查看 `checkin.log` 里的报错

**调试技巧**：把 `checkin.py` 顶部的 `HEADLESS = False` 改成 False 可看到浏览器实际操作（调试完改回 True）。

---

## 第 6 步：设置 cron 定时任务

```bash
crontab -e
```

添加以下一行（每天 19:00 触发，脚本内部随机延迟 0–60 分钟，实现 19:00–20:00 随机打卡）：

```cron
0 19 * * * cd /home/你的用户名/checkin && /home/你的用户名/checkin/venv/bin/python3 checkin.py >> /home/你的用户名/checkin/cron.log 2>&1
```

**注意**：
- 路径必须用**绝对路径**（cron 不识别 `~` 和 `cd` 相对路径的上下文）。上面的 `你的用户名` 换成真实值。
- 如果**没**用虚拟环境，把 python 路径换成 `/usr/bin/python3`：
  ```cron
  0 19 * * * cd /home/你的用户名/checkin && /usr/bin/python3 checkin.py >> /home/你的用户名/checkin/cron.log 2>&1
  ```

保存退出后验证：

```bash
crontab -l          # 查看定时任务是否已生效
```

---

## 第 7 步：验证定时任务

```bash
# 查看 cron 执行记录 (路径因系统而异)
grep CRON /var/log/syslog | tail -20

# 或直接看脚本日志
tail -f ~/checkin/checkin.log
```

---

## 快速排查清单

| 症状 | 处理 |
| --- | --- |
| 提示缺少 `CHECKIN_USER`/`CHECKIN_PASS` | `.env` 里账号密码没填，或 `.env` 不在脚本同目录 |
| Playwright 找不到 chromium | 重新执行 `python3 -m playwright install chromium` |
| 登录后找不到打卡文本框 | `el-id-3527-8` 是动态 id，需换更稳的选择器（见 README） |
| 微信收不到通知 | 检查 SENDKEY 是否填对、是否关注「方糖」公众号 |
| 点击提交没反应 | 提交按钮选择器点的是 font 文字，改为 button 本身试试 |
