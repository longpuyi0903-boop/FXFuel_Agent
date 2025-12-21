# report_generator.py - 报告生成器

from typing import Optional, Dict, Any
import json

from config import get_deepseek_client, DEEPSEEK_MODEL, REPORT_CONFIG
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
        校验报告（检测幻觉）
        
        Returns:
            校验结果字典
        """
        if self.data_context is None or self.generated_report is None:
            return {"error": "没有可校验的报告"}
        
        # 获取校验提示词
        prompt = get_validation_prompt(
            data_json=self.data_context.to_json(),
            report=self.generated_report
        )
        
        # 调用 LLM 进行校验
        client = self._get_client()
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.1  # 校验任务使用更低温度
        )
        
        try:
            # 尝试解析 JSON 结果
            result_text = response.choices[0].message.content
            # 提取 JSON 部分
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                self.validation_result = json.loads(json_match.group())
            else:
                self.validation_result = {"raw_response": result_text}
        except json.JSONDecodeError:
            self.validation_result = {"raw_response": response.choices[0].message.content}
        
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
