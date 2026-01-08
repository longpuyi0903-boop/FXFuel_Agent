# FXFuel Agent RAG 架构分析与优化建议报告

## 执行摘要

经过对项目代码的深入分析，我认为 **Gemini 的评估基本正确**，但有几处需要补充和修正。该项目采用的是 **结构化数据 RAG（Structured Data RAG）** 模式，而非传统的向量检索 RAG。这种选择在金融精确数据场景下是**正确且务实的架构决策**。

**当前版本：V3**（2025-01-08 更新）

**总体评价**：
- **RAG 完成度**：85%（V3 修复了缓存断路、解析脆弱性、新闻幻觉问题）
- **架构合理性**：★★★★☆（符合金融场景需求，但可扩展性受限）
- **行业规范符合度**：★★★★☆（核心机制完善，缺少历史数据检索）

**V3 版本改进**：
- ✅ 缓存功能真正接通（解决 Gemini 指出的"代码断路"问题）
- ✅ 新闻解析增加 Fallback 机制（增强鲁棒性）
- ✅ Self-Citation 引用规则（降低新闻幻觉风险）

---

## 一、对 Gemini 分析的评价

### ✅ 我同意的部分

1. **"非向量 RAG，而是 API 实时检索 RAG"** — 完全正确
   - 项目确实采用"确定性检索"而非"语义模糊匹配"
   - 对于汇率、利率等精确数值，这是正确选择

2. **"向量检索的语义模糊匹配是致命的"** — 非常精准
   - 向量检索会把 7.15 和 7.25 视为"语义相近"，这在金融场景是灾难性的
   - 把"上周"和"本周"混淆会导致报告失去价值

3. **"Hard Logic over Soft Logic"** — 项目的核心亮点
   - `verify_numbers_hard_code()` 函数使用正则+容差比对，而非让 LLM 自查
   - 这是防幻觉的正确做法

4. **"追问一致性处理"** — 实现合理
   - `answer_followup()` 将原始数据 + 报告 + 问题一起发送
   - 保证了多轮对话的数据口径一致

### ⚠️ 我部分同意/需要修正的部分

1. **关于 Perplexity 的使用**
   
   Gemini 说："利用 Perplexity 的联网搜索能力获取最近一周的新闻摘要"
   
   **我的补充**：代码中 Perplexity 的使用存在潜在问题：
   ```python
   # data_retriever.py 中的问题
   timeout=(30, 120),  # 连接30秒，读取120秒 - 过长
   verify=False        # 禁用 SSL 验证 - 安全隐患
   ```
   虽然功能实现了，但在生产环境中这种配置不够健壮。

2. **关于"结构化 RAG 优于向量 RAG"**

   Gemini 的表述过于绝对。更准确的说法是：
   - **定量数据场景**：结构化 RAG 更优
   - **定性分析场景**：向量 RAG 仍有价值（如历史相似行情检索）
   - **最佳实践**：两者结合（Hybrid RAG）

### ❌ 我不同意的部分

1. **"代码解释器让 Agent 自己写代码计算"的建议**

   在金融报告场景中，让 LLM 动态生成计算代码是**危险的**：
   - 计算逻辑应该是确定性的、可审计的
   - LLM 生成的代码可能有细微错误（如波动率计算公式错误）
   - 当前项目在 `data_retriever.py` 中硬编码计算是正确做法

2. **关于"Self-Correction 自修正机制"**

   Gemini 建议"将错误报告反向喂回 LLM 自我修正"。这在金融场景存在风险：
   - 多次迭代可能引入累积误差
   - 更好的做法是：校验失败 → 人工介入或重新采集数据
   - 当前项目的"软阻断"策略（显示警告但不自动修正）是更稳健的选择

---

## 二、项目 RAG 架构详细分析

### 2.1 检索层（Retrieval）

