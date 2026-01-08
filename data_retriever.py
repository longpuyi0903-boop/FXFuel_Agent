# data_retriever.py - 数据采集模块（修复版 v2）

import os
import ssl
import json
import time
import re
from datetime import datetime
from typing import Dict, Any, Optional, Callable
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

# P0-2: 导入超时配置; P1: 导入缓存 TTL 配置
try:
    from config import TIMEOUT_CONFIG, CACHE_TTL
except ImportError:
    # 如果 config.py 未更新，使用默认值
    TIMEOUT_CONFIG = {
        "default": (10, 30),
        "akshare": (10, 20),
        "fred": (10, 30),
        "perplexity": (30, 90),
        "yahoo": (10, 15),
        "hkma": (10, 20),
    }
    CACHE_TTL = {
        "cny_mid": 3600,
        "cny_spot": 60,
        "hkd": 60,
        "fred": 300,
        "global_fx": 60,
        "news": 600,
    }

# SSL修复
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def create_retry_session(retries=3, backoff_factor=1):
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

RETRY_SESSION = create_retry_session()


# ============================================================================
# P1: 简单缓存模块
# ============================================================================

import time as _time
from typing import TypeVar

_cache: Dict[str, Any] = {}
_cache_time: Dict[str, float] = {}

T = TypeVar('T')

def get_with_cache(key: str, fetch_func: Callable[[], T], ttl_seconds: int) -> T:
    """
    带 TTL 的简单缓存
    
    Args:
        key: 缓存键名
        fetch_func: 获取数据的函数
        ttl_seconds: 缓存有效期（秒）
        
    Returns:
        缓存的数据或新获取的数据
        
    TTL 推荐值（参考 config.CACHE_TTL）:
    - 中间价 (cny_mid): 3600秒（9:15发布后整天不变）
    - 实时汇率 (cny_spot): 60秒
    - FRED 数据: 300秒
    - 新闻: 600秒
    """
    now = _time.time()
    if key in _cache and (now - _cache_time.get(key, 0)) < ttl_seconds:
        return _cache[key]
    
    result = fetch_func()
    _cache[key] = result
    _cache_time[key] = now
    return result


def clear_cache():
    """清除所有缓存（用于强制刷新）"""
    global _cache, _cache_time
    _cache = {}
    _cache_time = {}


class DataContext:
    def __init__(self):
        self.report_date = datetime.now().strftime("%Y-%m-%d")
        self.snapshot = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cny = {}
        self.hkd = {}
        self.global_fx = {}
        self.macro = {}
        self.news = []  # 短标题列表（用于页面展示）
        self.news_detail = []  # 详细摘要列表（用于LLM生成报告）
        self.news_sources = []
        self.data_sources = {}
        self.errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_date": self.report_date,
            "snapshot": self.snapshot,
            "cny": self.cny,
            "hkd": self.hkd,
            "global_fx": self.global_fx,
            "macro": self.macro,
            "news": self.news,
            "news_detail": self.news_detail,
            "news_sources": self.news_sources,
            "data_sources": self.data_sources,
            "errors": self.errors,
            "data_points": self._count_data_points()
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    def _count_data_points(self) -> int:
        count = 0
        for section in [self.cny, self.hkd, self.global_fx, self.macro]:
            count += len([v for v in section.values() if v is not None])
        count += len(self.news)
        return count


ProgressCallback = Callable[[int, int, str], None]


