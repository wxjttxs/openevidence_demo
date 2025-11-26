#!/usr/bin/env python3
"""
测试科室分类功能（使用大模型）
需要设置环境变量：
- LLM_API_KEY 或 API_KEY: API密钥
- LLM_BASE_URL 或 API_BASE: API地址（可选，默认使用阿里云）
- LLM_MODEL: 模型名称（可选，默认qwen3-32b）
"""

import os
import sys
from department_classifier import classify_question_and_get_dataset_ids

# 测试用例
test_cases = [
    ("糖尿病患者如何控制血糖？", ["内分泌科"]),
    ("慢性肾衰竭的治疗方案是什么？", ["肾内科"]),
    ("高血压患者的心电图检查", ["心内科"]),
    ("过敏性鼻炎的治疗方法", ["耳鼻喉科"]),
    ("糖尿病肾病患者的治疗方案", ["内分泌科", "肾内科"]),  # 可能涉及多个科室
    ("心脏病合并肾功能不全", ["心内科", "肾内科"]),  # 可能涉及多个科室
    ("甲状腺功能亢进的诊断标准", ["内分泌科"]),
    ("中耳炎的治疗", ["耳鼻喉科"]),
    ("冠心病合并高血压", ["心内科"]),
    ("IgA肾病的预后", ["肾内科"]),
]

def check_env():
    """检查环境变量配置"""
    api_key = os.getenv('LLM_API_KEY') or os.getenv('API_KEY')
    base_url = os.getenv('LLM_BASE_URL') or os.getenv('API_BASE', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    model = os.getenv('LLM_MODEL', 'qwen3-32b')
    
    print("=" * 80)
    print("环境变量配置检查")
    print("=" * 80)
    print(f"API Key: {'已设置' if api_key else '❌ 未设置（需要设置LLM_API_KEY或API_KEY）'}")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print("=" * 80)
    
    if not api_key:
        print("\n⚠️  警告: 未设置API_KEY，将使用默认科室（内分泌科）")
        print("请设置环境变量: export LLM_API_KEY='your-api-key'")
        print("或: export API_KEY='your-api-key'")
        return False
    
    return True

def test_classifier():
    print("\n" + "=" * 80)
    print("科室分类功能测试（使用大模型）")
    print("=" * 80)
    
    if not check_env():
        print("\n跳过测试（环境变量未配置）")
        return
    
    print("\n开始测试...\n")
    
    passed = 0
    failed = 0
    
    for i, (question, expected_departments) in enumerate(test_cases, 1):
        print(f"\n[测试 {i}/{len(test_cases)}]")
        print(f"问题: {question}")
        print(f"期望科室: {expected_departments}")
        
        try:
            result = classify_question_and_get_dataset_ids(question)
            departments = result["departments"]
            dataset_ids = result["dataset_ids"]
            
            print(f"识别科室: {departments}")
            print(f"Dataset IDs: {dataset_ids}")
            
            # 检查是否至少匹配到一个期望的科室
            matched = any(dept in departments for dept in expected_departments)
            status = "✅ PASS" if matched else "❌ FAIL"
            print(f"状态: {status}")
            
            if matched:
                passed += 1
            else:
                failed += 1
                
        except Exception as e:
            print(f"❌ 测试出错: {str(e)}")
            failed += 1
            import traceback
            traceback.print_exc()
        
        print("-" * 80)
    
    # 输出测试总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"总计: {len(test_cases)} 个测试用例")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")
    print("=" * 80)

if __name__ == "__main__":
    test_classifier()