| 组件 | 实现方式 | 评价 |
|------|---------|------|
| 定量数据 | AKShare + FRED API | ★★★★★ 优秀 |
| 新闻数据 | Perplexity API | ★★★☆☆ 可用但不稳定 |
| 数据清洗 | `DataContext` 类 | ★★★★☆ 结构清晰 |
| 错误处理 | `None` 值 + `errors` 列表 | ★★★★☆ 符合 v2 计划 |

**优点**：
- 多数据源聚合设计合理
- 重试机制（3次 + 指数退避）
- 明确的 `None` 值处理（防止 LLM 补全）

**问题**：
- Perplexity 解析逻辑过于复杂（600+ 行），容易出错
- 没有数据缓存机制，每次都重新采集
- 网络超时配置不一致（有的 15s，有的 120s）

### 2.2 增强层（Augmentation）

| 组件 | 实现方式 | 评价 |
|------|---------|------|
| Context 构建 | JSON 序列化 | ★★★★☆ 标准做法 |
| 历史锚点 | `HISTORY_ANCHORS` | ★★★★★ 创新且实用 |
| Prompt 工程 | 严格约束 + XML 标签 | ★★★★☆ 符合最佳实践 |
| Token 管理 | 无明确管理 | ★★☆☆☆ 潜在风险 |

**亮点**：
```python
# config.py 中的历史锚点设计
HISTORY_ANCHORS = {
    "USDCNY_2022_HIGH": 7.328,  # 防止 LLM 凭空回忆
    "USDCNY_2023_HIGH": 7.351,
    "HKD_WEAK_SIDE": 7.85,      # 固定参数
}
```
这解决了"LLM 不知道历史高低点"的问题，且不需要向量数据库。

**问题**：
- 没有检查 Context 是否超过模型 Token 限制
- 当新闻数量多时（14条详细摘要），可能接近上限

### 2.3 生成层（Generation）

| 组件 | 实现方式 | 评价 |
|------|---------|------|
| 模型选择 | DeepSeek | ★★★★☆ 性价比高 |
| 温度设置 | 0.3 | ★★★★★ 正确选择 |
| 流式输出 | 支持 | ★★★★☆ 用户体验好 |
| 输出校验 | 硬编码正则 | ★★★★★ 核心亮点 |

**亮点**：
```python
# report_generator.py 中的硬校验
def verify_numbers_hard_code(data_context, report_text):
    # 不用 LLM 自查，用 Python 正则提取数字比对
    for indicator_name, config in CORE_INDICATORS.items():
        # 关键词定位 + 邻近数值提取 + 容差比对
```

这是项目最有价值的部分，完全符合"Hard Logic over Soft Logic"原则。

### 2.4 对话层（Follow-up）

| 组件 | 实现方式 | 评价 |
|------|---------|------|
| 上下文保持 | 原始数据 + 报告 + 问题 | ★★★★☆ 正确做法 |
| 历史管理 | 最近3轮 | ★★★☆☆ 基础实现 |
| 来源追溯 | 新闻 URL 传递 | ★★★★☆ 用户体验好 |

---

## 三、与行业最佳实践的差距

### 3.1 金融报告 Agent 行业标准

| 能力 | 行业标准 | 当前项目 | 差距 |
|------|---------|---------|------|
| 数据准确性 | Text-to-SQL/API | ✅ 已实现 | 无 |
| 幻觉检测 | 硬编码校验 | ✅ 已实现 | 无 |
| 引用溯源 | 每句标注来源 | ⚠️ 部分实现 | 报告中未标注句级来源 |
| 时间过滤 | Recency Filter | ⚠️ 部分实现 | 仅 Perplexity 有 week 过滤 |
| 历史对比 | 向量检索历史报告 | ❌ 未实现 | 仅有静态锚点 |
| 动态计算 | Code Interpreter | ❌ 未实现（但这是正确选择） | N/A |

### 3.2 缺失的关键能力

1. **Token 预算管理**
   ```python
   # 应该添加
   def estimate_tokens(text):
       return len(text) // 4  # 粗略估计
   
   MAX_CONTEXT_TOKENS = 8000
   if estimate_tokens(data_json) > MAX_CONTEXT_TOKENS:
       # 压缩策略：移除非核心数据
   ```