def fetch_cny_data(ctx: DataContext) -> str:
    """获取人民币数据"""
    try:
        import akshare as ak
        
        try:
            mid_df = None
            for attempt in range(3):
                try:
                    mid_df = ak.currency_boc_safe()
                    if mid_df is not None and not mid_df.empty and '美元' in mid_df.columns:
                        break
                except:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
            
            if mid_df is not None and not mid_df.empty and '美元' in mid_df.columns:
                usd_col = mid_df['美元'].astype(float) / 100
                ctx.cny["usdcny_mid"] = round(float(usd_col.iloc[-1]), 4)
                ctx.cny["usdcny_mid_date"] = str(mid_df['日期'].iloc[-1])
                ctx.data_sources["usdcny_mid"] = "国家外汇管理局"
                
                recent = usd_col.tail(5)
                ctx.cny["usdcny_mid_range"] = f"{round(recent.min(), 4)} - {round(recent.max(), 4)}"
                ctx.cny["usdcny_mid_high"] = round(recent.max(), 4)
                ctx.cny["usdcny_mid_low"] = round(recent.min(), 4)
            else:
                # API 失败或数据无效，显式设置 None
                ctx.cny["usdcny_mid"] = None
        except Exception as e:
            ctx.errors.append(f"人民币中间价: {str(e)[:80]}")
            ctx.cny["usdcny_mid"] = None
        
        try:
            fx_df = None
            for attempt in range(3):
                try:
                    fx_df = ak.forex_spot_em()
                    if fx_df is not None and not fx_df.empty:
                        break
                except:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
            
            if fx_df is not None and not fx_df.empty:
                cnh_row = fx_df[fx_df['代码'].str.contains('USDCNH', case=False, na=False)]
                if not cnh_row.empty:
                    ctx.cny["usdcnh_spot"] = float(cnh_row['最新价'].iloc[0])
                    ctx.data_sources["usdcnh"] = "东方财富"
                else:
                    # 未找到 USDCNH 数据
                    ctx.cny["usdcnh_spot"] = None
                # 计算价差（如果两个值都存在）
                if ctx.cny.get("usdcny_mid") is not None and ctx.cny.get("usdcnh_spot") is not None:
                    ctx.cny["cny_spread"] = round(ctx.cny["usdcnh_spot"] - ctx.cny["usdcny_mid"], 4)
            else:
                # API 失败或数据无效，显式设置 None
                ctx.cny["usdcnh_spot"] = None
        except Exception as e:
            ctx.errors.append(f"离岸汇率: {str(e)[:80]}")
            ctx.cny["usdcnh_spot"] = None
        
        parts = []
        if ctx.cny.get("usdcny_mid"):
            parts.append(f"中间价:{ctx.cny['usdcny_mid']}")
        if ctx.cny.get("usdcnh_spot"):
            parts.append(f"CNH:{ctx.cny['usdcnh_spot']}")
        
        return f"✅ 人民币: {', '.join(parts)}" if parts else "⚠️ 人民币数据部分缺失"
        
    except ImportError:
        ctx.errors.append("AKShare 未安装")
        return "❌ AKShare 未安装"
    except Exception as e:
        ctx.errors.append(f"人民币数据: {str(e)[:80]}")
        return "❌ 人民币数据获取失败"


