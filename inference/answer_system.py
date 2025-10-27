import json
import re
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
import os


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
        
        # 判断检索内容是否能回答问题的提示词
        self.judgment_prompt = """你是一个专业的问答系统评估专家。请评估检索到的内容是否能够回答用户的问题。

用户问题: {question}

检索内容:
{retrieval_content}

请分析检索内容是否包含足够的信息来回答用户问题。评估标准：
1. 检索内容是否与问题主题相关
2. 检索内容是否包含回答问题所需的关键信息
3. 检索内容的质量和完整性

注意：只要检索内容包含相关信息，即使不够完整，也应该判断为可以回答。

请以JSON格式回答：
{{
    "can_answer": true/false,
    "confidence": 0.0-1.0,
    "reason": "详细说明判断理由",
    "missing_info": "如果不能完整回答，说明缺少什么信息"
}}"""

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

Example（正确示例）:
"糖尿病主要分为1型糖尿病[1]和2型糖尿病[2]，还有妊娠糖尿病等特殊类型[3]。

参考文献:

[1] 糖尿病诊疗指南.pdf 
要点：·饮食质量和能量控制是血糖管理的基础...

[2] 内分泌学教材.pdf 
该段落总结了生活方式医学在2型糖尿病（T2D）及糖尿病前期预防和管理中的关键作用...

[3] 妊娠期疾病手册.pdf 
行为与生活方式干预的原则..."

