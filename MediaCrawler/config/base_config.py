# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习 and 研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

# 基础配置
# Basic configuration
# 平台, xhs | dy | ks | bili | wb | tieba | zhihu
PLATFORM = "xhs"  # Platform, xhs | dy | ks | bili | wb | tieba | zhihu

KEYWORDS = (
    # --- 1. 核心身份与社群黑话 ---
    "yn,xyn,药娘,药l娘,mtf,ts,男娘,伪娘,跨性别,跨拉,"
    # --- 2. 泛指交易与服药动作 ---
    "买糖,卖糖,出糖,收糖,拼糖,团糖,吃糖记录,怎么买糖,hrt购买"
    # --- 3. 雌激素类 (正规名、商品名与黑话) ---
    "补佳乐,补jj,小补,诺坤复,诺坤,蓝片,白片,爱斯妥,凝胶,抹的,日特,欧特,倍美力,马尿,戊酸雌二醇,雌二醇,雌激素,小白瓶,"
    # --- 4. 抗雄激素类 (正规名、商品名与黑话) ---
    "色谱龙,色普龙,色色,cpa,醋酸环丙孕酮,抑安,螺内酯,吃螺,安体舒通,醛固酮,比卡鲁胺,比卡,康士得,非那雄胺,非那,保法止,抗雄,"
    # --- 5. 孕激素类 ---
    "黄体酮,孕酮,琪宁,"
)  # Keyword search configuration, separated by English commas

# 登录类型：二维码、手机或 Cookie
# 二维码、手机或 Cookie
LOGIN_TYPE = "qrcode"  # qrcode or phone or cookie

COOKIES = ""

# 抓取类型：搜索（关键词搜索）| 详情（文章详情）| 创建者（创建者主页数据）
CRAWLER_TYPE = (
    "search"  # Crawling type, search (keyword search) | detail (post details) | creator (creator homepage data)
)


# 是否启用 IP 代理
# Whether to enable IP proxy
ENABLE_IP_PROXY = False

# 代理 IP 池数量
# Number of proxy IP pools
IP_PROXY_POOL_COUNT = 2

# 代理 IP 提供商名称
# Proxy IP provider name
IP_PROXY_PROVIDER_NAME = "kuaidaili"  # kuaidaili | wandouhttp

# 设置为 True 将不会打开浏览器（无头浏览器）
# 设置为 False 将打开浏览器
# 如果小红书一直扫码登录失败，请打开浏览器手动滑动验证码。
# 如果抖音一直提示登录失败，请打开浏览器，查看扫码登录后是否出现手机号码验证。如果出现，请手动验证后重试。
# Setting to True will not open the browser (headless browser)
# Setting False will open a browser
# If Xiaohongshu keeps scanning the code to log in but fails, open the browser and manually pass the sliding verification code.
# If Douyin keeps prompting failure, open the browser and see if mobile phone number verification appears after scanning the QR code to log in. If it does, manually go through it and try again.
HEADLESS = False

# 是否保存登录状态
# Whether to save login status
SAVE_LOGIN_STATE = True

# ==================== CDP (Chrome DevTools Protocol) Configuration ====================
# 是否启用 CDP 模式 - 使用用户现有的 Chrome/Edge 浏览器进行抓取，提供更好的防检测能力
# 启用后，系统将自动检测并启动用户的 Chrome/Edge 浏览器，并通过 CDP 协议进行控制。
# 此方法使用真实的浏览器环境，包括用户的扩展程序、Cookie 和设置，大大降低了被检测到的风险。
# ==================== CDP（Chrome 开发者工具协议）配置 ====================
# Whether to enable CDP mode - use the user's existing Chrome/Edge browser to crawl, providing better anti-detection capabilities
# Once enabled, the user's Chrome/Edge browser will be automatically detected and started, and controlled through the CDP protocol.
# This method uses the real browser environment, including the user's extensions, cookies and settings, greatly reducing the risk of detection.
ENABLE_CDP_MODE = True

# CDP 调试端口，用于与浏览器通信
# 如果端口已被占用，系统将自动尝试下一个可用端口
# CDP debug port, used to communicate with the browser
# If the port is occupied, the system will automatically try the next available port
CDP_DEBUG_PORT = 9222

# 自定义浏览器路径（可选）
# 如果为空，系统将自动检测 Chrome/Edge 的安装路径
# Windows 示例：“C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe”
# macOS 示例：“/Applications/Google Chrome.app/Contents/MacOS/Google Chrome”
# Custom browser path (optional)
# If it is empty, the system will automatically detect the installation path of Chrome/Edge
# Windows example: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# macOS example: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CUSTOM_BROWSER_PATH = ""

