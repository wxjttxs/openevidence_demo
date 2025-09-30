#!/usr/bin/env python3
"""
独立的推理API服务器
端口: 5006
功能: 提供流式推理服务，调用vLLM服务器进行深度研究
"""

import os
import json
import asyncio
from typing import Dict, Generator, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from streaming_agent import StreamingReactAgent

# 配置
API_PORT = int(os.getenv('API_PORT', 5006))
VLLM_PORT = int(os.getenv('PLANNING_PORTS', 6001))
MODEL_PATH = os.getenv('MODEL_PATH', '/path/to/your/model')

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

class ChatResponse(BaseModel):
    type: str
    content: str
    timestamp: str
    round: Optional[int] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    result: Optional[str] = None
    code: Optional[str] = None

# 全局变量
agent = None

def initialize_agent():
    """初始化推理代理"""
    global agent
    
    # 配置LLM参数
    llm_config = {
        "model": MODEL_PATH,
        "generate_cfg": {
            "temperature": 0.85,
            "top_p": 0.95,
            "presence_penalty": 1.1,
            "max_tokens": 10000
        }
    }
    
    # 初始化代理
    agent = StreamingReactAgent(llm=llm_config)
    print(f"✅ 推理代理初始化完成")
    print(f"📡 vLLM服务器地址: http://localhost:{VLLM_PORT}/v1")
    print(f"🤖 模型路径: {MODEL_PATH}")

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("🚀 启动Tongyi DeepResearch API服务器...")
    initialize_agent()
    print(f"🌐 API服务器将在端口 {API_PORT} 上运行")

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
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_initialized": agent is not None
    }

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口"""
    if agent is None:
        raise HTTPException(status_code=500, detail="推理代理未初始化")
    
    try:
        # 更新代理配置
        agent.llm_generate_cfg.update({
            "temperature": request.temperature,
            "top_p": request.top_p,
            "presence_penalty": request.presence_penalty,
            "max_tokens": request.max_tokens
        })
        
        def generate_stream():
            """生成流式响应"""
            try:
                for event in agent.stream_run(request.question, VLLM_PORT):
                    # 转换为JSON格式
                    response_data = {
                        "type": event.get("type", "unknown"),
                        "content": event.get("content", ""),
                        "timestamp": event.get("timestamp", datetime.now().isoformat())
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
                    
                    # 发送数据
                    yield f"data: {json.dumps(response_data, ensure_ascii=False)}\n\n"
                    
            except Exception as e:
                error_data = {
                    "type": "error",
                    "content": f"流式处理出错: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")

@app.post("/chat")
async def chat(request: ChatRequest):
    """非流式聊天接口（用于测试）"""
    if agent is None:
        raise HTTPException(status_code=500, detail="推理代理未初始化")
    
    try:
        # 更新代理配置
        agent.llm_generate_cfg.update({
            "temperature": request.temperature,
            "top_p": request.top_p,
            "presence_penalty": request.presence_penalty,
            "max_tokens": request.max_tokens
        })
        
        # 收集所有事件
        events = []
        for event in agent.stream_run(request.question, VLLM_PORT):
            events.append(event)
        
        return {
            "question": request.question,
            "events": events,
            "total_events": len(events),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")

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