def fetch_hkd_data(ctx: DataContext) -> str:
    """获取港元数据"""
    hkd_found = False
    
    try:
        import akshare as ak
        
        # 方法1: 东方财富外汇行情
        try:
            fx_df = None
            for attempt in range(3):
                try:
                    fx_df = ak.forex_spot_em()
                    if fx_df is not None and not fx_df.empty:
                        break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        ctx.errors.append(f"东方财富API: {str(e)[:40]}")
            
            if fx_df is not None and not fx_df.empty:
                hkd_row = fx_df[fx_df['代码'].str.contains('USDHKD', case=False, na=False)]
                if not hkd_row.empty:
                    usdhkd = float(hkd_row['最新价'].iloc[0])
                    ctx.hkd["usdhkd"] = usdhkd
                    ctx.data_sources["usdhkd"] = "东方财富"
                    hkd_found = True
                    
                    if usdhkd <= 7.77:
                        ctx.hkd["lers_position"] = "强方区间（接近7.75强方保证）"
                    elif usdhkd >= 7.83:
                        ctx.hkd["lers_position"] = "弱方区间（接近7.85弱方保证）"
                    else:
                        ctx.hkd["lers_position"] = "中间区间"
        except Exception as e:
            ctx.errors.append(f"港元(东方财富): {str(e)[:50]}")
        
        # 方法2: Yahoo Finance 备选
        if not hkd_found:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(
                    "https://query1.finance.yahoo.com/v8/finance/chart/HKDUSD=X?interval=1d&range=1d",
                    headers=headers,
                    timeout=TIMEOUT_CONFIG["yahoo"]
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                        meta = data['chart']['result'][0].get('meta', {})
                        hkdusd = meta.get('regularMarketPrice') or meta.get('previousClose')
                        if hkdusd:
                            usdhkd = round(1 / float(hkdusd), 4)
                            if 7.7 <= usdhkd <= 7.9:
                                ctx.hkd["usdhkd"] = usdhkd
                                ctx.data_sources["usdhkd"] = "Yahoo Finance"
                                hkd_found = True
            except Exception as e:
                ctx.errors.append(f"港元(Yahoo): {str(e)[:40]}")
        
        if not hkd_found:
            ctx.errors.append("USD/HKD: 所有数据源失败")
            ctx.hkd["usdhkd"] = None  # 显式设置 None
        
        # HIBOR 从金管局获取
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            resp = RETRY_SESSION.get(url, headers=headers, timeout=TIMEOUT_CONFIG["hkma"], verify=False)
            if resp.status_code == 200:
                data = resp.json()
                if 'result' in data and 'records' in data['result'] and data['result']['records']:
                    latest = data['result']['records'][0]
                    if 'ir_overnight' in latest:
                        ctx.hkd["hibor_overnight"] = float(latest['ir_overnight'])
                        ctx.data_sources["hibor"] = "香港金管局"
                    if 'ir_1week' in latest:
                        ctx.hkd["hibor_1w"] = float(latest['ir_1week'])
                    if 'ir_1month' in latest:
                        ctx.hkd["hibor_1m"] = float(latest['ir_1month'])
            else:
                # API 成功但数据格式不正确，显式设置 None
                if "hibor_overnight" not in ctx.hkd:
                    ctx.hkd["hibor_overnight"] = None
        except Exception as e:
            ctx.errors.append(f"HIBOR: {str(e)[:40]}")
            # API 失败，显式设置 None
            if "hibor_overnight" not in ctx.hkd:
                ctx.hkd["hibor_overnight"] = None
        
        # 计算港美利差（只有在两个值都不为 None 时才计算）
        if ctx.hkd.get("hibor_overnight") is not None and ctx.macro.get("fed_rate") is not None:
            ctx.hkd["hkd_usd_spread"] = round(ctx.hkd["hibor_overnight"] - ctx.macro["fed_rate"], 2)
        
        result = f"✅ 港元: {ctx.hkd.get('usdhkd', 'N/A')}"
        if ctx.hkd.get("hibor_overnight"):
            result += f", HIBOR:{ctx.hkd['hibor_overnight']}%"
        return result
        
    except Exception as e:
        ctx.errors.append(f"港元数据: {str(e)[:80]}")
        return "❌ 港元数据获取失败"


def fetch_dxy_direct(ctx: DataContext) -> bool:
    """直接从API获取DXY美元指数（ICE美元指数，范围约 90-115）
    
    数据源:
    1. Yahoo Finance DX-Y.NYB (ICE美元指数期货)
    2. 东方财富全球指数
    
    注意：不使用FRED贸易加权指数（范围100-130，与ICE DXY不同）
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    # 方案1: Yahoo Finance - DX-Y.NYB (ICE美元指数期货)
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=5d",
            headers=headers,
            timeout=TIMEOUT_CONFIG["yahoo"]
        )
        if resp.status_code == 200:
            data = resp.json()
            if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                result = data['chart']['result'][0]
                meta = result.get('meta', {})
                price = meta.get('regularMarketPrice') or meta.get('previousClose')
                if price:
                    dxy_val = round(float(price), 2)
                    if 90 <= dxy_val <= 115:  # ICE DXY 正常范围
                        ctx.global_fx["dxy"] = dxy_val
                        ctx.data_sources["dxy"] = "Yahoo(ICE)"
                        return True
                # 备选：从 indicators 获取
                indicators = result.get('indicators', {})
                quote = indicators.get('quote', [{}])[0]
                closes = quote.get('close', [])
                if closes:
                    for c in reversed(closes):
                        if c is not None:
                            dxy_val = round(float(c), 2)
                            if 90 <= dxy_val <= 115:
                                ctx.global_fx["dxy"] = dxy_val
                                ctx.data_sources["dxy"] = "Yahoo(ICE)"
                                return True
                            break
    except Exception as e:
        ctx.errors.append(f"DXY(Yahoo): {str(e)[:40]}")
    
    # 方案2: 东方财富全球指数（尝试多个可能的接口）
    try:
        import akshare as ak
        df = None
        # 尝试不同的接口
        for method_name in ['index_global_em', 'tool_trade_date_hist_sina']:
            try:
                if hasattr(ak, method_name):
                    if method_name == 'index_global_em':
                        df = ak.index_global_em()
                    break
            except:
                continue
        
        # 如果上述方法都失败，尝试从外汇数据中获取
        if df is None or df.empty:
            try:
                fx_df = ak.forex_spot_em()
                if fx_df is not None and not fx_df.empty:
                    dxy_row = fx_df[fx_df['名称'].str.contains('美元指数', na=False)]
                    if not dxy_row.empty:
                        dxy_val = round(float(dxy_row['最新价'].iloc[0]), 2)
                        if 90 <= dxy_val <= 115:
                            ctx.global_fx["dxy"] = dxy_val
                            ctx.data_sources["dxy"] = "东方财富"
                            return True
            except:
                pass
        
        if df is not None and not df.empty:
            dxy_row = df[df['名称'].str.contains('美元指数', na=False)]
            if not dxy_row.empty:
                dxy_val = round(float(dxy_row['最新价'].iloc[0]), 2)
                if 90 <= dxy_val <= 115:
                    ctx.global_fx["dxy"] = dxy_val
                    ctx.data_sources["dxy"] = "东方财富"
                    return True
    except Exception as e:
        ctx.errors.append(f"DXY(东方财富): {str(e)[:40]}")
    
    # 不使用FRED贸易加权指数，因为范围不同会误导用户
    ctx.errors.append("DXY: ICE美元指数获取失败")
    ctx.global_fx["dxy"] = None  # 显式设置 None
    return False


def fetch_global_fx(ctx: DataContext) -> str:
    """获取全球外汇数据（包括DXY）"""
    try:
        import akshare as ak
        
        fx_df = None
        for attempt in range(3):
            try:
                fx_df = ak.forex_spot_em()
                if fx_df is not None and not fx_df.empty:
                    break
            except:
                if attempt < 2:
                    time.sleep(2 ** attempt)
        
        found = []
        
        if fx_df is not None and not fx_df.empty:
            pairs = {
                "EURUSD": "eurusd",
                "USDJPY": "usdjpy", 
                "GBPUSD": "gbpusd",
                "AUDUSD": "audusd",
                "USDCAD": "usdcad",
                "USDCHF": "usdchf"
            }
            
            for code, key in pairs.items():
                try:
                    row = fx_df[fx_df['代码'].str.contains(code, case=False, na=False)]
                    if not row.empty:
                        ctx.global_fx[key] = float(row['最新价'].iloc[0])
                        found.append(code)
                except:
                    pass
            
            # 尝试从东方财富获取DXY
            try:
                dxy_row = fx_df[fx_df['名称'].str.contains('美元指数', na=False)]
                if not dxy_row.empty:
                    dxy_val = round(float(dxy_row['最新价'].iloc[0]), 2)
                    if 80 <= dxy_val <= 120:
                        ctx.global_fx["dxy"] = dxy_val
                        ctx.data_sources["dxy"] = "东方财富"
                        found.append("DXY")
            except:
                pass
        
        # 如果DXY还没获取到，使用直接API
        if "dxy" not in ctx.global_fx:
            if fetch_dxy_direct(ctx):
                found.append("DXY")
        
        if "dxy" not in ctx.global_fx:
            ctx.errors.append("DXY: 所有数据源均失败")
            ctx.global_fx["dxy"] = None  # 显式设置 None
        
        return f"✅ 全球外汇: {', '.join(found)}" if found else "⚠️ 全球外汇数据缺失"
        
    except Exception as e:
        # 即使AKShare失败，也尝试获取DXY
        if fetch_dxy_direct(ctx):
            return f"✅ DXY: {ctx.global_fx.get('dxy')}"
        ctx.errors.append(f"全球外汇: {str(e)[:80]}")
        return "❌ 全球外汇获取失败"


def fetch_fred_data(ctx: DataContext) -> str:
    """获取 FRED 宏观数据"""
    fred_key = os.getenv("FRED_API_KEY")
    if not fred_key:
        ctx.errors.append("FRED_API_KEY 未配置")
        return "⚠️ FRED 未配置"
    
    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_key)
        results = []
        
        try:
            us10y = fred.get_series_latest_release("DGS10")
            if us10y is not None and not us10y.empty:
                ctx.macro["us10y"] = round(float(us10y.iloc[-1]), 2)
                ctx.data_sources["us10y"] = "FRED"
                results.append("10Y")
            else:
                ctx.macro["us10y"] = None  # API 返回空数据，显式设置 None
        except Exception as e:
            ctx.errors.append(f"US10Y: {str(e)[:40]}")
            ctx.macro["us10y"] = None  # API 失败，显式设置 None
        
        try:
            us2y = fred.get_series_latest_release("DGS2")
            if us2y is not None and not us2y.empty:
                ctx.macro["us2y"] = round(float(us2y.iloc[-1]), 2)
                results.append("2Y")
            else:
                ctx.macro["us2y"] = None  # API 返回空数据，显式设置 None
        except Exception as e:
            ctx.errors.append(f"US2Y: {str(e)[:40]}")
            ctx.macro["us2y"] = None  # API 失败，显式设置 None
        
        # 计算收益率曲线（只有在两个值都不为 None 时才计算）
        if ctx.macro.get("us10y") is not None and ctx.macro.get("us2y") is not None:
            ctx.macro["yield_curve"] = round(ctx.macro["us10y"] - ctx.macro["us2y"], 2)
        
        try:
            vix = fred.get_series_latest_release("VIXCLS")
            if vix is not None and not vix.empty:
                vix_val = round(float(vix.iloc[-1]), 2)
                ctx.macro["vix"] = vix_val
                ctx.data_sources["vix"] = "CBOE/FRED"
                results.append("VIX")
                
                if vix_val < 15:
                    ctx.macro["market_sentiment"] = "乐观（低恐慌）"
                elif vix_val < 20:
                    ctx.macro["market_sentiment"] = "中性"
                elif vix_val < 30:
                    ctx.macro["market_sentiment"] = "谨慎"
                else:
                    ctx.macro["market_sentiment"] = "恐慌"
            else:
                ctx.macro["vix"] = None  # API 返回空数据，显式设置 None
        except Exception as e:
            ctx.errors.append(f"VIX: {str(e)[:40]}")
            ctx.macro["vix"] = None  # API 失败，显式设置 None
        
        try:
            ffr = fred.get_series_latest_release("FEDFUNDS")
            if ffr is not None and not ffr.empty:
                ctx.macro["fed_rate"] = round(float(ffr.iloc[-1]), 2)
                results.append("FedRate")
            else:
                ctx.macro["fed_rate"] = None  # API 返回空数据，显式设置 None
        except Exception as e:
            ctx.errors.append(f"FedRate: {str(e)[:40]}")
            ctx.macro["fed_rate"] = None  # API 失败，显式设置 None
        
        return f"✅ FRED: {', '.join(results)}" if results else "⚠️ FRED 数据缺失"
        
    except Exception as e:
        ctx.errors.append(f"FRED: {str(e)[:80]}")
        return "❌ FRED 获取失败"


def fetch_perplexity_news(ctx: DataContext) -> str:
    """使用 Perplexity API 获取外汇相关新闻
    
    方案B：分两次调用，分别搜索英文和中文来源
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        ctx.errors.append("PERPLEXITY_API_KEY 未配置")
        return "⚠️ Perplexity 未配置"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 计算日期范围
    from datetime import timedelta
    today_date = datetime.now()
    week_ago = today_date - timedelta(days=7)
    today_display = today_date.strftime("%B %d, %Y")
    week_ago_display = week_ago.strftime("%B %d, %Y")
    today_cn = today_date.strftime("%Y年%m月%d日")
    week_ago_cn = week_ago.strftime("%Y年%m月%d日")
    
    # 配置代理
    proxies = None
    socks5_proxy = os.getenv("SOCKS5_PROXY")
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    
    if socks5_proxy:
        try:
            import socks
            if not socks5_proxy.startswith("socks5://"):
                socks5_url = f"socks5h://{socks5_proxy}"
            else:
                socks5_url = socks5_proxy.replace("socks5://", "socks5h://")
            proxies = {"http": socks5_url, "https": socks5_url}
        except ImportError:
            ctx.errors.append("需要: pip install requests[socks]")
    elif http_proxy or https_proxy:
        proxies = {"http": http_proxy, "https": https_proxy or http_proxy}
    
    # ========== 英文 Prompt ==========
    payload_en = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": f"""You are an FX market news editor. Search ONLY English sources from {week_ago_display} to {today_display}.

Sources: Bloomberg, Reuters, Financial Times, WSJ, Federal Reserve, ECB, BOJ.

Output format - for each news item:
1. [EN]
TITLE: Headline here [1]
DETAIL: 150-200 word summary with specific data [1]

2. [EN]
TITLE: Next headline [2]
DETAIL: Summary [2]

IMPORTANT: 
- Each news starts with number and [EN] on its own line
- TITLE and DETAIL on separate lines
- Every line must end with citation [1], [2], etc."""
            },
            {
                "role": "user", 
                "content": f"Find 8 important English FX news. Topics: Fed/FOMC, DXY, EUR/USD, USD/JPY, Treasury yields. Use the exact format specified."
            }
        ],
        "max_tokens": 4000,
        "temperature": 0.1,
        "return_citations": True,
        "search_recency_filter": "week"
    }
    
    # ========== 中文 Prompt ==========
    payload_cn = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": f"""你是外汇市场新闻编辑。只搜索 {week_ago_cn} 至 {today_cn} 的中文来源。

来源：央行官网(pbc.gov.cn)、外管局(safe.gov.cn)、财新网、第一财经、金管局(hkma.gov.hk)。

输出格式 - 每条新闻：
1. [CN]
TITLE: 标题内容 [1]
DETAIL: 150-200字摘要，包含具体数据 [1]

2. [CN]
TITLE: 下一条标题 [2]
DETAIL: 摘要内容 [2]

重要：
- 每条新闻以数字和[CN]开头，单独一行
- TITLE和DETAIL分开两行
- 每行结尾必须有引用标记[1], [2]等"""
            },
            {
                "role": "user", 
                "content": f"搜索7条重要中文外汇新闻。主题：人民币中间价、USD/CNY、央行政策、港元、金管局。严格按照指定格式输出。"
            }
        ],
        "max_tokens": 3500,
        "temperature": 0.1,
        "return_citations": True,
        "search_recency_filter": "week"
    }
    
    # ========== 解析函数 ==========
    def parse_response(content, citations, lang_tag):
        """解析 Perplexity 返回内容"""
        # 提取有效 URLs
        valid_urls = []
        for c in citations:
            if isinstance(c, str) and c.startswith('http'):
                valid_urls.append(c)
            elif isinstance(c, dict):
                url = c.get('url') or c.get('link')
                if url and url.startswith('http'):
                    valid_urls.append(url)
        
        lines = content.strip().split('\n')
        news_items = []
        current = {'title': '', 'detail': '', 'refs': []}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测新闻开始: "1. [EN]" 或 "1. [CN]" 或 "1.[EN]" 等
            start_match = re.match(r'^(\d+)[\.\)]\s*\[(EN|CN)\]\s*$', line, re.IGNORECASE)
            if start_match:
                # 保存上一条
                if current['title']:
                    news_items.append(current.copy())
                current = {'title': '', 'detail': '', 'refs': []}
                continue
            
            # 检测 TITLE 行
            if line.upper().startswith('TITLE:'):
                # 提取引用标记
                refs = re.findall(r'\[(\d+)\]', line)
                current['refs'].extend([int(r)-1 for r in refs if r.isdigit()])
                # 清除引用标记后存储
                current['title'] = re.sub(r'\s*\[\d+\]\s*', ' ', line[6:]).strip()
                continue
            
            # 检测 DETAIL 行
            if line.upper().startswith('DETAIL:'):
                refs = re.findall(r'\[(\d+)\]', line)
                current['refs'].extend([int(r)-1 for r in refs if r.isdigit()])
                current['detail'] = re.sub(r'\s*\[\d+\]\s*', ' ', line[7:]).strip()
                continue
            
            # 累积 DETAIL（多行情况）
            if current['title'] and not re.match(r'^\d+[\.\)]\s*\[', line):
                refs = re.findall(r'\[(\d+)\]', line)
                current['refs'].extend([int(r)-1 for r in refs if r.isdigit()])
                clean = re.sub(r'\s*\[\d+\]\s*', ' ', line).strip()
                if clean and not clean.startswith('#'):
                    current['detail'] += ' ' + clean
        
        # 保存最后一条
        if current['title']:
            news_items.append(current.copy())
        
        # 构建结果
        results = []
        for item in news_items:
            title = f"[{lang_tag}] TITLE: {item['title']}"
            detail = item['detail'] if item['detail'] else item['title']
            # 分配 URLs
            urls = []
            for ref_idx in set(item['refs']):
                if 0 <= ref_idx < len(valid_urls):
                    urls.append(valid_urls[ref_idx])
            results.append((title, detail, urls))
        
        return results, len(valid_urls)
    
    # ========== 执行 API 调用 ==========
    all_news = []
    total_urls = 0
    en_count = 0
    cn_count = 0
    
    try:
        session = requests.Session()
        
        # 调用英文 API
        try:
            resp_en = session.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers, json=payload_en,
                timeout=TIMEOUT_CONFIG["perplexity"], verify=False, proxies=proxies  # verify=False 为兼容代理环境
            )
            if resp_en.status_code == 200:
                result = resp_en.json()
                content = result['choices'][0]['message']['content']
                citations = result.get('citations', [])
                if not citations:
                    citations = result['choices'][0].get('message', {}).get('citations', [])
                news_en, urls_en = parse_response(content, citations, 'EN')
                all_news.extend(news_en)
                total_urls += urls_en
                en_count = len(news_en)
            else:
                ctx.errors.append(f"Perplexity EN: {resp_en.status_code}")
        except Exception as e:
            ctx.errors.append(f"Perplexity EN: {str(e)[:50]}")
        
        # 调用中文 API
        try:
            resp_cn = session.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers, json=payload_cn,
                timeout=TIMEOUT_CONFIG["perplexity"], verify=False, proxies=proxies  # verify=False 为兼容代理环境
            )
            if resp_cn.status_code == 200:
                result = resp_cn.json()
                content = result['choices'][0]['message']['content']
                citations = result.get('citations', [])
                if not citations:
                    citations = result['choices'][0].get('message', {}).get('citations', [])
                news_cn, urls_cn = parse_response(content, citations, 'CN')
                all_news.extend(news_cn)
                total_urls += urls_cn
                cn_count = len(news_cn)
            else:
                ctx.errors.append(f"Perplexity CN: {resp_cn.status_code}")
        except Exception as e:
            ctx.errors.append(f"Perplexity CN: {str(e)[:50]}")
        
        # 存储结果
        news_with_urls = 0
        for title, detail, urls in all_news:
            ctx.news.append(title)
            ctx.news_detail.append(detail)
            ctx.news_sources.append(urls)
            if urls:
                news_with_urls += 1
        
        ctx.data_sources["news"] = "Perplexity(EN+CN)"
        ctx.data_sources["news_valid_urls"] = total_urls
        
        return f"✅ 新闻: {len(all_news)} 条 (EN:{en_count} + CN:{cn_count}, 有链接: {news_with_urls}/{len(all_news)})"
        
    except Exception as e:
        ctx.errors.append(f"Perplexity: {str(e)[:60]}")
        return f"⚠️ Perplexity: {str(e)[:40]}"


def calculate_metrics(ctx: DataContext) -> str:
    results = []
    
    # 计算港美利差（只有在两个值都不为 None 且还未计算时）
    if (ctx.hkd.get("hibor_overnight") is not None and 
        ctx.macro.get("fed_rate") is not None and 
        "hkd_usd_spread" not in ctx.hkd):
        ctx.hkd["hkd_usd_spread"] = round(ctx.hkd["hibor_overnight"] - ctx.macro["fed_rate"], 2)
        results.append("港美利差")
    
    # 计算 CNY 价差（只有在两个值都不为 None 且还未计算时）
    if (ctx.cny.get("usdcny_mid") is not None and 
        ctx.cny.get("usdcnh_spot") is not None and 
        "cny_spread" not in ctx.cny):
        ctx.cny["cny_spread"] = round(ctx.cny["usdcnh_spot"] - ctx.cny["usdcny_mid"], 4)
        results.append("CNY价差")
    
    return f"✅ 计算完成"


def retrieve_all_data(progress_callback: Optional[ProgressCallback] = None) -> DataContext:
    ctx = DataContext()
    
    steps = [
        ("FRED 宏观数据", lambda: fetch_fred_data(ctx)),
        ("人民币数据", lambda: fetch_cny_data(ctx)),
        ("港元数据", lambda: fetch_hkd_data(ctx)),
        ("全球外汇", lambda: fetch_global_fx(ctx)),
        ("Perplexity 新闻", lambda: fetch_perplexity_news(ctx)),
        ("计算衍生指标", lambda: calculate_metrics(ctx)),
    ]
    
    total = len(steps)
    
    for i, (name, func) in enumerate(steps):
        if progress_callback:
            progress_callback(i, total, f"📊 {name}...")
        
        try:
            result = func()
            if progress_callback:
                progress_callback(i + 1, total, result)
        except Exception as e:
            ctx.errors.append(f"{name}: {str(e)[:50]}")
            if progress_callback:
                progress_callback(i + 1, total, f"❌ {name} 失败")
    
    return ctx


if __name__ == "__main__":
    def print_progress(step, total, msg):
        print(f"[{step}/{total}] {msg}")
    
    ctx = retrieve_all_data(print_progress)
    print("\n" + "="*60)
    print(ctx.to_json())
