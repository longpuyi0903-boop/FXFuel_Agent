# report_generator.py - 报告生成器

from typing import Optional, Dict, Any
import json
import re

from config import get_deepseek_client, DEEPSEEK_MODEL, REPORT_CONFIG, CORE_INDICATORS, DEFAULT_TOLERANCE
from data_retriever import DataContext, retrieve_all_data
from prompt_templates import get_report_prompt, get_followup_prompt, get_validation_prompt


class ReportGenerator:
    """外汇周报生成器"""
    
    def __init__(self):
        self.client = None  # 延迟初始化
        self.data_context: Optional[DataContext] = None
        self.generated_report: Optional[str] = None
        self.validation_result: Optional[Dict] = None
    
    def _get_client(self):
        """获取 DeepSeek 客户端（延迟初始化）"""
        if self.client is None:
            self.client = get_deepseek_client()
        return self.client
    
    def collect_data(self) -> DataContext:
        """采集数据"""
        self.data_context = retrieve_all_data()
        return self.data_context
    
    def generate_report(self, data_context: Optional[DataContext] = None) -> str:
        """
        生成周报
        
        Args:
            data_context: 数据上下文，如果为 None 则自动采集
            
        Returns:
            生成的报告 Markdown 文本
        """
        # 如果没有提供数据，则采集
        if data_context is None:
            if self.data_context is None:
                self.collect_data()
            data_context = self.data_context
        else:
            self.data_context = data_context
        
        # 获取提示词
        data_json = data_context.to_json()
        prompts = get_report_prompt(data_json)
        
        # 调用 LLM
        client = self._get_client()
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": prompts["user"]}
            ],
            max_tokens=REPORT_CONFIG["max_tokens"],
            temperature=REPORT_CONFIG["temperature"]
        )
        
        self.generated_report = response.choices[0].message.content
        return self.generated_report
    
    def answer_followup(self, question: str) -> str:
        """
        回答追问
        
        Args:
            question: 用户的追问问题
            
        Returns:
            回答文本
        """
        if self.data_context is None or self.generated_report is None:
            return "请先生成报告再进行追问。"
        
        # 获取追问提示词
        prompts = get_followup_prompt(
            data_json=self.data_context.to_json(),
            report=self.generated_report,
            question=question
        )
        
        # 调用 LLM
        client = self._get_client()
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": prompts["user"]}
            ],
            max_tokens=2000,
            temperature=REPORT_CONFIG["temperature"]
        )
        
        return response.choices[0].message.content
    
    def validate_report(self) -> Dict[str, Any]:
        """
        校验报告（检测幻觉）- 使用硬编码校验逻辑
        
        Returns:
            校验结果字典
        """
        if self.data_context is None or self.generated_report is None:
            return {"error": "没有可校验的报告"}
        
        # 将 DataContext 转换为字典格式（与 streamlit_app.py 中的格式一致）
        ctx_dict = {
            "USDCNY_MID": self.data_context.cny.get("usdcny_mid"),
            "USDCNH_CLOSE": self.data_context.cny.get("usdcnh_spot"),
            "CNY_SPREAD": self.data_context.cny.get("cny_spread"),
            "USDHKD": self.data_context.hkd.get("usdhkd"),
            "HIBOR_OVERNIGHT": self.data_context.hkd.get("hibor_overnight"),
            "HKD_USD_SPREAD": self.data_context.hkd.get("hkd_usd_spread"),
            "EURUSD": self.data_context.global_fx.get("eurusd"),
            "USDJPY": self.data_context.global_fx.get("usdjpy"),
            "DXY": self.data_context.global_fx.get("dxy"),
            "US10Y_YIELD": self.data_context.macro.get("us10y"),
            "US2Y_YIELD": self.data_context.macro.get("us2y"),
            "VIX_LAST": self.data_context.macro.get("vix"),
        }
        
        # 调用硬编码校验函数
        self.validation_result = verify_numbers_hard_code(ctx_dict, self.generated_report)
        return self.validation_result
    
    def get_data_summary(self) -> str:
        """获取数据摘要（用于展示）"""
        if self.data_context is None:
            return "尚未采集数据"
        
        ctx = self.data_context
        summary_parts = []
        
        # 人民币数据摘要
        if ctx.cny:
            cny_items = []
            if ctx.cny.get("usdcny_mid_latest"):
                cny_items.append(f"中间价: {ctx.cny['usdcny_mid_latest']}")
            if ctx.cny.get("usdcnh_spot"):
                cny_items.append(f"离岸: {ctx.cny['usdcnh_spot']}")
            if ctx.cny.get("usdcny_mid_weekly_high") and ctx.cny.get("usdcny_mid_weekly_low"):
                cny_items.append(f"本周区间: {ctx.cny['usdcny_mid_weekly_low']}-{ctx.cny['usdcny_mid_weekly_high']}")
            if cny_items:
                summary_parts.append(f"**人民币**: " + " | ".join(cny_items))
        
        # 港元数据摘要
        if ctx.hkd:
            hkd_items = []
            if ctx.hkd.get("usdhkd_spot"):
                hkd_items.append(f"USD/HKD: {ctx.hkd['usdhkd_spot']}")
            if ctx.hkd.get("lers_position"):
                hkd_items.append(f"区间: {ctx.hkd['lers_position']}")
            if ctx.hkd.get("hibor_overnight"):
                hkd_items.append(f"HIBOR隔夜: {ctx.hkd['hibor_overnight']}%")
            if hkd_items:
                summary_parts.append(f"**港元**: " + " | ".join(hkd_items))
        
        # 全球市场摘要
        if ctx.global_fx:
            global_items = []
            if ctx.global_fx.get("dxy"):
                global_items.append(f"DXY: {ctx.global_fx['dxy']}")
            if ctx.global_fx.get("us10y_yield"):
                global_items.append(f"10Y: {ctx.global_fx['us10y_yield']}%")
            if ctx.global_fx.get("vix"):
                global_items.append(f"VIX: {ctx.global_fx['vix']}")
            if global_items:
                summary_parts.append(f"**全球**: " + " | ".join(global_items))
        
        # 数据采集状态
        status = f"\n\n📊 数据点: {ctx._count_data_points()} | ⚠️ 错误: {len(ctx.errors)}"
        
        return "\n".join(summary_parts) + status if summary_parts else "数据采集中..."
    
    def get_raw_data(self) -> str:
        """获取原始数据 JSON（用于调试）"""
        if self.data_context is None:
            return "{}"
        return self.data_context.to_json()


