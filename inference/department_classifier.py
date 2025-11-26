"""
科室分类模块
使用大模型根据用户问题判断所属科室，返回对应的dataset_ids
"""

import logging
import os
import json
import re
from typing import List, Dict, Optional
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError

logger = logging.getLogger(__name__)

# 科室与dataset_ids的映射关系
DEPARTMENT_DATASET_MAP = {
    "肾内科": "654c10c2b53d11f0ba4f0242c0a8a006",
    "耳鼻喉科": "0da740b4b53111f0b80b0242c0a87006",
    "心内科": "5732b33ab4c311f098ff0242c0a87006",
    "内分泌科": "1c9c4d369ce411f093700242ac170006"
}

# 可用科室列表
AVAILABLE_DEPARTMENTS = list(DEPARTMENT_DATASET_MAP.keys())

# 科室分类提示词
CLASSIFICATION_PROMPT = """你是一个专业的医疗科室分类助手。请根据用户提出的医学问题，判断这个问题属于哪个科室。

可用科室：
1. 肾内科 - 涉及肾脏疾病、肾功能、透析、肾移植等
2. 耳鼻喉科 - 涉及耳、鼻、喉、咽等器官的疾病
3. 心内科 - 涉及心脏、心血管疾病、心律失常、心衰等
4. 内分泌科 - 涉及糖尿病、甲状腺疾病、内分泌代谢疾病等

注意：
- 一个问题可能涉及多个科室，请列出所有相关的科室
- 如果问题不明确或无法判断，请返回"内分泌科"作为默认科室
- 请只返回科室名称，多个科室用逗号分隔，不要返回其他内容

用户问题：{question}

请判断这个问题的科室（只返回科室名称，多个科室用逗号分隔）："""


class DepartmentClassifier:
    """使用大模型进行科室分类"""
    
    def __init__(self):
        # 从环境变量读取配置
        self.base_url = os.getenv('LLM_BASE_URL', os.getenv('API_BASE', 'https://dashscope.aliyuncs.com/compatible-mode/v1'))
        self.api_key = os.getenv('LLM_API_KEY', os.getenv('API_KEY', ''))
        self.model = os.getenv('LLM_MODEL', 'qwen3-32b')
        
        # 初始化OpenAI客户端
        self.client = None
        if self.api_key:
            try:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=30.0
                )
                logger.info(f"科室分类器初始化成功 - Model: {self.model}, Base URL: {self.base_url}")
            except Exception as e:
                logger.error(f"初始化OpenAI客户端失败: {str(e)}")
                self.client = None
        else:
            logger.warning("未设置API_KEY环境变量，科室分类功能将不可用")
    
    def classify_department(self, question: str) -> List[str]:
        """
        使用大模型根据问题判断所属科室
        
        Args:
            question: 用户问题
            
        Returns:
            科室列表（可能包含多个科室）
        """
        if not question or not question.strip():
            return []
        
        if not self.client:
            logger.warning("OpenAI客户端未初始化，返回默认科室（内分泌科）")
            return ["内分泌科"]
        
        try:
            # 构建提示词
            prompt = CLASSIFICATION_PROMPT.format(question=question)
            
            # 调用大模型
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的医疗科室分类助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # 降低温度以提高准确性
                max_tokens=512
            )
            
            # 解析响应
            content = response.choices[0].message.content.strip()
            logger.debug(f"大模型返回的科室分类结果: {content}")
            
            # 提取科室名称
            departments = self._parse_departments(content)
            
            # 验证科室名称是否有效
            valid_departments = [dept for dept in departments if dept in AVAILABLE_DEPARTMENTS]
            
            if not valid_departments:
                logger.warning(f"未识别到有效科室，返回默认科室（内分泌科）。原始返回: {content}")
                return ["内分泌科"]
            
            logger.info(f"科室分类成功 - 问题: {question[:50]}..., 识别科室: {valid_departments}")
            return valid_departments
            
        except (APIError, APIConnectionError, APITimeoutError) as e:
            logger.error(f"调用大模型API失败: {str(e)}，返回默认科室（内分泌科）")
            return ["内分泌科"]
        except Exception as e:
            logger.error(f"科室分类过程出错: {str(e)}，返回默认科室（内分泌科）")
            import traceback
            traceback.print_exc()
            return ["内分泌科"]
    
    def _parse_departments(self, content: str) -> List[str]:
        """
        从大模型返回的内容中解析科室名称
        
        Args:
            content: 大模型返回的内容
            
        Returns:
            科室名称列表
        """
        if not content:
            return []
        
        # 移除可能的标点符号和多余字符
        content = content.strip()
        
        # 尝试提取科室名称（支持多种格式）
        departments = []
        
        # 方法1: 直接匹配科室名称
        for dept in AVAILABLE_DEPARTMENTS:
            if dept in content:
                departments.append(dept)
        
        # 方法2: 如果方法1没找到，尝试提取逗号分隔的内容
        if not departments:
            # 移除编号（如"1. "、"①"等）
            content_clean = re.sub(r'^\d+[\.、]\s*', '', content)
            content_clean = re.sub(r'^[①②③④]\s*', '', content_clean)
            
            # 按逗号分割
            parts = [p.strip() for p in content_clean.split('，') if p.strip()]
            parts.extend([p.strip() for p in content_clean.split(',') if p.strip()])
            
            # 匹配科室名称
            for part in parts:
                for dept in AVAILABLE_DEPARTMENTS:
                    if dept in part or part in dept:
                        if dept not in departments:
                            departments.append(dept)
        
        # 方法3: 如果还是没找到，尝试提取中文科室名称（去除"科"字）
        if not departments:
            for dept in AVAILABLE_DEPARTMENTS:
                dept_name_short = dept.replace('科', '')
                if dept_name_short in content:
                    departments.append(dept)
        
        return departments


