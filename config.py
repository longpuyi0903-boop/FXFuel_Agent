# config.py - DeepSeek 客户端配置

import os
from dotenv import load_dotenv
import streamlit as st
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
def initialize_deepseek_client():
    """初始化 DeepSeek 客户端"""
    if not DEEPSEEK_API_KEY:
        st.error("⚠️ 未找到 DeepSeek API Key，请在 .env 中设置 DEEPSEEK_API_KEY")
        st.stop()
    
    try:
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1"
        )
        return client
    except Exception as e:
        st.error(f"DeepSeek 客户端初始化失败: {e}")
        st.stop()

DEEPSEEK_CLIENT = initialize_deepseek_client()

# --- 4. 辅助函数 ---
def get_proxy_status():
    """返回代理状态"""
    return HTTP_PROXY or HTTPS_PROXY

# 模型名称
DEEPSEEK_MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-chat")
