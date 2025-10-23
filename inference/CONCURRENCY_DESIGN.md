# 并发控制设计文档

## 🔍 问题分析

### 原有架构的并发问题

**问题描述**：
- 所有请求共享一个全局 `agent` 实例
- 后来的请求会覆盖前面请求的配置
- 多个 `stream_run()` 并发执行时状态互相干扰
- 导致回答内容混乱

**示例场景**：
```
时间轴：
T1: 用户A发送问题"糖尿病如何干预？" → agent开始处理
T2: 用户B发送问题"高血压如何治疗？" → agent配置被覆盖，状态混乱
T3: 两个问题的回答互相穿插，内容错乱
```

## ✅ 最终解决方案

### 核心设计

使用 **信号量（Semaphore）+ 独立Agent实例** 的方案：

1. **配置模板**：启动时初始化一次配置模板
2. **独立实例**：每个请求创建独立的Agent实例
3. **有限并发**：使用信号量控制最大并发数（默认3个）
4. **会话跟踪**：每个请求分配唯一的session_id

### 架构对比

#### 修改前
```python
# 全局单例（问题所在）
agent = None  

def initialize_agent():
    global agent
    agent = StreamingReactAgent(llm=llm_config)

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    # ❌ 所有请求共享同一个agent
    agent.llm_generate_cfg.update({...})  # ❌ 配置会被覆盖
    for event in agent.stream_run(...):   # ❌ 状态互相干扰
        yield event
```

#### 修改后
```python
# 配置模板（只读）
agent_config_template = None
MAX_CONCURRENT_REQUESTS = 3  # ✅ 可配置的最大并发数
processing_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)  # ✅ 信号量
active_sessions = {}
session_lock = threading.Lock()  # 仅用于保护字典

def initialize_agent_config():
    global agent_config_template
    agent_config_template = {...}  # 只初始化模板

def create_agent_instance(**kwargs):
    # ✅ 为每个请求创建独立实例
    config = copy.deepcopy(agent_config_template)
    config["generate_cfg"].update(kwargs)
    return StreamingReactAgent(llm=config)

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    session_id = str(uuid.uuid4())  # ✅ 唯一会话ID
    
    def generate_stream():
        acquired = False
        try:
            # ✅ 有限并发：最多3个请求同时处理
            acquired = processing_semaphore.acquire(timeout=300)
            if not acquired:
                yield error_message  # 超时提示
                return
            
            agent = create_agent_instance(...)  # ✅ 独立实例
            for event in agent.stream_run(...):
                yield event
        finally:
            if agent:
                del agent  # ✅ 及时释放
            if acquired:
                processing_semaphore.release()  # ✅ 释放槽位
```

## 🎯 关键改进

### 1. 配置模板化
```python
# 启动时初始化一次
agent_config_template = {
    "model": MODEL_PATH,
    "generate_cfg": {...}
}

# 每次请求使用深拷贝
config = copy.deepcopy(agent_config_template)
```

### 2. 会话隔离
```python
session_id = str(uuid.uuid4())  # 唯一标识

active_sessions[session_id] = {
    "question": request.question,
    "start_time": datetime.now().isoformat(),
    "status": "processing"
}
```

### 3. 串行处理
```python
with processing_lock:
    # 同一时间只有一个请求在处理
    agent = create_agent_instance(...)
    for event in agent.stream_run(...):
        yield event
```

### 4. 资源清理
```python
finally:
    # 清理会话记录
    active_sessions[session_id]["status"] = "completed"
    active_sessions[session_id]["end_time"] = datetime.now().isoformat()
    
    # 释放agent实例
    if agent is not None:
        del agent
```

## 📊 工作流程

### 请求处理流程

```
客户端请求
    ↓
生成session_id
    ↓
尝试获取processing_lock ←─────┐
    ↓                          │
锁已被占用？                   │
    ├── 是 → 等待释放 ──────────┘
    └── 否 ↓
         获取锁
         ↓
    创建独立Agent实例
         ↓
    记录到active_sessions
         ↓
    执行stream_run()
         ↓
    发送流式事件
         ↓
    发送完成事件
         ↓
    更新会话状态
         ↓
    释放Agent实例
         ↓
    释放锁
         ↓
    返回响应
```