# 全局分类器实例（懒加载）
_classifier_instance: Optional[DepartmentClassifier] = None


def get_classifier() -> DepartmentClassifier:
    """获取全局分类器实例（单例模式）"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = DepartmentClassifier()
    return _classifier_instance


def classify_department(question: str) -> List[str]:
    """
    根据问题判断所属科室（使用大模型）
    
    Args:
        question: 用户问题
        
    Returns:
        科室列表（可能包含多个科室）
    """
    classifier = get_classifier()
    return classifier.classify_department(question)


def get_dataset_ids_for_departments(departments: List[str]) -> List[str]:
    """
    根据科室列表获取对应的dataset_ids
    
    Args:
        departments: 科室列表
        
    Returns:
        dataset_ids列表
    """
    if not departments:
        # 如果没有匹配到科室，返回默认的（内分泌科）
        return [DEPARTMENT_DATASET_MAP["内分泌科"]]
    
    dataset_ids = []
    for dept in departments:
        if dept in DEPARTMENT_DATASET_MAP:
            dataset_id = DEPARTMENT_DATASET_MAP[dept]
            if dataset_id not in dataset_ids:
                dataset_ids.append(dataset_id)
    
    # 如果匹配到科室但找不到对应的dataset_id，返回默认的
    if not dataset_ids:
        return [DEPARTMENT_DATASET_MAP["内分泌科"]]
    
    return dataset_ids


def classify_question_and_get_dataset_ids(question: str) -> Dict:
    """
    分类问题并返回科室和dataset_ids（使用大模型判断）
    
    Args:
        question: 用户问题
        
    Returns:
        包含departments和dataset_ids的字典
    """
    departments = classify_department(question)
    dataset_ids = get_dataset_ids_for_departments(departments)
    
    result = {
        "departments": departments,
        "dataset_ids": dataset_ids
    }
    
    logger.info(f"问题分类结果 - 问题: {question[:50]}..., 科室: {departments}, dataset_ids: {dataset_ids}")
    
    return result

