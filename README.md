# 每日自动打卡项目 (Daily Auto Check-in)

基于 **Python + Playwright（无头 Chromium）** 的每日自动打卡脚本。登录 → 导航到打卡页 → 清除预设文本 → 填入随机打卡文本 → 提交，全程无人值守，结果通过 **Server酱（ServerChan）** 推送到微信。

---

## 一、功能特性

| 功能 | 说明 |
| --- | --- |
| 自动登录 | 账号密码从环境变量读取，不硬编码 |
| 随机打卡文本 | 内置 10 段文本，每日随机抽取 1 段 |
| 随机开始时间 | 配合 cron，实现 19:00–20:00 之间随机开始 |
| 微信通知 | 成功/失败均通过 Server酱 推送 |
| 反频繁操作检测 | 随机延时、隐藏 webdriver 特征、伪装 UA 等 |
| 资源优化 | 无头模式、禁用图片加载、禁用 GPU 等 |
| 日志 | logging 模块，输出到 `checkin.log` |
| 异常处理 | 任一步骤失败记录日志并推送微信 |

---

## 二、前置准备

### 1. 注册 Server酱 获取 SENDKEY（用于微信通知）

1. 打开 <https://sct.ftqq.com/>，用微信扫码登录
2. 登录后在「SendKey」页面获取你的 `SENDKEY`（形如 `SCTxxxxxxxxxxxxx`）
3. 关注公众号「方糖」，即可接收通知推送

> 如果你暂时不想配置通知，也可以先跳过：脚本检测不到 `SENDKEY` 时会自动跳过推送，仅记录日志。

### 2. 确认服务器信息

- 操作系统：**Ubuntu 22.04**（本文档以此为准）
- 已具备 Python 3.8+ 环境（22.04 自带 Python 3.10）

---

## 三、环境安装

在服务器上依次执行：

```bash
# 1. 更新软件源并安装 Python 与 pip
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# 2. (推荐) 创建独立虚拟环境，避免污染系统环境
python3 -m venv checkin-venv
source checkin-venv/bin/activate

# 3. 安装 Python 依赖 (国内服务器建议加清华镜像加速)
pip3 install playwright requests -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 关键: 解决 Chromium 下载的网络问题 (腾讯云等服务器无 IPv6)
export NODE_OPTIONS="--dns-result-order=ipv4first"
export PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"

# 5. 安装 Chromium 浏览器本体 (在 venv 内执行, 不要加 sudo)
python3 -m playwright install chromium

# 6. 安装 Chromium 所需系统库 (需要 sudo, 用 venv 的 python 完整路径,
#    否则 sudo 调用系统 python 会报 "No module named playwright")
sudo /home/你的用户名/checkin/checkin-venv/bin/python3 -m playwright install-deps
```

> 安装完成后，确认可执行：`python3 -c "from playwright.sync_api import sync_playwright; print('ok')"`

---

## 四、配置脚本

### 1. 填写站点信息（重要）

用编辑器打开 `checkin.py`，修改文件开头「第一部分：可配置变量」：

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `LOGIN_URL` | 登录页 URL | `https://xxx.com/login` |
| `USERNAME_SELECTOR` | 用户名输入框选择器 | `#username` |
| `PASSWORD_SELECTOR` | 密码输入框选择器 | `#password` |
| `LOGIN_BUTTON_SELECTOR` | 登录按钮选择器 | `#login-btn` |
| `LOGIN_SUCCESS_INDICATOR_SELECTOR` | 登录成功标志（可选） | `.user-avatar` |
| `CHECKIN_PAGE_URL` | 登录后访问的打卡页 URL | `https://xxx.com/checkin` |
| `CHECKIN_NAV_SELECTOR` | 进入打卡页需点击的导航元素（可选） | `.nav-checkin` |
| `TEXTAREA_SELECTOR` | 打卡文本框选择器 | `#content` |
| `SUBMIT_BUTTON_SELECTOR` | 提交按钮选择器 | `#submit` |
| `PRESET_TEXT_CLEAR_METHOD` | 预设文本清除方式 | `fill` / `clear_then_type` / `click_clear` |
| `SUCCESS_INDICATOR_SELECTOR` | 打卡成功标志（可选） | `.success-tip` |
| `SUCCESS_TEXT` | 打卡成功关键词（可选） | `打卡成功` |
| `CHECKIN_TEXTS` | 10 段打卡文本 | 替换成你自己的 |

