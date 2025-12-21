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


class DataContext:
    def __init__(self):
        self.report_date = datetime.now().strftime("%Y-%m-%d")
        self.snapshot = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cny = {}
        self.hkd = {}
        self.global_fx = {}
        self.macro = {}
        self.news = []
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
        except Exception as e:
            ctx.errors.append(f"人民币中间价: {str(e)[:80]}")
        
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
                
                if ctx.cny.get("usdcny_mid") and ctx.cny.get("usdcnh_spot"):
                    ctx.cny["cny_spread"] = round(ctx.cny["usdcnh_spot"] - ctx.cny["usdcny_mid"], 4)
        except Exception as e:
            ctx.errors.append(f"离岸汇率: {str(e)[:80]}")
        
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
                    timeout=15
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
        
        # HIBOR 从金管局获取
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            resp = RETRY_SESSION.get(url, headers=headers, timeout=30, verify=False)
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
        except Exception as e:
            ctx.errors.append(f"HIBOR: {str(e)[:40]}")
        
        if ctx.hkd.get("hibor_overnight") and ctx.macro.get("fed_rate"):
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
            timeout=15
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
    
    # 方案2: 东方财富全球指数
    try:
        import akshare as ak
        df = ak.index_global_em()
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
        except:
            pass
        
        try:
            us2y = fred.get_series_latest_release("DGS2")
            if us2y is not None and not us2y.empty:
                ctx.macro["us2y"] = round(float(us2y.iloc[-1]), 2)
                results.append("2Y")
        except:
            pass
        
        if ctx.macro.get("us10y") and ctx.macro.get("us2y"):
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
        except:
            pass
        
        try:
            ffr = fred.get_series_latest_release("FEDFUNDS")
            if ffr is not None and not ffr.empty:
                ctx.macro["fed_rate"] = round(float(ffr.iloc[-1]), 2)
                results.append("FedRate")
        except:
            pass
        
        return f"✅ FRED: {', '.join(results)}" if results else "⚠️ FRED 数据缺失"
        
    except Exception as e:
        ctx.errors.append(f"FRED: {str(e)[:80]}")
        return "❌ FRED 获取失败"


def fetch_perplexity_news(ctx: DataContext) -> str:
    """使用 Perplexity API 获取外汇相关新闻
    
    范围：人民币/港元/G10货币对美元、各国央行政策
    来源：权威财经媒体+央行官网
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        ctx.errors.append("PERPLEXITY_API_KEY 未配置")
        return "⚠️ Perplexity 未配置"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    today = datetime.now().strftime("%Y年%m月%d日")
    
    payload = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "system",
                "content": """你是专业外汇市场新闻编辑。

【新闻范围】
1. 人民币(USD/CNY, USD/CNH)：中间价、离岸在岸价差、中国央行(PBOC)、外管局(SAFE)政策
2. 港元(USD/HKD)：联系汇率、香港金管局(HKMA)操作、HIBOR
3. G10货币对美元：EUR/USD、USD/JPY、GBP/USD、AUD/USD、USD/CAD、USD/CHF等
4. 各国央行政策：美联储(Fed/FOMC)、欧央行(ECB)、日本央行(BOJ)、英国央行(BOE)等
5. 美元指数(DXY)、美债收益率、VIX、风险情绪

【输出格式】
直接输出新闻内容，每条一行，用数字编号。不要标注来源名称。

示例：
1. 美联储12月FOMC会议宣布降息25基点至4.25%-4.50%，但点阵图显示2025年仅预期降息两次
2. 中国央行将人民币中间价设定为7.1876，连续第三日维持在7.19下方
3. 香港金管局入市买入18.46亿港元，为本月第四次捍卫联系汇率

注意：
- 所有货币对以美元为基准（USD/JPY，不要JPY/USD）
- 只报道事实，不要加"据XX报道"这类来源标注
- 新闻要具体、有数据支撑"""
            },
            {
                "role": "user", 
                "content": f"""搜索{today}前后一周的外汇市场重要新闻：

