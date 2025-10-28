import json
import re
import logging
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
import os

# 配置日志
logger = logging.getLogger(__name__)


class AnswerJudgmentSystem:
    """答案判断和引用系统"""
    
    def __init__(self):
        self.api_key = os.environ.get("API_KEY")
        self.api_base = os.environ.get("API_BASE")
        self.model_name = os.environ.get("SUMMARY_MODEL_NAME", "")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
        )
        
        # 判断检索内容是否能回答问题的提示词（友好格式输出）
        self.judgment_prompt = """评估检索内容是否能回答用户问题。

问题: {question}

检索内容:
{retrieval_content}

请按以下格式输出评估结果：

**能否回答**: 可以/不能
**置信度**: 0.XX (0.0-1.0之间的数字)
**分析**: 简要说明检索内容的相关性和完整性

注意：输出完"分析"内容后，立即停止。不要输出任何JSON格式的内容。"""

        # 生成带引用答案的提示词
        self.citation_prompt = """你是一个专业的问答专家。请基于提供的检索内容回答用户问题，并严格按照学术论文格式添加引用。

用户问题: {question}

检索内容及来源:
{sources_content}

要求：
When providing final answers, you MUST use academic citation format:
1. Include numbered citations [1][2][3] in your answer text
2. Provide a reference list at the end with format: "Document Title\\n relevant part"
3. Make citations clickable by using the proper format
4. make sure the reference not the same

**CRITICAL: 参考文献编号规则（必须严格遵守）**
- 编号必须从1开始，严格按照在答案中首次出现的顺序分配
- 第一个引用的内容必须标记为[1]，第二个为[2]，第三个为[3]，以此类推
- 绝对禁止跳跃编号，如[1][2][14]或[1][3][5]等
- 编号必须连续递增：1, 2, 3, 4, 5...
- 在citations数组中，id字段也必须对应：1, 2, 3, 4, 5...

**重要：请分两个阶段生成内容**
第一阶段：先生成完整的答案内容（包含引用标号）
第二阶段：立即生成参考文献列表

Example（正确示例）:
第一阶段 - 答案内容:
"糖尿病主要分为1型糖尿病[1]和2型糖尿病[2]，还有妊娠糖尿病等特殊类型[3]。根据最新指南，1型糖尿病需要终身胰岛素治疗[1]，而2型糖尿病可以通过生活方式干预和药物治疗来控制[2]。妊娠糖尿病需要特殊的血糖管理策略[3]。"

第二阶段 - 参考文献:
"参考文献:

[1] 糖尿病诊疗指南.pdf 
要点：·饮食质量和能量控制是血糖管理的基础...

[2] 内分泌学教材.pdf 
该段落总结了生活方式医学在2型糖尿病（T2D）及糖尿病前期预防和管理中的关键作用...

[3] 妊娠期疾病手册.pdf 
行为与生活方式干预的原则..."

请严格按照以下JSON格式回答（注意JSON格式的正确性）：
{{
    "answer": "完整的答案内容，包含引用标号[1][2][3]等（编号必须从1开始依次递增）",
    "citations": [
        {{
            "id": 1,
            "title": "文档标题",
            "preview": "引用内容前30字...",
            "full_content": "完整的引用内容"
        }},
        {{
            "id": 2,
            "title": "文档标题",
            "preview": "引用内容前30字...",
            "full_content": "完整的引用内容"
        }}
    ]
}}"""

    def judge_retrieval_sufficiency_stream(self, question: str, retrieval_content: str):
        """流式判断检索内容是否足够回答问题 - 实时流式输出判断文本"""
        try:
            # 确保输入都是字符串
            if not isinstance(question, str):
                question = str(question)
            if not isinstance(retrieval_content, str):
                retrieval_content = str(retrieval_content)
                
            logger.debug(f"[DEBUG] Judging retrieval sufficiency (streaming) for question: {question[:100]}...")
            logger.debug(f"[DEBUG] Retrieval content length: {len(retrieval_content)}")
            
            messages = [
                {
                    "role": "user", 
                    "content": self.judgment_prompt.format(
                        question=question,
                        retrieval_content=retrieval_content
                    )
                }
            ]
            
            # 使用流式API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=500,
                stream=True,
                extra_body={"enable_thinking": False}
            )
            
            # 流式接收并实时发送内容
            accumulated_content = ""
            judgment_text = ""
            
            for chunk in response:
                if chunk.choices[0].delta.content:
                    chunk_text = chunk.choices[0].delta.content
                    accumulated_content += chunk_text
                    judgment_text += chunk_text
                    
                    # 实时发送判断文本片段
                    yield {
                        "type": "judgment_chunk",
                        "content": chunk_text,
                        "accumulated": judgment_text
                    }
            
            logger.debug(f"[DEBUG] Judgment text complete (length={len(judgment_text)})")
            
            # 流式完成后，直接从文本中提取判断结果（不再依赖JSON）
            try:
                result = self._extract_judgment_from_text(accumulated_content)
                logger.debug(f"[DEBUG] Extracted judgment from text: {result}")
                yield {
                    "type": "judgment_complete",
                    "judgment": result
                }
            except Exception as e:
                logger.debug(f"[DEBUG] Error extracting judgment: {e}")
                # 返回默认值
                yield {
                    "type": "judgment_complete",
                    "judgment": {"can_answer": True, "confidence": 0.5, "reason": "无法解析判断结果"}
                }
                
        except Exception as e:
            logger.debug(f"[DEBUG] Error in streaming judgment: {e}")
            import traceback
            traceback.print_exc()
            
            yield {
                "type": "judgment_error",
                "content": f"判断过程出错: {str(e)}"
            }

    def judge_retrieval_sufficiency(self, question: str, retrieval_content: str) -> Dict:
        """判断检索内容是否足够回答问题 - 使用流式输出加速"""
        try:
            # 确保输入都是字符串
            if not isinstance(question, str):
                question = str(question)
            if not isinstance(retrieval_content, str):
                retrieval_content = str(retrieval_content)
                
            logger.debug(f"[DEBUG] Judging retrieval sufficiency (streaming) for question: {question[:100]}...")
            logger.debug(f"[DEBUG] Retrieval content length: {len(retrieval_content)}")
            
            messages = [
                {
                    "role": "user", 
                    "content": self.judgment_prompt.format(
                        question=question,
                        retrieval_content=retrieval_content
                    )
                }
            ]
            
            # 使用流式API加速响应，限制token数以加快判断速度
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1,  # 降低温度，提高确定性和速度
                max_tokens=500,  # 大幅减少token数，加快响应（判断只需要简短的JSON）
                stream=True,  # 改为流式
                extra_body={"enable_thinking": False}
            )
            
            # 流式接收并累积内容，尝试提前检测完整JSON
            content = ""
            early_parsed = False
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
                    
                    # 尝试提前检测完整的JSON对象（当检测到 }} 时）
                    if not early_parsed and content.count('}') >= 2:
                        try:
                            # 尝试解析当前累积的内容
                            temp_content = content.strip()
                            if temp_content.startswith("```json"):
                                temp_content = temp_content.replace("```json", "").strip()
                            elif temp_content.startswith("```"):
                                temp_content = temp_content.replace("```", "").strip()
                            
                            # 尝试找到第一个完整的JSON对象
                            if '{' in temp_content and '}' in temp_content:
                                start = temp_content.find('{')
                                # 简单的括号匹配
                                depth = 0
                                end = -1
                                for i in range(start, len(temp_content)):
                                    if temp_content[i] == '{':
                                        depth += 1
                                    elif temp_content[i] == '}':
                                        depth -= 1
                                        if depth == 0:
                                            end = i + 1
                                            break
                                
                                if end > 0:
                                    json_str = temp_content[start:end]
                                    result = json.loads(json_str)
                                    # 检查是否包含必要字段
                                    if 'can_answer' in result and 'confidence' in result:
                                        logger.debug(f"[DEBUG] Early parsed judgment result from stream")
                                        early_parsed = True
                                        # 继续接收剩余内容，但不再尝试解析
                                        break
                        except:
                            pass  # 继续接收更多内容
            
            logger.debug(f"[DEBUG] Judgment response (streamed, length={len(content)}): {content[:200]}...")
            
            # 尝试解析JSON（支持markdown包裹的JSON）
            try:
                # 首先尝试直接解析
                result = json.loads(content)
                logger.debug(f"[DEBUG] Parsed judgment result: {result}")
                return result
            except json.JSONDecodeError:
                # 尝试清理markdown标记后再解析
                cleaned_content = content.strip()
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content.replace("```json", "").replace("```", "").strip()
                elif cleaned_content.startswith("```"):
                    cleaned_content = cleaned_content.replace("```", "").strip()
                
                try:
                    result = json.loads(cleaned_content)
                    logger.debug(f"[DEBUG] Parsed judgment result after cleaning: {result}")
                    return result
                except json.JSONDecodeError:
                    # 如果仍然无法解析，尝试从文本中提取
                    logger.debug(f"[DEBUG] Failed to parse JSON even after cleaning, extracting from text")
                    return self._extract_judgment_from_text(content)
                
        except Exception as e:
            logger.debug(f"[DEBUG] Error in judgment: {e}")
            import traceback
            traceback.print_exc()
            return {
                "can_answer": False,
                "confidence": 0.0,
                "reason": f"判断过程出错: {str(e)}",
                "missing_info": "无法评估"
            }

    def _pre_generate_citations(self, question: str, retrieval_results: List[Dict]) -> List[Dict]:
        """
        预生成参考文献列表
        
        Args:
            question: 用户问题
            retrieval_results: 检索结果列表
            
        Returns:
            List[Dict]: 预生成的参考文献列表
        """
        try:
            # 基于检索结果直接构造参考文献
            citations = []
            for i, result in enumerate(retrieval_results[:10], 1):  # 最多10个参考文献
                citation = {
                    "id": i,
                    "title": result.get("title", f"文档 {i}"),
                    "preview": result.get("content", "")[:30] + "..." if len(result.get("content", "")) > 30 else result.get("content", ""),
                    "full_content": result.get("content", "")
                }
                citations.append(citation)
            
            logger.debug(f"[DEBUG] 预生成参考文献完成: {len(citations)} items")
            return citations
            
        except Exception as e:
            logger.debug(f"[DEBUG] 预生成参考文献失败: {e}")
            return []

    def generate_answer_with_citations_stream(self, question: str, retrieval_results: List[Dict]):
        """
        流式生成带引用的答案 - 预生成参考文献优化版本
        
        优化策略：
        1. 先基于检索结果预生成参考文献
        2. 然后流式生成答案文本
        3. 答案生成完成后立即显示预生成的参考文献
        """
        try:
            # 准备来源内容
            sources_content = self.create_sources_content_for_citation(retrieval_results)
            
            logger.debug(f"[DEBUG] Streaming answer generation for question: {question[:100]}...")
            logger.debug(f"[DEBUG] Sources content length: {len(sources_content)}")
            
            # 第一步：预生成参考文献
            logger.debug(f"[DEBUG] 预生成参考文献...")
            pre_generated_citations = self._pre_generate_citations(question, retrieval_results)
            
            # 第二步：流式生成答案文本（不包含参考文献）
            answer_prompt = f"""你是一个专业的问答专家。请基于提供的检索内容回答用户问题，并在答案中添加引用标号。

用户问题: {question}

检索内容及来源:
{sources_content}

要求：
1. 在答案中使用引用标号[1][2][3]等
2. 编号必须从1开始，严格按照在答案中首次出现的顺序分配
3. 只生成答案内容，不要生成参考文献列表

请直接回答用户问题，在相关部分添加引用标号："""
            
            messages = [
                {
                    "role": "user",
                    "content": answer_prompt
                }
            ]
            
            # 使用流式API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.5,
                max_tokens=8192,  # 增加 max_tokens 确保完整生成
                stream=True  # 启用流式
            )
            
            accumulated_content = ""
            answer_text = ""
            last_yield_length = 0  # 记录上次发送的位置
            citations_sent = False  # 标记是否已发送citations
            
            # 简化的流式生成逻辑
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content_piece = chunk.choices[0].delta.content
                    accumulated_content += content_piece
                    answer_text += content_piece
                    
                    # 发送答案片段
                    if len(answer_text) > last_yield_length:
                        new_content = answer_text[last_yield_length:]
                        last_yield_length = len(answer_text)
                        
                        if new_content:
                            yield {
                                "type": "answer_chunk",
                                "content": new_content,
                            }
            
            # 流式完成后，立即发送预生成的参考文献
            logger.debug(f"[DEBUG] Stream completed, answer length: {len(answer_text)}")
            
            if not citations_sent and pre_generated_citations:
                logger.debug(f"[DEBUG] 发送预生成的参考文献: {len(pre_generated_citations)} items")
                
                # 构造完整的answer_data
                answer_data = {
                    "answer": answer_text.strip(),
                    "citations": pre_generated_citations
                }
                
                yield {
                    "type": "answer_complete",
                    "answer_data": answer_data
                }
                citations_sent = True
                
        except Exception as e:
            logger.debug(f"[DEBUG] Error in streaming answer: {e}")
            import traceback
            traceback.print_exc()
            yield {
                "type": "answer_error",
                "content": f"生成答案时出错: {str(e)}"
            }
    
    def generate_answer_with_citations(self, question: str, retrieval_results: List[Dict]) -> Dict:
        """生成带引用的答案（非流式版本，保留用于兼容）"""
        try:
            # 准备来源内容
            sources_content = self.create_sources_content_for_citation(retrieval_results)
            
            logger.debug(f"[DEBUG] Generating answer with citations for question: {question[:100]}...")
            logger.debug(f"[DEBUG] Sources content length: {len(sources_content)}")
            
            messages = [
                {
                    "role": "user",
                    "content": self.citation_prompt.format(
                        question=question,
                        sources_content=sources_content
                    )
                }
            ]
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.5,
                max_tokens=4096,
                stream=False,
                extra_body={"enable_thinking": False}  # 明确禁用thinking模式（非流式调用）
            )
            
            content = response.choices[0].message.content
            logger.debug(f"[DEBUG] Raw answer generation response: {content}")
            
            # 尝试解析JSON
            try:
                # 清理可能的markdown格式
                if content.startswith("```json"):
                    content = content.replace("```json", "").replace("```", "").strip()
                elif content.startswith("```"):
                    content = content.replace("```", "").strip()
                
                result = json.loads(content)
                logger.debug(f"[DEBUG] Parsed answer result: {result}")
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"[DEBUG] JSON parse failed: {e}")
                # 如果不是有效JSON，尝试提取
                return self._extract_answer_from_text(content)
                
        except Exception as e:
            logger.debug(f"[DEBUG] Error generating answer: {e}")
            import traceback
            traceback.print_exc()
            return {
                "answer": f"生成答案时出错: {str(e)}",
                "citations": []
            }

    def _extract_judgment_from_text(self, text: str) -> Dict:
        """从文本中提取判断结果（从格式化文本中提取）"""
        logger.debug(f"[DEBUG] Extracting judgment from text: {text[:300]}...")
        
        import re
        
        # 默认值
        can_answer = True  # 默认假设可以回答
        confidence = 0.8
        reason = "检索内容相关"
        missing_info = ""
        
        # 提取 **能否回答**: 可以/不能
        can_answer_match = re.search(r'\*\*能否回答\*\*:\s*(可以|不能)', text)
        if can_answer_match:
            can_answer = can_answer_match.group(1) == "可以"
        else:
            # 备用：从JSON中提取（如果有）
            can_answer_json = re.search(r'"can_answer"\s*:\s*(true|false)', text, re.IGNORECASE)
            if can_answer_json:
                can_answer = can_answer_json.group(1).lower() == 'true'
            else:
                # 从文本推断
                can_answer = "可以" in text or "能够" in text
        
        # 提取 **置信度**: 0.XX
        confidence_match = re.search(r'\*\*置信度\*\*:\s*(0\.\d+|1\.0|0|1)', text)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
            except ValueError:
                pass
        else:
            # 备用：从JSON中提取（如果有）
            confidence_json = re.search(r'"confidence"\s*:\s*(0\.\d+|1\.0|0|1)', text)
            if confidence_json:
                try:
                    confidence = float(confidence_json.group(1))
                except ValueError:
                    pass
        
        # 提取 **分析**: 后的内容作为reason
        analysis_match = re.search(r'\*\*分析\*\*:\s*(.+?)(?:\n\n|\{|$)', text, re.DOTALL)
        if analysis_match:
            reason = analysis_match.group(1).strip()
        else:
            # 备用：从JSON中提取（如果有）
            reason_json = re.search(r'"reason"\s*:\s*"([^"]+)"', text, re.DOTALL)
            if reason_json:
                reason = reason_json.group(1).strip()
            else:
                # 使用整个文本（清理后）
                cleaned_text = re.sub(r'```json|```|\{.*\}', '', text, flags=re.DOTALL)
                cleaned_text = re.sub(r'\*\*能否回答\*\*:.*?\n', '', cleaned_text)
                cleaned_text = re.sub(r'\*\*置信度\*\*:.*?\n', '', cleaned_text)
                cleaned_text = re.sub(r'\*\*分析\*\*:\s*', '', cleaned_text)
                reason = cleaned_text.strip()[:300]
        
        # 尝试提取 missing_info（如果有JSON）
        missing_match = re.search(r'"missing_info"\s*:\s*"([^"]+)"', text, re.DOTALL)
        if missing_match:
            missing_info = missing_match.group(1).strip()
        
        result = {
            "can_answer": can_answer,
            "confidence": confidence,
            "reason": reason,
            "missing_info": missing_info
        }
        logger.debug(f"[DEBUG] Extracted judgment result: {result}")
        return result

    def _extract_answer_from_text(self, text: str) -> Dict:
        """从文本中提取答案和引用"""
        logger.debug(f"[DEBUG] Extracting answer from text: {text[:200]}...")
        
        try:
            # 尝试从文本中提取JSON部分
            # 查找可能的JSON块
            start_markers = ['{', '{\n', '```json\n{', '```\n{']
            end_markers = ['}', '\n}', '}\n```', '}\n']
            
            for start_marker in start_markers:
                start_idx = text.find(start_marker)
                if start_idx != -1:
                    for end_marker in end_markers:
                        end_idx = text.rfind(end_marker)
                        if end_idx > start_idx:
                            json_text = text[start_idx:end_idx + len(end_marker.rstrip('\n'))]
                            try:
                                result = json.loads(json_text)
                                logger.debug(f"[DEBUG] Successfully extracted JSON: {result}")
                                return result
                            except json.JSONDecodeError:
                                continue
            
            # 如果无法提取JSON，创建一个简单的答案结构
            logger.debug(f"[DEBUG] Could not extract JSON, creating simple answer structure")
            return {
                "answer": text.strip(),
                "citations": []
            }
            
        except Exception as e:
            logger.debug(f"[DEBUG] Error in _extract_answer_from_text: {e}")
            return {
                "answer": text.strip() if text else "无法生成答案",
                "citations": []
            }

    def format_final_answer(self, answer_data: Dict) -> str:
        """格式化最终答案，支持可点击的引用展开"""
        # 确保answer_data是字典
        if isinstance(answer_data, str):
            try:
                answer_data = json.loads(answer_data)
            except json.JSONDecodeError:
                return answer_data  # 如果不是JSON，直接返回原始字符串
        
        answer = answer_data.get("answer", "")
        citations = answer_data.get("citations", [])
        
        # 如果没有answer字段，可能整个答案就在answer_data中
        if not answer and isinstance(answer_data, str):
            answer = answer_data
        
        # 构建最终答案
        final_answer = answer + "\n\n"
        
        if citations:
            final_answer += "参考文献: \n\n"
            for citation in citations:
                citation_id = citation.get("id", "")
                title = citation.get("title", "")
                preview = citation.get("preview", "")
                full_content = citation.get("full_content", "")
                similarity = citation.get("similarity", 0.0)
                
                # 生成可点击的引用格式
                # 使用HTML格式支持点击展开
                clickable_preview = f'<span class="citation-preview" data-full-content="{full_content}" data-citation-id="{citation_id}">{preview}</span>'
                final_answer += f"[{citation_id}] {title} {clickable_preview}\n"
        
        return final_answer

    def format_final_answer_plain(self, answer_data: Dict) -> str:
        """格式化最终答案（纯文本版本）"""
        logger.debug(f"[DEBUG] format_final_answer_plain called with: {answer_data}")
        
        # 确保answer_data是字典
        if isinstance(answer_data, str):
            try:
                answer_data = json.loads(answer_data)
            except json.JSONDecodeError:
                return answer_data  # 如果不是JSON，直接返回原始字符串
        
        answer = answer_data.get("answer", "")
        citations = answer_data.get("citations", [])
        
        # 如果没有answer字段，可能整个答案就在answer_data中
        if not answer and isinstance(answer_data, str):
            answer = answer_data
        
        logger.debug(f"[DEBUG] Extracted answer: {answer}")
        logger.debug(f"[DEBUG] Extracted citations: {citations}")
        
        # 构建最终答案
        final_answer = answer
        
        if citations and len(citations) > 0:
            final_answer += "\n\n参考文献:\n"
            for citation in citations:
                citation_id = citation.get("id", "")
                title = citation.get("title", "")
                full_content = citation.get("full_content", "")
                
                # 截取前30个字作为预览
                preview = full_content[:30] if len(full_content) > 30 else full_content
                
                # 格式：[编号] 文章题目（换行）参考片段（前30字）
                final_answer += f"[{citation_id}] {title}\n{preview}\n"
        
        logger.debug(f"[DEBUG] Final formatted answer: {final_answer}")
        return final_answer

    def parse_retrieval_results(self, retrieval_output: str) -> List[Dict]:
        """解析检索结果"""
        results = []
        
        try:
            # 确保输入是字符串
            if not isinstance(retrieval_output, str):
                retrieval_output = str(retrieval_output)
            
            logger.debug(f"[DEBUG] Parsing retrieval output: {retrieval_output[:200]}...")
            
            # 使用正则表达式解析检索结果
            pattern = r'\[(\d+)\] Document: (.*?)\nSimilarity: (.*?)\nContent: (.*?)(?=\n\[|\n---|\Z)'
            matches = re.findall(pattern, retrieval_output, re.DOTALL)
            
            logger.debug(f"[DEBUG] Found {len(matches)} matches")
            
            for match in matches:
                index, title, similarity, content = match
                
                # 处理内容，生成预览和完整内容
                content = content.strip()
                preview = content[:30] + "..." if len(content) > 30 else content
                
                results.append({
                    "id": int(index),
                    "title": title.strip(),
                    "similarity": float(similarity.strip()),
                    "content": content,
                    "preview": preview,
                    "full_content": content
                })
            
            logger.debug(f"[DEBUG] Parsed {len(results)} retrieval results")
            return results
            
        except Exception as e:
            logger.debug(f"[DEBUG] Error parsing retrieval results: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def create_sources_content_for_citation(self, retrieval_results: List[Dict]) -> str:
        """为引用生成创建来源内容字符串"""
        sources_content = ""
        for i, result in enumerate(retrieval_results, 1):
            title = result.get("title", f"文档{i}")
            content = result.get("content", "")
            similarity = result.get("similarity", 0.0)
            
            # 确保结果有正确的ID（用于引用）
            if "id" not in result:
                result["id"] = i
            
            # 确保有预览文本
            if "preview" not in result:
                result["preview"] = content[:30] + "..." if len(content) > 30 else content
            
            sources_content += f"[{i}] 标题: {title}\n"
            sources_content += f"相似度: {similarity:.3f}\n"
            sources_content += f"内容: {content}\n\n"
        
        logger.debug(f"[DEBUG] Created sources content: {sources_content[:500]}...")
        return sources_content