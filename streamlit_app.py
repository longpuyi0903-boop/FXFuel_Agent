# streamlit_app.py - 外汇周报 Agent（修复重复采集问题）

import streamlit as st
import datetime
import traceback
import re

# --- 页面配置 ---
st.set_page_config(page_title="外汇周报生成器", layout="wide")
st.title("📊 外汇周报生成器")

# --- Session State 初始化 ---
if 'report_text' not in st.session_state:
    st.session_state['report_text'] = ""
if 'pitch_ready' not in st.session_state:
    st.session_state['pitch_ready'] = False
if 'data_context' not in st.session_state:
    st.session_state['data_context'] = None
if 'messages' not in st.session_state:
    st.session_state['messages'] = []
if 'data_collected' not in st.session_state:
    st.session_state['data_collected'] = False
if 'validation_result' not in st.session_state:
    st.session_state['validation_result'] = None

CHAT_HISTORY_LIMIT = 3
today = datetime.date.today()
REPORT_DATE = today.strftime("%Y年%m月%d日")
REPORT_PERIOD = f"截至 {REPORT_DATE}"


# ==============================================================================
# 工具函数
# ==============================================================================

def _mark_historical_comparisons(text: str) -> str:
    """
    识别报告中的历史对比表述，并使用下划线标记
    
    只标记真正的历史对比表述，不标记数据中的日期、年份
    """
    marked_text = text
    
    # 只标记明确的历史对比表述，避免标记数据中的日期
    # 1. 完整的历史对比短语（优先级最高）
    marked_text = re.sub(r'(?<!__)从形态上看(?!__)', r'__从形态上看__', marked_text)
    marked_text = re.sub(r'(?<!__)形态上类似(?!__)', r'__形态上类似__', marked_text)
    marked_text = re.sub(r'(?<!__)类似于(?!__)', r'__类似于__', marked_text)
    
    # 2. "历史" + 高点/低点等（但排除数据日期，如"2025年"这类具体日期）
    # 使用更精确的匹配：历史+高点/低点，且不在数据上下文中
    marked_text = re.sub(r'(?<![\d年月日])历史(高点|低点|峰值|高位|低位)(?![\d年月日])', r'__历史\1__', marked_text)
    
    # 3. 历史对比词（避免匹配数据中的"之前"、"过去"等）
    # 只在明确的历史对比语境中标记（如"较之前"、"较过去"等）
    marked_text = re.sub(r'较(过去|之前|以往)(?![\d年月日])', r'较__\1__', marked_text)
    marked_text = re.sub(r'比(过去|之前|以往)(?![\d年月日])', r'比__\1__', marked_text)
    
    # 4. 高点/低点（只在明确的对比语境中标记，避免标记数据中的"高点"、"低点"）
    # 例如"创历史高点"、"接近历史低点"等，但不标记"最高点7.328"这种数据表述
    marked_text = re.sub(r'(创|接近|触及|达到)(高点|低点|峰值|高位|低位)(?![\d\.])', r'\1__\2__', marked_text)
    
    # 不再标记年份，因为会误标记数据中的日期
    # 不再标记单独的"类似"、"过去"等词，避免误匹配
    
    return marked_text


