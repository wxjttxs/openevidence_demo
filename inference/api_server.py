#!/usr/bin/env python3
"""
独立的推理API服务器
端口: 5006
功能: 提供流式推理服务，调用vLLM服务器进行深度研究
"""

import os
import json
import asyncio
import uuid
from typing import Dict, Generator, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import threading

from streaming_agent import StreamingReactAgent

# 配置
API_PORT = int(os.getenv('API_PORT', 5006))
VLLM_PORT = int(os.getenv('PLANNING_PORTS', 6001))
MODEL_PATH = os.getenv('MODEL_PATH', '/path/to/your/model')

# 并发控制
MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT_REQUESTS', 3))  # 最大并发数
processing_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)  # 信号量控制并发
active_sessions = {}  # 跟踪活跃的会话
global_citations = {}  # 全局存储所有 citations 数据（按 citation_id 索引）
session_lock = threading.Lock()  # 仅用于保护active_sessions和global_citations字典

# 创建FastAPI应用
app = FastAPI(
    title="Tongyi DeepResearch API",
    description="深度研究推理API服务",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class ChatRequest(BaseModel):
    question: str
    temperature: Optional[float] = 0.85
    top_p: Optional[float] = 0.95
    presence_penalty: Optional[float] = 1.1
    max_tokens: Optional[int] = 10000
    session_id: Optional[str] = None  # 可选的会话ID

class ChatResponse(BaseModel):
    type: str
    content: str
    timestamp: str
    round: Optional[int] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    result: Optional[str] = None
    code: Optional[str] = None

# 全局配置（模板）
agent_config_template = None

def initialize_agent_config():
    """初始化代理配置模板"""
    global agent_config_template
    
    # 配置LLM参数模板
    agent_config_template = {
        "model": MODEL_PATH,
        "generate_cfg": {
            "temperature": 0.85,
            "top_p": 0.95,
            "presence_penalty": 1.1,
            "max_tokens": 10000
        }
    }
    
    print(f"✅ 推理代理配置模板初始化完成")
    print(f"📡 vLLM服务器地址: http://localhost:{VLLM_PORT}/v1")
    print(f"🤖 模型路径: {MODEL_PATH}")

def create_agent_instance(temperature=0.85, top_p=0.95, presence_penalty=1.1, max_tokens=10000):
    """为每个请求创建独立的agent实例"""
    import copy
    config = copy.deepcopy(agent_config_template)
    config["generate_cfg"].update({
        "temperature": temperature,
        "top_p": top_p,
        "presence_penalty": presence_penalty,
        "max_tokens": max_tokens
    })
    return StreamingReactAgent(llm=config)

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("🚀 启动Tongyi DeepResearch API服务器...")
    initialize_agent_config()
    print(f"🌐 API服务器将在端口 {API_PORT} 上运行")
    print(f"🔒 并发控制: 最大并发请求数 = {MAX_CONCURRENT_REQUESTS}")
    print(f"💡 提示: 可通过环境变量 MAX_CONCURRENT_REQUESTS 调整并发数")

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Tongyi DeepResearch API Server",
        "version": "1.0.0",
        "status": "running",
        "vllm_port": VLLM_PORT,
        "model_path": MODEL_PATH
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    available_slots = processing_semaphore._value  # 可用槽位数
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_config_initialized": agent_config_template is not None,
        "active_sessions": len(active_sessions),
        "max_concurrent": MAX_CONCURRENT_REQUESTS,
        "available_slots": available_slots,
        "processing_count": MAX_CONCURRENT_REQUESTS - available_slots
    }

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口"""
    if agent_config_template is None:
        raise HTTPException(status_code=500, detail="推理代理配置未初始化")
    
    # 生成唯一的会话ID
    session_id = request.session_id or str(uuid.uuid4())
    
    try:
        def generate_stream():
            """生成流式响应"""
            agent = None
            acquired = False
            cancelled = {"value": False}  # 客户端断开标记（使用字典以便传递引用）
            
            try:
                # 获取信号量（允许有限并发）
                print(f"⏳ [Session {session_id[:8]}] 等待获取处理槽位... (当前活跃: {len(active_sessions)})")
                acquired = processing_semaphore.acquire(timeout=300)  # 最多等待5分钟
                
                if not acquired:
                    error_data = {
                        "type": "error",
                        "content": "服务器繁忙，请求超时，请稍后重试",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                    
                    # 发送 completed 事件以确保流正确关闭
                    completed_data = {
                        "type": "completed",
                        "content": "请求超时，流程结束",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(completed_data, ensure_ascii=False)}\n\n"
                    return
                
                print(f"🚀 [Session {session_id[:8]}] 获取槽位成功，开始处理问题: {request.question[:50]}...")
                
                # 为这个请求创建独立的agent实例
                agent = create_agent_instance(
                    temperature=request.temperature,
                    top_p=request.top_p,
                    presence_penalty=request.presence_penalty,
                    max_tokens=request.max_tokens
                )
                
                # 记录活跃会话（使用锁保护字典操作）
                with session_lock:
                    active_sessions[session_id] = {
                        "question": request.question,
                        "start_time": datetime.now().isoformat(),
                        "status": "processing",
                        "cancelled": cancelled  # 保存引用，便于外部检查
                    }
                
                # 发送会话开始事件
                session_start_data = {
                    "type": "session_start",
                    "content": f"会话 {session_id[:8]} 开始处理",
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(session_start_data, ensure_ascii=False)}\n\n"
                
                # 执行流式处理（传入 cancelled 标记）
                has_completed = False  # 标记是否已发送 completed 事件
                
                event_count = 0
                for event in agent.stream_run(request.question, VLLM_PORT, cancelled=cancelled):
                    event_count += 1
                    
                    # 每个事件前检查客户端是否断开
                    if cancelled["value"]:
                        print(f"⚠️ [Session {session_id[:8]}] 检测到客户端断开，停止处理（已处理 {event_count} 个事件）")
                        break
                    
                    # 转换为JSON格式
                    response_data = {
                        "type": event.get("type", "unknown"),
                        "content": event.get("content", ""),
                        "timestamp": event.get("timestamp", datetime.now().isoformat()),
                        "session_id": session_id
                    }
                    
                    # 添加可选字段
                    if "round" in event:
                        response_data["round"] = event["round"]
                    if "tool_name" in event:
                        response_data["tool_name"] = event["tool_name"]
                    if "tool_args" in event:
                        response_data["tool_args"] = event["tool_args"]
                    if "result" in event:
                        response_data["result"] = event["result"]
                    if "code" in event:
                        response_data["code"] = event["code"]
                    if "judgment" in event:
                        response_data["judgment"] = event["judgment"]
                    if "accumulated" in event:
                        response_data["accumulated"] = event["accumulated"]
                    if "is_streaming" in event:
                        response_data["is_streaming"] = event["is_streaming"]
                    if "answer_data" in event:
                        # 优化：为 citations 添加 preview 字段（前50字）
                        answer_data = event["answer_data"]
                        print(f"[DEBUG] Processing answer_data: {type(answer_data)}, has citations: {'citations' in answer_data if isinstance(answer_data, dict) else 'N/A'}")
                        if isinstance(answer_data, dict) and "citations" in answer_data:
                            full_citations = answer_data.get("citations", [])
                            print(f"[DEBUG] Full citations count: {len(full_citations)}")
                            
                            # 保存完整的 citations 到全局存储（供后续接口查询）
                            with session_lock:
                                for citation in full_citations:
                                    citation_id = citation.get("id")
                                    full_content = citation.get("full_content", "")
                                    if citation_id:
                                        # 使用 citation_id 作为全局唯一键
                                        global_citations[str(citation_id)] = {
                                            "id": citation_id,
                                            "title": citation.get("title", ""),
                                            "full_content": full_content
                                        }
                                        print(f"[DEBUG] Saved citation {citation_id} to global_citations")
                            
                            # 处理发送给前端的 citations（只包含 preview）
                            processed_citations = []
                            for citation in full_citations:
                                processed_citation = {
                                    "id": citation.get("id"),
                                    "title": citation.get("title", ""),
                                }
                                # 添加 preview 字段（前30字）
                                if "full_content" in citation:
                                    full_content = citation["full_content"]
                                    processed_citation["preview"] = full_content[:30] if len(full_content) > 30 else full_content
                                processed_citations.append(processed_citation)
                            answer_data = answer_data.copy()
                            answer_data["citations"] = processed_citations
                            print(f"[DEBUG] Processed citations count: {len(processed_citations)}")
                        response_data["answer_data"] = answer_data
                        print(f"[DEBUG] Added answer_data to response_data, citations: {len(response_data['answer_data'].get('citations', [])) if isinstance(response_data.get('answer_data'), dict) else 'N/A'}")
                    
                    # 检查是否是 completed 事件
                    if event.get("type") == "completed":
                        has_completed = True
                    
                    # 发送数据（添加异常处理）
                    try:
                        # 在序列化前记录事件类型
                        event_type = response_data.get('type')
                        if event_type == 'final_answer':
                            print(f"🔍 [Session {session_id[:8]}] 准备序列化 final_answer 事件...")
                            print(f"   - answer_data存在: {'answer_data' in response_data}")
                            if 'answer_data' in response_data and isinstance(response_data['answer_data'], dict):
                                print(f"   - citations数量: {len(response_data['answer_data'].get('citations', []))}")
                        
                        json_str = json.dumps(response_data, ensure_ascii=False)
                        
                        # 记录大数据包的大小
                        if len(json_str) > 10000:  # 超过 10KB
                            print(f"⚠️ [Session {session_id[:8]}] 发送大数据包: {len(json_str)} 字节, 类型: {event_type}")
                        elif event_type == 'final_answer':
                            print(f"✅ [Session {session_id[:8]}] final_answer序列化成功: {len(json_str)} 字节")
                        
                        yield f"data: {json_str}\n\n"
                        
                        if event_type == 'final_answer':
                            print(f"✅ [Session {session_id[:8]}] final_answer数据已yield")
                    except Exception as json_error:
                        # JSON序列化失败：只记录日志，不发送error事件给前端（避免重复错误卡片）
                        print(f"❌ [Session {session_id[:8]}] JSON序列化失败: {str(json_error)}")
                        print(f"   Event type: {response_data.get('type')}")
                        import traceback
                        traceback.print_exc()
                        # 尝试发送简化版本（只包含基本字段）
                        try:
                            simple_data = {
                                "type": response_data.get("type", "unknown"),
                                "content": str(response_data.get("content", ""))[:500],  # 截断内容
                                "session_id": session_id,
                                "timestamp": response_data.get("timestamp", datetime.now().isoformat())
                            }
                            yield f"data: {json.dumps(simple_data, ensure_ascii=False)}\n\n"
                        except:
                            print(f"❌ [Session {session_id[:8]}] 连简化数据也无法序列化，跳过此事件")
                            pass
                
                # 只有当 agent 没有发送 completed 事件时，才补发一个
                if not has_completed:
                    print(f"⚠️ [Session {session_id[:8]}] Agent未发送completed事件，补发")
                    completed_data = {
                        "type": "completed",
                        "content": "处理完成",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(completed_data, ensure_ascii=False)}\n\n"
                
                print(f"✅ [Session {session_id[:8]}] 处理完成，释放槽位")
                
            except GeneratorExit:
                # 客户端主动断开连接
                print(f"⚠️ [Session {session_id[:8]}] 客户端断开连接（GeneratorExit）")
                cancelled["value"] = True
                with session_lock:
                    if session_id in active_sessions:
                        active_sessions[session_id]["status"] = "client_disconnected"
                raise  # 重新抛出，让 FastAPI 处理
                
            except Exception as e:
                print(f"❌ [Session {session_id[:8]}] Stream generation error: {str(e)}")
                import traceback
                traceback.print_exc()
                try:
                    error_data = {
                        "type": "error",
                        "content": f"流式处理出错: {str(e)}",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                    
                    # 发送 completed 事件以确保流正确关闭
                    completed_data = {
                        "type": "completed",
                        "content": "处理失败，流程结束",
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(completed_data, ensure_ascii=False)}\n\n"
                except:
                    pass  # 如果无法发送错误消息，静默失败
            finally:
                # 清理会话记录
                try:
                    with session_lock:
                        if session_id in active_sessions:
                            # 根据 cancelled 状态设置不同的结束状态
                            if cancelled["value"]:
                                active_sessions[session_id]["status"] = "client_disconnected"
                                print(f"✅ [Session {session_id[:8]}] 客户端断开，会话已清理")
                            else:
                                active_sessions[session_id]["status"] = "completed"
                                print(f"✅ [Session {session_id[:8]}] 会话正常完成")
                            active_sessions[session_id]["end_time"] = datetime.now().isoformat()
                except Exception as e:
                    print(f"⚠️ [Session {session_id[:8]}] 清理会话记录失败: {e}")
                
                # 清理agent实例
                if agent is not None:
                    try:
                        del agent
                    except:
                        pass
                
                # 释放信号量
                if acquired:
                    try:
                        processing_semaphore.release()
                        print(f"🔓 [Session {session_id[:8]}] 槽位已释放")
                    except:
                        pass
        
        # 创建流式响应，确保数据及时发送
        response = StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Transfer-Encoding": "chunked",
            }
        )
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")

@app.post("/chat")
async def chat(request: ChatRequest):
    """非流式聊天接口（用于测试）"""
    if agent_config_template is None:
        raise HTTPException(status_code=500, detail="推理代理配置未初始化")
    
    session_id = request.session_id or str(uuid.uuid4())
    
    acquired = False
    try:
        # 获取信号量
        acquired = processing_semaphore.acquire(timeout=300)
        if not acquired:
            raise HTTPException(status_code=503, detail="服务器繁忙，请稍后重试")
        
        # 为这个请求创建独立的agent实例
        agent = create_agent_instance(
            temperature=request.temperature,
            top_p=request.top_p,
            presence_penalty=request.presence_penalty,
            max_tokens=request.max_tokens
        )
        
        # 收集所有事件
        events = []
        for event in agent.stream_run(request.question, VLLM_PORT):
            events.append(event)
        
        return {
            "session_id": session_id,
            "question": request.question,
            "events": events,
            "total_events": len(events),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")
    finally:
        if acquired:
            processing_semaphore.release()

@app.get("/sessions")
async def get_sessions():
    """获取活跃会话列表"""
    return {
        "active_sessions": active_sessions,
        "total": len(active_sessions),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/citation/{citation_id}")
async def get_citation_detail(citation_id: str):
    """
    获取引用的完整内容（公共接口，不依赖session）
    
    Args:
        citation_id: 引用ID
        
    Returns:
        完整的引用内容
    """
    try:
        with session_lock:
            # 尝试多种 ID 格式（可能是字符串或数字）
            citation_data = None
            for possible_id in [citation_id, str(citation_id)]:
                if possible_id in global_citations:
                    citation_data = global_citations[possible_id]
                    break
            
            if citation_data is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "Citation not found",
                        "message": f"引用 [{citation_id}] 不存在",
                        "citation_id": citation_id,
                        "available_citations": list(global_citations.keys())[:10]  # 只返回前10个
                    }
                )
        
        # 返回完整内容
        return {
            "citation_id": citation_data["id"],
            "title": citation_data["title"],
            "full_content": citation_data["full_content"],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"❌ 获取引用详情失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": f"获取引用详情失败: {str(e)}"
            }
        )

if __name__ == "__main__":
    print("🔧 启动配置:")
    print(f"   API端口: {API_PORT}")
    print(f"   vLLM端口: {VLLM_PORT}")
    print(f"   模型路径: {MODEL_PATH}")
    print()
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=API_PORT,
        reload=False,
        log_level="info"
    )





