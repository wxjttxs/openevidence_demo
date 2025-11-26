import json
import json5
import os
import time
import asyncio
import logging
from typing import Dict, Iterator, List, Optional, Generator
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from react_agent import MultiTurnReactAgent, TOOL_MAP, MAX_LLM_CALL_PER_RUN, today_date
from prompt import SYSTEM_PROMPT
from answer_system import AnswerJudgmentSystem
from department_classifier import classify_question_and_get_dataset_ids

# 配置日志
logger = logging.getLogger(__name__)

class StreamingReactAgent(MultiTurnReactAgent):
    """流式推理代理，支持实时输出思考过程和工具调用"""
    
    def __init__(self, llm=None, function_list=None, **kwargs):
        logger.debug(f"Initializing StreamingReactAgent with llm: {llm}, function_list: {function_list}")
        
        if llm is None:
            raise ValueError("llm parameter is required")
        
        self.llm_generate_cfg = llm["generate_cfg"]
        self.llm_model = llm["model"]
        self.llm_base_url = llm.get("base_url", "http://127.0.0.1:6001/v1")
        self.llm_api_key = llm.get("api_key", "EMPTY")
        
        # 不调用父类的__init__，因为我们只需要其中的部分功能
        self.function_list = function_list or []
        
        # 初始化答案判断系统
        self.answer_system = AnswerJudgmentSystem()
        
    def call_server(self, msgs, max_tries=3):
        """调用LLM服务器"""
        from openai import OpenAI, APIError, APIConnectionError, APITimeoutError
        import random

        client = OpenAI(
            api_key=self.llm_api_key,
            base_url=self.llm_base_url,
            timeout=600.0,
        )

        base_sleep_time = 1 
        
        for attempt in range(max_tries):
            try:
                logger.debug(f"--- Attempting to call the service, try {attempt + 1}/{max_tries} ---")
                chat_response = client.chat.completions.create(
                    model=self.llm_model,
                    messages=msgs,
                    stop=["\n<tool_response>", "<tool_response>"],
                    temperature=self.llm_generate_cfg.get('temperature', 0.6),
                    top_p=self.llm_generate_cfg.get('top_p', 0.95),
                    logprobs=True,
                    max_tokens=8000,
                    presence_penalty=self.llm_generate_cfg.get('presence_penalty', 1.1)
                )
                content = chat_response.choices[0].message.content
                if content and content.strip():
                    logger.debug("--- Service call successful, received a valid response ---")
                    return content.strip()
                else:
                    logger.debug(f"Warning: Attempt {attempt + 1} received an empty response.")

            except (APIError, APIConnectionError, APITimeoutError) as e:
                logger.debug(f"Error: Attempt {attempt + 1} failed with an API or network error: {e}")
            except Exception as e:
                logger.debug(f"Error: Attempt {attempt + 1} failed with an unexpected error: {e}")

            if attempt < max_tries - 1:
                sleep_time = base_sleep_time * (2 ** attempt) + random.uniform(0, 1)
                sleep_time = min(sleep_time, 30) 
                
                logger.debug(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            else:
                logger.debug("Error: All retry attempts have been exhausted. The call has failed.")
        
        return f"vllm server error!!!"
    
    def call_server_stream(self, msgs, max_tries=3, enable_thinking=True):
        """
        流式调用LLM服务器，支持阿里云模型的thinking模式
        
        Args:
            msgs: 消息列表
            max_tries: 最大重试次数
            enable_thinking: 是否启用思考模式（阿里云模型专用）
            
        Yields:
            dict: 包含 type 和 content 的字典
                - type: 'reasoning' (思考过程) 或 'content' (回答内容)
                - content: 文本内容
        """
        from openai import OpenAI, APIError, APIConnectionError, APITimeoutError
        import random

        client = OpenAI(
            api_key=self.llm_api_key,
            base_url=self.llm_base_url,
            timeout=600.0,
        )

        base_sleep_time = 1 
        
        for attempt in range(max_tries):
            try:
                logger.debug(f"--- Attempting to call the service (stream), try {attempt + 1}/{max_tries} ---")
                
                # 构建API调用参数
                api_params = {
                    "model": self.llm_model,
                    "messages": msgs,
                    "stop": ["\n<tool_response>", "<tool_response>"],
                    "temperature": self.llm_generate_cfg.get('temperature', 0.6),
                    "top_p": self.llm_generate_cfg.get('top_p', 0.95),
                    "max_tokens": 1000,
                    "presence_penalty": self.llm_generate_cfg.get('presence_penalty', 1.1),
                    "stream": True
                }
                
                # 如果启用思考模式，添加extra_body参数（阿里云模型专用）
                if enable_thinking and 'qwen' in self.llm_model.lower():
                    api_params["extra_body"] = {
                        "enable_thinking": True,
                        "thinking_budget": 1000  # 最大思考token数
                    }
                    logger.info(f"🧠 已启用思考模式 (thinking_budget=1000)")
                
                stream = client.chat.completions.create(**api_params)
                
                accumulated_reasoning = ""
                accumulated_content = ""
                has_reasoning = False
                has_content = False
                
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    
                    delta = chunk.choices[0].delta
                    
                    # 处理思考内容 (reasoning_content)
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                        has_reasoning = True
                        accumulated_reasoning += delta.reasoning_content
                        yield {
                            "type": "reasoning",
                            "content": delta.reasoning_content,
                            "accumulated": accumulated_reasoning
                        }
                    
                    # 处理回答内容 (content)
                    if hasattr(delta, "content") and delta.content:
                        has_content = True
                        accumulated_content += delta.content
                        yield {
                            "type": "content",
                            "content": delta.content,
                            "accumulated": accumulated_content
                        }
                
                if has_reasoning or has_content:
                    logger.info(f"✅ 流式调用成功 - 思考: {len(accumulated_reasoning)}字, 回答: {len(accumulated_content)}字")
                    return  # 成功完成
                else:
                    logger.debug(f"Warning: Attempt {attempt + 1} received an empty response.")

            except (APIError, APIConnectionError, APITimeoutError) as e:
                logger.debug(f"Error: Attempt {attempt + 1} failed with an API or network error: {e}")
            except Exception as e:
                logger.debug(f"Error: Attempt {attempt + 1} failed with an unexpected error: {e}")

            if attempt < max_tries - 1:
                sleep_time = base_sleep_time * (2 ** attempt) + random.uniform(0, 1)
                sleep_time = min(sleep_time, 30) 
                
                logger.debug(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            else:
                logger.debug("Error: All retry attempts have been exhausted. The call has failed.")
        
        yield {"type": "error", "content": "vllm server error!!!"}
        
    def count_tokens(self, messages, model="gpt-4o"):
        """计算token数量"""
        try: 
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(self.llm_model) 
        except Exception as e: 
            import tiktoken
            tokenizer = tiktoken.encoding_for_model(model)
        
        from qwen_agent.llm.schema import Message
        from qwen_agent.utils.utils import build_text_completion_prompt
        
        full_message = [Message(**x) for x in messages]
        full_prompt = build_text_completion_prompt(full_message, allow_special=True)
        
        return len(tokenizer.encode(full_prompt))
        
    def custom_call_tool(self, tool_name: str, tool_args: dict, **kwargs):
        """调用工具"""
        logger.debug(f"[DEBUG] custom_call_tool called with: tool_name={tool_name}, tool_args={tool_args}")
        
        if tool_name in TOOL_MAP:
            if "python" in tool_name.lower():
                result = TOOL_MAP['PythonInterpreter'].call(tool_args)
            elif tool_name == "parse_file":
                params = {"files": tool_args["files"]}
                
                raw_result = asyncio.run(TOOL_MAP[tool_name].call(params, file_root_path="./eval_data/file_corpus"))
                result = raw_result

                if not isinstance(raw_result, str):
                    result = str(raw_result)
            else:
                # 直接传递tool_args，不要添加额外的params包装
                raw_result = TOOL_MAP[tool_name].call(tool_args, **kwargs)
                result = raw_result
            return result

        else:
            return f"Error: Tool {tool_name} not found"
        
    def stream_run(self, question: str, cancelled: dict = None, history_messages: list = None) -> Generator[Dict, None, None]:
        """
        流式运行推理过程，实时输出各个阶段的信息
        
        Args:
            question: 用户问题
            cancelled: 取消标记字典 {"value": False}，当设置为 True 时中断处理
            history_messages: 历史消息列表 [{"role": "user/assistant", "content": "..."}]
            
        Yields:
            Dict: 包含当前阶段信息的字典
        """
        # 初始化 cancelled 标记
        if cancelled is None:
            cancelled = {"value": False}
        if history_messages is None:
            history_messages = []
        
        logger.info(f"=== StreamingReactAgent.stream_run START ===")
        logger.debug(f"Question: {question}")
        logger.debug(f"LLM Model: {self.llm_model}")
        logger.debug(f"History messages: {len(history_messages)} messages")
        
        start_time = time.time()
        self.user_prompt = question
        
        # 初始化消息列表（包含历史消息）
        system_prompt = SYSTEM_PROMPT + str(today_date())
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 添加历史消息（排除system消息）
        for msg in history_messages:
            if msg.get("role") != "system":
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # 添加当前用户问题
        messages.append({"role": "user", "content": question})
        
        init_event = {
            "type": "init",
            "content": f"开始处理问题...",
            "timestamp": datetime.now().isoformat()
        }
        logger.debug(f"Yielding init event: {init_event}")
        yield init_event
        
        # 限制检索循环最多3次
        MAX_RETRIEVAL_ROUNDS = 3
        num_llm_calls_available = MAX_LLM_CALL_PER_RUN
        round_num = 0
        retrieval_round_num = 0  # 检索轮次计数
        previous_search_keywords = []  # 记录之前使用的检索关键词
        
        logger.debug(f"Starting main loop, max retrieval rounds: {MAX_RETRIEVAL_ROUNDS}")
        
        while num_llm_calls_available > 0:
            # 检查客户端是否断开
            if cancelled["value"]:
                cancelled_event = {
                    "type": "cancelled",
                    "content": "检测到客户端断开，停止处理",
                    "timestamp": datetime.now().isoformat()
                }
                logger.warning(f"⚠️ 客户端断开，停止推理循环")
                yield cancelled_event
                
                completed_event = {
                    "type": "completed",
                    "content": "客户端断开，流程结束",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding completed event (cancelled): {completed_event}")
                yield completed_event
                return
            
            # 检查超时
            if time.time() - start_time > 150 * 60:  # 150分钟
                timeout_event = {
                    "type": "timeout",
                    "content": "推理超时（150分钟）",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding timeout event: {timeout_event}")
                yield timeout_event
                
                completed_event = {
                    "type": "completed",
                    "content": "推理超时，流程结束",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding completed event (timeout): {completed_event}")
                yield completed_event
                return
                
            round_num += 1
            num_llm_calls_available -= 1
            
            round_start_event = {
                "type": "round_start",
                "content": f"第 {round_num} 轮推理开始",
                "round": round_num,
                "timestamp": datetime.now().isoformat()
            }
            logger.debug(f"Yielding round_start event: {round_start_event}")
            yield round_start_event
            
            # 检查检索轮次限制（在调用检索工具前检查）
            if retrieval_round_num >= MAX_RETRIEVAL_ROUNDS:
                # 已达到最大检索轮次，返回抱歉消息
                logger.warning(f"⚠️ 已达到最大检索轮次 {MAX_RETRIEVAL_ROUNDS}，无法找到答案")
                
                no_answer_event = {
                    "type": "final_answer",
                    "content": "抱歉，经过多轮检索后，我无法基于现有知识库找到足够的信息来回答您的问题。建议您：\n\n1. 尝试使用更具体或不同的关键词重新提问\n2. 将问题拆分为更小的子问题\n3. 如果可能，提供更多相关的背景信息",
                    "timestamp": datetime.now().isoformat(),
                    "is_streaming": False
                }
                logger.debug(f"Yielding no_answer event: {no_answer_event}")
                yield no_answer_event
                
                completed_event = {
                    "type": "completed",
                    "content": f"已达到最大检索轮次（{MAX_RETRIEVAL_ROUNDS}次），未能找到答案",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding completed event (max rounds): {completed_event}")
                yield completed_event
                logger.info(f"=== StreamingReactAgent.stream_run MAX_ROUNDS_REACHED ===")
                return
            
            # 调用LLM
            thinking_start_time = time.time()
            
            # 构建思考提示，强调使用不同的检索关键词
            thinking_hint = ""
            if previous_search_keywords:
                keywords_list = "、".join([f'"{kw}"' for kw in previous_search_keywords])
                thinking_hint = f"\n\n【重要提示】这是第 {retrieval_round_num + 1} 轮检索。之前已使用过以下检索关键词：{keywords_list}。\n请务必使用**不同的检索关键词**或**不同的检索角度**，确保本次检索能获得不同的结果。避免重复使用相同的关键词。"
            
            thinking_content = "正在思考..." + thinking_hint
            thinking_start_event = {
                "type": "thinking_start",
                "content": thinking_content,
                "timestamp": datetime.now().isoformat()
            }
            logger.debug(f"Yielding thinking_start event (round {retrieval_round_num + 1}/{MAX_RETRIEVAL_ROUNDS}): {thinking_start_event}")
            yield thinking_start_event
            
            try:
                logger.debug(f"Calling LLM server (stream) - Model: {self.llm_model}, Retrieval Round: {retrieval_round_num + 1}/{MAX_RETRIEVAL_ROUNDS}")
                
                # 如果之前有检索失败，在system message中添加提示
                current_messages = messages.copy()
                if previous_search_keywords and retrieval_round_num > 0:
                    # 添加提示消息，强调使用不同的关键词
                    keyword_hint = f"注意：这是第 {retrieval_round_num + 1} 轮检索。之前的检索未能找到足够的信息。已使用过的检索关键词包括：{', '.join(previous_search_keywords)}。请务必使用**完全不同的检索关键词**或**不同的检索角度**，确保本次检索能获得不同的结果。"
                    # 将提示插入到user消息中
                    if len(current_messages) > 0:
                        # 在最后一条user消息后添加提示
                        last_user_idx = -1
                        for i in range(len(current_messages) - 1, -1, -1):
                            if current_messages[i]["role"] == "user":
                                last_user_idx = i
                                break
                        if last_user_idx >= 0:
                            current_messages[last_user_idx]["content"] += "\n\n" + keyword_hint
                        else:
                            # 如果没有user消息，添加一条
                            current_messages.append({"role": "user", "content": keyword_hint})
                
                # 使用新的流式API，支持阿里云thinking模式
                reasoning_content = ""  # 完整思考过程
                answer_content = ""  # 完整回答内容
                is_answering = False  # 是否进入回答阶段
                
                for chunk_data in self.call_server_stream(current_messages, enable_thinking=True):
                    # 在流式接收过程中检查客户端是否断开
                    if cancelled["value"]:
                        logger.warning(f"⚠️ 客户端断开，停止LLM流式接收")
                        return
                    
                    chunk_type = chunk_data.get("type")
                    chunk_content = chunk_data.get("content", "")
                    
                    # 处理思考内容（reasoning）
                    if chunk_type == "reasoning":
                        reasoning_content = chunk_data.get("accumulated", reasoning_content)
                        # 实时发送思考片段
                        if chunk_content.strip():
                            thinking_chunk_event = {
                                "type": "thinking_chunk",
                                "content": chunk_content,
                                "accumulated": reasoning_content,
                                "is_streaming": True,
                                "is_complete": False,
                                "timestamp": datetime.now().isoformat()
                            }
                            yield thinking_chunk_event
                    
                    # 处理回答内容（content）
                    elif chunk_type == "content":
                        if not is_answering:
                            # 第一次收到content，说明思考阶段结束
                            is_answering = True
                            
                            # 如果有思考内容，发送思考完成事件
                            if reasoning_content.strip():
                                thinking_elapsed = time.time() - thinking_start_time
                                logger.info(f"⏱️  【时间统计】思考过程完成，耗时: {thinking_elapsed:.2f} 秒")
                                
                                thinking_complete_event = {
                                    "type": "thinking",
                                    "content": reasoning_content.strip(),
                                    "is_streaming": False,
                                    "timestamp": datetime.now().isoformat(),
                                    "elapsed_time": f"{thinking_elapsed:.2f}秒"
                                }
                                # logger.info(f"💭 思考内容长度: {len(reasoning_content)} 字")
                                yield thinking_complete_event
                            else:
                                logger.info(f"⚠️ 模型未输出思考内容（可能是非thinking模型）")
                        
                        # 累积回答内容
                        answer_content += chunk_content
                    
                    # 处理错误
                    elif chunk_type == "error":
                        raise Exception(chunk_content)
                
                # 使用answer_content作为最终content
                content = answer_content if answer_content else reasoning_content
                # logger.info(f"✅ LLM响应完成 - 思考: {len(reasoning_content)}字, 回答: {len(answer_content)}字")
                
                # 清理tool_response标记
                if '<tool_response>' in content:
                    pos = content.find('<tool_response>')
                    content = content[:pos]
                    
                messages.append({"role": "assistant", "content": content.strip()})
                logger.debug(f"Added assistant message to conversation")
                
                # 检查工具调用（支持多个连续的tool_call）
                if '<tool_call>' in content and '</tool_call>' in content:
                    # 在执行工具调用前检查客户端是否断开
                    if cancelled["value"]:
                        cancelled_event = {
                            "type": "cancelled",
                            "content": "检测到客户端断开，停止处理",
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.warning(f"⚠️ 客户端断开，跳过工具调用")
                        yield cancelled_event
                        
                        completed_event = {
                            "type": "completed",
                            "content": "客户端断开，流程结束",
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.debug(f"Yielding completed event (cancelled before tool): {completed_event}")
                        yield completed_event
                        return
                    
                    # 提取所有tool_call（支持多个连续的tool_call）
                    import re
                    tool_call_pattern = r'<tool_call>(.*?)</tool_call>'
                    tool_calls_raw = re.findall(tool_call_pattern, content, re.DOTALL)
                    
                    logger.debug(f"Found {len(tool_calls_raw)} tool call(s) in response")
                    
                    # 如果只有一个tool_call，串行处理（保持原有逻辑）
                    if len(tool_calls_raw) == 1:
                        tool_call_raw = tool_calls_raw[0].strip()
                        
                        tool_call_start_event = {
                            "type": "tool_call_start",
                            "content": f"准备调用工具: {tool_call_raw[:100]}...",
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.debug(f"Yielding tool_call_start event: {tool_call_start_event}")
                        yield tool_call_start_event
                        
                        try:
                            if "python" in tool_call_raw.lower():
                                # Python代码执行
                                try:
                                    code_raw = content.split('<tool_call>')[1].split('</tool_call>')[0].split('<code>')[1].split('</code>')[0].strip()
                                    python_exec_event = {
                                        "type": "python_execution",
                                        "content": f"执行Python代码:\n```python\n{code_raw}\n```",
                                        "code": code_raw,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    logger.debug(f"Yielding python_execution event: {python_exec_event}")
                                    yield python_exec_event
                                    
                                    result = TOOL_MAP['PythonInterpreter'].call(code_raw)
                                    logger.debug(f"Python execution result: {result[:200]}...")
                                except Exception as e:
                                    result = f"[Python Interpreter Error]: {str(e)}"
                                    logger.debug(f"Python execution error: {result}")
                            else:
                                # 其他工具调用
                                tool_call = json5.loads(tool_call_raw)
                                tool_name = tool_call.get('name', '')
                                tool_args = tool_call.get('arguments', {})
                                
                                tool_exec_event = {
                                    "type": "tool_execution",
                                    "content": f"调用工具 {tool_name}，参数: {json.dumps(tool_args, indent=2, ensure_ascii=False)}",
                                    "tool_name": tool_name,
                                    "tool_args": tool_args,
                                    "timestamp": datetime.now().isoformat()
                                }
                                logger.debug(f"Yielding tool_execution event: {tool_exec_event}")
                                yield tool_exec_event
                                
                                retrieval_start_time = time.time()
                                logger.debug(f"Calling tool {tool_name} with args {tool_args}")
                                
                                # 如果是检索工具，记录检索关键词并自动补充dataset_ids
                                if tool_name == "retrieval":
                                    retrieval_round_num += 1
                                    search_keyword = tool_args.get("question", "")
                                    if search_keyword:
                                        previous_search_keywords.append(search_keyword)
                                        logger.info(f"🔍 第 {retrieval_round_num} 轮检索，关键词: {search_keyword}")
                                    
                                    # 自动根据问题判断科室并补充dataset_ids
                                    provided_dataset_ids = tool_args.get("dataset_ids", [])
                                    if not provided_dataset_ids or len(provided_dataset_ids) == 0:
                                        classification_result = classify_question_and_get_dataset_ids(self.user_prompt)
                                        auto_dataset_ids = classification_result["dataset_ids"]
                                        tool_args["dataset_ids"] = auto_dataset_ids
                                        logger.info(f"📋 LLM未提供dataset_ids，自动根据问题判断科室: {classification_result['departments']}, 使用dataset_ids: {auto_dataset_ids}")
                                    else:
                                        logger.info(f"📋 LLM已提供dataset_ids: {provided_dataset_ids}")
                                
                                result = self.custom_call_tool(tool_name, tool_args)
                                retrieval_elapsed = time.time() - retrieval_start_time
                                logger.info(f"⏱️  【时间统计】工具 {tool_name} 执行完成，耗时: {retrieval_elapsed:.2f} 秒")
                                logger.debug(f"Tool result: {result[:200]}...")
                                
                                # 工具调用完成后检查客户端是否断开
                                if cancelled["value"]:
                                    logger.warning(f"⚠️ 客户端断开，停止工具结果处理")
                                    return
                                
                        except Exception as e:
                            result = f'工具调用错误: {str(e)}'
                            tool_error_event = {
                                "type": "tool_error",
                                "content": result,
                                "timestamp": datetime.now().isoformat()
                            }
                            logger.debug(f"Yielding tool_error event: {tool_error_event}")
                            yield tool_error_event
                        
                        # 输出工具结果
                        tool_result_event = {
                            "type": "tool_result",
                            "content": f"工具调用完成" + (f"，检索到 {len(result.split('---')) if '---' in result else 1} 条相关文献" if tool_name == "retrieval" else ""),
                            "result": result,
                            "timestamp": datetime.now().isoformat(),
                            "elapsed_time": f"{retrieval_elapsed:.2f}秒" if 'retrieval_elapsed' in locals() else None
                        }
                        logger.debug(f"Yielding tool_result event: {tool_result_event}")
                        yield tool_result_event
                        
                        # 设置has_retrieval_tool和result变量
                        has_retrieval_tool = (tool_name == "retrieval")
                        if has_retrieval_tool:
                            all_retrieval_results = [result]
                        else:
                            all_retrieval_results = []
                    
                    else:
                        # 多个tool_call：并发处理
                        logger.info(f"🚀 检测到 {len(tool_calls_raw)} 个工具调用，开始并发执行")
                        
                        # 发送并发开始事件
                        concurrent_start_event = {
                            "type": "concurrent_tool_calls_start",
                            "content": f"开始并发执行 {len(tool_calls_raw)} 个工具调用",
                            "timestamp": datetime.now().isoformat()
                        }
                        yield concurrent_start_event
                        
                        # 定义单个工具调用的执行函数
                        def execute_single_tool(tool_call_idx, tool_call_raw, content_ref):
                            """执行单个工具调用"""
                            tool_call_raw = tool_call_raw.strip()
                            tool_result = {
                                "index": tool_call_idx,
                                "success": False,
                                "result": None,
                                "tool_name": None,
                                "error": None,
                                "elapsed_time": 0
                            }
                            
                            try:
                                start_time = time.time()
                                
                                if "python" in tool_call_raw.lower():
                                    # Python代码执行
                                    try:
                                        code_raw = content_ref.split('<tool_call>')[tool_call_idx + 1].split('</tool_call>')[0].split('<code>')[1].split('</code>')[0].strip()
                                        result = TOOL_MAP['PythonInterpreter'].call(code_raw)
                                        tool_result["success"] = True
                                        tool_result["result"] = result
                                        tool_result["tool_name"] = "PythonInterpreter"
                                    except Exception as e:
                                        tool_result["error"] = f"[Python Interpreter Error]: {str(e)}"
                                        tool_result["result"] = tool_result["error"]
                                else:
                                    # 其他工具调用
                                    tool_call = json5.loads(tool_call_raw)
                                    tool_name = tool_call.get('name', '')
                                    tool_args = tool_call.get('arguments', {})
                                    tool_result["tool_name"] = tool_name
                                    tool_result["tool_args"] = tool_args  # 保存tool_args以便后续使用
                                    
                                    # 如果是检索工具，自动补充dataset_ids
                                    if tool_name == "retrieval":
                                        provided_dataset_ids = tool_args.get("dataset_ids", [])
                                        if not provided_dataset_ids or len(provided_dataset_ids) == 0:
                                            classification_result = classify_question_and_get_dataset_ids(self.user_prompt)
                                            auto_dataset_ids = classification_result["dataset_ids"]
                                            tool_args["dataset_ids"] = auto_dataset_ids
                                            logger.debug(f"📋 工具 {tool_call_idx + 1}: LLM未提供dataset_ids，自动判断科室: {classification_result['departments']}")
                                    
                                    result = self.custom_call_tool(tool_name, tool_args)
                                    tool_result["success"] = True
                                    tool_result["result"] = result
                                
                                tool_result["elapsed_time"] = time.time() - start_time
                                
                            except Exception as e:
                                tool_result["error"] = str(e)
                                tool_result["result"] = f'工具调用错误 ({tool_call_idx + 1}/{len(tool_calls_raw)}): {str(e)}'
                            
                            return tool_result
                        
                        # 使用ThreadPoolExecutor并发执行所有工具调用
                        all_retrieval_results = []
                        has_retrieval_tool = False
                        tool_results = {}  # 存储所有工具调用结果，按索引排序
                        
                        with ThreadPoolExecutor(max_workers=min(len(tool_calls_raw), 5)) as executor:
                            # 提交所有任务
                            future_to_index = {
                                executor.submit(execute_single_tool, idx, tool_call_raw, content): idx
                                for idx, tool_call_raw in enumerate(tool_calls_raw)
                            }
                            
                            # 按完成顺序处理结果（不等待所有完成）
                            for future in as_completed(future_to_index):
                                tool_call_idx = future_to_index[future]
                                
                                # 检查客户端是否断开
                                if cancelled["value"]:
                                    logger.warning(f"⚠️ 客户端断开，停止并发工具调用")
                                    break
                                
                                try:
                                    tool_result = future.result()
                                    tool_results[tool_call_idx] = tool_result
                                    
                                    tool_name = tool_result["tool_name"]
                                    result = tool_result["result"]
                                    elapsed_time = tool_result["elapsed_time"]
                                    
                                    # 发送工具执行事件
                                    tool_exec_event = {
                                        "type": "tool_execution",
                                        "content": f"并发调用工具 {tool_name} ({tool_call_idx + 1}/{len(tool_calls_raw)}) 完成，耗时: {elapsed_time:.2f}秒",
                                        "tool_name": tool_name,
                                        "tool_args": tool_result.get("tool_args", {}),
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    yield tool_exec_event
                                    
                                    # 如果是检索工具，记录并累积结果
                                    if tool_name == "retrieval":
                                        has_retrieval_tool = True
                                        # 第一轮多组检索时，只在第一个检索调用时增加检索轮次计数
                                        if tool_call_idx == 0:
                                            retrieval_round_num += 1
                                        
                                        search_keyword = tool_result.get("tool_args", {}).get("question", "")
                                        if search_keyword:
                                            previous_search_keywords.append(search_keyword)
                                            logger.info(f"🔍 并发检索调用 {tool_call_idx + 1}/{len(tool_calls_raw)} 完成，关键词: {search_keyword}")
                                        
                                        all_retrieval_results.append((tool_call_idx, result))
                                    
                                    # 发送工具结果事件
                                    tool_result_event = {
                                        "type": "tool_result",
                                        "content": f"工具调用 {tool_call_idx + 1}/{len(tool_calls_raw)} 完成" + (f"，检索到 {len(result.split('---')) if '---' in result else 1} 条相关文献" if tool_name == "retrieval" else ""),
                                        "result": result,
                                        "timestamp": datetime.now().isoformat(),
                                        "elapsed_time": f"{elapsed_time:.2f}秒"
                                    }
                                    yield tool_result_event
                                    
                                except Exception as e:
                                    logger.error(f"❌ 工具调用 {tool_call_idx + 1} 执行出错: {str(e)}")
                                    error_event = {
                                        "type": "tool_error",
                                        "content": f"工具调用 {tool_call_idx + 1} 出错: {str(e)}",
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    yield error_event
                        
                        # 按索引顺序排序检索结果
                        if has_retrieval_tool:
                            all_retrieval_results.sort(key=lambda x: x[0])
                            all_retrieval_results = [result for _, result in all_retrieval_results]
                        
                        # 发送并发完成事件
                        concurrent_complete_event = {
                            "type": "concurrent_tool_calls_complete",
                            "content": f"并发执行完成，共 {len(tool_calls_raw)} 个工具调用",
                            "timestamp": datetime.now().isoformat()
                        }
                        yield concurrent_complete_event
                    
                    # 处理检索工具的结果合并（如果有多个检索调用）
                    if has_retrieval_tool:
                        if len(all_retrieval_results) > 1:
                            # 合并所有检索结果
                            combined_result = "\n\n--- 检索结果分割线 ---\n\n".join(all_retrieval_results)
                            result = combined_result
                            logger.info(f"✅ 合并了 {len(all_retrieval_results)} 组检索结果")
                            
                            # 发送合并结果事件
                            combined_result_event = {
                                "type": "retrieval_combined",
                                "content": f"已合并 {len(all_retrieval_results)} 组检索结果",
                                "result": result,
                                "timestamp": datetime.now().isoformat()
                            }
                            yield combined_result_event
                        elif len(all_retrieval_results) == 1:
                            result = all_retrieval_results[0]
                        else:
                            # 没有检索结果，使用默认错误消息
                            result = "[Retrieval] Error: No retrieval results"
                    
                    # 如果是检索工具，流式判断结果是否足够回答问题（只在所有检索完成后判断一次）
                    if has_retrieval_tool and result and not result.startswith("[Retrieval] Error"):
                        judgment_start_time = time.time()
                        judgment_start_event = {
                            "type": "retrieval_judgment",
                            "content": "正在评估检索内容是否足够回答问题...",
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.debug(f"Yielding retrieval_judgment event: {judgment_start_event}")
                        yield judgment_start_event
                        
                        try:
                            # 使用流式判断方法，实时发送判断文本
                            judgment = None
                            accumulated_judgment_text = ""
                            
                            for judgment_event in self.answer_system.judge_retrieval_sufficiency_stream(self.user_prompt, result):
                                event_type = judgment_event.get("type")
                                
                                if event_type == "judgment_chunk":
                                    # 流式发送判断文本片段（增量chunk）
                                    chunk_text = judgment_event.get("content", "")  # 增量chunk内容
                                    accumulated_judgment_text = judgment_event.get("accumulated", "")
                                    chunk_event = {
                                        "type": "judgment_streaming",
                                        "content": chunk_text,  # 发送增量chunk，而不是累积内容
                                        "accumulated": accumulated_judgment_text,  # 可选：也提供累积内容给前端
                                        "is_streaming": True,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    yield chunk_event
                                    
                                elif event_type == "judgment_complete":
                                    # 判断完成，获取最终结果
                                    judgment = judgment_event.get("judgment", {})
                                    judgment_elapsed = time.time() - judgment_start_time
                                    logger.info(f"⏱️  【时间统计】检索结果评估完成，耗时: {judgment_elapsed:.2f} 秒")
                                    logger.debug(f"Judgment complete: {judgment}")
                                    
                                    # 发送流式完成事件（停止光标闪烁）
                                    if accumulated_judgment_text:
                                        judgment_final_event = {
                                            "type": "judgment_streaming",
                                            "content": accumulated_judgment_text,
                                            "is_streaming": False,  # 标记流式结束
                                            "timestamp": datetime.now().isoformat(),
                                            "elapsed_time": f"{judgment_elapsed:.2f}秒"
                                        }
                                        yield judgment_final_event
                                    
                                elif event_type == "judgment_error":
                                    # 判断出错，记录但继续
                                    logger.debug(f"Judgment error: {judgment_event.get('content')}")
                                    judgment = {"can_answer": True, "confidence": 0.5}  # 默认假设可以回答
                            
                            # 如果判断结果为空（出错），使用默认值
                            if judgment is None:
                                judgment = {"can_answer": True, "confidence": 0.5}
                            
                            # 如果检索内容足够，直接生成答案，不继续推理
                            if judgment.get('can_answer', False):
                                answer_start_time = time.time()
                                answer_generation_event = {
                                    "type": "answer_generation", 
                                    "content": f"检索内容可以回答问题（置信度: {judgment.get('confidence', 0):.2f}），正在生成最终答案...",
                                    "timestamp": datetime.now().isoformat()
                                }
                                logger.debug(f"Yielding answer_generation event: {answer_generation_event}")
                                yield answer_generation_event
                                
                                try:
                                    # 解析检索结果
                                    retrieval_results = self.answer_system.parse_retrieval_results(result)
                                    
                                    # 使用流式生成答案
                                    logger.debug(f"[DEBUG] Starting streaming answer generation...")
                                    
                                    accumulated_answer = ""
                                    answer_data = None
                                    first_chunk = True
                                    
                                    for stream_event in self.answer_system.generate_answer_with_citations_stream(self.user_prompt, retrieval_results):
                                        event_type = stream_event.get("type")
                                        
                                        if event_type == "answer_chunk":
                                            # 逐块发送增量chunk（仅答案主体，不含参考文献）
                                            chunk_content = stream_event.get("content", "")  # 增量chunk内容
                                            accumulated_answer += chunk_content
                                            
                                            # 使用final_answer_chunk类型，前端会用最终答案样式渲染
                                            chunk_event = {
                                                "type": "final_answer_chunk",
                                                "content": chunk_content,  # 发送增量chunk，而不是累积内容
                                                "accumulated": accumulated_answer,  # 可选：也提供累积内容给前端
                                                "is_streaming": True,  # 标记为流式中
                                                "timestamp": datetime.now().isoformat()
                                            }
                                            yield chunk_event
                                            
                                        elif event_type == "answer_complete":
                                            # 答案生成完成，获取完整的 answer_data（包含 citations）
                                            answer_data = stream_event.get("answer_data", {})
                                            logger.debug(f"[DEBUG] Answer streaming completed, citations count: {len(answer_data.get('citations', []))}")
                                            
                                            # 直接使用 answer 字段内容，不进行格式化
                                            # accumulated_answer 已包含流式传输的答案主体
                                            final_answer_content = accumulated_answer.strip() if accumulated_answer else answer_data.get("answer", "")
                                            
                                            answer_elapsed = time.time() - answer_start_time
                                            logger.info(f"⏱️  【时间统计】最终答案生成完成，耗时: {answer_elapsed:.2f} 秒")
                                            
                                            # 直接传递 answer_complete 事件，让前端立即显示参考文献
                                            answer_complete_event = {
                                                "type": "answer_complete",
                                                "content": final_answer_content,  # 只发送答案主体，不含 "参考文献:" 格式化
                                                "answer_data": answer_data,  # 前端从这里提取 citations
                                                "is_streaming": False,  # 标记流式结束
                                                "timestamp": datetime.now().isoformat(),
                                                "elapsed_time": f"{answer_elapsed:.2f}秒"
                                            }
                                            logger.debug(f"Yielding answer_complete event with citations (from retrieval stream)")
                                            yield answer_complete_event
                                            
                                        elif event_type == "answer_error":
                                            # 答案生成出错 - 立即返回，不再发送completed事件
                                            error_content = stream_event.get("content", "生成答案时出错")
                                            error_event = {
                                                "type": "error",
                                                "content": error_content,
                                                "timestamp": datetime.now().isoformat()
                                            }
                                            logger.debug(f"Answer generation error: {error_content}")
                                            yield error_event
                                            
                                            # 发送completed事件后立即返回
                                            completed_event = {
                                                "type": "completed",
                                                "content": "答案生成失败，流程结束",
                                    "timestamp": datetime.now().isoformat()
                                }
                                            logger.debug(f"Yielding completed event (after error): {completed_event}")
                                            yield completed_event
                                            return  # 立即返回，避免后续处理
                                    
                                    # 发送完成事件（正常流程）
                                    total_elapsed = time.time() - start_time
                                    logger.info(f"⏱️  【时间统计】整个流程完成，总耗时: {total_elapsed:.2f} 秒")
                                    
                                    completed_event = {
                                        "type": "completed",
                                        "content": "基于检索内容生成答案完成",
                                        "timestamp": datetime.now().isoformat(),
                                        "total_elapsed_time": f"{total_elapsed:.2f}秒"
                                    }
                                    logger.debug(f"Yielding completed event (from retrieval): {completed_event}")
                                    yield completed_event
                                    logger.info(f"=== StreamingReactAgent.stream_run COMPLETED (FROM RETRIEVAL) ===")
                                    return
                                    
                                except Exception as e:
                                    error_event = {
                                        "type": "error",
                                        "content": f"生成最终答案时出错: {str(e)}",
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    logger.debug(f"Error generating final answer from retrieval: {str(e)}")
                                    import traceback
                                    traceback.print_exc()
                                    logger.debug(f"Yielding error event: {error_event}")
                                    yield error_event
                                    
                                    completed_event = {
                                        "type": "completed",
                                        "content": "生成答案失败，流程结束",
                                    "timestamp": datetime.now().isoformat()
                                }
                                    logger.debug(f"Yielding completed event (error): {completed_event}")
                                yield completed_event
                                return
                            else:
                                # 检索内容不足，进入下一轮循环（思考→检索→判断）
                                # 检查是否已达到最大检索轮次
                                if retrieval_round_num >= MAX_RETRIEVAL_ROUNDS:
                                    # 已达到最大检索轮次，返回抱歉消息
                                    logger.warning(f"⚠️ 第 {retrieval_round_num} 轮检索后仍无法回答问题，已达到最大检索轮次 {MAX_RETRIEVAL_ROUNDS}")
                                    
                                    no_answer_event = {
                                        "type": "final_answer",
                                        "content": "抱歉，经过多轮检索后，我无法基于现有知识库找到足够的信息来回答您的问题。建议您：\n\n1. 尝试使用更具体或不同的关键词重新提问\n2. 将问题拆分为更小的子问题\n3. 如果可能，提供更多相关的背景信息",
                                        "timestamp": datetime.now().isoformat(),
                                        "is_streaming": False
                                    }
                                    logger.debug(f"Yielding no_answer event: {no_answer_event}")
                                    yield no_answer_event
                                    
                                    completed_event = {
                                        "type": "completed",
                                        "content": f"已达到最大检索轮次（{MAX_RETRIEVAL_ROUNDS}次），未能找到答案",
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    logger.debug(f"Yielding completed event (max rounds): {completed_event}")
                                    yield completed_event
                                    logger.info(f"=== StreamingReactAgent.stream_run MAX_ROUNDS_REACHED ===")
                                    return
                                
                                continue_reasoning_event = {
                                    "type": "continue_reasoning",
                                    "content": f"检索内容不足以回答问题（置信度: {judgment.get('confidence', 0):.2f}），继续下一轮检索（第 {retrieval_round_num + 1}/{MAX_RETRIEVAL_ROUNDS} 轮）...",
                                    "timestamp": datetime.now().isoformat()
                                }
                                logger.debug(f"Yielding continue_reasoning event: {continue_reasoning_event}")
                                yield continue_reasoning_event
                                
                                # 判断为不能回答时，不添加工具结果到消息，直接进入下一轮循环
                                # 这样下一轮会重新思考检索策略，使用不同的关键词
                                logger.info(f"🔄 检索结果不足以回答问题（置信度: {judgment.get('confidence', 0):.2f}），跳过添加工具结果，进入下一轮循环（思考→检索→判断）")
                                logger.info(f"📝 已使用过的检索关键词: {previous_search_keywords}")
                                continue  # 直接跳到下一轮循环
                                
                        except Exception as e:
                            judgment_error_event = {
                                "type": "judgment_error",
                                "content": f"检索内容评估出错: {str(e)}",
                                "timestamp": datetime.now().isoformat()
                            }
                            logger.debug(f"Yielding judgment_error event: {judgment_error_event}")
                            yield judgment_error_event
                            # 评估出错时，也跳过添加工具结果，进入下一轮
                            logger.info(f"🔄 检索结果评估出错，跳过添加工具结果，进入下一轮循环")
                            continue  # 直接跳到下一轮循环
                    
                    # 只有在非检索工具，或者检索工具但判断结果未明确为"不能回答"时，才添加工具结果到消息
                    # 对于检索工具且已判断为"不能回答"的情况，已经在上面continue了
                    result = "<tool_response>\n" + result + "\n</tool_response>"
                    messages.append({"role": "user", "content": result})
                    logger.debug(f"Added tool result to conversation")
                
                # 检查是否有最终答案
                if '<answer>' in content and '</answer>' in content:
                    answer = content.split('<answer>')[1].split('</answer>')[0]
                    final_answer_event = {
                        "type": "final_answer",
                        "content": answer.strip(),
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.debug(f"Yielding final_answer event: {final_answer_event}")
                    yield final_answer_event
                    
                    completed_event = {
                        "type": "completed",
                        "content": "推理完成",
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.debug(f"Yielding completed event: {completed_event}")
                    yield completed_event
                    logger.info(f"=== StreamingReactAgent.stream_run COMPLETED ===")
                    return
                    
            except Exception as e:
                error_event = {
                    "type": "error",
                    "content": f"推理过程出错: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Exception in stream_run: {str(e)}")
                logger.debug(f"Yielding error event: {error_event}")
                yield error_event
                
                completed_event = {
                    "type": "completed",
                    "content": "推理错误，流程结束",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding completed event (error): {completed_event}")
                yield completed_event
                logger.info(f"=== StreamingReactAgent.stream_run ERROR ===")
                return
            
            # 检查token限制
            max_tokens = 108 * 1024
            token_count = self.count_tokens(messages)
            logger.debug(f"Current token count: {token_count}/{max_tokens}")
            
            if token_count > max_tokens:
                token_limit_event = {
                    "type": "token_limit",
                    "content": f"达到token限制 ({token_count} > {max_tokens})，尝试生成最终答案",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding token_limit event: {token_limit_event}")
                yield token_limit_event
                
                messages[-1]['content'] = "You have now reached the maximum context length you can handle. You should stop making tool calls and, based on all the information above, think again and provide what you consider the most likely answer in the following format:<think>your final thinking</think>\n<answer>your answer</answer>"
                
                try:
                    content = self.call_server(messages, planning_port)
                    messages.append({"role": "assistant", "content": content.strip()})
                    
                    if '<answer>' in content and '</answer>' in content:
                        answer = content.split('<answer>')[1].split('</answer>')[0]
                        final_answer_event = {
                            "type": "final_answer",
                            "content": answer.strip(),
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.debug(f"Yielding final_answer event (token limit): {final_answer_event}")
                        yield final_answer_event
                    else:
                        final_answer_event = {
                            "type": "final_answer",
                            "content": content.strip(),
                            "timestamp": datetime.now().isoformat()
                        }
                        logger.debug(f"Yielding final_answer event (token limit, no format): {final_answer_event}")
                        yield final_answer_event
                except Exception as e:
                    error_event = {
                        "type": "error",
                        "content": f"生成最终答案时出错: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.debug(f"Error generating final answer: {str(e)}")
                    logger.debug(f"Yielding error event: {error_event}")
                    yield error_event
                
                # 发送 completed 事件（无论成功与否）
                completed_event = {
                    "type": "completed",
                    "content": "Token限制，流程结束",
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"Yielding completed event (token limit): {completed_event}")
                yield completed_event
                logger.info(f"=== StreamingReactAgent.stream_run TOKEN_LIMIT_END ===")
                return
                
            round_end_event = {
                "type": "round_end",
                "content": f"第 {round_num} 轮推理结束",
                "round": round_num,
                "timestamp": datetime.now().isoformat()
            }
            logger.debug(f"Yielding round_end event: {round_end_event}")
            yield round_end_event
        
        # 如果循环结束仍未找到答案
        no_answer_event = {
            "type": "no_answer",
            "content": "未找到明确答案，可能需要更多推理轮次",
            "timestamp": datetime.now().isoformat()
        }
        logger.debug(f"Yielding no_answer event: {no_answer_event}")
        yield no_answer_event
        
        # 发送 completed 事件
        completed_event = {
            "type": "completed",
            "content": "推理完成（未找到答案）",
            "timestamp": datetime.now().isoformat()
        }
        logger.debug(f"Yielding completed event (no answer): {completed_event}")
        yield completed_event
        logger.info(f"=== StreamingReactAgent.stream_run NO_ANSWER_END ===")



