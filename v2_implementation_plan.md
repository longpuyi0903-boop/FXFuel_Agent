
# Project V2.0 Implementation Plan: Hard Logic & Trust UX
# 目标：从 Demo 升级为 MVP，增加确定性校验与专业信任交互

## 0. 全局指令 (General Instructions)
- **角色**：资深 Python 后端工程师 & Streamlit 专家。
- **核心原则**：
  1. **Hard Logic over Soft Logic**：数据校验必须用 Python 代码（Regex/Assert），严禁使用 LLM 自查。
  2. **Trust UX**：前端交互必须透明化（White-box），使用 `st.status` 替代简单的进度条。
  3. **MVP Scope**：不引入向量数据库，使用静态锚点（Static Anchors）解决历史对比需求。
- **文件范围**：`config.py`, `data_retriever.py`, `report_generator.py`, `prompt_templates.py`, `streamlit_app.py`

## 0.1 关键决策总结 (Key Decisions)

### 配置管理
- **Single Source of Truth**：`config.py` 作为唯一配置源，补充 `get_deepseek_client()`, `DEEPSEEK_MODEL`, `REPORT_CONFIG`
- **历史锚点**：使用精确数值（2022高点7.328, 2023高点7.351, 5年均值6.95）
- **核心指标配置**：`CORE_INDICATORS` 字典，包含关键词、数据字段映射、容差、类型

### 错误处理
- **统一策略**：API 失败时设置 `None`，在 Prompt 构建时转换为 `"数据暂缺"`
- **数据缺失处理**：标记为 `WARNING`（数据缺失），不进行数值比对

### 校验逻辑
- **容差策略**：按类型动态容差（汇率0.05, 利率0.1, 指数0.5-1.0），优先使用配置中的特定容差
- **数值提取**：关键词 + 邻近数值（前后20字符）的模糊匹配，支持负数
- **未提及处理**：标记为 `WARNING`（未提及），不影响 `is_valid` 状态
- **接口兼容**：保留 `validate_report` 方法，内部调用 `verify_numbers_hard_code`

### 前端交互
- **两段式状态**：数据采集和报告生成分别使用 `st.status`
- **校验展示**：后置校验，软阻断（显示警告但不阻止报告展示）
- **免责声明**：紧贴报告内容下方，原始数据上方

---

## 阶段一：配置与静态锚点 (Configuration & Anchors)
**目标**：建立历史数据的“参考系”，为 LLM 提供防幻觉的对比标尺。

### 1.1 修改 `config.py`
- **动作**：补充缺失配置项，新增历史锚点和核心指标配置。
- **内容**：
  1. **补充缺失项**：
     - `get_deepseek_client()` 函数（封装初始化逻辑）
     - `DEEPSEEK_MODEL = "deepseek-chat"` 常量
     - `REPORT_CONFIG` 字典（temperature, max_tokens 等）
  
  2. **历史锚点**：
     ```python
     HISTORY_ANCHORS = {
         "USDCNY_2022_HIGH": 7.328,  # 2022年11月高点
         "USDCNY_2023_HIGH": 7.351,  # 2023年9月高点
         "USDCNY_AVG_5Y": 6.95,      # 5年均值
         "HKD_WEAK_SIDE": 7.85,      # 弱方兑换保证（固定）
         "HKD_STRONG_SIDE": 7.75     # 强方兑换保证（固定）
     }
     ```
  
  3. **核心指标配置**（用于硬校验）：
     ```python
     CORE_INDICATORS = {
         # 汇率类 (FX): tolerance 0.02-0.05
         # 利率类 (Rates): tolerance 0.1
         # 指数类 (Index): tolerance 0.5-1.0
         # 每个指标包含: keywords, data_field, tolerance, type
     }
     ```
     - 完整配置见对话记录，包含 12 个核心指标
     - `data_field` 严格映射到 `streamlit_app.py` 中的字典键名

---

