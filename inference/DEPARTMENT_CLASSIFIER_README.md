# 科室分类功能说明

## 概述

科室分类功能使用大模型（LLM）根据用户问题自动判断所属科室，并返回对应的 `dataset_ids`，以优化检索效率。

## 环境变量配置

科室分类功能需要以下环境变量：

- **LLM_API_KEY** 或 **API_KEY**: API密钥（必需）
- **LLM_BASE_URL** 或 **API_BASE**: API地址（可选，默认：`https://dashscope.aliyuncs.com/compatible-mode/v1`）
- **LLM_MODEL**: 模型名称（可选，默认：`qwen3-32b`）

### 设置示例

```bash
export LLM_API_KEY='your-api-key-here'
export LLM_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export LLM_MODEL='qwen3-32b'
```

## 科室映射

| 科室 | Dataset ID |
|------|------------|
| 肾内科 | 654c10c2b53d11f0ba4f0242c0a8a006 |
| 耳鼻喉科 | 0da740b4b53111f0b80b0242c0a87006 |
| 心内科 | 5732b33ab4c311f098ff0242c0a87006 |
| 内分泌科 | 1c9c4d369ce411f093700242ac170006 |

## 使用方法

### Python代码中使用

```python
from department_classifier import classify_question_and_get_dataset_ids

# 分类问题并获取dataset_ids
result = classify_question_and_get_dataset_ids("糖尿病患者如何控制血糖？")
print(f"科室: {result['departments']}")
print(f"Dataset IDs: {result['dataset_ids']}")
```

### 在streaming_agent.py中的自动使用

在 `streaming_agent.py` 中，当LLM调用检索工具时，如果未提供 `dataset_ids`，系统会自动根据问题判断科室并补充 `dataset_ids`。

## 工作原理

1. **问题输入**: 用户提交医学问题
2. **大模型判断**: 使用LLM分析问题，判断所属科室（可能涉及多个科室）
3. **映射转换**: 将科室名称映射为对应的 `dataset_ids`
4. **检索优化**: 只在相关科室的知识库中检索，避免全库检索

## 容错机制

- 如果API调用失败，返回默认科室（内分泌科）
- 如果未设置API_KEY，返回默认科室（内分泌科）
- 如果大模型返回的科室名称无法识别，返回默认科室（内分泌科）

## 测试

运行测试脚本：

```bash
cd inference
python test_department_classifier.py
```

确保已设置必要的环境变量。

## 注意事项

1. 首次调用时会初始化分类器（单例模式）
2. API调用有30秒超时限制
3. 大模型返回结果会经过多级解析，确保能正确提取科室名称
4. 支持多科室识别（如"糖尿病肾病"会同时匹配内分泌科和肾内科）

