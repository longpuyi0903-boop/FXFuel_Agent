# config.py - DeepSeek 客户端配置

import os
from dotenv import load_dotenv
from openai import OpenAI

# --- 1. 加载环境变量 ---
load_dotenv()

# API Keys
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

# --- 2. 代理设置 ---
if HTTP_PROXY:
    os.environ['http_proxy'] = HTTP_PROXY
if HTTPS_PROXY:
    os.environ['https_proxy'] = HTTPS_PROXY

# --- 3. DeepSeek 客户端 ---
def get_deepseek_client():
    """获取 DeepSeek 客户端（单例模式）"""
    if not DEEPSEEK_API_KEY:
        # 如果在 Streamlit 环境中，显示错误并停止
        try:
            import streamlit as st
            st.error("⚠️ 未找到 DeepSeek API Key，请在 .env 中设置 DEEPSEEK_API_KEY")
            st.stop()
        except ImportError:
            # 非 Streamlit 环境，抛出异常
            raise ValueError("未找到 DeepSeek API Key，请在 .env 中设置 DEEPSEEK_API_KEY")
    
    try:
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1"
        )
        return client
    except Exception as e:
        try:
            import streamlit as st
            st.error(f"DeepSeek 客户端初始化失败: {e}")
            st.stop()
        except ImportError:
            raise RuntimeError(f"DeepSeek 客户端初始化失败: {e}")

# 向后兼容：保留全局客户端实例（用于 streamlit_app.py，后续阶段会重构）
DEEPSEEK_CLIENT = get_deepseek_client()

# --- 4. 模型配置 ---
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-chat")  # 向后兼容

# --- 5. 报告生成配置 ---
REPORT_CONFIG = {
    "temperature": 0.3,       # 保持低创造性以确保事实准确
    "max_tokens": 5000,       # 增加以容纳更长的新闻摘要内容
    "top_p": 0.95
}

# --- 6. 超时配置 (P0-2 新增) ---
TIMEOUT_CONFIG = {
    "default": (10, 30),      # (连接超时, 读取超时) 秒 - 通用默认值
    "akshare": (10, 20),      # AKShare 国内源，响应较快
    "fred": (10, 30),         # FRED API
    "perplexity": (30, 90),   # Perplexity 响应较慢，需要更长超时
    "yahoo": (10, 15),        # Yahoo Finance
    "hkma": (10, 20),         # 香港金管局
}

# --- 7. 历史锚点数据（用于 LLM 历史对比参考） ---
HISTORY_ANCHORS = {
    "USDCNY_2022_HIGH": 7.328,  # 2022年11月高点
    "USDCNY_2023_HIGH": 7.351,  # 2023年9月高点
    "USDCNY_AVG_5Y": 6.95,      # 5年均值（估算值）
    "HKD_WEAK_SIDE": 7.85,      # 弱方兑换保证（固定）
    "HKD_STRONG_SIDE": 7.75     # 强方兑换保证（固定）
}

# --- 8. 核心指标配置（用于硬校验） ---
CORE_INDICATORS = {
    # --- 汇率类 (FX) ---
    "USD/CNY": {
        "keywords": ["USD/CNY", "人民币中间价", "中间价"],
        "data_field": "USDCNY_MID",
        "tolerance": 0.05,
        "type": "FX"
    },
    "USD/CNH": {
        "keywords": ["USD/CNH", "离岸人民币", "离岸CNH"],
        "data_field": "USDCNH_CLOSE",
        "tolerance": 0.05,
        "type": "FX"
    },
    "CNY_SPREAD": {
        "keywords": ["价差", "点子", "倒挂"],
        "data_field": "CNY_SPREAD",
        "tolerance": 0.02,  # 价差数值较小，容差需收紧
        "type": "FX"
    },
    "USD/HKD": {
        "keywords": ["USD/HKD", "港元汇率"],
        "data_field": "USDHKD",
        "tolerance": 0.02,  # 港币波动极窄
        "type": "FX"
    },
    "EUR/USD": {
        "keywords": ["EUR/USD", "欧美汇率"],
        "data_field": "EURUSD",
        "tolerance": 0.05,
        "type": "FX"
    },
    "USD/JPY": {
        "keywords": ["USD/JPY", "日元汇率"],
        "data_field": "USDJPY",
        "tolerance": 0.5,
        "type": "FX"
    },
    
    # --- 利率类 (Rates) ---
    "HIBOR": {
        "keywords": ["HIBOR", "隔夜HIBOR"],
        "data_field": "HIBOR_OVERNIGHT",
        "tolerance": 0.1,
        "type": "Rates"
    },
    "HKD_USD_SPREAD": {
        "keywords": ["港美利差", "息差"],
        "data_field": "HKD_USD_SPREAD",
        "tolerance": 0.1,
        "type": "Rates"
    },
    "US10Y": {
        "keywords": ["10年期", "10Y"],
        "data_field": "US10Y_YIELD",
        "tolerance": 0.1,
        "type": "Rates"
    },
    "US2Y": {
        "keywords": ["2年期", "2Y"],
        "data_field": "US2Y_YIELD",
        "tolerance": 0.1,
        "type": "Rates"
    },
    
    # --- 指数类 (Index) ---
    "DXY": {
        "keywords": ["DXY", "美元指数"],
        "data_field": "DXY",
        "tolerance": 0.5,
        "type": "Index"
    },
    "VIX": {
        "keywords": ["VIX", "恐慌指数"],
        "data_field": "VIX_LAST",
        "tolerance": 1.0,
        "type": "Index"
    }
}

# 默认容差（防御性编程）
DEFAULT_TOLERANCE = 0.05

# --- 9. Token 管理配置 (P0-1 新增) ---
TOKEN_CONFIG = {
    "max_context_tokens": 6000,   # Context 最大 Token 数（保守值，留空间给输出）
    "max_news_items": 7,          # 超限时保留的新闻条数
    "chars_per_token": 1.5,       # 中文约 1.5 字符/token
}

# --- 10. 数据缓存配置 (P1 新增) ---
CACHE_TTL = {
    "cny_mid": 3600,        # 中间价：1小时（9:15发布后整天不变）
    "cny_spot": 60,         # 实时汇率：1分钟
    "hkd": 60,              # 港元汇率：1分钟
    "fred": 300,            # FRED 数据：5分钟
    "global_fx": 60,        # 全球外汇：1分钟
    "news": 600,            # 新闻：10分钟
}

# --- 11. 辅助函数 ---
def get_proxy_status():
    """返回代理状态"""
    return HTTP_PROXY or HTTPS_PROXY
