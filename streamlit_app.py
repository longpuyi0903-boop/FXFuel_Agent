# streamlit_app.py - DeepSeek 兼容最终版本 (专业修复版：解决所有交互性问题和API错误)

import streamlit as st
import datetime
from fx_data_retriever import retrieve_all_data
# 从 config 文件导入 DeepSeek 客户端、模型名和配置信息
from config import DEEPSEEK_CLIENT, get_proxy_status, DEEPSEEK_MODEL_NAME
from openai import OpenAI 

# --- 0. Streamlit 界面配置和状态初始化 ---
st.set_page_config(page_title="FXFuel: 外汇周报 Agent (DeepSeek)", layout="wide")
st.title("💰 FXFuel: 投行外汇周报自动化 Agent (Powered by DeepSeek)")

# 初始化 session state 
if 'report_text' not in st.session_state:
    st.session_state['report_text'] = ""
if 'pitch_ready' not in st.session_state:
    st.session_state['pitch_ready'] = False
if 'run_analysis' not in st.session_state:
    st.session_state['run_analysis'] = False
if 'rag_context' not in st.session_state: # 存储 API 抓取的数据，避免重复调用 (问题 3 优化)
    st.session_state['rag_context'] = {}
if 'messages' not in st.session_state: # 存储问答历史 (问题 4)
    st.session_state['messages'] = [] 

CHAT_HISTORY_LIMIT = 3 # 限制对话记录条数 (问题 5)

# --- 1. 界面交互 (启动按钮和日期配置) ---
with st.sidebar:
    st.header("⚙️ 报告配置")
    
    today = datetime.date.today()
    REPORT_DATE = today.strftime("%Y年%m月%d日") 
    REPORT_PERIOD = f"截至 {REPORT_DATE}" 
    
    st.success(f"报告生成日期: **{REPORT_DATE}**")
    st.info("数据快照：程序运行时实时获取。") 

    st.markdown("---")
    st.header("📈 模型状态")
    st.write(f"驱动模型: **{DEEPSEEK_MODEL_NAME}**")
    if get_proxy_status():
        st.info("⚠️ 代理已启用（网络敏感）。")
    
    if st.button("🚀 开始分析并生成通用报告"):
        # 强制运行报告生成逻辑并清除旧状态
        st.session_state['run_analysis'] = True
        st.session_state['pitch_ready'] = False 
        st.session_state['report_text'] = "" 
        st.session_state['rag_context'] = {} 
        st.session_state['messages'] = [] 
        st.toast("开始生成报告并检索最新深度观点...")
        st.rerun() # 强制运行以开始生成


# --- 2. 核心 AI 逻辑 (生成通用报告 - 仅在未生成时运行) ---

