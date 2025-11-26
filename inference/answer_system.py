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
        self.model_name = os.environ.get("LLM_MODEL", "")
        self.summary_model_name = os.environ.get("SUMMARY_MODEL_NAME", "")
        
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
**分析**: 简要分析检索内容是否能够回答问题及原因，字数限制在300字以内。

注意：输出完"分析"内容后，立即停止。不要输出任何JSON格式的内容。"""

        # 生成带引用答案的提示词
        self.citation_prompt = """你是一个专业的临床医生。请基于提供的检索内容回答用户问题，并严格按照学术论文格式添加引用。

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
        预生成参考文献列表（使用retrieval_XX编号）
        
        Args:
            question: 用户问题
            retrieval_results: 检索结果列表
            
        Returns:
            List[Dict]: 预生成的参考文献列表，包含retrieval_id字段
        """
        try:
            # 基于检索结果直接构造参考文献，使用retrieval_01到retrieval_XX的编号（按实际数量）
            citations = []
            
            for i in range(len(retrieval_results)):
                result = retrieval_results[i]
                # 根据实际数量决定编号格式：1-9用01-09，10以上用实际数字
                if i + 1 < 10:
                    retrieval_id = f"retrieval_{i+1:02d}"  # retrieval_01, retrieval_02, ..., retrieval_09
                else:
                    retrieval_id = f"retrieval_{i+1}"  # retrieval_10, retrieval_11, ...
                
                citation = {
                    "id": i + 1,  # 临时ID，后续会被替换
                    "retrieval_id": retrieval_id,  # 检索编号：retrieval_01, retrieval_02, ...
                    "title": result.get("title", f"文档 {i+1}"),
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
            answer_prompt = f"""**请根据以下检索内容回答用户问题：**

**提示：** 在回答中引用文献时，**必须使用ref01, ref02, ref03...这样的编号格式**，从ref01开始，按首次引用的顺序依次递增。**不要生成参考文献列表**。**不要在答案中添加任何注释说明**。

## 引用编号规则（严格遵守）：

* **重要**：检索内容中的每篇文献已经标记了编号 [retrieval_01], [retrieval_02], [retrieval_03]...（见下方检索内容）
* **但在答案中引用时，必须使用ref01, ref02, ref03...这样的格式**
* **编号必须从ref01开始，按首次引用的顺序连续递增**
* **引用格式**：在答案中使用 [ref01], [ref02], [ref03]... 这样的格式引用文献
* **映射说明**：在首次引用某个文献时，可以在ref编号后注明对应的retrieval编号，格式为 [ref01(retrieval_03)]，后续引用同一文献时只需使用 [ref01]
* **禁止添加注释**：不要在答案中添加任何关于引用映射的注释说明（如"注：[retrieval_01]与[retrieval_02]内容一致"等），只输出答案内容本身

**正确示例：**
检索结果：
[retrieval_01] 标题: 糖尿病诊断指南
[retrieval_02] 标题: 糖尿病治疗指南  
[retrieval_03] 标题: 糖尿病并发症指南

如果答案中先引用retrieval_03，再引用retrieval_01，应该写：
"糖尿病并发症需要特别注意[ref01(retrieval_03)]，同时遵循诊断标准[ref02(retrieval_01)]..."
或者：
"糖尿病并发症需要特别注意[ref01]，同时遵循诊断标准[ref02]..."

**错误示例：**
"糖尿病并发症需要特别注意[retrieval_03]，同时遵循诊断标准[retrieval_01]..." ← 错误！必须使用ref01, ref02格式
"糖尿病并发症需要特别注意[ref02]，同时遵循诊断标准[ref01]..." ← 错误！必须从ref01开始，按顺序递增

---
## 检索内容：{sources_content}

