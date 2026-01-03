#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 Perplexity API 连接和 SOCKS5 代理"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# 获取配置
api_key = os.getenv("PERPLEXITY_API_KEY")
socks5_proxy = os.getenv("SOCKS5_PROXY") or os.getenv("socks5_proxy")

print("=" * 60)
print("Perplexity API 连接诊断")
print("=" * 60)
print(f"API Key: {'已配置' if api_key else '❌ 未配置'}")
print(f"SOCKS5代理: {socks5_proxy if socks5_proxy else '❌ 未配置'}")
print()

# 配置代理
proxies = None
if socks5_proxy:
    if not socks5_proxy.startswith("socks5://"):
        socks5_url = f"socks5://{socks5_proxy}"
    else:
        socks5_url = socks5_proxy
    proxies = {
        "http": socks5_url,
        "https": socks5_url
    }
    print(f"使用代理: {socks5_url}")

print("\n" + "-" * 60)
print("测试1: 基本连接测试（api.perplexity.ai）")
print("-" * 60)
try:
        start = time.time()
        resp = requests.get(
            "https://api.perplexity.ai",
            proxies=proxies,
            timeout=(5, 30),  # 连接5秒，读取30秒
            verify=False
        )
        elapsed = time.time() - start
        print(f"✅ 连接成功: {elapsed:.2f}秒, 状态码: {resp.status_code}")
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ 连接失败: {elapsed:.2f}秒")
    print(f"   错误: {type(e).__name__}: {str(e)[:100]}")

print("\n" + "-" * 60)
print("测试2: DNS 解析测试")
print("-" * 60)
import socket
try:
    start = time.time()
    ip = socket.gethostbyname("api.perplexity.ai")
    elapsed = time.time() - start
    print(f"✅ DNS解析成功: {ip}, 耗时: {elapsed:.2f}秒")
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ DNS解析失败: {elapsed:.2f}秒")
    print(f"   错误: {type(e).__name__}: {str(e)}")

print("\n" + "-" * 60)
print("测试3: 实际 API 请求（简化版）")
print("-" * 60)
if not api_key:
    print("⚠️ 跳过：API Key 未配置")
else:
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "user", "content": "测试"}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        start = time.time()
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=(10, 30),  # 连接10秒，读取30秒
            verify=False
        )
        elapsed = time.time() - start
        print(f"✅ API请求成功: {elapsed:.2f}秒, 状态码: {resp.status_code}")
        if resp.status_code == 200:
            result = resp.json()
            print(f"   响应包含: {len(str(result))} 字符")
        else:
            print(f"   响应: {resp.text[:200]}")
    except requests.exceptions.ConnectTimeout:
        elapsed = time.time() - start
        print(f"❌ 连接超时: {elapsed:.2f}秒")
        print("   💡 10秒内无法建立TCP连接")
        print("   💡 可能原因: 代理未正确工作或网络问题")
    except requests.exceptions.ReadTimeout:
        elapsed = time.time() - start
        print(f"❌ 读取超时: {elapsed:.2f}秒")
        print("   💡 30秒内未收到API响应")
        print("   💡 可能原因: API服务器响应慢或请求被阻塞")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ 请求失败: {elapsed:.2f}秒")
        print(f"   错误类型: {type(e).__name__}")
        print(f"   错误信息: {str(e)[:200]}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)