if st.session_state.get('report_text', "") == "":
    # 报告未生成，执行生成流程
    
    if st.session_state.get('run_analysis', False):
        
        # 进度条放在主体区
        progress_bar = st.progress(0, text="📊 正在初始化数据...")
        
        # 2.1 提取基础 API 数据 (RAG) - 仅在 rag_context 为空时运行 (问题 3 优化)
        if not st.session_state['rag_context']:
            try:
                with st.spinner("1/3 正在连接数据源、获取 Federal Reserve Economic Data (FRED)/Alpha Vantage (AV) 实时数据..."):
                    rag_context = retrieve_all_data() 
                st.session_state['rag_context'] = rag_context
                
            except Exception as e:
                progress_bar.progress(100, text="❌ 数据检索失败")
                st.error(f"数据检索失败: {e}")
                st.stop()
        
        rag_context = st.session_state['rag_context']
        SNAPSHOT = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        progress_bar.progress(33, text="💾 2/3 数据获取完成，正在进行 DeepSeek 检索...")
        
        # 将 RAG 数据概览放到侧边栏
        st.sidebar.markdown("---")
        st.sidebar.caption("实时 RAG 数据概览:")
        st.sidebar.json(rag_context) 

        # 2.2 构造通用报告 Prompt (保持时效性、无源即弃的严格要求)
        system_prompt = f"""
        您是顶尖的投行外汇策略师，请生成一份客观、中立、专业的中文外汇周报。

        **【时效性最高原则】**：
        1. **时间校准**：当前日期是 {REPORT_DATE}。您的报告分析必须基于**已发生的事实**，严禁包含对已结束事件（如已在 {REPORT_DATE} 或之前完成的央行会议）的**任何猜测性措辞**，必须引用**最终决议结果**。
        2. **结果优先**：所有宏观事件，必须优先检索**最近一到两天内已公布的最终结果**和官方/权威媒体解读。

        **【格式和内容要求】**
        3. **【核心修复：强制真实内容与来源 - 无源即弃原则】**：
           - **最高原则 (Verifiability):** 报告中所有通过 Web 检索获取的外部观点、市场情绪或事实，**必须是真实且可追溯的**。
           - **强制要求 (No Faked Content):** 您绝对禁止编造任何内容、观点或数据。如果您的检索工具未返回**可信的、可验证的来源信息**（如有效链接、具体报告标题、作者、或书籍名称），则该观点/内容**必须被省略**。
           - **引用格式:** 所有引用的外部信息，必须在引用处的末尾，严格使用 Markdown 格式的引用链接 `[来源: 机构名称/报告标题](真实URL)` 进行标注。
        """
        
        # 动态构建 API 数据输入
        api_data_input = ""
        fx_pairs = ["USDCNH", "EURUSD"] 
        for pair in fx_pairs:
            close = rag_context.get(f"{pair}_CLOSE", "Data N/A")
            source = rag_context.get("PRICE_SOURCE", "Alpha Vantage (AV)")
            api_data_input += f"- {pair} 实时价格: {close} (来源: {source})\n"
            
        api_data_input += f"- 10年期美债收益率: {rag_context.get('US10Y_YIELD', 'Data N/A')} (来源: Federal Reserve Economic Data (FRED))\n"
        api_data_input += f"- VIX 恐慌指数: {rag_context.get('VIX_LAST', 'Data N/A')} (来源: Federal Reserve Economic Data (FRED))\n"


        user_prompt = f"""
        请根据以下基础数据和关键检索要求，生成报告。

        **【报告日期】**: {REPORT_DATE}
        **【基础数据输入 (全部通过 API 获取)】**
        {api_data_input}
        
        **【关键检索要求】**
        1. **时效性与宏观事件焦点 (高优先级):** 请立即检索和分析**最近一到两天内**（紧邻 {REPORT_DATE}）发生的**所有重大宏观经济事件**（如全球主要央行利率决议、关键经济数据公布、地缘政治突发事件）的**最终结果**和权威媒体解读。
        2. **人民币汇率深度分析:** 请重点检索 **中国人民银行 (PBOC)** 官网、**中国外汇交易中心 (CFETS)** 和 **中国货币网** 上关于人民币汇率、流动性操作的**最新官方表态和权威分析**。请务必提供人民币**中间价**的具体稳定区间（例如：在 7.08-7.10 波动）的权威说法。
        3. 针对主要货币对 (EUR/USD, USD/JPY, GBP/USD等) 走势，权威机构的战术性交易建议和拥挤程度分析是什么？
        
        **【报告框架要求】** (请严格按照以下结构输出 Markdown 格式)
        ## 🌐 投行外汇周报：{REPORT_PERIOD}

        ### I. 市场主题与核心观点
        ### II. 深度聚焦：人民币汇率 (CNY & CNH)
        ### III. 核心板块：美元及宏观驱动
        ### IV. 市场情绪与资金流向 (非 API 数据必须严格遵守“无源即弃”原则)
        ### V. 主要货币对战术策略
        ### VI. 下周焦点与风险提示
        
        请严格遵守上面的引用要求（真实链接或仅名称降级），**不应出现任何无法追溯来源的观点**。
        """
        
        # 2.3 调用 DeepSeek API 并启用 STREAMING
        progress_bar.progress(66, text=f"⚡ 3/3 正在调用 {DEEPSEEK_MODEL_NAME} 模型，等待 Web Search 结果并开始流式输出...")
        
        report_placeholder = st.empty()
        full_response_content = ""
        
        try:
            response_stream = DEEPSEEK_CLIENT.chat.completions.create(
                model=DEEPSEEK_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ], 
                temperature=0.3, 
                max_tokens=4000,
                stream=True 
            )
            
            # 迭代响应流并更新占位符
            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    full_response_content += chunk.choices[0].delta.content
                    report_placeholder.markdown(full_response_content)
            
            progress_bar.progress(100, text="✅ 报告生成成功！")
            st.subheader("✅ 通用报告已生成")
            
            # 存储最终的报告内容
            st.session_state['report_text'] = full_response_content
            st.session_state['pitch_ready'] = True
            st.session_state['run_analysis'] = False
            
        except Exception as e:
            progress_bar.progress(100, text="❌ 报告生成失败")
            st.error(f"DeepSeek API 调用失败: {e}")
            st.session_state['report_text'] = ""


else:
    # 报告已生成 (问题 1 解决: 只要 report_text 不为空，就显示它，不再重新生成)
    st.subheader("✅ 通用报告已生成")
    st.markdown(st.session_state['report_text']) 
    st.session_state['pitch_ready'] = True
    st.session_state['run_analysis'] = False
    
