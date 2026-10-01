#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 每日自动打卡脚本 (Daily Auto Check-in)
================================================================================
功能概述:
  1. 使用 Playwright + 无头 Chromium 自动登录目标网站
  2. 登录后导航到打卡页面, 清除文本框预设内容, 填入随机打卡文本并提交
  3. 通过 Server酱(ServerChan) 将打卡结果推送到微信
  4. 内置频繁操作检测规避: 随机延时、隐藏 webdriver 特征、禁用图片加载等
  5. 全程日志记录 + 异常处理, 任何步骤失败都会记录日志并推送微信通知

安全说明:
  - 账号/密码/通知密钥均从环境变量读取, 严禁硬编码在本脚本中
  - 请勿将包含密码的 .env 文件提交到版本库或上传到公开位置

依赖安装 (在目标 Linux 服务器上执行):
  pip3 install playwright requests
  python3 -m playwright install --with-deps chromium

运行方式:
  CHECKIN_USER=xxx CHECKIN_PASS=yyy SENDKEY=zzz python3 checkin.py
  (也可以配置 .env 文件, 脚本会自动读取, 见 README.md)

作者/日期: auto-generated
================================================================================
"""

import os
import sys
import time
import random
import logging
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==============================================================================
#  第一部分: 可配置变量 (请按需修改, 全部集中在此, 方便维护)
# ==============================================================================

# --- 登录相关 ---
LOGIN_URL = "https://ai.cqzuxia.com/#/login"     # 登录页面完整 URL
USERNAME_SELECTOR = 'xpath=//*[@id="app"]/div/div[2]/div/div/div[2]/div[2]/form/div[1]/div/div[1]/input'  # 用户名输入框
PASSWORD_SELECTOR = 'xpath=//*[@id="app"]/div/div[2]/div/div/div[2]/div[2]/form/div[2]/div/div[1]/input'  # 密码输入框
LOGIN_BUTTON_SELECTOR = 'xpath=//*[@id="app"]/div/div[2]/div/div/div[2]/div[2]/div/div'  # 登录按钮

# 登录成功的判定选择器 (可选): 登录后页面上会出现、而登录前没有的元素。
# 留空 "" 则跳过此校验, 直接进入下一步 (靠后续步骤的报错间接判断登录是否成功)。
LOGIN_SUCCESS_INDICATOR_SELECTOR = ""

# --- 打卡页导航 ---
# 登录成功后先访问的 URL (如果登录成功后已直接进入打卡页, 可填与打卡页相同的地址)
CHECKIN_PAGE_URL = "https://ai.cqzuxia.com/stu-growing/#/daily-assign"
# 进入打卡页后需要点击的「导航」元素选择器 (可选)。留空 "" 则跳过点击导航这一步。
CHECKIN_NAV_SELECTOR = 'xpath=//*[@id="tab-1"]'   # 进入打卡页后点击的导航 tab

# --- 打卡表单 ---
TEXTAREA_SELECTOR = 'xpath=//*[@id="pane-1"]//textarea'  # 打卡文本框 (原 el-id 是 Element Plus 动态 id, 不稳定; 改用 pane-1 下的 textarea)
SUBMIT_BUTTON_SELECTOR = 'xpath=//*[@id="pane-1"]/div/div[2]/div[2]/button'  # 提交按钮

# 预设文本清除方式, 三选一:
#   "fill"            -> Playwright 的 fill() 会自动清空原有内容再输入 (最推荐, 默认)
#   "clear_then_type" -> 先 Ctrl+A 全选再删除, 然后逐字输入 (更接近真人, 但略慢)
#   "click_clear"     -> 页面上有专门的清空/删除按钮, 需同时填写下方 CLEAR_BUTTON_SELECTOR
PRESET_TEXT_CLEAR_METHOD = "fill"
CLEAR_BUTTON_SELECTOR = ""                       # 仅当方式为 "click_clear" 时使用

# --- 打卡成功判定 (可选) ---
# 提交后用于确认成功的元素选择器; 留空 "" 则跳过选择器校验
SUCCESS_INDICATOR_SELECTOR = ""
# 提交后用于确认成功的关键词 (会在整个页面正文中查找); 留空 "" 则跳过关键词校验
SUCCESS_TEXT = ""

# --- 运动打卡 (上传图片, 可选) ---
# 如需每天额外做「运动打卡」(上传一张图片), 保持 SPORT_CHECKIN_ENABLED = True;
# 否则设为 False 跳过。
SPORT_CHECKIN_ENABLED = True
SPORT_NAV_SELECTOR = 'xpath=//*[@id="tab-0"]'      # 运动打卡导航 tab
SPORT_UPLOAD_SELECTOR = 'xpath=//*[@id="pane-0"]/div/div[2]/div[2]/div[1]'  # 图片上传按钮(点击弹出文件选择)
SPORT_SUBMIT_SELECTOR = 'xpath=//*[@id="pane-0"]/div/div[2]/div[2]/button'  # 运动打卡提交按钮
SPORT_IMAGE_FILENAME = "IMG_5568.PNG"              # 图片文件名(放在脚本同目录)
SPORT_TEXT = "运动"                                 # 运动打卡上方文本框要输入的字符
SPORT_TEXT_SELECTOR = 'xpath=//*[@id="pane-0"]//textarea'  # 运动打卡文本框 (直接定位 textarea, 避免点到外层 div)

# --- 每日打卡文本 (10 段, 每天随机取 1 段) ---
# 请替换成你真实需要填写的内容。脚本会随机抽取, 不要重复即可。
CHECKIN_TEXTS = [
    "专注当下，全力以赴。今日事今日毕，不拖延，不敷衍。保持高效，注重细节，追求卓越。学习新技能，总结不足，持续优化。与人为善，传递温暖。坚持锻炼，强健体魄。心怀感恩，珍惜拥有。日拱一卒，功不唐捐，遇见更好的自己。",
    "把握今天，拒绝拖延。今日事今日毕，不找借口，不推诿。保持专注，提升效率，精益求精。学习新思维，反思短板，持续进步。与人为善，传递善意。坚持运动，保持活力。心怀感恩，珍惜时光。每天进步一点点，汇聚成河，成就非凡。",
    "活在当下，高效执行。今日事今日毕，不拖延，不懈怠。保持专注，注重细节，追求完美。学习新知识，总结得失，持续改进。与人为善，传递快乐。坚持锻炼，保持健康。心怀感恩，珍惜遇见。日积月累，聚沙成塔，塑造更优秀的自己。",
    "珍惜今日，即刻行动。今日事今日毕，不拖延，不逃避。保持专注，提高效率，一丝不苟。学习新经验，反思不足，持续优化。与人为善，传递爱心。坚持运动，强健身心。心怀感恩，珍惜所有。每天一小步，积累一大步，成就理想自我。",
    "今日事，今日清。拒绝拖延，拒绝借口。保持专注，提升效能，注重细节。学习新技能，总结反思，持续精进。与人为善，传递正能量。坚持锻炼，保持活力。心怀感恩，珍惜当下。日有所进，月有所成，遇见更好的自己。",
    "专注当下，高效完成。今日事今日毕，不拖延，不敷衍。保持专注，提高效率，精益求精。学习新知识，反思不足，持续改进。与人为善，传递温暖。坚持运动，保持健康。心怀感恩，珍惜拥有。每天进步一点点，积少成多，成就非凡自我。",
    "今日事今日毕，不拖延，不懈怠。保持专注，注重细节，追求卓越。学习新思维，总结得失，持续优化。与人为善，传递善意。坚持锻炼，强健体魄。心怀感恩，珍惜时光。日拱一卒，功不唐捐，塑造更优秀的自己。",
    "把握当下，即刻行动。今日事今日毕，不拖延，不推诿。保持专注，提升效率，一丝不苟。学习新经验，反思短板，持续进步。与人为善，传递快乐。坚持运动，保持活力。心怀感恩，珍惜遇见。每天一小步，积累一大步，成就理想自我。",
    "今日事，今日清。拒绝拖延，拒绝借口。保持专注，提高效能，注重细节。学习新技能，总结反思，持续精进。与人为善，传递正能量。坚持锻炼，保持健康。心怀感恩，珍惜当下。日有所进，月有所成，遇见更好的自己。",
    "专注当下，全力以赴。今日事今日毕，不拖延，不敷衍。保持高效，注重细节，追求卓越。学习新技能，总结不足，持续优化。与人为善，传递温暖。坚持锻炼，强健体魄。心怀感恩，珍惜拥有。日拱一卒，功不唐捐，遇见更好的自己。",
]

# --- 时间与延时 ---
# 脚本启动后先随机等待 0 ~ RANDOM_START_SECONDS 秒再开始打卡。
# 配合 cron 在 12:00 触发, 可实现「每天 12:00-14:00 之间随机开始」的效果。
# 如果不需要随机开始, 把该值设为 0 即可。
RANDOM_START_SECONDS = 7200

# --- 超时设置 (毫秒) ---
LOGIN_TIMEOUT_MS = 15000          # 等待登录结果/元素出现的最大时长
SUCCESS_TIMEOUT_MS = 8000         # 等待打卡成功标志出现的最大时长
NAV_TIMEOUT_MS = 10000            # 等待导航元素的超时

# --- 其他 ---
LOG_FILE = "checkin.log"          # 日志文件名 (与脚本同目录)
HEADLESS = True                   # 无头模式; 调试时可改为 False 观察浏览器

# ==============================================================================
#  第二部分: 环境变量读取
# ==============================================================================

CHECKIN_USER = os.getenv("CHECKIN_USER", "")
CHECKIN_PASS = os.getenv("CHECKIN_PASS", "")
SENDKEY = os.getenv("SENDKEY", "")

# 轻量 .env 加载器: 如果脚本同目录存在 .env, 则读取其中的 KEY=VALUE,
# 且仅当环境变量尚未设置时才生效 (命令行直接传入的优先级更高)。
def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)

load_dotenv()

# 重新读取 (确保 .env 生效)
CHECKIN_USER = os.getenv("CHECKIN_USER", "")
CHECKIN_PASS = os.getenv("CHECKIN_PASS", "")
SENDKEY = os.getenv("SENDKEY", "")

# 快速测试开关: 设为任意非空值(如 1)则跳过「启动随机等待」(12:00-14:00 的随机延迟),
# 让脚本立即开始执行打卡。操作之间的 3 秒间隔仍保留, 以规避速率限制。
# 正式定时运行时不要设置此变量。
QUICK_TEST = os.getenv("QUICK_TEST", "")

# ==============================================================================
#  第三部分: 日志配置
# ==============================================================================

def setup_logging(log_file=LOG_FILE):
    logger = logging.getLogger("checkin")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    # 输出到文件
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # 同时输出到控制台 (方便 cron 重定向捕获)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger

logger = setup_logging()

# ==============================================================================
#  第四部分: 微信通知 (Server酱)
# ==============================================================================

def send_wechat_notification(title, content=""):
    """通过 Server酱 推送微信通知。未配置 SENDKEY 时自动跳过并记录日志。"""
    if not SENDKEY:
        logger.warning("未配置 SENDKEY, 跳过微信通知")
        return False
    # Server酱 新版接口: https://sctapi.ftqq.com/{SENDKEY}.send
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    data = {"title": title, "desp": content}
    try:
        resp = requests.post(url, data=data, timeout=15)
        result = resp.json()
        if result.get("code") == 0:
            logger.info("微信通知发送成功")
            return True
        logger.warning(f"微信通知发送失败: {result}")
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning(f"微信通知发送异常: {e}")
        return False

# ==============================================================================
#  第五部分: 反检测与资源优化辅助函数
# ==============================================================================

def human_delay(min_sec=0.5, max_sec=2.0):
    """每次操作间隔: 固定 3 秒 + 随机延时, 规避频繁操作检测/速率限制。"""
    time.sleep(3 + random.uniform(min_sec, max_sec))

def apply_stealth(context):
    """
    隐藏 webdriver 自动化特征, 降低被反爬/风控识别的概率:
      - 删除 navigator.webdriver
      - 伪造 navigator.languages / plugins / chrome
      - 伪装权限查询 (notifications)
    """
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    window.navigator.chrome = { runtime: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
    """
    context.add_init_script(stealth_js)