## 问题如下："""
            
            messages = [
                {
                    "role": "system",
                    "content": answer_prompt
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
            
            # 使用流式API（优化首token响应速度）
            import time
            api_start_time = time.time()
            logger.info(f"🚀 开始调用答案生成API (模型: {self.summary_model_name})")
            
            response = self.client.chat.completions.create(
                model=self.summary_model_name,
                messages=messages,
                temperature=0.1,  # 极低temperature确保严格遵守规则
                max_tokens=2048,  # 进一步减少max_tokens加快首token (4096→2048)
                stream=True  # 启用流式
            )
            
            accumulated_content = ""
            answer_text = ""
            last_yield_length = 0  # 记录上次发送的位置
            citations_sent = False  # 标记是否已发送citations
            first_token_received = False  # 标记首token
            
            # 简化的流式生成逻辑
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content_piece = chunk.choices[0].delta.content
                    
                    # 记录首token时间
                    if not first_token_received:
                        first_token_time = time.time() - api_start_time
                        logger.info(f"⚡ 收到首个token，耗时: {first_token_time:.2f}秒")
                        first_token_received = True
                    
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
            
            # 流式完成后，过滤并发送实际使用的参考文献
            logger.debug(f"[DEBUG] Stream completed, answer length: {len(answer_text)}")
            
            if not citations_sent and pre_generated_citations:
                # 提取答案中实际使用的引用编号（ref01, ref02, ref03...格式）
                import re
                ref_citations = []  # 存储按首次出现顺序的ref编号
                ref_to_retrieval = {}  # {ref01: retrieval_01, ref02: retrieval_02, ...}
                
                # 匹配 [ref01], [ref02]... 或 [ref01(retrieval_XX)] 格式（不区分大小写）
                # 先匹配带括号的格式: [ref01(retrieval_03)]
                for match in re.finditer(r'\[ref(\d+)\(retrieval_\d+\)\]', answer_text, re.IGNORECASE):
                    ref_num = int(match.group(1))
                    ref_id = f"ref{ref_num:02d}"  # ref01, ref02, ...
                    if ref_id not in ref_citations:
                        ref_citations.append(ref_id)
                
                # 再匹配不带括号的格式: [ref01]（避免重复添加）
                for match in re.finditer(r'\[ref(\d+)\]', answer_text, re.IGNORECASE):
                    ref_num = int(match.group(1))
                    ref_id = f"ref{ref_num:02d}"  # ref01, ref02, ...
                    if ref_id not in ref_citations:
                        ref_citations.append(ref_id)
                
                logger.info(f"📚 答案中引用的ref编号（按首次出现顺序）: {ref_citations}")
                
                # 创建retrieval_id到citation的映射
                retrieval_to_citation = {}
                for c in pre_generated_citations:
                    retrieval_id = c.get('retrieval_id', f'retrieval_{c["id"]:02d}')
                    retrieval_to_citation[retrieval_id] = c
                
                # 建立ref到retrieval的映射关系
                # 方法：从答案中提取ref编号对应的retrieval_id
                # 查找答案中ref编号附近是否有retrieval_XX的引用
                used_citations = []
                
                for ref_idx, ref_id in enumerate(ref_citations):
                    # 尝试从答案中找到ref_id对应的retrieval_id
                    # 方法1：查找ref_id后是否有(retrieval_XX)的说明，格式为 [ref01(retrieval_03)]
                    ref_with_retrieval_pattern = rf'\[{re.escape(ref_id)}\(retrieval_(\d+)\)\]'
                    match = re.search(ref_with_retrieval_pattern, answer_text, re.IGNORECASE)
                    
                    retrieval_id = None
                    if match:
                        # 找到了明确的映射关系
                        retrieval_num = int(match.group(1))
                        # 根据数字大小决定格式：1-9用01-09，10以上用实际数字
                        if retrieval_num < 10:
                            retrieval_id = f"retrieval_{retrieval_num:02d}"  # retrieval_01, retrieval_02, ...
                        else:
                            retrieval_id = f"retrieval_{retrieval_num}"  # retrieval_10, retrieval_11, ...
                        logger.debug(f"✅ 找到映射关系: {ref_id} -> {retrieval_id}")
                    else:
                        # 方法2：查找ref_id附近是否有retrieval_XX引用
                        # 查找ref_id前后50个字符范围内的retrieval_XX
                        ref_positions = [m.start() for m in re.finditer(rf'\[{re.escape(ref_id)}\]', answer_text, re.IGNORECASE)]
                        if ref_positions:
                            ref_pos = ref_positions[0]  # 使用第一个出现的位置
                            context_start = max(0, ref_pos - 50)
                            context_end = min(len(answer_text), ref_pos + 50)
                            context = answer_text[context_start:context_end]
                            
                            # 在上下文中查找retrieval_XX（匹配retrieval_01或retrieval_10等格式）
                            retrieval_match = re.search(r'retrieval_(\d+)', context, re.IGNORECASE)
                            if retrieval_match:
                                retrieval_num = int(retrieval_match.group(1))
                                # 根据数字大小决定格式：1-9用01-09，10以上用实际数字
                                if retrieval_num < 10:
                                    retrieval_id = f"retrieval_{retrieval_num:02d}"  # retrieval_01, retrieval_02, ...
                                else:
                                    retrieval_id = f"retrieval_{retrieval_num}"  # retrieval_10, retrieval_11, ...
                                logger.debug(f"✅ 在上下文中找到映射关系: {ref_id} -> {retrieval_id}")
                    
                    # 如果没找到明确的映射，按ref编号顺序依次映射到检索结果
                    # 这里简化处理：按ref编号顺序，依次选择检索结果
                    if not retrieval_id:
                        # 按顺序选择：ref01 -> retrieval_01, ref02 -> retrieval_02...
                        # 注意：这不是最优方案，但可以保证有映射关系
                        if ref_idx < len(pre_generated_citations):
                            # 从预生成的citations中获取retrieval_id（已经正确格式化）
                            retrieval_id = pre_generated_citations[ref_idx].get('retrieval_id')
                            if not retrieval_id:
                                # 如果没有retrieval_id，根据索引生成
                                if ref_idx + 1 < 10:
                                    retrieval_id = f'retrieval_{ref_idx+1:02d}'
                                else:
                                    retrieval_id = f'retrieval_{ref_idx+1}'
                            logger.debug(f"⚠️ 未找到明确映射，使用顺序映射: {ref_id} -> {retrieval_id}")
                        else:
                            logger.warning(f"⚠️ ref编号 {ref_id} 超出检索结果范围")
                            continue
                    
                    if retrieval_id in retrieval_to_citation:
                        citation = retrieval_to_citation[retrieval_id].copy()
                        citation['id'] = ref_idx + 1  # 重新编号为1, 2, 3...（用于最终显示）
                        citation['ref_id'] = ref_id  # 保存ref编号（ref01, ref02...）
                        citation['retrieval_id'] = retrieval_id  # 保存retrieval编号（retrieval_01, retrieval_02...）
                        used_citations.append(citation)
                        ref_to_retrieval[ref_id] = retrieval_id
                    else:
                        logger.warning(f"⚠️ ref编号 {ref_id} 对应的 retrieval_id {retrieval_id} 不存在")
                
                # 替换答案中的ref编号为连续的数字编号 [1], [2], [3]...
                final_answer_text = answer_text
                replacement_count = 0
                
                for ref_idx, ref_id in enumerate(ref_citations):
                    ref_num = ref_idx + 1
                    # 替换所有 [refXX] 为 [数字]（不区分大小写）
                    # 先处理带括号的格式: [ref01(retrieval_XX)] -> [1]（优先级更高，避免重复替换）
                    pattern_with_bracket = rf'\[{re.escape(ref_id)}\(retrieval_\d+\)\]'
                    matches_before = len(re.findall(pattern_with_bracket, final_answer_text, re.IGNORECASE))
                    final_answer_text = re.sub(pattern_with_bracket, f'[{ref_num}]', final_answer_text, flags=re.IGNORECASE)
                    matches_after = len(re.findall(pattern_with_bracket, final_answer_text, re.IGNORECASE))
                    if matches_before > 0:
                        replacement_count += matches_before
                        logger.debug(f"✅ 替换 {matches_before} 处 [{ref_id}(retrieval_XX)] -> [{ref_num}]")
                    
                    # 再处理不带括号的格式: [ref01] -> [1]
                    pattern_simple = rf'\[{re.escape(ref_id)}\]'
                    matches_before2 = len(re.findall(pattern_simple, final_answer_text, re.IGNORECASE))
                    final_answer_text = re.sub(pattern_simple, f'[{ref_num}]', final_answer_text, flags=re.IGNORECASE)
                    matches_after2 = len(re.findall(pattern_simple, final_answer_text, re.IGNORECASE))
                    if matches_before2 > 0:
                        replacement_count += matches_before2
                        logger.debug(f"✅ 替换 {matches_before2} 处 [{ref_id}] -> [{ref_num}]")
                
                logger.info(f"📝 答案文本替换完成，共替换 {replacement_count} 处")
                
                # 清理答案中的注释说明（如"注：[retrieval_01]与[retrieval_02]内容一致，首次引用标记为ref01。"）
                # 匹配各种可能的注释格式（更宽泛的匹配，确保能匹配所有变体）
                comment_patterns = [
                    r'注[：:].*?retrieval_\d+.*?内容一致.*?首次引用标记为ref\d+[。.]?\s*',  # 注：[retrieval_01]与[retrieval_02]内容一致，首次引用标记为ref01。
                    r'注[：:].*?retrieval_\d+.*?内容一致.*?[。.]?\s*',  # 注：[retrieval_01]与[retrieval_02]内容一致
                    r'\[retrieval_\d+\].*?内容一致.*?首次引用标记为ref\d+[。.]?\s*',  # [retrieval_01]与[retrieval_02]内容一致，首次引用标记为ref01。
                    r'注[：:].*?ref\d+.*?',  # 注：...ref01...（匹配任何包含ref编号的注释）
                ]
                
                cleaned_text = final_answer_text
                removed_comments = 0
                for pattern in comment_patterns:
                    matches = re.findall(pattern, cleaned_text, re.IGNORECASE | re.DOTALL)
                    if matches:
                        removed_comments += len(matches)
                        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE | re.DOTALL)
                        logger.debug(f"移除注释: {matches[0][:50]}...")
                
                # 清理多余的空行（连续两个或更多换行符替换为一个）
                cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
                # 清理行首行尾的空白
                cleaned_text = cleaned_text.strip()
                
                if removed_comments > 0:
                    logger.info(f"🧹 清理了 {removed_comments} 条注释说明")
                    final_answer_text = cleaned_text
                
                if final_answer_text != answer_text:
                    logger.info(f"✅ 替换成功：原始文本长度 {len(answer_text)}, 替换后长度 {len(final_answer_text)}")
                    # 显示替换前后的对比
                    import difflib
                    diff = list(difflib.unified_diff(
                        answer_text.splitlines(keepends=True),
                        final_answer_text.splitlines(keepends=True),
                        lineterm='',
                        n=0
                    ))
                    if diff:
                        logger.debug(f"替换差异预览: {''.join(diff[:10])}")
                else:
                    logger.warning(f"⚠️ 替换未生效，原始文本和替换后文本相同")
                    logger.debug(f"原始文本包含ref01: {'ref01' in answer_text}")
                    logger.debug(f"原始文本包含ref02: {'ref02' in answer_text}")
                
                # 检查是否有替换发生
                if final_answer_text != answer_text:
                    logger.info(f"✅ 成功替换了答案中的ref编号")
                    # 发送替换后的完整答案（用于替换流式输出的原始内容）
                    yield {
                        "type": "answer_chunk",
                        "content": final_answer_text,  # 发送完整的替换后答案
                        "is_final": True  # 标记这是最终版本，应该替换之前的内容
                    }
                else:
                    logger.warning(f"⚠️ 答案文本替换未生效，原始文本和替换后文本相同")
                
                logger.info(f"📚 最终使用的参考文献数量: {len(used_citations)}/{len(pre_generated_citations)}")
                logger.info(f"📚 ref到retrieval的映射关系: {ref_to_retrieval}")
                logger.info(f"📚 最终使用的参考文献ref编号: {[c.get('ref_id') for c in used_citations]}")
                logger.info(f"📚 最终使用的参考文献retrieval编号: {[c.get('retrieval_id') for c in used_citations]}")
                
                # 构造完整的answer_data（只包含实际使用的citations，使用连续的ID编号）
                answer_data = {
                    "answer": final_answer_text.strip(),  # 使用替换后的答案文本
                    "citations": used_citations  # 使用重新编号的citations（ID为1, 2, 3...，但保留ref_id和retrieval_id字段）
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
        """
        为引用生成创建来源内容字符串（使用retrieval_XX编号）
        
        检索结果编号：retrieval_01, retrieval_02, ..., retrieval_10, retrieval_11, ...（按实际数量）
        """
        sources_content = ""
        MAX_CONTENT_LENGTH = 800  # 每条检索结果最多800字
        
        for i in range(len(retrieval_results)):
            result = retrieval_results[i]
            # 根据实际数量决定编号格式：1-9用01-09，10以上用实际数字
            if i + 1 < 10:
                retrieval_id = f"retrieval_{i+1:02d}"  # retrieval_01, retrieval_02, ..., retrieval_09
            else:
                retrieval_id = f"retrieval_{i+1}"  # retrieval_10, retrieval_11, ...
            title = result.get("title", f"文档{i+1}")
            content = result.get("content", "")
            similarity = result.get("similarity", 0.0)
            
            # 限制内容长度，减少prompt tokens
            if len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "..."
            
            # 确保结果有正确的retrieval_id
            result["retrieval_id"] = retrieval_id
            
            # 确保有预览文本
            if "preview" not in result:
                result["preview"] = content[:30] + "..." if len(content) > 30 else content
            
            sources_content += f"[{retrieval_id}] 标题: {title}\n"
            sources_content += f"内容: {content}\n\n"  # 移除相似度，减少tokens
        
        logger.info(f"📝 准备答案生成内容: {len(sources_content)} 字符, {len(retrieval_results)} 条检索结果")
        return sources_content