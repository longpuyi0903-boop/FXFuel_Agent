# config.py - DeepSeek 客户端设置 (适配 OpenAI SDK 兼容模式)

import os
from dotenv import load_dotenv
import streamlit as st
from openai import OpenAI 

# --- 1. 密钥加载与配置 ---
load_dotenv()
# 明确从 .env 文件中加载密钥。推荐使用 DEEPSEEK_API_KEY，但兼容 OPENAI_API_KEY
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

# --- 2. 设置全局代理 ---
if HTTP_PROXY:
    os.environ['http_proxy'] = HTTP_PROXY
if HTTPS_PROXY:
    os.environ['https_proxy'] = HTTPS_PROXY

# --- 3. 初始化 DeepSeek 客户端 ---
def initialize_deepseek_client():
    """初始化并返回 DeepSeek 客户端"""
    if not DEEPSEEK_API_KEY:
        st.error("无法加载 DeepSeek Key。请在 .env 文件中设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。")
        st.stop()
    
    try:
        # 兼容 OpenAI 客户端，指向 DeepSeek 的 base_url
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1" 
        )
        return client
    except Exception as e:
        st.error(f"DeepSeek 客户端初始化失败，请检查您的 Key 是否正确: {e}")
        st.stop()
        
# 初始化并存储客户端
DEEPSEEK_CLIENT = initialize_deepseek_client()

# --- 4. 配置辅助函数 ---
def get_proxy_status():
    """返回代理是否启用的状态信息"""
    return HTTP_PROXY or HTTPS_PROXY

# 定义使用的 DeepSeek 模型
DEEPSEEK_MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-chat")