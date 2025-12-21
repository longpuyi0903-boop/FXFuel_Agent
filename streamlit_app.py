# streamlit_app.py - 外汇周报 Agent（修复重复采集问题）

import streamlit as st
import datetime
import traceback

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

CHAT_HISTORY_LIMIT = 3
today = datetime.date.today()
REPORT_DATE = today.strftime("%Y年%m月%d日")
REPORT_PERIOD = f"截至 {REPORT_DATE}"


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
        "NEWS": ctx_obj.news,
        "NEWS_SOURCES": ctx_obj.news_sources,  # 添加新闻源链接
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
        progress_bar = st.progress(0, text="正在初始化...")
        status_text = st.empty()
        
        def update_progress(step, total, msg):
            progress_bar.progress(step / total)
            status_text.text(msg)
        
        try:
            with st.spinner("正在采集外汇数据..."):
                ctx = do_collect_data(progress_callback=update_progress)
            
            # 保存到 session state
            st.session_state['data_context'] = ctx
            st.session_state['data_collected'] = True
            
            progress_bar.progress(1.0)
            status_text.text(f"✅ 完成！{ctx['data_points']} 个数据点")
            st.success(f"✅ 数据采集完成！共 {ctx['data_points']} 个数据点，{len(ctx.get('NEWS', []))} 条新闻")
            
            # 自动刷新页面以显示数据
            st.rerun()
            
        except Exception as e:
            progress_bar.progress(100, text="❌ 采集失败")
            status_text.text("❌ 采集失败")
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
                    if i < len(news_sources) and news_sources[i]:
                        source_urls = news_sources[i] if isinstance(news_sources[i], list) else [news_sources[i]]
                        urls = [u for u in source_urls if u and isinstance(u, str) and u.startswith('http')]
                    
                    # 展示：编号 + 内容 + 链接(可能多个)
                    if urls:
                        links = " ".join([f"[🔗]({url})" for url in urls[:3]])  # 最多显示3个链接
                        st.markdown(f"{i+1}. {news_text} {links}")
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
        progress_bar = st.progress(0, text="📝 正在构建报告...")
        
        try:
            from config import DEEPSEEK_CLIENT, DEEPSEEK_MODEL_NAME
        except ImportError:
            st.error("❌ 无法导入 config.py")
            st.stop()
        
        # System Prompt
        system_prompt = f"""你是顶尖的投行外汇策略师，生成专业的中文外汇周报。

**核心要求**
1. 数据准确：使用【基础数据】中的精确数字，标注来源
2. 新闻融入：将【本周新闻】融入分析，用"据[来源]报道"格式
3. 专业分析：有逻辑推演，不只是数据罗列
4. 专业措辞：使用"承压"、"走强"、"偏鸽/偏鹰"等表达

**新闻引用格式**
- 据[路透]报道，...
- [彭博]指出，...

**禁止**
- 禁止编造数据或新闻
- 数据为空则说明"数据暂缺"
"""
        
        # 数据输入
        api_data = f"""
**【基础数据】**

人民币：
- USD/CNY 中间价: {ctx.get('USDCNY_MID') or 'N/A'} (外管局)
- 中间价区间: {ctx.get('USDCNY_MID_RANGE') or 'N/A'}
- USD/CNH 离岸: {ctx.get('USDCNH_CLOSE') or 'N/A'} (东方财富)
- 价差: {ctx.get('CNY_SPREAD') or 'N/A'}

港元：
- USD/HKD: {ctx.get('USDHKD') or 'N/A'} (东方财富)
- 联汇位置: {ctx.get('LERS_POSITION') or 'N/A'}
- HIBOR隔夜: {ctx.get('HIBOR_OVERNIGHT') or 'N/A'}% (金管局)
- 港美利差: {ctx.get('HKD_USD_SPREAD') or 'N/A'}%

全球：
- DXY: {ctx.get('DXY') or 'N/A'} (ICE)
- EUR/USD: {ctx.get('EURUSD') or 'N/A'}
- USD/JPY: {ctx.get('USDJPY') or 'N/A'}
- GBP/USD: {ctx.get('GBPUSD') or 'N/A'}

宏观：
- 10Y美债: {ctx.get('US10Y_YIELD') or 'N/A'}% (FRED)
- 2Y美债: {ctx.get('US2Y_YIELD') or 'N/A'}%
- 收益率曲线: {ctx.get('YIELD_CURVE') or 'N/A'}%
- VIX: {ctx.get('VIX_LAST') or 'N/A'} (CBOE)
- 联邦基金利率: {ctx.get('FED_RATE') or 'N/A'}%
- 市场情绪: {ctx.get('MARKET_SENTIMENT') or 'N/A'}
"""
        
        # 新闻输入
        news_input = "\n**【本周市场动态】**（融入报告分析）\n"
        news_list = ctx.get('NEWS', [])
        if news_list:
            for i, item in enumerate(news_list[:12], 1):
                if isinstance(item, dict):
                    content = item.get('content', '')
                    news_input += f"{i}. {content}\n"
                else:
                    news_input += f"{i}. {item}\n"
        else:
            news_input += "（暂无新闻）\n"
        
        progress_bar.progress(30, text="⚡ 调用 DeepSeek...")
        
        user_prompt = f"""生成外汇周报。

**报告日期**: {REPORT_DATE}

{api_data}
{news_input}

**报告结构**（一页纸篇幅）

## 🌐 外汇周报：{REPORT_PERIOD}

### I. 市场主题与核心观点
（总结本周核心动态）

### II. 人民币汇率 (CNY & CNH)

### III. 港元汇率 (HKD)

### IV. 美元及宏观驱动

### V. 主要货币对策略

### VI. 下周焦点与风险提示

---
*数据快照: {ctx.get('SNAPSHOT', '')}*

**重要提示**：
- 数据标注来源（如"外管局"、"FRED"、"东方财富"等）
- 不要编造"据路透/彭博报道"这类来源标注
- 直接陈述事实和分析，无需标注新闻来源
"""
        
        report_placeholder = st.empty()
        full_response = ""
        
        try:
            response_stream = DEEPSEEK_CLIENT.chat.completions.create(
                model=DEEPSEEK_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.4,
                max_tokens=4000,
                stream=True
            )
            
            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    report_placeholder.markdown(full_response)
                    progress = min(30 + len(full_response) // 50, 95)
                    progress_bar.progress(progress, text="✍️ AI 撰写中...")
            
            progress_bar.progress(100, text="✅ 完成！")
            st.session_state['report_text'] = full_response
            st.session_state['pitch_ready'] = True
            
        except Exception as e:
            progress_bar.progress(100, text="❌ 失败")
            st.error(f"DeepSeek 错误: {e}")

elif st.session_state.get('report_text'):
    st.markdown(st.session_state['report_text'])
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