# ==============================================================================
# 数据采集函数
# ==============================================================================
def do_collect_data(progress_callback=None):
    """执行数据采集，返回 ctx dict"""
    from data_retriever import retrieve_all_data
    
    ctx_obj = retrieve_all_data(progress_callback=progress_callback)
    
    # 转换为 dict 格式
    ctx = {
        "SNAPSHOT": ctx_obj.snapshot,
        "USDCNH_CLOSE": ctx_obj.cny.get("usdcnh_spot"),
        "USDCNY_MID": ctx_obj.cny.get("usdcny_mid"),
        "USDCNY_MID_DATE": ctx_obj.cny.get("usdcny_mid_date", ""),
        "USDCNY_MID_RANGE": ctx_obj.cny.get("usdcny_mid_range"),
        "USDCNY_MID_HIGH": ctx_obj.cny.get("usdcny_mid_high"),
        "USDCNY_MID_LOW": ctx_obj.cny.get("usdcny_mid_low"),
        "CNY_SPREAD": ctx_obj.cny.get("cny_spread"),
        "USDHKD": ctx_obj.hkd.get("usdhkd"),
        "HIBOR_OVERNIGHT": ctx_obj.hkd.get("hibor_overnight"),
        "HIBOR_1W": ctx_obj.hkd.get("hibor_1w"),
        "HIBOR_1M": ctx_obj.hkd.get("hibor_1m"),
        "HKD_USD_SPREAD": ctx_obj.hkd.get("hkd_usd_spread"),
        "LERS_POSITION": ctx_obj.hkd.get("lers_position"),
        "EURUSD": ctx_obj.global_fx.get("eurusd"),
        "USDJPY": ctx_obj.global_fx.get("usdjpy"),
        "GBPUSD": ctx_obj.global_fx.get("gbpusd"),
        "AUDUSD": ctx_obj.global_fx.get("audusd"),
        "USDCAD": ctx_obj.global_fx.get("usdcad"),
        "USDCHF": ctx_obj.global_fx.get("usdchf"),
        "DXY": ctx_obj.global_fx.get("dxy"),
        "US10Y_YIELD": ctx_obj.macro.get("us10y"),
        "US2Y_YIELD": ctx_obj.macro.get("us2y"),
        "YIELD_CURVE": ctx_obj.macro.get("yield_curve"),
        "VIX_LAST": ctx_obj.macro.get("vix"),
        "FED_RATE": ctx_obj.macro.get("fed_rate"),
        "MARKET_SENTIMENT": ctx_obj.macro.get("market_sentiment"),
        "NEWS": ctx_obj.news,  # 短标题（用于页面展示）
        "NEWS_DETAIL": ctx_obj.news_detail,  # 详细摘要（用于LLM生成报告）
        "NEWS_SOURCES": ctx_obj.news_sources,
        "ERRORS": ctx_obj.errors,
        "data_points": ctx_obj._count_data_points(),
    }
    return ctx


# ==============================================================================
# 侧边栏
# ==============================================================================
with st.sidebar:
    st.header("⚙️ 控制面板")
    
    # 刷新数据按钮
    if st.button("🔄 刷新数据", use_container_width=True):
        st.session_state['data_context'] = None
        st.session_state['data_collected'] = False
        st.session_state['report_text'] = ""
        st.session_state['messages'] = []
        st.session_state['validation_result'] = None
        st.rerun()
    
    # 生成报告按钮 - 检查data_context是否存在
    has_data = st.session_state.get('data_collected', False) and st.session_state.get('data_context') is not None
    generate_btn = st.button("📝 生成周报", use_container_width=True, type="primary", 
                             disabled=not has_data)
    
    # 数据状态
    if st.session_state.get('data_context'):
        ctx = st.session_state['data_context']
        st.markdown("---")
        st.subheader("📊 数据状态")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("数据点", ctx.get('data_points', 0))
        with col2:
            st.metric("错误", len(ctx.get('ERRORS', [])))
        
        news_count = len(ctx.get('NEWS', []))
        st.caption(f"📰 新闻: {news_count}条")
        
        if ctx.get('ERRORS'):
            with st.expander("⚠️ 查看错误"):
                for err in ctx['ERRORS']:
                    st.caption(f"• {err}")
        
        with st.expander("🔍 原始数据"):
            st.json(ctx)
    
    st.markdown("---")
    st.caption(f"更新: {datetime.datetime.now().strftime('%H:%M:%S')}")


# ==============================================================================
# 主界面：数据采集
# ==============================================================================

st.subheader("📊 实时数据摘要")

# 检查是否已有数据
if not st.session_state.get('data_collected', False):
    st.info("👆 点击「刷新数据」或下方按钮开始采集")
    
    if st.button("🚀 开始采集数据", use_container_width=True):
        try:
            with st.status("📡 正在连接权威数据源...", expanded=True) as status:
                status.write("📡 正在连接权威数据源 (外管局/FRED/AKShare)...")
                
                def update_progress(step, total, msg):
                    status.write(msg)
                
                ctx = do_collect_data(progress_callback=update_progress)
                
                status.write("🔍 数据清洗与格式化...")
                status.write("✅ 数据采集完成")
            
            # 保存到 session state
            st.session_state['data_context'] = ctx
            st.session_state['data_collected'] = True
            
            st.success(f"✅ 数据就绪！共 {ctx['data_points']} 个数据点，{len(ctx.get('NEWS', []))} 条新闻")
            
            # 自动刷新页面以显示数据
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 数据采集失败: {str(e)}")
            st.code(traceback.format_exc())