2. **数据新鲜度验证**
   ```python
   # 当前缺失：检查数据是否过时
   from datetime import datetime, timedelta
   
   def is_data_stale(snapshot_time, max_age_hours=4):
       snapshot = datetime.fromisoformat(snapshot_time)
       return datetime.now() - snapshot > timedelta(hours=max_age_hours)
   ```

3. **结构化输出保障**
   ```python
   # 建议添加：强制 JSON 输出 + 解析验证
   response_format={"type": "json_object"}  # OpenAI 格式
   ```

---

## 四、优化建议（按优先级排序）

> **优先级说明**：基于"Vibe Coding 项目"的实际情况重新排序，优先修复影响功能的问题，低优先级处理"理论上有风险但实际影响小"的问题。

### P0 - 建议尽快实现（影响稳定性）

| 序号 | 改动项 | 改动量 | 收益 | 文件 |
|------|--------|--------|------|------|
| 1 | Token 预算管理 | 小（20行） | 防止新闻过多导致生成失败 | `prompt_templates.py` |
| 2 | 统一超时配置 | 小（10行） | 减少网络不稳定时的报错 | `config.py` + `data_retriever.py` |

#### 1. Token 预算管理（推荐首先实现）

**问题**：当 Perplexity 返回 14 条详细新闻时，Context 可能接近 DeepSeek 的 Token 上限。

**实现方案**：
```python
# prompt_templates.py 中添加

def _estimate_tokens(text: str) -> int:
    """粗略估算 Token 数（中文约 1.5 字符/token）"""
    return int(len(text) / 1.5)

MAX_CONTEXT_TOKENS = 6000  # 保守估计，留 2000 给输出

def get_report_prompt(data_json: str) -> dict:
    # ... 现有逻辑 ...
    
    # 新增：检查并压缩
    estimated = _estimate_tokens(data_json_cleaned)
    if estimated > MAX_CONTEXT_TOKENS:
        # 压缩策略：只保留前 7 条新闻详情
        data_dict = json.loads(data_json_cleaned)
        if 'news_detail' in data_dict and len(data_dict['news_detail']) > 7:
            data_dict['news_detail'] = data_dict['news_detail'][:7]
            data_dict['_note'] = "新闻已压缩至7条以控制Token"
        data_json_cleaned = json.dumps(data_dict, ensure_ascii=False, indent=2)
    
    # ... 后续逻辑 ...
```

#### 2. 统一超时配置

**问题**：当前超时设置散落在代码各处（15s、30s、120s），难以维护。

**实现方案**：
```python
# config.py 中添加

TIMEOUT_CONFIG = {
    "default": (10, 30),      # (连接, 读取) 秒
    "perplexity": (30, 90),   # Perplexity 响应较慢
    "akshare": (10, 20),      # 国内源较快
}

# data_retriever.py 中使用
from config import TIMEOUT_CONFIG
requests.post(url, timeout=TIMEOUT_CONFIG["perplexity"])
```

---

### P1 - 建议实现（提升体验，非必须）

| 序号 | 改动项 | 改动量 | 收益 | 文件 |
|------|--------|--------|------|------|
| 3 | 简单数据缓存 | 中（50行） | 避免重复请求、加快二次生成 | `data_retriever.py` |

#### 3. 简单数据缓存（基于 TTL）

**适用场景**：用户短时间内多次点击"刷新数据"时避免重复请求。