# --- 3. 交互式 Pitch 生成模块 (对话框和 RAG 优化) ---
if st.session_state.get('pitch_ready', False):
    st.divider()
    st.header("⚡ 交互式 Pitch / 深度查询")
    
    # 3.1 显示历史记录 (问题 4 & 5)
    # 使用一个容器来显示历史记录
    history_container = st.container()
    with history_container:
        # 循环显示历史问答
        for i, (query, response) in enumerate(st.session_state['messages']):
            st.markdown(f"**👉 用户查询 {i+1}**: {query}")
            st.markdown(f"**🤖 AI 回复 {i+1}**:\n{response}")
            st.divider()
            
    # 3.2 创建 Chat Input
    st.write("请在下方输入框中输入您的指令。")
    user_pitch_input = st.chat_input(
        "我可以帮你生成一个 pitch (机构/企业) / 深入了解以上信息...",
        key="pitch_input_key"
    )

    if user_pitch_input:
        
        # 每次收到新输入时，创建一个**局部**占位符用于显示 loading/回复 (问题 2)
        # 注意：这里我们使用 st.empty() 来管理回复，然后强制 rerun 来更新历史
        
        # 在历史记录容器的下方，创建一个新的占位符，用于本次查询的输出
        new_output_placeholder = st.empty()
        
        is_pitch_request = "pitch" in user_pitch_input.lower() or "推介" in user_pitch_input or "生成" in user_pitch_input
        
        full_response_content = ""
        
        if is_pitch_request:
            
            # ... (客户类型解析逻辑) ...
            if "机构" in user_pitch_input or "fi" in user_pitch_input.lower() or "hf" in user_pitch_input.lower():
                client_type = "Institutional (FI/HF)"
                type_focus = "战术交易、情绪极值和高阶衍生品"
            elif "企业" in user_pitch_input or "财务" in user_pitch_input:
                client_type = "Corporate (企业财务)"
                type_focus = "风险管理和锁定利润，特别是 CNH 贬值风险观点和政策信号"
            else:
                client_type = "通用客户"
                type_focus = "综合市场概述和关键风险"
                
            
            pitch_system_prompt = f"您是顶尖的投行 FX Sales，请根据下方通用报告内容，生成一份针对 {client_type} 客户的 Pitch 文案。**请严格只基于通用报告内容进行合成，严禁进行新的 Web 检索，以保证速度和一致性。**请严格使用中文输出。"
            
            pitch_user_prompt = f"""
            **【通用报告核心分析】**: {st.session_state['report_text']}
            **要求**: Pitch 必须聚焦 {type_focus}。
            """
            
            # 使用全局 st.spinner，但由于 State Management 锁定，它只在局部显示
            with st.spinner(f"正在为 {client_type} 客户生成 Pitch... (基于报告 RAG 快速合成)"):
                try:
                    pitch_response_stream = DEEPSEEK_CLIENT.chat.completions.create(
                        model=DEEPSEEK_MODEL_NAME,
                        messages=[
                            {"role": "system", "content": pitch_system_prompt},
                            {"role": "user", "content": pitch_user_prompt}
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                        stream=True 
                    )
                    
                    # 流式输出到局部占位符
                    for chunk in pitch_response_stream:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            full_response_content += chunk.choices[0].delta.content
                            new_output_placeholder.markdown(full_response_content)
                            
                except Exception as e:
                    new_output_placeholder.error(f"Pitch 生成失败: DeepSeek API 错误: {e}")
                    full_response_content = f"生成失败：{e}"


        else:
            # Logic for Deep Dive / General Query 
            # 强化 System Prompt，强制纠正报告中的时效性错误
            deep_dive_system_prompt = f"""
            您是外汇策略分析师，请根据下方提供的通用报告内容，针对用户的具体问题或深入分析要求进行回复。
            
            **最高优先级：事实核查与纠错**：如果用户质疑报告中关于**宏观事件时效性**（如 FOMC 决议日期）的错误，您必须立即通过 Web 检索核实**当前日期（{REPORT_DATE}）**及**事件的最终结果**，并**直接纠正**报告中的错误措辞，引用最新的事实和来源。
            
            **信息追溯原则**：您的回复应严格基于报告内容及其引用的来源。如果报告中信息不足，您可以进行额外的 Web 检索来补充，但必须遵守“无源即弃”的最高原则。
            """
            
            deep_dive_user_prompt = f"""
            **【通用报告内容】**: {st.session_state['report_text']}
            **【用户请求】**: {user_pitch_input}
            
            请以专业的格式和语气进行回复。
            """

            # 使用全局 st.spinner，实现局部加载的视觉效果
            with st.spinner(f"正在分析并回复您的请求: {user_pitch_input}... (可能触发 Web 检索)"):
                try:
                    dive_response_stream = DEEPSEEK_CLIENT.chat.completions.create(
                        model=DEEPSEEK_MODEL_NAME,
                        messages=[
                            {"role": "system", "content": deep_dive_system_prompt},
                            {"role": "user", "content": deep_dive_user_prompt}
                        ],
                        temperature=0.3,
                        max_tokens=3000,
                        stream=True
                    )
                    
                    # 流式输出到局部占位符
                    for chunk in dive_response_stream:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            full_response_content += chunk.choices[0].delta.content
                            new_output_placeholder.markdown(full_response_content)
                            
                except Exception as e:
                    new_output_placeholder.error(f"请求失败: DeepSeek API 错误: {e}")
                    full_response_content = f"请求失败：{e}"


        # 4. 更新历史记录并重绘页面 (最关键步骤)
        if full_response_content:
            # 清除局部占位符
            new_output_placeholder.empty()

            # 追加新问答到历史记录
            st.session_state['messages'].append((user_pitch_input, full_response_content))
            
            # 限制历史记录条数 (问题 5)
            if len(st.session_state['messages']) > CHAT_HISTORY_LIMIT:
                st.session_state['messages'].pop(0)

            # 强制 Streamlit 重新运行脚本，以**显示更新后的历史记录**，完成局部更新的视觉效果。
            st.rerun()