else:
    # 显示已采集的数据
    ctx = st.session_state['data_context']
    
    if ctx:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            mid = ctx.get('USDCNY_MID')
            st.metric("USD/CNY 中间价", mid if mid else "N/A")
            if ctx.get('USDCNY_MID_RANGE'):
                st.caption(f"周区间: {ctx['USDCNY_MID_RANGE']}")
        
        with col2:
            hkd = ctx.get('USDHKD')
            st.metric("USD/HKD", round(hkd, 4) if hkd else "N/A")
            lers = ctx.get('LERS_POSITION', '')
            if lers:
                st.caption(lers)
        
        with col3:
            dxy = ctx.get('DXY')
            st.metric("美元指数 (DXY)", dxy if dxy else "N/A")
        
        with col4:
            vix = ctx.get('VIX_LAST')
            st.metric("VIX 恐慌指数", vix if vix else "N/A")
            sentiment = ctx.get('MARKET_SENTIMENT', '')
            if sentiment:
                st.caption(sentiment)
        
        with st.expander("📈 更多数据详情"):
            c1, c2, c3 = st.columns(3)
            
            with c1:
                st.markdown("**人民币**")
                st.write(f"离岸 CNH: {ctx.get('USDCNH_CLOSE', 'N/A')}")
                spread = ctx.get('CNY_SPREAD')
                if spread:
                    st.write(f"价差: {spread}")
            
            with c2:
                st.markdown("**港元**")
                hibor = ctx.get('HIBOR_OVERNIGHT')
                st.write(f"HIBOR隔夜: {hibor}%" if hibor else "HIBOR隔夜: N/A")
                hkd_spread = ctx.get('HKD_USD_SPREAD')
                st.write(f"港美利差: {hkd_spread}%" if hkd_spread else "港美利差: N/A")
            
            with c3:
                st.markdown("**全球**")
                us10y = ctx.get('US10Y_YIELD')
                st.write(f"10Y美债: {us10y}%" if us10y else "10Y美债: N/A")
                st.write(f"EUR/USD: {ctx.get('EURUSD', 'N/A')}")
                st.write(f"USD/JPY: {ctx.get('USDJPY', 'N/A')}")
                fed = ctx.get('FED_RATE')
                st.write(f"联邦基金利率: {fed}%" if fed else "联邦基金利率: N/A")
        
        # 显示新闻
        news_list = ctx.get('NEWS', [])
        news_sources = ctx.get('NEWS_SOURCES', [])
        if news_list:
            with st.expander(f"📰 本周新闻 ({len(news_list)}条)", expanded=True):
                for i, item in enumerate(news_list[:12]):
                    news_text = item if isinstance(item, str) else str(item)
                    
                    # 获取对应的URLs（可能有多个）
                    urls = []
                    if i < len(news_sources) and news_sources[i] is not None:
                        source_urls = news_sources[i] if isinstance(news_sources[i], list) else [news_sources[i]]
                        urls = [u for u in source_urls if u and isinstance(u, str) and u.startswith('http')]
                    
                    # 展示：编号 + 内容 + 链接(可能多个)
                    if urls:
                        # 为每个链接创建可点击的格式
                        links_text = " ".join([f"[🔗]({url})" for url in urls[:3]])  # 最多显示3个链接
                        st.markdown(f"{i+1}. {news_text} {links_text}")
                    else:
                        st.markdown(f"{i+1}. {news_text}")
        elif ctx.get('ERRORS'):
            # 如果有错误但没有新闻，显示错误信息
            perplexity_errors = [e for e in ctx.get('ERRORS', []) if 'Perplexity' in e]
            if perplexity_errors:
                st.warning(f"⚠️ 新闻获取失败: {perplexity_errors[0]}")

st.markdown("---")


# ==============================================================================
# 生成报告
# ==============================================================================

