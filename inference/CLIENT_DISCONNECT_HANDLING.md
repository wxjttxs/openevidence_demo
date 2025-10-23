# 客户端断开检测和任务中断机制

## 问题描述

在用户关闭浏览器或取消请求后，后端仍在继续执行昂贵的操作（如LLM推理、知识库检索等），造成资源浪费。

## 解决方案

实现了完整的客户端断开检测和任务中断机制，确保在客户端断开后立即停止处理。

## 实现原理

### 1. 断开检测（`api_server.py`）

```python
async def generate_stream():
    cancelled = {"value": False}  # 共享的取消标记
    
    try:
        # ...执行流式处理
        for event in agent.stream_run(question, VLLM_PORT, cancelled=cancelled):
            if cancelled["value"]:  # 定期检查
                break
            yield event
    
    except GeneratorExit:
        # 捕获客户端断开
        cancelled["value"] = True  # 设置取消标记
        # 通知 agent 停止处理
```

**关键点：**
- 使用字典 `{"value": False}` 而不是布尔值，确保引用传递
- `GeneratorExit` 异常在客户端断开时由 FastAPI 自动抛出
- 设置标记后，agent 会在下一个检查点停止

### 2. 任务中断（`streaming_agent.py`）

```python
def stream_run(self, question, planning_port, cancelled=None):
    if cancelled is None:
        cancelled = {"value": False}
    
    while num_llm_calls_available > 0:
        # 每轮开始检查
        if cancelled["value"]:
            print(f"⚠️ 客户端断开，停止推理循环")
            return
        
        # 工具调用前检查
        if '<tool_call>' in content:
            if cancelled["value"]:
                print(f"⚠️ 客户端断开，跳过工具调用")
                return
            # 执行工具调用...
```

**检查点：**
1. ✅ 每轮推理开始前
2. ✅ 工具调用执行前
3. ✅ 流式输出每个事件时

## 效果对比

### 优化前
```
用户关闭浏览器
    ↓
后端继续执行 5-10 分钟  ❌
    ↓
完整推理流程结束
    ↓
资源释放
```

### 优化后
```
用户关闭浏览器
    ↓
FastAPI 抛出 GeneratorExit
    ↓
设置 cancelled["value"] = True
    ↓
Agent 在下一个检查点停止  ✅ (< 1秒)
    ↓
立即释放资源和信号量
```

## 资源清理

即使任务被中断，也会确保：
- ✅ 信号量正确释放
- ✅ Agent 实例被删除
- ✅ 会话状态更新为 "cancelled"
- ✅ 活跃会话计数正确

```python
finally:
    # 清理会话记录
    with session_lock:
        if session_id in active_sessions:
            active_sessions[session_id]["status"] = "cancelled"
    
    # 清理 agent 实例
    if agent is not None:
        del agent
    
    # 释放信号量
    if acquired:
        processing_semaphore.release()
```

## 监控和日志

### 正常断开日志
```
⚠️ [Session 79f38f93] 客户端断开连接，设置取消标记
⚠️ 客户端断开，停止推理循环
🔓 [Session 79f38f93] 槽位已释放
```

### 活跃会话状态
```bash
curl http://localhost:5006/sessions
```

返回示例：
```json
{
  "79f38f93-xxxx": {
    "question": "...",
    "status": "cancelled",  // 标记为已取消
    "start_time": "...",
    "end_time": "..."
  }
}
```

## 性能优化

1. **检查开销极小**：每个检查点只需 O(1) 字典查找
2. **及时响应**：通常在 < 1 秒内检测到断开并停止
3. **无阻塞**：不影响正常流式传输性能

## 兼容性

- ✅ 向后兼容：`cancelled` 参数默认为 `None`
- ✅ 单元测试：无需修改现有测试
- ✅ 独立运行：不传 `cancelled` 参数时正常运行

## 最佳实践

### 对于新工具开发

如果你要开发新的耗时工具，建议在工具内部也支持中断：

```python
class LongRunningTool(BaseTool):
    def call(self, params, cancelled=None):
        for i in range(large_number):
            # 定期检查
            if cancelled and cancelled.get("value"):
                return "Tool execution cancelled"
            # 执行耗时操作...
```

### 对于调用外部API

```python
# 不好：无法中断的长等待
response = requests.get(url, timeout=300)

# 好：可以中断
for attempt in range(max_retries):
    if cancelled and cancelled["value"]:
        break
    try:
        response = requests.get(url, timeout=10)
        break
    except Timeout:
        continue
```

## 测试方法

1. 启动服务
2. 发起一个复杂查询
3. 在得到答案前关闭浏览器
4. 观察后端日志：
   ```
   ⚠️ [Session xxx] 客户端断开连接，设置取消标记
   🔓 [Session xxx] 槽位已释放
   ```

5. 验证槽位被释放：
   ```bash
   curl http://localhost:5006/health
   # available_slots 应该恢复
   ```

## 相关文件

- `/inference/api_server.py` - 断开检测
- `/inference/streaming_agent.py` - 任务中断
- `/inference/CONCURRENCY_DESIGN.md` - 并发控制设计