**实现方案**：
```python
# data_retriever.py 顶部添加

import time
from typing import Callable, Any

_cache = {}
_cache_time = {}

def get_with_cache(key: str, fetch_func: Callable, ttl_seconds: int) -> Any:
    """
    带 TTL 的简单缓存
    
    推荐 TTL 设置：
    - 中间价 (usdcny_mid): 3600 秒（9:15发布后整天不变）
    - 实时汇率 (usdcnh): 60 秒
    - FRED 数据: 300 秒（5分钟，更新不频繁）
    - 新闻: 600 秒（10分钟）
    """
    now = time.time()
    if key in _cache and (now - _cache_time.get(key, 0)) < ttl_seconds:
        return _cache[key]
    
    result = fetch_func()
    _cache[key] = result
    _cache_time[key] = now
    return result

# 使用示例（在 fetch_cny_data 中）
def fetch_cny_data(ctx: DataContext) -> str:
    def _do_fetch():
        # 原有的获取逻辑
        mid_df = ak.currency_boc_safe()
        return mid_df
    
    mid_df = get_with_cache("cny_mid", _do_fetch, ttl_seconds=3600)
    # ... 后续处理 ...
```

---

### P2 - 可选增强（长期演进，当前可忽略）

| 序号 | 改动项 | 改动量 | 收益 | 建议 |
|------|--------|--------|------|------|
| 4 | 凭空数字检测 | 中 | 增强校验 | **暂不做**，见下方说明 |
| 5 | `verify=False` 修复 | 小 | 理论安全性 | **暂不改**，加注释说明即可 |
| 6 | Perplexity 代码精简 | 中 | 可读性 | **暂不改**，能跑就别动 |
| 7 | 历史报告对比 | 大 | 分析深度 | 未来版本考虑 |
| 8 | 多模型备份 | 中 | 可用性 | 未来版本考虑 |
| 9 | 向量检索（新闻去重） | 大 | 新闻质量 | 未来版本考虑 |

#### 关于"凭空数字检测"的说明

**结论：暂不实现**，理由：
- 当前校验逻辑只遍历 `data_context` 中的数值字段（汇率、利率等）
- **不包含** `news_detail` 新闻摘要中的数字
- 如果报告引用新闻中的数字（如"美联储加息25基点"、"CPI 3.2%"），会被误报为"凭空出现"
- 要解决这个问题需要额外处理新闻文本，增加复杂度
- **当前的 12 个核心指标校验已经足够**，凭空检测是锦上添花

#### 关于 `verify=False` 的说明

**结论：暂不修改**，理由：
- 你的项目是周报生成器，不是交易系统
- 修改后可能导致代理环境下无法访问 Perplexity
- 实际安全风险很低

**建议做法**：在代码中加注释说明
```python
# data_retriever.py
resp = requests.post(
    url,
    verify=False  # 注意：为兼容代理环境禁用SSL验证，非生产最佳实践
)
```

#### 关于 Perplexity 代码精简

**结论：暂不改动**，理由：
- 代码是调试出来的，逻辑已经 work
- 改动可能破坏边界情况处理
- 如果未来需要维护，再考虑重构

---

## 五、架构演进路线图

```
当前状态 (MVP)                    短期目标 (1-2周)                  中期目标 (1-2月)
┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
│ 结构化数据 RAG   │              │ + Token 管理     │              │ + 数据缓存      │
│ 静态历史锚点     │   ──────>   │ + 统一超时配置   │   ──────>   │ + 凭空数字检测   │
│ 硬编码校验       │              │                  │              │ + 报告版本控制   │
│ Perplexity 新闻  │              │                  │              │                  │
└─────────────────┘              └─────────────────┘              └─────────────────┘
     完成度: 70%                      完成度: 80%                      完成度: 90%
     
                                                                  长期目标 (3-6月)
                                                                 ┌─────────────────┐
                                                                 │ + 历史报告对比   │
                                                      ──────>   │ + 多模型备份     │
                                                                 │ + 向量去重(可选) │
                                                                 └─────────────────┘
                                                                      完成度: 95%
```

### 改动优先级速查表

