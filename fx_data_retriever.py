# fx_data_retriever.py - RAG 数据抓取模块 (最终自动化版本 - 专业命名)

import os
from dotenv import load_dotenv
import pandas as pd
from fredapi import Fred
import requests
import json 

# --- 1. 初始化和密钥加载 ---
load_dotenv() 
FRED_KEY = os.getenv("FRED_API_KEY")
AV_KEY = os.getenv("ALPHA_VANTAGE_KEY") 
data_context = {}

# --- 2. Alpha Vantage 价格数据获取 ---
def get_fx_data():
    """从 Alpha Vantage 获取 FX 实时价格 (USD/CNH 和 EUR/USD)"""
    
    # ... (中间获取数据的逻辑保持不变) ...

    # 修正：将 PRICE_SOURCE 修改为英文全称
    data_context["PRICE_SOURCE"] = "Alpha Vantage (AV)"

# --- 3. 真实 FRED 宏观数据调用 ---
def get_fred_data():
    """从 FRED 获取核心宏观数据和替代指标 (真实 API 调用)"""
    
    if not FRED_KEY:
        # ... (错误处理逻辑保持不变) ...
        return

    try:
        fred = Fred(api_key=FRED_KEY)
        series_ids = {
            "US10Y_YIELD": "DGS10",      # 10年期美债收益率
            "VIX_LAST": "VIXCLS",        # VIX 指数 (全球恐慌情绪)
        }
        
        for key, series_id in series_ids.items():
            data = fred.get_series_latest_release(series_id)
            if data is not None and not data.empty:
                latest_value = data.iloc[-1]
                data_context[key] = f"{latest_value}" 
                # 修正：将 SOURCE 修改为英文全称
                data_context[f"{key}_SOURCE"] = f"Federal Reserve Economic Data (FRED)"
            else:
                data_context[key] = "Data N/A (Empty)"

        # ... (NFP 特殊处理逻辑保持不变) ...
        
    except Exception as e:
        print(f"FRED 数据获取失败，请检查密钥或序列ID: {e}")

# --- 4. 统一数据检索函数 ---
def retrieve_all_data():
    get_fx_data()   
    get_fred_data() 
    return data_context