**如何获取选择器：**

1. 浏览器打开目标页面，按 `F12` 打开开发者工具
2. 右键目标输入框/按钮 → 「检查」
3. 在 Elements 面板中，右键对应元素 → **Copy → Copy selector**（得到 CSS 选择器）或 **Copy XPath**

### 2. 设置环境变量

**方式 A：使用 `.env` 文件（推荐）**

```bash
cp .env.example .env
vim .env          # 填入真实账号、密码、SENDKEY
chmod 600 .env    # 限制权限，防止其他用户读取
```

**方式 B：直接使用环境变量**

```bash
export CHECKIN_USER="你的账号"
export CHECKIN_PASS="你的密码"
export SENDKEY="你的SENDKEY"
```

---

## 五、手动测试（务必先做！）

**在设置定时任务之前，必须先手动运行一次，确认流程正确：**

```bash
# 激活虚拟环境(如果用了)
source checkin-venv/bin/activate

# 运行脚本
python3 checkin.py
```

观察点：
- 控制台/`checkin.log` 是否输出「打卡成功」
- 微信是否收到「每日打卡成功」通知
- 若失败，查看日志中的错误信息，通常是选择器或 URL 填错

> **调试技巧**：把 `checkin.py` 顶部的 `HEADLESS = False`，可看到浏览器实际操作过程，便于排查问题；调试完记得改回 `True`。

---

## 六、部署与定时任务

### 1. 上传脚本到服务器

```bash
# 本地执行(或使用 scp / WinSCP / FileZilla 上传)
scp checkin.py .env.example user@你的服务器IP:/home/user/checkin/
```

### 2. 设置 cron 定时任务

```bash
crontab -e
```

添加以下行（每天 19:00 触发，脚本内部会随机延迟 0–60 分钟，实现 19–20 点随机打卡）：

```cron
0 19 * * * cd /home/user/checkin && /usr/bin/python3 checkin.py >> /home/user/checkin/cron.log 2>&1
```

> **说明**：
> - `0 19 * * *` = 每天 19:00 执行
> - 如果用虚拟环境，把 `/usr/bin/python3` 换成虚拟环境的绝对路径，例如 `/home/user/checkin-venv/bin/python3`
> - 脚本内 `RANDOM_START_SECONDS = 3600` 实现随机开始，如需固定时间，把它改为 `0`
> - `cron.log` 记录每次运行的输出，方便排查

### 3. 验证定时任务

```bash
crontab -l          # 查看已设置的定时任务
grep CRON /var/log/syslog | tail   # 查看 cron 执行日志(部分系统路径不同)
```

---

## 七、安全提醒 ⚠️

1. **严禁将密码硬编码在脚本中**。请始终使用环境变量或权限受限的 `.env` 文件（`chmod 600 .env`）。
2. **不要将 `.env` 文件提交到 Git**。建议在 `.gitignore` 中加入 `.env`。
3. 服务器账号密码、SENDKEY 都属于敏感信息，妥善保管。
4. 定时任务和脚本文件中不要留下明文密码。
5. 若服务器多人共用，请确保脚本目录权限限制为本人可读写：`chmod 700 /home/user/checkin`。

---

## 八、常见问题（FAQ）

| 问题 | 解决方法 |
| --- | --- |
| 提示缺少 `CHECKIN_USER`/`CHECKIN_PASS` | 未正确设置环境变量或 `.env`，检查第五步 |
| 登录失败 / 找不到元素 | 检查 `checkin.py` 开头的选择器是否正确 |
| Chromium 启动失败 | 确认已执行 `playwright install --with-deps chromium` |
| 微信收不到通知 | 检查 SENDKEY 是否正确、是否关注了「方糖」公众号 |
| 频繁操作被检测 | 把 `human_delay` 的随机区间调大、确认已启用 stealth |
| 想固定时间打卡 | 将 `RANDOM_START_SECONDS` 设为 `0` |

---

## 九、文件清单

```
checkin/
├── checkin.py        # 主脚本
├── .env.example      # 环境变量示例
└── checkin.log       # 运行日志(自动生成)
```