## 阶段二：后端逻辑增强 (Backend Hard Logic)

**目标**：用 Python 代码接管数据完整性与准确性校验。

### 2.1 增强 `data_retriever.py` (兜底机制)

* **动作**：优化 `fetch_*` 系列函数。
* **细则**：
  * 确保所有外部 API 调用（AKShare/FRED/Perplexity）都在 `try-except` 块中。
  * **关键修改**：如果 API 失败，必须给 dict 设置显式的 `None` 值，防止 LLM 看到空变量后编造。
  * 错误信息仍记录到 `ctx.errors`，但数据字段必须为 `None`。

### 2.2 升级 `report_generator.py` (硬校验)

* **动作**：实现 `verify_numbers_hard_code`，重构 `validate_report`。
* **细则**：
  * **新增函数**：`verify_numbers_hard_code(data_context: dict, report_text: str) -> dict`
  * **移除**：`validate_report` 中的 LLM 调用代码
  * **保留接口**：`validate_report` 方法签名不变，内部调用 `verify_numbers_hard_code`
  
* **校验逻辑**：
  1. **数值提取**：使用关键词 + 邻近数值（前后20字符）的模糊匹配策略
     - 定位关键词（从 `CORE_INDICATORS` 配置中获取）
     - 提取关键词前后20字符内的第一个浮点数（支持负数）
     - 如果提取不到，标记为 `WARNING`（未提及）
  
  2. **数值比对**：
     - 从 `data_context` 中获取原始值（通过 `data_field` 映射）
     - 如果原始值为 `None`，标记为 `WARNING`（数据缺失），跳过比对
     - 计算差异：`diff = abs(report_val - raw_val)`
     - 获取容差：优先使用配置中的 `tolerance`，否则默认 `0.05`
     - 判断：`diff <= tolerance` 为 `PASS`，否则为 `FAIL`
  
  3. **返回格式**：
     ```python
     {
         "is_valid": bool,  # 只要有一个核心数据偏差过大即为 False
         "audit_log": [
             {
                 "item": "USD/CNY",
                 "report_val": 7.25,
                 "raw_val": 7.20,
                 "diff": 0.05,
                 "status": "FAIL",
                 "msg": "差异 0.05 > 容差 0.05"
             },
             # ...
         ]
     }
     ```





---

## 阶段三：Prompt 工程 (Prompt Engineering)

**目标**：注入锚点并管理 LLM 的语气，降低幻觉风险。

### 3.1 修改 `prompt_templates.py`

* **动作**：更新 `REPORT_GENERATION_PROMPT`，注入历史锚点。
* **细则**：
  * **注入位置**：在 `REPORT_GENERATION_PROMPT` 的 `<DATA>` 标签闭合后，新增 `<HISTORY_ANCHORS>` 标签块
  * **不污染 SYSTEM_PROMPT**：保持系统提示词简洁，只在用户提示词中注入锚点
  * **格式**：将 `config.HISTORY_ANCHORS` 字典格式化为文本注入
  
* **增加指令**：
  - "在分析当前汇率位置时，必须参考提供的【历史锚点数据】。严禁凭空回忆历史高低点。"
  - "对于非本次数据范围内的时间对比，必须使用'从形态上看'、'类似'等非绝对性表述。"
  
* **数据缺失处理**：在构建 Prompt 时，如果 `data_context` 中值为 `None`，替换为字符串 `"数据暂缺"`



---

## 阶段四：前端交互重构 (Frontend Trust UX)

**目标**：将“等待焦虑”转化为“专业信任”。

### 4.1 修改 `streamlit_app.py` (两段式状态展示)