# 是否在 CDP 模式下启用无头模式
# 注意：即使设置为 True，某些防检测功能在无头模式下可能无法正常工作
# Whether to enable headless mode in CDP mode
# NOTE: Even if set to True, some anti-detection features may not work well in headless mode
CDP_HEADLESS = False

# 浏览器启动超时时间（秒）
# Browser startup timeout (seconds)
BROWSER_LAUNCH_TIMEOUT = 60

# 程序结束时是否自动关闭浏览器
# 设置为 False 以保持浏览器运行，方便调试
# Whether to automatically close the browser when the program ends
# Set to False to keep the browser running for easy debugging
AUTO_CLOSE_BROWSER = True

# 数据保存类型选项配置，支持：csv, db, json, jsonl, sqlite, excel, postgres。最好保存到 DB，具有去重功能。
# Data saving type option configuration, supports: csv, db, json, jsonl, sqlite, excel, postgres. It is best to save to DB, with deduplication function.
SAVE_DATA_OPTION = "jsonl"  # csv or db or json or jsonl or sqlite or excel or postgres

# 数据保存路径，如果默认未指定，将保存到 data 文件夹。
# Data saving path, if not specified by default, it will be saved to the data folder.
SAVE_DATA_PATH = ""

# 用户浏览器缓存的浏览器文件配置
# Browser file configuration cached by the user's browser
USER_DATA_DIR = "%s_user_data_dir"  # %s will be replaced by platform name

# 开始抓取的页数，默认从第一页开始
# The number of pages to start crawling starts from the first page by default
START_PAGE = 1

# 控制抓取的视频/帖子数量
# Control the number of crawled videos/posts
CRAWLER_MAX_NOTES_COUNT = 30

# 控制并发爬虫的数量
# Controlling the number of concurrent crawlers
MAX_CONCURRENCY_NUM = 1

# 是否启用抓取媒体模式（包括图片或视频资源），默认不开启抓取媒体
# Whether to enable crawling media mode (including image or video resources), crawling media is not enabled by default
ENABLE_GET_MEIDAS = False

# 是否启用评论抓取模式。默认启用评论抓取。
# Whether to enable comment crawling mode. Comment crawling is enabled by default.
ENABLE_GET_COMMENTS = True

# 控制抓取的一级评论数量（单个视频/帖子）
# Control the number of crawled first-level comments (single video/post)
CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 100

# 是否开启二级评论抓取模式。默认不开启二级评论抓取。
# 如果旧版本项目使用 db，需要参考 schema/tables.sql 第 287 行添加表字段。
# Whether to enable the mode of crawling second-level comments. By default, crawling of second-level comments is not enabled.
# If the old version of the project uses db, you need to refer to schema/tables.sql line 287 to add table fields.
ENABLE_GET_SUB_COMMENTS = True

# 词云相关
# word cloud related
# 是否启用生成评论词云
# Whether to enable generating comment word clouds
ENABLE_GET_WORDCLOUD = False

# 自定义词及其分组
# 添加规则：xx:yy，其中 xx 是自定义添加的短语，yy 是短语 xx 分配到的组名。
# Custom words and their groups
# Add rule: xx:yy where xx is a custom-added phrase, and yy is the group name to which the phrase xx is assigned.
CUSTOM_WORDS = {
    "零几": "年份",  # 将“零几”识别为一个整体 | Recognize "zero points" as a whole
    "高频词": "专业术语",  # 自定义词示例 | Example custom words
}

# 停用（禁用）词文件路径
# Deactivate (disabled) word file path
STOP_WORDS_FILE = "./docs/hit_stopwords.txt"

# 中文字体文件路径
# Chinese font file path
FONT_PATH = "./docs/STZHONGS.TTF"

# 抓取间隔
# Crawl interval
CRAWLER_MAX_SLEEP_SEC = 8

# 是否禁用 SSL 证书验证。仅在使用企业代理、Burp Suite、mitmproxy 等会注入自签名证书的中间人代理时设为 True。
# 警告：禁用 SSL 验证将使所有流量暴露于中间人攻击风险，请勿在生产环境中开启。
# Whether to disable SSL certificate verification. Set to True only when using man-in-the-middle proxies that inject self-signed certificates such as corporate proxies, Burp Suite, mitmproxy, etc.
# WARNING: Disabling SSL verification exposes all traffic to man-in-the-middle attack risks, do not enable in production environments.
DISABLE_SSL_VERIFY = False

from .bilibili_config import *
from .xhs_config import *
from .dy_config import *
from .ks_config import *
from .weibo_config import *
from .tieba_config import *
from .zhihu_config import *