def block_images(route, request):
    """拦截图片请求, 减少流量与资源占用, 加快页面加载。"""
    if request.resource_type == "image":
        route.abort()
    else:
        route.continue_()

# ==============================================================================
#  第六部分: 核心打卡流程
# ==============================================================================

def do_checkin():
    """
    执行完整打卡流程, 任何一步失败都会抛出异常, 由 main() 统一捕获处理。
    """
    with sync_playwright() as p:
        # 浏览器启动参数: 禁用 GPU 与不必要功能, 降低服务器资源占用
        launch_args = [
            "--disable-gpu",
            "--disable-dev-shm-usage",      # 避免容器/低内存环境共享内存不足
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--hide-scrollbars",
            "--mute-audio",
            "--no-first-run",
            "--no-zygote",
            "--disable-software-rasterizer",
            "--disable-accelerated-2d-canvas",
            "--memory-pressure-off",
        ]
        # 以 root 运行 Linux 服务器时通常需要 --no-sandbox, 非 root 建议去掉
        if os.name == "posix" and os.geteuid() == 0:
            launch_args.append("--no-sandbox")

        browser = p.chromium.launch(headless=HEADLESS, args=launch_args)

        # 创建带反检测的上下文
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        apply_stealth(context)
        # 全局禁用图片加载
        context.route("**/*", block_images)

        page = context.new_page()

        try:
            # ---- 1. 打开登录页 ----
            logger.info(f"打开登录页: {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=LOGIN_TIMEOUT_MS)
            human_delay(1.0, 2.5)

            # ---- 2. 输入用户名/密码 ----
            logger.info("输入用户名")
            page.wait_for_selector(USERNAME_SELECTOR, timeout=LOGIN_TIMEOUT_MS)
            page.fill(USERNAME_SELECTOR, CHECKIN_USER)
            human_delay(0.6, 1.6)

            logger.info("输入密码")
            page.fill(PASSWORD_SELECTOR, CHECKIN_PASS)
            human_delay(0.6, 1.6)

            # ---- 3. 点击登录 ----
            logger.info("点击登录按钮")
            page.click(LOGIN_BUTTON_SELECTOR)
            human_delay(1.5, 3.0)

            # 等待登录结果
            if LOGIN_SUCCESS_INDICATOR_SELECTOR:
                page.wait_for_selector(
                    LOGIN_SUCCESS_INDICATOR_SELECTOR, timeout=LOGIN_TIMEOUT_MS
                )
                logger.info("检测到登录成功标志")
            else:
                page.wait_for_load_state("networkidle", timeout=LOGIN_TIMEOUT_MS)

            # ---- 4. 进入打卡页 ----
            if CHECKIN_PAGE_URL:
                logger.info(f"访问打卡页: {CHECKIN_PAGE_URL}")
                page.goto(CHECKIN_PAGE_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                human_delay(1.0, 2.5)

            # 如果需要点击导航进入打卡页
            if CHECKIN_NAV_SELECTOR:
                logger.info("点击导航进入打卡页")
                page.wait_for_selector(CHECKIN_NAV_SELECTOR, timeout=NAV_TIMEOUT_MS)
                page.click(CHECKIN_NAV_SELECTOR)
                human_delay(1.0, 2.5)

            # ---- 5. 清除预设文本并填写打卡内容 ----
            logger.info("定位打卡文本框")
            page.wait_for_selector(TEXTAREA_SELECTOR, timeout=NAV_TIMEOUT_MS)

            # 随机抽取一段打卡文本
            checkin_text = random.choice(CHECKIN_TEXTS)
            logger.info(f"本次打卡文本: {checkin_text}")

            if PRESET_TEXT_CLEAR_METHOD == "clear_then_type":
                # 先全选再删除, 然后逐字输入 (更接近真人)
                page.click(TEXTAREA_SELECTOR)
                page.keyboard.press("Control+A")
                human_delay(0.3, 0.8)
                page.keyboard.press("Delete")
                human_delay(0.3, 0.8)
                page.type(TEXTAREA_SELECTOR, checkin_text, delay=random.randint(60, 150))
            elif PRESET_TEXT_CLEAR_METHOD == "click_clear":
                # 点击专门的清空按钮
                if not CLEAR_BUTTON_SELECTOR:
                    raise ValueError("PRESET_TEXT_CLEAR_METHOD=click_clear 但未配置 CLEAR_BUTTON_SELECTOR")
                page.click(CLEAR_BUTTON_SELECTOR)
                human_delay(0.5, 1.2)
                page.fill(TEXTAREA_SELECTOR, checkin_text)
            else:
                # 默认 "fill": fill() 会自动清空原有内容再输入
                page.fill(TEXTAREA_SELECTOR, checkin_text)
            human_delay(0.8, 2.0)

            # ---- 6. 点击提交 ----
            logger.info("点击提交按钮")
            page.click(SUBMIT_BUTTON_SELECTOR)
            human_delay(2.0, 4.0)

            # ---- 7. 校验打卡结果 ----
            success = verify_success(page)
            if not success:
                raise RuntimeError("提交后未检测到打卡成功标志")

            # 文本打卡(日精进打卡)成功, 发送通知
            send_wechat_notification(
                "日精进打卡成功",
                f"时间: {datetime.now():%H:%M:%S}\n打卡内容: {checkin_text}",
            )

            # ---- 8. 运动打卡 (上传图片, 可选) ----
            do_sport_checkin(page)

            logger.info("打卡成功")
            return True

        except Exception:
            # 失败时保存截图, 方便排查是哪一步、页面当时是什么状态
            try:
                page.screenshot(path="error_screenshot.png", full_page=True)
                logger.info("已保存失败截图: error_screenshot.png")
            except Exception:  # noqa: BLE001
                pass
            raise

        finally:
            browser.close()

def do_sport_checkin(page):
    """运动打卡: 切换到运动打卡 tab, 上传图片并提交。"""
    if not SPORT_CHECKIN_ENABLED:
        logger.info("运动打卡未启用, 跳过")
        return

    # 图片放在脚本同目录下 (即 /home/ubuntu/daily-checkin/)
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SPORT_IMAGE_FILENAME)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"运动打卡图片不存在: {image_path}")

    # 切换到运动打卡 tab
    logger.info("切换到运动打卡 tab")
    page.wait_for_selector(SPORT_NAV_SELECTOR, timeout=NAV_TIMEOUT_MS)
    page.click(SPORT_NAV_SELECTOR)
    human_delay(0.8, 2.0)

    # 在运动打卡文本框输入字符
    logger.info(f"填写运动打卡文本框: {SPORT_TEXT}")
    page.wait_for_selector(SPORT_TEXT_SELECTOR, timeout=NAV_TIMEOUT_MS)
    page.fill(SPORT_TEXT_SELECTOR, SPORT_TEXT)
    human_delay(0.5, 1.5)

    # 直接给 el-upload 内部的隐藏 <input type="file"> 设置文件
    # (比 expect_file_chooser 更直接, 一定能触发原生 change 事件, 让 el-upload 真正启动上传)
    logger.info("设置运动打卡图片 (set_input_files)")
    file_input_selector = "//*[@id='pane-0']//input[@type='file']"
    page.set_input_files(file_input_selector, image_path)
    logger.info(f"已设置图片: {image_path}")

    # 等待 el-upload 出现上传列表项 (证明 change 事件触发, 上传已启动)
    # el-upload 一旦接收到文件会立刻把列表项渲染到 DOM
    try:
        page.wait_for_selector(
            "//*[@id='pane-0']//*[contains(@class, 'el-upload-list')]",
            timeout=30000,
        )
        logger.info("检测到上传列表项, el-upload 已开始处理")
    except PlaywrightTimeoutError:
        # 上传未启动, 截图并抛错(让 main 发失败通知, 不会发"运动打卡成功"假通知)
        try:
            page.screenshot(
                path=os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "sport_upload_failed.png",
                ),
                full_page=True,
            )
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            "30 秒内未检测到 el-upload 上传列表项, 上传可能未启动 (组件加载失败?)"
        )

    # 列表项出现后再等 10 秒, 让图片真正传输完成
    logger.info("等待 10 秒让图片传输完成...")
    time.sleep(10)

    human_delay(1.0, 2.0)

    # 点击运动打卡提交按钮
    logger.info("点击运动打卡提交按钮")
    page.click(SPORT_SUBMIT_SELECTOR)
    logger.info("运动打卡提交完成")
    human_delay(2.0, 4.0)

    # 运动打卡成功, 发送通知
    send_wechat_notification(
        "运动打卡成功",
        f"时间: {datetime.now():%H:%M:%S}\n已上传图片: {SPORT_IMAGE_FILENAME}",
    )