* **动作**：将 `st.progress` 替换为 `st.status`，拆分为两个独立环节。
* **细则**：
  
  **环节 A：数据采集阶段**
  - 点击【刷新数据】按钮时触发
  - 使用 `st.status("📡 正在连接权威数据源...", expanded=True)`
  - 步骤展示：
    - `st.write("📡 正在连接权威数据源 (外管局/FRED)...")`
    - `st.write("🔍 数据清洗与格式化...")`
    - `st.write("✅ 数据采集完成")`
  - 完成后：`status.update(label="✅ 数据就绪", state="complete", expanded=False)`
  
  **环节 B：报告生成阶段**
  - 点击【生成周报】按钮时触发
  - 使用 `st.status("🤖 AI 策略师正在工作...", expanded=True)`
  - 步骤展示：
    - `st.write("📊 读取已采集数据...")`
    - `st.write("✍️ AI 正在撰写策略周报...")`
    - `st.write("🔍 执行 Hard-Logic 数值校验...")`（调用 `verify_numbers_hard_code`）
  - 完成后：`status.update(label="✅ 报告生成完成", state="complete", expanded=False)`

### 4.2 校验结果展示 (软阻断策略)

* **动作**：在报告生成后立即执行校验，展示结果但不阻止报告展示。
* **细则**：
  * **校验时机**：报告生成完成后，立即调用 `verify_numbers_hard_code`
  * **展示位置**：报告内容下方，免责声明上方
  * **展示方式**：
    - 如果 `is_valid == True`：显示 `st.success("✅ 数据校验通过")`
    - 如果 `is_valid == False`：显示 `st.warning("⚠️ 发现数据潜在偏差")`，并列出不一致的数据点
  * **关键原则**：无论校验结果如何，都展示报告内容

### 4.3 新增 UI 组件 (免责声明)

* **动作**：在报告展示区域下方添加免责声明。
* **位置**：紧贴报告内容下方，原始数据上方（用户阅读动线：结论 → 风险提示 → 原始数据）
* **内容**：
  ```markdown
  ⚠️ **风险提示**：本报告中的历史行情对比基于 AI 语义分析及静态锚点数据，非全量历史数据回测结果。所有投资决策请以实时盘面为准。
  ```
* **实现**：使用 `st.caption()` 或 `st.info()` 组件

---

## 执行顺序总结

### 阶段一：配置与静态锚点
1. 修改 `config.py`：
   - 补充 `get_deepseek_client()`, `DEEPSEEK_MODEL`, `REPORT_CONFIG`
   - 新增 `HISTORY_ANCHORS` 常量
   - 新增 `CORE_INDICATORS` 配置字典（12个核心指标）

### 阶段二：后端逻辑增强
2. 修改 `data_retriever.py`：
   - 确保所有 API 失败时设置 `None` 而非仅记录错误
3. 修改 `report_generator.py`：
   - 实现 `verify_numbers_hard_code(data_context, report_text)` 函数
   - 重构 `validate_report()` 方法（移除 LLM 调用，调用硬校验函数）

### 阶段三：Prompt 工程
4. 修改 `prompt_templates.py`：
   - 在 `REPORT_GENERATION_PROMPT` 中注入 `<HISTORY_ANCHORS>` 标签块
   - 增加历史锚点使用指令和语气约束
   - 实现 `None` 值到 `"数据暂缺"` 的转换逻辑

### 阶段四：前端交互重构
5. 修改 `streamlit_app.py`：
   - 数据采集阶段：使用 `st.status` 替代 `st.progress`
   - 报告生成阶段：使用 `st.status` 展示生成和校验过程
   - 添加校验结果展示（报告下方，软阻断）
   - 添加免责声明（报告下方，原始数据上方）

---

## 关键实现细节

- **容差策略**：按类型动态容差（汇率0.05, 利率0.1, 指数0.5-1.0），优先使用配置值
- **数值提取**：关键词匹配 + 前后20字符内浮点数提取（支持负数）
- **错误处理**：数据缺失标记 `WARNING`，不影响 `is_valid`；未提及也标记 `WARNING`
- **接口兼容**：保留 `validate_report` 方法签名，内部重构为硬校验