st.subheader("📄 周度报告")

if generate_btn and st.session_state.get('data_collected', False):
    ctx = st.session_state['data_context']
    
    if not ctx:
        st.error("数据未加载，请先采集数据")
    else:
        try:
            from config import DEEPSEEK_CLIENT, DEEPSEEK_MODEL_NAME, DEEPSEEK_MODEL, REPORT_CONFIG
            from report_generator import verify_numbers_hard_code
            from prompt_templates import get_report_prompt
            from data_retriever import DataContext
            
            # 将字典转换为 DataContext 对象以便使用 prompt_templates（包含历史锚点）
            ctx_obj = DataContext()
            ctx_obj.snapshot = ctx.get('SNAPSHOT', '')
            ctx_obj.cny = {
                "usdcny_mid": ctx.get('USDCNY_MID'),
                "usdcnh_spot": ctx.get('USDCNH_CLOSE'),
                "cny_spread": ctx.get('CNY_SPREAD'),
                "usdcny_mid_date": ctx.get('USDCNY_MID_DATE', ''),
                "usdcny_mid_range": ctx.get('USDCNY_MID_RANGE'),
                "usdcny_mid_high": ctx.get('USDCNY_MID_HIGH'),
                "usdcny_mid_low": ctx.get('USDCNY_MID_LOW'),
            }
            ctx_obj.hkd = {
                "usdhkd": ctx.get('USDHKD'),
                "hibor_overnight": ctx.get('HIBOR_OVERNIGHT'),
                "hibor_1w": ctx.get('HIBOR_1W'),
                "hibor_1m": ctx.get('HIBOR_1M'),
                "hkd_usd_spread": ctx.get('HKD_USD_SPREAD'),
                "lers_position": ctx.get('LERS_POSITION'),
            }
            ctx_obj.global_fx = {
                "eurusd": ctx.get('EURUSD'),
                "usdjpy": ctx.get('USDJPY'),
                "gbpusd": ctx.get('GBPUSD'),
                "audusd": ctx.get('AUDUSD'),
                "usdcad": ctx.get('USDCAD'),
                "usdchf": ctx.get('USDCHF'),
                "dxy": ctx.get('DXY'),
            }
            ctx_obj.macro = {
                "us10y": ctx.get('US10Y_YIELD'),
                "us2y": ctx.get('US2Y_YIELD'),
                "yield_curve": ctx.get('YIELD_CURVE'),
                "vix": ctx.get('VIX_LAST'),
                "fed_rate": ctx.get('FED_RATE'),
                "market_sentiment": ctx.get('MARKET_SENTIMENT'),
            }
            ctx_obj.news = ctx.get('NEWS', [])
            ctx_obj.news_detail = ctx.get('NEWS_DETAIL', [])  # 详细摘要用于LLM生成报告
            ctx_obj.news_sources = ctx.get('NEWS_SOURCES', [])
            ctx_obj.errors = ctx.get('ERRORS', [])
            
            with st.status("📝 正在生成报告...", expanded=True) as status:
                status.write("📊 读取已采集数据...")
                
                # 使用 prompt_templates（包含历史锚点）生成报告
                data_json = ctx_obj.to_json()
                prompts = get_report_prompt(data_json)
                
                status.write("✍️ 正在撰写报告...")
                report_placeholder = st.empty()
                full_response = ""
                
                response_stream = DEEPSEEK_CLIENT.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": prompts["system"]},
                        {"role": "user", "content": prompts["user"]}
                    ],
                    max_tokens=REPORT_CONFIG["max_tokens"],
                    temperature=REPORT_CONFIG["temperature"],
                    stream=True
                )
                
                for chunk in response_stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                        report_placeholder.markdown(full_response)
                
                status.write("🔍 执行数值校验...")
                # 执行校验（使用字典格式，与 do_collect_data 返回的格式一致）
                validation_result = verify_numbers_hard_code(ctx, full_response)
                st.session_state['validation_result'] = validation_result
                status.write("✅ 报告生成完成")
            
            # 保存报告到 session_state
            st.session_state['report_text'] = full_response
            st.session_state['pitch_ready'] = True
            
            # 刷新页面使状态框消失（与数据采集阶段一致）
            st.rerun()
            
        except ImportError as e:
            st.error(f"❌ 无法导入必要模块: {e}")
            st.code(traceback.format_exc())
        except Exception as e:
            st.error(f"❌ 报告生成失败: {e}")
            st.code(traceback.format_exc())