## 🔄 前后端协作

### 前端（无需修改）
```typescript
// 前端正常发送异步请求
await fetch(`${API_BASE_URL}/chat/stream`, {
  method: 'POST',
  body: JSON.stringify({question, ...config})
})
```

### 后端（自动处理）
```python
# 自动分配session_id
session_id = str(uuid.uuid4())

# 发送会话开始事件
yield {
  "type": "session_start",
  "session_id": session_id,
  ...
}

# 所有后续事件都包含session_id
yield {
  "type": "thinking",
  "session_id": session_id,  # 用于前端关联
  ...
}
```

## 📈 监控与调试

### 新增API端点

#### 1. 健康检查（增强）
```bash
GET /health

Response:
{
  "status": "healthy",
  "agent_config_initialized": true,
  "active_sessions": 2,        # 当前活跃会话数
  "lock_acquired": true         # 锁是否被占用
}
```

#### 2. 会话列表
```bash
GET /sessions

Response:
{
  "active_sessions": {
    "abc123...": {
      "question": "糖尿病如何干预？",
      "start_time": "2025-10-23T10:00:00",
      "status": "processing"
    },
    "def456...": {
      "question": "高血压如何治疗？", 
      "start_time": "2025-10-23T10:00:05",
      "status": "completed",
      "end_time": "2025-10-23T10:02:30"
    }
  },
  "total": 2
}
```

### 日志输出

```bash
🔐 [Session abc12345] 获取处理锁，开始处理问题: 糖尿病如何干预？...
✅ [Session abc12345] 处理完成，释放锁
🔐 [Session def45678] 获取处理锁，开始处理问题: 高血压如何治疗？...
✅ [Session def45678] 处理完成，释放锁
```

## ⚡ 性能考虑

### 优点
- ✅ **完全隔离**：每个请求独立，不会互相干扰
- ✅ **状态清晰**：会话状态可追踪
- ✅ **资源可控**：及时释放不用的实例

### 权衡
- ⚠️ **串行处理**：同时只能处理一个请求
- ⚠️ **内存开销**：每个请求创建新实例（但会及时释放）

### 为什么选择串行？

1. **深度研究的特点**：
   - 每个问题处理时间长（几分钟）
   - 需要大量计算资源（LLM推理）
   - 并发意义不大（资源瓶颈在vLLM）

2. **简单可靠**：
   - 避免复杂的并发控制
   - 状态管理简单
   - 易于调试

3. **资源最优**：
   - vLLM服务器本身就是瓶颈
   - 串行处理确保资源充分利用
   - 避免多个请求争抢资源

## 🚀 未来优化方向

如果需要支持真正的并发处理，可以考虑：

### 方案A：任务队列
```python
# 使用Celery或RQ
@app.post("/chat/stream")
async def chat_stream(request):
    task = process_question.delay(request.question)
    return {"task_id": task.id}
```

### 方案B：多vLLM实例
```python
# 负载均衡到多个vLLM服务器
vllm_pool = [6001, 6002, 6003]
port = select_available_vllm(vllm_pool)
```

### 方案C：流式响应池
```python
# 使用连接池管理多个Agent
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=3)
```

## 📝 测试建议

### 测试场景

1. **串行测试**
```bash
# 终端1
curl -X POST http://localhost:5006/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"糖尿病如何干预？"}'

# 终端2（稍后执行）
curl -X POST http://localhost:5006/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"高血压如何治疗？"}'
```

2. **并发测试**
```bash
# 同时发送两个请求
curl -X POST http://localhost:5006/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"糖尿病如何干预？"}' &

curl -X POST http://localhost:5006/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"高血压如何治疗？"}' &
```

**预期结果**：
- 第一个请求立即开始处理
- 第二个请求等待第一个完成后再开始
- 两个请求的回答完全独立，不会混淆

## 🔧 重启服务

修改后需要重启API服务：

```bash
cd /mnt/data6t/wangxiaojing/tongyi_deepresearch/DeepResearch-openevidence/inference

# 停止服务
./stop_api.sh

# 重新启动
./start_api_only.sh
```

查看日志确认并发控制生效：
```bash
tail -f logs/api_server.log | grep "Session"
```