请以JSON格式回答（注意JSON格式的正确性）：
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

    def judge_retrieval_sufficiency(self, question: str, retrieval_content: str) -> Dict:
        """判断检索内容是否足够回答问题"""
        try:
            # 确保输入都是字符串
            if not isinstance(question, str):
                question = str(question)
            if not isinstance(retrieval_content, str):
                retrieval_content = str(retrieval_content)
                
            print(f"[DEBUG] Judging retrieval sufficiency for question: {question[:100]}...")
            print(f"[DEBUG] Retrieval content length: {len(retrieval_content)}")
            
            messages = [
                {
                    "role": "user", 
                    "content": self.judgment_prompt.format(
                        question=question,
                        retrieval_content=retrieval_content
                    )
                }
            ]
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=10000,
                stream=False,
                extra_body={"enable_thinking": False}  # 明确禁用thinking模式（非流式调用）
            )
            
            content = response.choices[0].message.content
            print(f"[DEBUG] Judgment response: {content}")
            
            # 尝试解析JSON（支持markdown包裹的JSON）
            try:
                # 首先尝试直接解析
                result = json.loads(content)
                print(f"[DEBUG] Parsed judgment result: {result}")
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
                    print(f"[DEBUG] Parsed judgment result after cleaning: {result}")
                    return result
                except json.JSONDecodeError:
                    # 如果仍然无法解析，尝试从文本中提取
                    print(f"[DEBUG] Failed to parse JSON even after cleaning, extracting from text")
                    return self._extract_judgment_from_text(content)
                
        except Exception as e:
            print(f"[DEBUG] Error in judgment: {e}")
            import traceback
            traceback.print_exc()
            return {
                "can_answer": False,
                "confidence": 0.0,
                "reason": f"判断过程出错: {str(e)}",
                "missing_info": "无法评估"
            }

    def generate_answer_with_citations_stream(self, question: str, retrieval_results: List[Dict]):
        """流式生成带引用的答案 - 只发送纯文本，前端无需解析JSON"""
        try:
            # 准备来源内容
            sources_content = self.create_sources_content_for_citation(retrieval_results)
            
            print(f"[DEBUG] Streaming answer generation for question: {question[:100]}...")
            print(f"[DEBUG] Sources content length: {len(sources_content)}")
            
            messages = [
                {
                    "role": "user",
                    "content": self.citation_prompt.format(
                        question=question,
                        sources_content=sources_content
                    )
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
            in_answer_field = False
            answer_text = ""
            last_yield_length = 0  # 记录上次发送的位置
            found_answer_start = False
            answer_field_complete = False  # 标记 answer 字段是否已完成提取
            citations_sent = False  # 标记是否已发送citations
            
            # 逐块接收并智能提取answer字段内容
            for chunk in response:
                if answer_field_complete:
                    # answer 字段已提取完成，继续读取剩余数据
                    if chunk.choices[0].delta.content:
                        accumulated_content += chunk.choices[0].delta.content
                        
                        # 尝试提前解析 citations（一旦检测到完整的 citations 数组）
                        if not citations_sent and '"citations"' in accumulated_content and ']' in accumulated_content:
                            try:
                                # 尝试解析已接收的内容
                                temp_content = accumulated_content.strip()
                                # 如果还没有结束花括号，临时添加一个
                                if not temp_content.endswith('}'):
                                    temp_content = temp_content.rstrip(',') + '}'
                                
                                temp_result = json.loads(temp_content)
                                if 'citations' in temp_result and len(temp_result.get('citations', [])) > 0:
                                    # 成功解析到citations，立即发送
                                    print(f"[DEBUG] Early citations parsed: {len(temp_result['citations'])} items")
                                    yield {
                                        "type": "answer_complete",
                                        "answer_data": temp_result
                                    }
                                    citations_sent = True
                            except json.JSONDecodeError:
                                # 解析失败，继续等待更多数据
                                pass
                    continue
                
                if chunk.choices[0].delta.content:
                    content_piece = chunk.choices[0].delta.content
                    accumulated_content += content_piece
                    
                    # 检测是否进入answer字段（只检测一次）
                    if not found_answer_start and '"answer"' in accumulated_content:
                        found_answer_start = True
                        in_answer_field = True
                        # 找到answer字段开始位置（"answer": "后面的内容）
                        answer_start = accumulated_content.find('"answer"')
                        remaining = accumulated_content[answer_start:]
                        colon_pos = remaining.find(':')
                        if colon_pos != -1:
                            after_colon = remaining[colon_pos + 1:].lstrip()
                            if after_colon.startswith('"'):
                                # 找到开始引号后的内容
                                answer_text = after_colon[1:]
                    
                    # 如果已经在answer字段内，处理新增的chunk
                    elif in_answer_field:
                        # 逐字符检查，寻找结束引号
                        for i, char in enumerate(content_piece):
                            # 检测未转义的引号（不是 \"）
                            if char == '"':
                                # 检查前一个字符是否是反斜杠
                                if len(answer_text) > 0 and answer_text[-1] == '\\':
                                    # 这是转义的引号，继续累积
                                    answer_text += char
                                else:
                                    # 这是结束引号，停止累积
                                    in_answer_field = False
                                    answer_field_complete = True
                                    print(f"[DEBUG] Found answer field end, total length: {len(answer_text)}")
                                    break
                            else:
                                answer_text += char
                        
                        # 发送新增内容
                        if len(answer_text) > last_yield_length:
                            # 清理转义字符
                            clean_answer = answer_text.replace('\\n', '\n').replace('\\"', '"')
                            
                            # 检查是否包含"参考文献:"，只发送之前的部分
                            if '\n\n参考文献:' in clean_answer:
                                clean_answer = clean_answer[:clean_answer.find('\n\n参考文献:')]
                            elif '\n参考文献:' in clean_answer:
                                clean_answer = clean_answer[:clean_answer.find('\n参考文献:')]
                            
                            # 只发送新增的部分
                            if len(clean_answer) > last_yield_length:
                                new_content = clean_answer[last_yield_length:]
                                last_yield_length = len(clean_answer)
                                
                                if new_content:  # 确保有内容才发送
                                    yield {
                                        "type": "answer_chunk",
                                        "content": new_content,
                                    }
                        
                        if answer_field_complete:
                            print(f"[DEBUG] Answer field extraction completed, continuing to read remaining data...")
            
            print(f"[DEBUG] Stream completed, total length: {len(accumulated_content)}")
            print(f"[DEBUG] Extracted answer length: {len(answer_text)}")
            print(f"[DEBUG] Accumulated content preview: {accumulated_content[:500]}...")
            print(f"[DEBUG] Accumulated content end: ...{accumulated_content[-500:]}")
            
            # 流式完成后，解析完整内容以提取 citations（如果还没发送）
            if not citations_sent:
                try:
                    # 清理可能的markdown格式
                    content = accumulated_content
                    if content.startswith("```json"):
                        content = content.replace("```json", "").replace("```", "").strip()
                    elif content.startswith("```"):
                        content = content.replace("```", "").strip()
                    
                    result = json.loads(content)
                    print(f"[DEBUG] Parsed complete answer, citations count: {len(result.get('citations', []))}")
                    
                    # 发送最终的完整结果（包含 citations）
                    yield {
                        "type": "answer_complete",
                        "answer_data": result
                    }
                    
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] JSON parse failed: {e}")
                    print(f"[DEBUG] Attempting to fix incomplete JSON...")
                    
                    # 尝试修复不完整的 JSON
                    content = accumulated_content
                    if content.startswith("```json"):
                        content = content.replace("```json", "").replace("```", "").strip()
                    elif content.startswith("```"):
                        content = content.replace("```", "").strip()
                    
                    # 如果 JSON 不完整，尝试手动补全
                    if not content.strip().endswith('}'):
                        # 可能缺少结尾的 }
                        # 尝试找到最后一个完整的 citation 项
                        import re
                        # 查找所有 citation 项
                        citations_pattern = r'"citations"\s*:\s*\[(.*?)(?:\]|$)'
                        citations_match = re.search(citations_pattern, content, re.DOTALL)
                        
                        if citations_match:
                            citations_content = citations_match.group(1)
                            # 补全可能不完整的 JSON
                            content = content.rstrip() + ']}'
                    
                    # 再次尝试解析
                    try:
                        result = json.loads(content)
                        print(f"[DEBUG] Successfully parsed after fixing, citations count: {len(result.get('citations', []))}")
                        yield {
                            "type": "answer_complete",
                            "answer_data": result
                        }
                    except json.JSONDecodeError as e2:
                        print(f"[DEBUG] Still failed after fixing: {e2}")
                        # 如果仍然失败，使用提取方法
                        result = self._extract_answer_from_text(accumulated_content)
                        yield {
                            "type": "answer_complete",
                            "answer_data": result
                        }
            else:
                print(f"[DEBUG] Citations already sent early, skipping final parse")
                
        except Exception as e:
            print(f"[DEBUG] Error in streaming answer: {e}")
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
            
            print(f"[DEBUG] Generating answer with citations for question: {question[:100]}...")
            print(f"[DEBUG] Sources content length: {len(sources_content)}")
            
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
            print(f"[DEBUG] Raw answer generation response: {content}")
            
            # 尝试解析JSON
            try:
                # 清理可能的markdown格式
                if content.startswith("```json"):
                    content = content.replace("```json", "").replace("```", "").strip()
                elif content.startswith("```"):
                    content = content.replace("```", "").strip()
                
                result = json.loads(content)
                print(f"[DEBUG] Parsed answer result: {result}")
                return result
            except json.JSONDecodeError as e:
                print(f"[DEBUG] JSON parse failed: {e}")
                # 如果不是有效JSON，尝试提取
                return self._extract_answer_from_text(content)
                
        except Exception as e:
            print(f"[DEBUG] Error generating answer: {e}")
            import traceback
            traceback.print_exc()
            return {
                "answer": f"生成答案时出错: {str(e)}",
                "citations": []
            }

    def _extract_judgment_from_text(self, text: str) -> Dict:
        """从文本中提取判断结果（改进版：能够提取JSON中的实际值）"""
        print(f"[DEBUG] Extracting judgment from text: {text[:300]}...")
        
        # 尝试提取JSON对象（即使格式不完美）
        import re
        
        # 默认值
        can_answer = False
        confidence = 0.5
        reason = "无法解析判断结果"
        missing_info = "无法确定"
        
        # 尝试提取 can_answer
        can_answer_match = re.search(r'"can_answer"\s*:\s*(true|false)', text, re.IGNORECASE)
        if can_answer_match:
            can_answer = can_answer_match.group(1).lower() == 'true'
        else:
            # 备用：从文本中推断
            can_answer = "true" in text.lower() or "可以" in text or "能够" in text
        
        # 尝试提取 confidence
        confidence_match = re.search(r'"confidence"\s*:\s*(0\.\d+|1\.0|0|1)', text)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
            except ValueError:
                pass
        
        # 尝试提取 reason
        reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', text, re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()
        else:
            # 如果没有找到reason字段，使用清理后的文本片段
            cleaned_text = re.sub(r'```json|```|"can_answer"|"confidence"|"reason"|"missing_info"', '', text)
            cleaned_text = re.sub(r'[{}:,]', ' ', cleaned_text).strip()
            reason = cleaned_text[:200] + "..." if len(cleaned_text) > 200 else cleaned_text
        
        # 尝试提取 missing_info
        missing_match = re.search(r'"missing_info"\s*:\s*"([^"]+)"', text, re.DOTALL)
        if missing_match:
            missing_info = missing_match.group(1).strip()
        
        result = {
            "can_answer": can_answer,
            "confidence": confidence,
            "reason": reason,
            "missing_info": missing_info
        }
        print(f"[DEBUG] Extracted judgment result: {result}")
        return result

    def _extract_answer_from_text(self, text: str) -> Dict:
        """从文本中提取答案和引用"""
        print(f"[DEBUG] Extracting answer from text: {text[:200]}...")
        
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
                                print(f"[DEBUG] Successfully extracted JSON: {result}")
                                return result
                            except json.JSONDecodeError:
                                continue
            
            # 如果无法提取JSON，创建一个简单的答案结构
            print(f"[DEBUG] Could not extract JSON, creating simple answer structure")
            return {
                "answer": text.strip(),
                "citations": []
            }
            
        except Exception as e:
            print(f"[DEBUG] Error in _extract_answer_from_text: {e}")
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
        print(f"[DEBUG] format_final_answer_plain called with: {answer_data}")
        
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
        
        print(f"[DEBUG] Extracted answer: {answer}")
        print(f"[DEBUG] Extracted citations: {citations}")
        
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
        
        print(f"[DEBUG] Final formatted answer: {final_answer}")
        return final_answer

    def parse_retrieval_results(self, retrieval_output: str) -> List[Dict]:
        """解析检索结果"""
        results = []
        
        try:
            # 确保输入是字符串
            if not isinstance(retrieval_output, str):
                retrieval_output = str(retrieval_output)
            
            print(f"[DEBUG] Parsing retrieval output: {retrieval_output[:200]}...")
            
            # 使用正则表达式解析检索结果
            pattern = r'\[(\d+)\] Document: (.*?)\nSimilarity: (.*?)\nContent: (.*?)(?=\n\[|\n---|\Z)'
            matches = re.findall(pattern, retrieval_output, re.DOTALL)
            
            print(f"[DEBUG] Found {len(matches)} matches")
            
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
            
            print(f"[DEBUG] Parsed {len(results)} retrieval results")
            return results
            
        except Exception as e:
            print(f"[DEBUG] Error parsing retrieval results: {str(e)}")
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
        
        print(f"[DEBUG] Created sources content: {sources_content[:500]}...")
        return sources_content