elif st.session_state.get('report_text'):
    # 处理历史对比标记（添加下划线）
    marked_report = _mark_historical_comparisons(st.session_state['report_text'])
    
    # 显示已生成的报告
    st.markdown(marked_report)
    
    # 显示校验结果（如果存在）
    validation_result = st.session_state.get('validation_result')
    if validation_result:
        import pandas as pd
        if validation_result.get('is_valid', False):
            st.success("✅ 数据校验通过 (点击查看详情)")
            with st.expander("🔍 审计日志"):
                audit_df = pd.DataFrame(validation_result.get('audit_log', []))
                st.table(audit_df)
        else:
            fail_count = sum(1 for item in validation_result.get('audit_log', []) if item.get('status') == 'FAIL')
            st.warning(f"⚠️ 发现 {fail_count} 处数据潜在偏差 (点击查看详情)")
            with st.expander("🔍 审计日志"):
                audit_df = pd.DataFrame(validation_result.get('audit_log', []))
                st.table(audit_df)
    
    # 免责声明
    st.caption("⚠️ **风险提示**：本报告中的历史行情对比基于 AI 语义分析及静态锚点数据，非全量历史数据回测结果。所有投资决策请以实时盘面为准。")
    
    st.session_state['pitch_ready'] = True

elif st.session_state.get('data_collected'):
    st.info("👈 点击「生成周报」按钮")
else:
    st.info("请先完成数据采集")


# ==============================================================================
# 追问
# ==============================================================================

st.markdown("---")
st.subheader("💬 追问细节")

if st.session_state.get('pitch_ready'):
    for i, (query, response) in enumerate(st.session_state['messages']):
        st.markdown(f"**👉 {i+1}**: {query}")
        st.markdown(f"**🤖**: {response}")
        st.divider()
    
    user_input = st.chat_input("生成 Pitch / 深入分析...")
    
    if user_input:
        from config import DEEPSEEK_CLIENT, DEEPSEEK_MODEL_NAME
        
        output_placeholder = st.empty()
        full_response = ""
        
        # 构建新闻来源信息
        news_context = ""
        if st.session_state.get('data_context'):
            ctx = st.session_state['data_context']
            news_list = ctx.get('NEWS', [])
            news_sources = ctx.get('NEWS_SOURCES', [])
            if news_list:
                news_context = "\n\n**【新闻来源参考】**\n"
                for i, item in enumerate(news_list[:12]):
                    news_text = item if isinstance(item, str) else str(item)
                    url = ""
                    if i < len(news_sources) and news_sources[i]:
                        urls = news_sources[i] if isinstance(news_sources[i], list) else [news_sources[i]]
                        url = urls[0] if urls else ""
                    if url:
                        news_context += f"{i+1}. {news_text}\n   来源: {url}\n"
                    else:
                        news_context += f"{i+1}. {news_text}\n   来源: Perplexity搜索综合\n"
        
        prompt = f"""你是外汇分析师助手。根据以下报告和新闻来源回答用户问题。

**【周报内容】**
{st.session_state['report_text']}
{news_context}

**【用户问题】**
{user_input}

**回答要求**：
- 如果用户询问某个信息的来源，请指出具体的新闻条目和URL
- 如果报告中提到的数据来源于API（如外管局、FRED、东方财富），请说明
- 新闻内容来源于Perplexity搜索，可能是综合多个网站的信息"""
        
        with st.spinner("分析中..."):
            try:
                stream = DEEPSEEK_CLIENT.chat.completions.create(
                    model=DEEPSEEK_MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2000,
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                        output_placeholder.markdown(full_response)
            except Exception as e:
                full_response = f"错误: {e}"
        
        if full_response:
            st.session_state['messages'].append((user_input, full_response))
            if len(st.session_state['messages']) > CHAT_HISTORY_LIMIT:
                st.session_state['messages'].pop(0)
            st.rerun()

else:
    st.info("生成报告后可追问")