| 优先级 | 改动项 | 改动量 | 影响 | 状态 |
|--------|--------|--------|------|------|
| **P0-1** | Token 预算管理 | 20行 | 防止生成失败 | ✅ **V2 已实现** |
| **P0-2** | 统一超时配置 | 10行 | 减少网络报错 | ✅ **V2 已实现** |
| **P0-3** | Perplexity 分类检索 | 200行 | 提升新闻质量 | ✅ **V2 已实现** |
| **P1-1** | 缓存接通 | 30行 | 避免重复请求 | ✅ **V3 已实现** |
| **P1-2** | 新闻解析 Fallback | 25行 | 增强鲁棒性 | ✅ **V3 已实现** |
| **P1-3** | Self-Citation | 10行 | 降低新闻幻觉 | ✅ **V3 已实现** |
| P2-4 | 凭空数字检测 | 中 | 增强校验 | ⏸️ 暂不做，易误报 |
| P2-5 | `verify=False` | 5行 | 理论安全 | ⏸️ 暂不改，加注释 |
| P2-6 | 历史数据存储 | 中 | 周环比功能 | 📅 未来版本 |
| P2-7+ | 历史对比/多模型 | 大 | 功能扩展 | 📅 未来版本 |

---

## V3 版本更新说明（最新）

### 本次修复的问题

基于 Gemini 的代码审查反馈，V3 版本修复了以下"代码断路"问题：

#### 1. ✅ 缓存接通（Critical Fix）

**问题**：V2 定义了 `get_with_cache()` 函数，但没有在任何地方调用。

**修复**：在以下函数中接通缓存：
- `fetch_cny_data()` - 中间价缓存 1 小时，实时汇率缓存 1 分钟
- `fetch_fred_data()` - FRED 数据缓存 5 分钟

```python
# 修复后的调用方式
mid_df = get_with_cache("cny_mid", _fetch_mid, CACHE_TTL.get("cny_mid", 3600))
```

#### 2. ✅ 新闻解析 Fallback

**问题**：`_parse_news_response()` 完全依赖正则匹配 LLM 输出格式，如果格式稍有变化就会返回空列表。

**修复**：添加降级策略：
```python
# 如果正则解析失败但内容不为空
if not news_items and content and len(content.strip()) > 50:
    # 按段落分割，取前2段作为降级新闻
    paragraphs = content.split('\n\n')
    for para in paragraphs[:2]:
        news_items.append({
            "category": category,
            "title": para.split('。')[0][:100],
            "summary": para[:500],
            "urls": []
        })
```

#### 3. ✅ Self-Citation 机制

**问题**：新闻摘要中的数字无法被硬编码校验器检测，存在幻觉风险。

**修复**：在 `prompt_templates.py` 中添加强制引用要求：
```
【Self-Citation 规则】引用新闻信息时必须标注来源编号：
- 格式：（据新闻#N）或（参见新闻#N）
- 例如：美联储官员暗示可能放缓加息步伐（据新闻#1）
```

这不能完全消除幻觉，但通过给 LLM 施加 Attention 约束，降低胡编乱造的概率。

---

## 六、总结

### 项目做对的事情

1. **选择结构化 RAG 而非向量 RAG** — 在金融精确数据场景是正确决策
2. **硬编码校验** — 用 Python 代码而非 LLM 自查，防幻觉效果好
3. **历史锚点设计** — 用静态数据解决历史对比需求，简洁有效
4. **多数据源聚合** — AKShare + FRED + Perplexity 覆盖定量+定性
5. **追问上下文保持** — 保证多轮对话数据一致性

### 项目需要改进的地方

1. **Token 管理缺失** — 当新闻多时可能超限
2. **安全配置问题** — `verify=False` 不应用于生产
3. **超时配置混乱** — 15s 到 120s 不一致
4. **缺少数据缓存** — 每次都重新采集
5. **校验覆盖不全** — 未检测"凭空出现"的数字

### 最终评价

**作为 MVP，该项目在架构选择上是正确的，核心功能（防幻觉、数据准确性）实现良好。** 

主要差距在于工程健壮性（超时、缓存、Token管理）而非 RAG 架构本身。建议优先修复 P0 级问题后，再考虑功能扩展。

---

*报告生成时间：2025年1月8日*
*分析基于项目代码 v2 版本*
