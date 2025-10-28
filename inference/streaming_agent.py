import json
import json5
import os
import time
import asyncio
import logging
from typing import Dict, Iterator, List, Optional, Generator
from datetime import datetime
from react_agent import MultiTurnReactAgent, TOOL_MAP, MAX_LLM_CALL_PER_RUN, today_date
from prompt import SYSTEM_PROMPT
from answer_system import AnswerJudgmentSystem

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
    
    def call_server_stream(self, msgs, max_tries=3):
        """流式调用LLM服务器"""
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
                stream = client.chat.completions.create(
                    model=self.llm_model,
                    messages=msgs,
                    stop=["\n<tool_response>", "<tool_response>"],
                    temperature=self.llm_generate_cfg.get('temperature', 0.6),
                    top_p=self.llm_generate_cfg.get('top_p', 0.95),
                    max_tokens=8000,
                    presence_penalty=self.llm_generate_cfg.get('presence_penalty', 1.1),
                    stream=True  # 启用流式
                )
                
                accumulated_content = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content_piece = chunk.choices[0].delta.content
                        accumulated_content += content_piece
                        yield content_piece  # 逐块yield
                
                if accumulated_content.strip():
                    logger.debug("--- Streaming service call successful ---")
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
        
        yield "vllm server error!!!"
        
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
        
    def stream_run(self, question: str, cancelled: dict = None) -> Generator[Dict, None, None]:
        """
        流式运行推理过程，实时输出各个阶段的信息
        
        Args:
            question: 用户问题
            planning_port: vLLM服务器端口
            cancelled: 取消标记字典 {"value": False}，当设置为 True 时中断处理
            
        Yields:
            Dict: 包含当前阶段信息的字典
        """
        # 初始化 cancelled 标记
        if cancelled is None:
            cancelled = {"value": False}
        logger.info(f"=== StreamingReactAgent.stream_run START ===")
        logger.debug(f"Question: {question}")
        logger.debug(f"LLM Model: {self.llm_model}")
        
        start_time = time.time()
        self.user_prompt = question
        
        # 初始化
        system_prompt = SYSTEM_PROMPT + str(today_date())
        messages = [
            {"role": "system", "content": system_prompt}, 
            {"role": "user", "content": question}
        ]
        
        init_event = {
            "type": "init",
            "content": f"开始处理问题...",
            "timestamp": datetime.now().isoformat()
        }
        logger.debug(f"Yielding init event: {init_event}")
        yield init_event
        
        num_llm_calls_available = MAX_LLM_CALL_PER_RUN
        round_num = 0
        
        logger.debug(f"Starting main loop, max calls: {MAX_LLM_CALL_PER_RUN}")
        
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
            
            # 调用LLM
            thinking_start_time = time.time()
            thinking_start_event = {
                "type": "thinking_start",
                "content": "正在思考...",
                "timestamp": datetime.now().isoformat()
            }
            logger.debug(f"Yielding thinking_start event: {thinking_start_event}")
            yield thinking_start_event
            
            try:
                logger.debug(f"Calling LLM server (stream) - Model: {self.llm_model}")
                
                # 使用流式方式获取LLM响应
                accumulated_content = ""
                in_think_tag = False
                think_buffer = ""
                
                for chunk in self.call_server_stream(messages):
                    # 在流式接收过程中检查客户端是否断开
                    if cancelled["value"]:
                        logger.warning(f"⚠️ 客户端断开，停止LLM流式接收")
                        return
                    
                    accumulated_content += chunk
                    
                    # 实时检测和提取 <think> 标签内容
                    if not in_think_tag and '<think>' in accumulated_content:
                        in_think_tag = True
                        # 找到 <think> 后的内容（不包含<think>标签本身）
                        start_pos = accumulated_content.find('<think>') + len('<think>')
                        remaining_content = accumulated_content[start_pos:]
                        
                        # 检查是否已经包含结束标签
                        if '</think>' in remaining_content:
                            # 只提取到 </think> 之前的内容
                            end_pos = remaining_content.find('</think>')
                            think_buffer = remaining_content[:end_pos]
                            chunk_to_send = think_buffer
                            in_think_tag = False  # 立即标记为完成
                        elif '<tool_call>' in remaining_content:
                            # 只提取到 <tool_call> 之前的内容
                            end_pos = remaining_content.find('<tool_call>')
                            think_buffer = remaining_content[:end_pos]
                            chunk_to_send = think_buffer
                            in_think_tag = False  # 立即标记为完成
                        else:
                            think_buffer = remaining_content
                            chunk_to_send = think_buffer
                        
                        # 发送第一块thinking内容（如果有的话）
                        if chunk_to_send.strip():
                            # 清理内容，确保不包含任何标签
                            clean_content = chunk_to_send.strip()
                            clean_accumulated = think_buffer.strip()
                            
                            # 移除可能的标签残留
                            for tag in ['</think>', '<think>', '<tool_call>', '</tool_call>']:
                                clean_content = clean_content.replace(tag, '')
                                clean_accumulated = clean_accumulated.replace(tag, '')
                            
                            if clean_content:  # 确保清理后仍有内容
                                thinking_chunk_event = {
                                    "type": "thinking_chunk",
                                    "content": clean_content,
                                    "accumulated": clean_accumulated,
                                    "is_streaming": not in_think_tag,  # 如果已经找到结束标签，则不再流式
                                    "is_complete": not in_think_tag,
                                    "timestamp": datetime.now().isoformat()
                                }
                                logger.debug(f"[DEBUG] Sending thinking_chunk: content_length={len(clean_content)}, accumulated_length={len(clean_accumulated)}")
                                yield thinking_chunk_event
                            
                    elif in_think_tag:
                        # 检查是否遇到结束标签或tool_call标签
                        if '</think>' in chunk or '<tool_call>' in chunk:
                            # 找到结束位置（优先</think>，其次<tool_call>）
                            end_pos_think = chunk.find('</think>') if '</think>' in chunk else len(chunk)
                            end_pos_tool = chunk.find('<tool_call>') if '<tool_call>' in chunk else len(chunk)
                            end_pos = min(end_pos_think, end_pos_tool)
                            
                            # 提取结束标签前的内容（不包含标签本身）
                            chunk_to_send = chunk[:end_pos]
                            think_buffer += chunk_to_send
                            in_think_tag = False
                            
                            # 发送最后一块thinking内容（如果有的话）
                            if chunk_to_send.strip():
                                # 清理内容
                                clean_content = chunk_to_send.strip()
                                clean_accumulated = think_buffer.strip()
                                
                                for tag in ['</think>', '<think>', '<tool_call>', '</tool_call>']:
                                    clean_content = clean_content.replace(tag, '')
                                    clean_accumulated = clean_accumulated.replace(tag, '')
                                
                                if clean_content:
                                    thinking_chunk_event = {
                                        "type": "thinking_chunk",
                                        "content": clean_content,
                                        "accumulated": clean_accumulated,
                                        "is_streaming": True,  # 仍在流式传输
                                        "is_complete": True,  # 这是最后一块
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    logger.debug(f"[DEBUG] Sending final thinking_chunk: accumulated_length={len(clean_accumulated)}")
                                    yield thinking_chunk_event
                        else:
                            # 继续累积thinking内容
                            think_buffer += chunk
                            chunk_to_send = chunk
                            
                            # 发送thinking片段
                            if chunk_to_send.strip():
                                # 清理内容
                                clean_content = chunk_to_send.strip()
                                clean_accumulated = think_buffer.strip()
                                
                                for tag in ['</think>', '<think>', '<tool_call>', '</tool_call>']:
                                    clean_content = clean_content.replace(tag, '')
                                    clean_accumulated = clean_accumulated.replace(tag, '')
                                
                                if clean_content:
                                    thinking_chunk_event = {
                                        "type": "thinking_chunk",
                                        "content": clean_content,
                                        "accumulated": clean_accumulated,
                                        "is_streaming": True,  # 正在流式传输
                                        "is_complete": False,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    yield thinking_chunk_event
                
                content = accumulated_content
                logger.debug(f"LLM response received (stream completed): {content[:200]}...")
                
                # 如果有思考内容，发送最终的 thinking 事件（标记思考完成，触发前端折叠）
                if think_buffer.strip():
                    # 清理思考内容：移除可能残留的标签
                    clean_thinking = think_buffer.strip()
                    
                    # 移除所有可能的标签
                    for tag in ['</think>', '<think>', '<tool_call>', '</tool_call>', '<tool_response>', '</tool_response>']:
                        clean_thinking = clean_thinking.replace(tag, '')
                    
                    # 移除标签后可能的多余空白
                    clean_thinking = clean_thinking.strip()
                    
                    # 只有在有实际内容时才发送 thinking 事件
                    if clean_thinking:
                        thinking_elapsed = time.time() - thinking_start_time
                        logger.info(f"⏱️  【时间统计】思考过程完成，耗时: {thinking_elapsed:.2f} 秒")
                        
                        thinking_complete_event = {
                            "type": "thinking",
                            "content": clean_thinking,
                            "is_streaming": False,  # 明确标记流式结束，触发折叠
                            "timestamp": datetime.now().isoformat(),
                            "elapsed_time": f"{thinking_elapsed:.2f}秒"
                        }
                        logger.debug(f"[DEBUG] Yielding thinking complete event: content_length={len(clean_thinking)}")
                        logger.debug(f"[DEBUG] Content preview: {clean_thinking[:200]}...")
                        yield thinking_complete_event
                
                # 清理tool_response标记
                if '<tool_response>' in content:
                    pos = content.find('<tool_response>')
                    content = content[:pos]
                    
                messages.append({"role": "assistant", "content": content.strip()})
                logger.debug(f"Added assistant message to conversation")
                
                # 检查工具调用
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
                    
                    logger.debug(f"Found tool call in response")
                    tool_call_raw = content.split('<tool_call>')[1].split('</tool_call>')[0]
                    
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
                            result = self.custom_call_tool(tool_name, tool_args)
                            retrieval_elapsed = time.time() - retrieval_start_time
                            logger.info(f"⏱️  【时间统计】检索工具执行完成，耗时: {retrieval_elapsed:.2f} 秒")
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
                        "content": f"检索到 {len(result.split('---')) if '---' in result else 1} 条相关文献",
                        "result": result,
                        "timestamp": datetime.now().isoformat(),
                        "elapsed_time": f"{retrieval_elapsed:.2f}秒" if 'retrieval_elapsed' in locals() else None
                    }
                    logger.debug(f"Yielding tool_result event: {tool_result_event}")
                    yield tool_result_event
                    
                    # 如果是检索工具，流式判断结果是否足够回答问题
                    if tool_name == "retrieval" and result and not result.startswith("[Retrieval] Error"):
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
                                    # 流式发送判断文本片段
                                    accumulated_judgment_text = judgment_event.get("accumulated", "")
                                    chunk_event = {
                                        "type": "judgment_streaming",
                                        "content": accumulated_judgment_text,  # 累积的判断文本
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
                                            # 逐块发送最终答案内容（仅答案主体，不含参考文献）
                                            chunk_content = stream_event.get("content", "")
                                            accumulated_answer += chunk_content
                                            
                                            # 使用final_answer_chunk类型，前端会用最终答案样式渲染
                                            chunk_event = {
                                                "type": "final_answer_chunk",
                                                "content": accumulated_answer,  # 发送累积的答案内容（不含参考文献）
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
                                # 检索内容不足，继续推理流程
                                continue_reasoning_event = {
                                    "type": "continue_reasoning",
                                    "content": f"检索内容不足以回答问题（置信度: {judgment.get('confidence', 0):.2f}），继续推理流程...",
                                    "timestamp": datetime.now().isoformat()
                                }
                                logger.debug(f"Yielding continue_reasoning event: {continue_reasoning_event}")
                                yield continue_reasoning_event
                                
                        except Exception as e:
                            judgment_error_event = {
                                "type": "judgment_error",
                                "content": f"检索内容评估出错: {str(e)}",
                                "timestamp": datetime.now().isoformat()
                            }
                            logger.debug(f"Yielding judgment_error event: {judgment_error_event}")
                            yield judgment_error_event
                    
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



