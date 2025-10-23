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

Example:
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
    "answer": "完整的答案内容，包含引用标号[1][2][3]等",
    "citations": [
        {{
            "id": 1,
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
                max_tokens=10000
            )
            
            content = response.choices[0].message.content
            print(f"[DEBUG] Judgment response: {content}")
            
            # 尝试解析JSON
            try:
                result = json.loads(content)
                print(f"[DEBUG] Parsed judgment result: {result}")
                return result
            except json.JSONDecodeError:
                # 如果不是有效JSON，尝试提取
                print(f"[DEBUG] Failed to parse JSON, extracting from text")
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
                max_tokens=4096,
                stream=True  # 启用流式
            )
            
            accumulated_content = ""
            in_answer_field = False
            answer_text = ""
            brace_count = 0
            
            # 逐块接收并智能提取answer字段内容
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content_piece = chunk.choices[0].delta.content
                    accumulated_content += content_piece
                    
                    # 检测是否进入answer字段
                    if not in_answer_field and '"answer"' in accumulated_content:
                        in_answer_field = True
                        # 找到answer字段开始位置
                        answer_start = accumulated_content.find('"answer"')
                        # 跳过 "answer": "
                        remaining = accumulated_content[answer_start:]
                        colon_pos = remaining.find(':')
                        if colon_pos != -1:
                            after_colon = remaining[colon_pos + 1:].lstrip()
                            if after_colon.startswith('"'):
                                # 找到开始的引号后的内容
                                answer_text = after_colon[1:]
                    
                    # 如果已经在answer字段内，累积内容
                    if in_answer_field:
                        # 检测是否遇到了结束引号（排除转义的\"）
                        for char in content_piece:
                            if char == '"' and (not answer_text or answer_text[-1] != '\\'):
                                # 遇到未转义的引号，可能是answer字段结束
                                in_answer_field = False
                                break
                            else:
                                answer_text += char
                        
                        # 只发送answer字段的纯文本内容
                        if in_answer_field and content_piece:
                            # 清理可能的转义字符
                            clean_piece = content_piece.replace('\\n', '\n').replace('\\"', '"')
                            
                            yield {
                                "type": "answer_chunk",
                                "content": clean_piece,
                            }
            
            print(f"[DEBUG] Stream completed, total length: {len(accumulated_content)}")
            print(f"[DEBUG] Extracted answer length: {len(answer_text)}")
            
            # 流式完成后，解析完整内容以提取 citations
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
                # 如果不是有效JSON，尝试提取
                result = self._extract_answer_from_text(accumulated_content)
                yield {
                    "type": "answer_complete",
                    "answer_data": result
                }
                
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
                max_tokens=4096
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
        """从文本中提取判断结果"""
        # 简单的文本解析逻辑
        can_answer = "true" in text.lower() or "可以" in text or "能够" in text
        confidence = 0.5  # 默认置信度
        
        return {
            "can_answer": can_answer,
            "confidence": confidence,
            "reason": text[:200] + "..." if len(text) > 200 else text,
            "missing_info": "无法确定"
        }

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
                preview = citation.get("preview", "")
                final_answer += f"[{citation_id}] {title} {preview}\n"
        
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