# ============================================================================
# 硬编码校验函数
# ============================================================================

def verify_numbers_hard_code(data_context: Dict[str, Any], report_text: str) -> Dict[str, Any]:
    """
    使用硬编码逻辑校验报告中的数值是否与原始数据一致
    
    Args:
        data_context: 数据字典，键名为 CORE_INDICATORS 中定义的 data_field
        report_text: 生成的报告文本
        
    Returns:
        校验结果字典，包含 is_valid 和 audit_log
    """
    audit_log = []
    is_valid = True
    
    # 浮点数正则表达式（支持负数）
    float_pattern = r'-?\d+\.?\d*'
    
    # 遍历所有核心指标
    for indicator_name, config in CORE_INDICATORS.items():
        keywords = config["keywords"]
        data_field = config["data_field"]
        tolerance = config.get("tolerance", DEFAULT_TOLERANCE)
        
        # 获取原始数据值
        raw_val = data_context.get(data_field)
        
        # 如果原始数据为 None，标记为 WARNING（数据缺失），不进行比对
        if raw_val is None:
            audit_log.append({
                "item": indicator_name,
                "report_val": None,
                "raw_val": None,
                "diff": None,
                "status": "WARNING",
                "msg": "数据缺失"
            })
            continue
        
        # 尝试从报告中提取数值
        report_val = None
        matched_keyword = None
        
        for keyword in keywords:
            # 在报告中搜索关键词位置
            keyword_match = re.search(re.escape(keyword), report_text, re.IGNORECASE)
            
            if keyword_match:
                # 从关键词结束位置开始，向后搜索30字符内的浮点数
                keyword_end_pos = keyword_match.end()
                search_text = report_text[keyword_end_pos:keyword_end_pos + 50]  # 向后搜索50字符
                
                # 在搜索文本中查找浮点数（避免匹配关键词本身包含的数字）
                # 优先匹配带小数点的数字（更可能是实际数值，而不是年份或编号）
                decimal_pattern = r'-?\d+\.\d+'
                number_matches = re.findall(decimal_pattern, search_text)
                
                # 如果没有找到带小数点的数字，再尝试匹配整数
                if not number_matches:
                    number_matches = re.findall(float_pattern, search_text)
                
                if number_matches:
                    # 尝试每个数值，选择最接近原始值的那个
                    best_val = None
                    min_diff = float('inf')
                    
                    for num_str in number_matches:
                        try:
                            candidate_val = float(num_str)
                            # 计算与原始值的差异
                            diff = abs(candidate_val - raw_val)
                            
                            # 选择差异最小的数值（但也要在合理范围内，差异超过10的可能是误匹配）
                            if diff < min_diff and diff < 10:
                                min_diff = diff
                                best_val = candidate_val
                        except ValueError:
                            continue
                    
                    if best_val is not None:
                        report_val = best_val
                        matched_keyword = keyword
                        break  # 找到匹配就退出关键词循环
        
        # 判断结果
        if report_val is None:
            # 未在报告中提及
            audit_log.append({
                "item": indicator_name,
                "report_val": None,
                "raw_val": raw_val,
                "diff": None,
                "status": "WARNING",
                "msg": "未在报告中提及"
            })
            # WARNING 不影响 is_valid 状态
        else:
            # 进行数值比对
            diff = abs(report_val - raw_val)
            
            if diff <= tolerance:
                status = "PASS"
                msg = f"一致（差异 {diff:.4f} <= 容差 {tolerance}）"
            else:
                status = "FAIL"
                msg = f"差异 {diff:.4f} > 容差 {tolerance}"
                is_valid = False  # 有一个失败就标记为无效
            
            audit_log.append({
                "item": indicator_name,
                "report_val": report_val,
                "raw_val": raw_val,
                "diff": round(diff, 4),
                "status": status,
                "msg": msg
            })
    
    return {
        "is_valid": is_valid,
        "audit_log": audit_log
    }


# ============================================================================
# 便捷函数
# ============================================================================

def generate_fx_report() -> tuple[str, DataContext]:
    """
    一键生成外汇周报
    
    Returns:
        (报告文本, 数据上下文)
    """
    generator = ReportGenerator()
    generator.collect_data()
    report = generator.generate_report()
    return report, generator.data_context


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("外汇周报生成器测试")
    print("="*60)
    
    generator = ReportGenerator()
    
    # 1. 采集数据
    print("\n[1] 采集数据...")
    ctx = generator.collect_data()
    print(generator.get_data_summary())
    
    # 2. 生成报告
    print("\n[2] 生成报告...")
    report = generator.generate_report()
    print("\n" + "-"*60)
    print(report)
    print("-"*60)
    
    # 3. 校验报告
    print("\n[3] 校验报告...")
    validation = generator.validate_report()
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    
    # 4. 测试追问
    print("\n[4] 测试追问...")
    answer = generator.answer_followup("本周人民币中间价具体是多少？")
    print(answer)