1. 美联储/FOMC最新政策和官员讲话
2. 中国央行/外管局政策、人民币中间价和汇率走势
3. 香港金管局操作、港元和HIBOR动态
4. 其他G10货币（EUR/USD、USD/JPY、GBP/USD等）重大变动
5. 影响汇市的宏观数据和风险事件

列出10-12条最重要的新闻，要求具体、有数据。"""
            }
        ],
        "max_tokens": 2500,
        "temperature": 0.1,
        "return_citations": True,
        "search_recency_filter": "week"
    }
    
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
            ctx.data_sources["perplexity_proxy"] = f"SOCKS5"
        except ImportError:
            ctx.errors.append("需要: pip install requests[socks]")
            proxies = None
    elif http_proxy or https_proxy:
        proxies = {"http": http_proxy, "https": https_proxy or http_proxy}
        ctx.data_sources["perplexity_proxy"] = "HTTP代理"
    else:
        ctx.data_sources["perplexity_proxy"] = "直连"
    
    try:
        session = requests.Session()
        response = session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=(30, 120),
            verify=False,
            proxies=proxies
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            # Perplexity 的 citations 是一个URL数组
            citations = result.get('citations', [])
            
            lines = content.strip().split('\n')
            news_count = 0
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('---') or line.startswith('【'):
                    continue
                
                # 清理行首的编号和符号
                news_content = re.sub(r'^[\d]+[.、)\]\s]+', '', line).strip()
                news_content = news_content.lstrip('•*- ').strip()
                
                if news_content and len(news_content) > 20:
                    # 方法1: 从新闻内容中提取引用标记 [1], [2][3] 等
                    ref_matches = re.findall(r'\[(\d+)\]', news_content)
                    
                    urls = []
                    if ref_matches:
                        # 有引用标记，按标记匹配
                        for ref in ref_matches:
                            ref_idx = int(ref) - 1
                            if 0 <= ref_idx < len(citations):
                                citation = citations[ref_idx]
                                if isinstance(citation, str) and citation.startswith('http'):
                                    if citation not in urls:
                                        urls.append(citation)
                        # 清理引用标记
                        news_content = re.sub(r'\s*\[\d+\]\s*', ' ', news_content).strip()
                    else:
                        # 方法2: 没有引用标记，按顺序分配 citations
                        if news_count < len(citations):
                            citation = citations[news_count]
                            if isinstance(citation, str) and citation.startswith('http'):
                                urls.append(citation)
                    
                    ctx.news.append(news_content)
                    ctx.news_sources.append(urls if urls else [])
                    news_count += 1
            
            ctx.data_sources["news"] = "Perplexity搜索"
            ctx.data_sources["news_citations_count"] = len(citations)
            return f"✅ 新闻: {news_count} 条 (引用源: {len(citations)}个)"
        else:
            error_msg = f"API错误 {response.status_code}"
            try:
                err_json = response.json()
                error_msg += f": {err_json.get('error', {}).get('message', '')[:50]}"
            except:
                pass
            ctx.errors.append(f"Perplexity: {error_msg}")
            return f"❌ Perplexity: {error_msg}"
            
    except requests.exceptions.Timeout:
        ctx.errors.append("Perplexity: 连接超时")
        return "⚠️ Perplexity: 超时"
    except Exception as e:
        ctx.errors.append(f"Perplexity: {str(e)[:60]}")
        return f"⚠️ Perplexity: {str(e)[:40]}"


def calculate_metrics(ctx: DataContext) -> str:
    results = []
    
    if ctx.hkd.get("hibor_overnight") and ctx.macro.get("fed_rate") and not ctx.hkd.get("hkd_usd_spread"):
        ctx.hkd["hkd_usd_spread"] = round(ctx.hkd["hibor_overnight"] - ctx.macro["fed_rate"], 2)
        results.append("港美利差")
    
    if ctx.cny.get("usdcny_mid") and ctx.cny.get("usdcnh_spot") and not ctx.cny.get("cny_spread"):
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