def verify_success(page):
    """提交后校验是否打卡成功。未配置校验条件时默认视为成功。"""
    if SUCCESS_INDICATOR_SELECTOR:
        try:
            page.wait_for_selector(SUCCESS_INDICATOR_SELECTOR, timeout=SUCCESS_TIMEOUT_MS)
            logger.info("检测到打卡成功标志(选择器)")
            return True
        except PlaywrightTimeoutError:
            logger.warning("未检测到打卡成功标志(选择器)")
            return False
    if SUCCESS_TEXT:
        body_text = page.inner_text("body")
        if SUCCESS_TEXT in body_text:
            logger.info("检测到打卡成功标志(关键词)")
            return True
        logger.warning("未检测到打卡成功标志(关键词)")
        return False
    # 未配置任何校验条件, 默认视为成功
    logger.info("未配置成功校验条件, 默认视为打卡成功")
    return True

# ==============================================================================
#  第七部分: 入口
# ==============================================================================

def main():
    start = datetime.now()
    logger.info("=" * 60)
    logger.info(f"打卡任务启动: {start:%Y-%m-%d %H:%M:%S}")

    # 前置检查: 环境变量
    missing = []
    if not CHECKIN_USER:
        missing.append("CHECKIN_USER")
    if not CHECKIN_PASS:
        missing.append("CHECKIN_PASS")
    if missing:
        msg = f"缺少必要环境变量: {', '.join(missing)}"
        logger.error(msg)
        send_wechat_notification("打卡失败: 缺少环境变量", msg)
        return 1

    # 随机开始: 在 0 ~ RANDOM_START_SECONDS 秒之间随机等待 (QUICK_TEST 下跳过)
    if RANDOM_START_SECONDS > 0 and not QUICK_TEST:
        wait = random.uniform(0, RANDOM_START_SECONDS)
        logger.info(f"随机延迟 {wait:.0f} 秒后开始打卡")
        time.sleep(wait)

    try:
        do_checkin()
        end = datetime.now()
        cost = (end - start).total_seconds()
        summary = f"打卡全部完成!\n开始时间: {start:%H:%M:%S}\n结束时间: {end:%H:%M:%S}\n耗时: {cost:.1f} 秒"
        logger.info(summary)
        # 成功通知已在「日精进打卡」和「运动打卡」步骤内分别发送, 这里不再重复
        return 0
    except Exception as e:  # noqa: BLE001
        end = datetime.now()
        logger.exception("打卡失败")
        summary = f"打卡失败!\n时间: {end:%Y-%m-%d %H:%M:%S}\n错误: {e}"
        send_wechat_notification("每日打卡失败", summary)
        return 1

if __name__ == "__main__":
    sys.exit(main())
