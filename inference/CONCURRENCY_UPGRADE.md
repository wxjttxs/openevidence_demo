# 并发控制升级说明

## 🎯 升级原因

**之前的问题**：使用全局锁（Lock）导致所有请求串行处理
- 第2个请求需要等待第1个完全处理完成（可能几分钟）
- 用户体验很差，响应速度慢

**升级方案**：使用信号量（Semaphore）支持有限并发
- 允许同时处理多个请求（默认3个）
- 平衡性能和资源使用
- 大幅提升用户体验

## 📊 性能对比

### 方案对比

| 方案 | 并发数 | 第2个请求等待时间 | 资源使用 | 用户体验 |
|------|--------|-----------------|---------|---------|
| **串行（Lock）** | 1 | 2-5分钟 | 低 | ⭐ |
| **有限并发（Semaphore）** | 3 | 0秒（如果<3个）| 中等 | ⭐⭐⭐⭐⭐ |
| **无限并发** | ∞ | 0秒 | 极高，可能崩溃 | ⭐⭐ |

### 实际场景

```
场景1：2个用户同时提问
┌─────────┐                      ┌─────────┐
│ 用户A   │ ────┐                │ 用户A   │ ────┐
└─────────┘     │                └─────────┘     │
                ├─ 串行: B等3分钟               ├─ 并发: 同时处理
┌─────────┐     │                ┌─────────┐     │
│ 用户B   │ ────┘                │ 用户B   │ ────┘
└─────────┘                      └─────────┘

场景2：5个用户同时提问
┌─────────┐                      ┌─────────┐
│ 用户A-E │ ────┐                │用户A-C  │ ────┐ 立即处理
└─────────┘     │                ├─────────┤     │
                ├─ 串行: 排队15分钟 │用户D-E  │ ────┘ 等待槽位
                │                └─────────┘
                ↓
          B等3min, C等6min...      D,E等有槽位释放（更快）
```

## 🔧 核心改进

### 1. 信号量控制

```python
# 旧版：全局锁（串行）
processing_lock = threading.Lock()

with processing_lock:  # 同一时间只能1个
    process_request()

# 新版：信号量（有限并发）
MAX_CONCURRENT_REQUESTS = 3
processing_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

with processing_semaphore:  # 同一时间最多3个
    process_request()
```

### 2. 可配置并发数

```bash
# 默认3个并发
./start_api_only.sh

# 自定义5个并发
export MAX_CONCURRENT_REQUESTS=5
./start_api_only.sh

# 根据服务器性能调整
# - 高性能服务器：5-10
# - 中等服务器：3-5
# - 低配服务器：1-2
```

### 3. 超时保护

```python
# 最多等待5分钟获取槽位
acquired = processing_semaphore.acquire(timeout=300)

if not acquired:
    # 返回友好错误提示
    return "服务器繁忙，请稍后重试"
```

### 4. 实时监控

```bash
# 查看当前状态
curl http://localhost:5006/health

{
  "max_concurrent": 3,           # 最大并发数
  "available_slots": 1,          # 可用槽位
  "processing_count": 2,         # 正在处理的请求数
  "active_sessions": 2           # 活跃会话数
}
```

## 🚀 工作流程

### 并发处理流程

```
请求1 (T0)          请求2 (T0.1)         请求3 (T0.2)         请求4 (T1)
   ↓                    ↓                    ↓                    ↓
获取槽位1 ✓          获取槽位2 ✓          获取槽位3 ✓          等待槽位...
   ↓                    ↓                    ↓                    ↓
创建Agent1           创建Agent2           创建Agent3           排队中...
   ↓                    ↓                    ↓                    ↓
处理中...            处理中...            处理中...            排队中...
   ↓                    ↓                    ↓                    ↓
完成 (T3)            完成 (T4)            完成 (T5)            获取槽位1 ✓
   ↓                    ↓                    ↓                    ↓
释放槽位1 →──────────→ 槽位可用 ←──────────── 请求4使用       处理中...
```

### 时间线对比

```
旧版串行（Lock）：
T0    T3       T6       T9       T12
├─────┼────────┼────────┼────────┼────────►
│ R1  │   R2   │   R3   │   R4   │
└─────┴────────┴────────┴────────┴────────►
总耗时：12分钟处理4个请求

新版并发（Semaphore，max=3）：
T0    T3       T6
├─────┼────────┼────────►
│ R1  │        │
│ R2  │   R4   │
│ R3  │        │
└─────┴────────┴────────►
总耗时：6分钟处理4个请求（快50%）
```

## 📈 性能测试

### 建议测试

```bash
# 1. 单请求测试
time curl -X POST http://localhost:5006/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"测试问题"}'

# 2. 并发测试（3个）
for i in {1..3}; do
  curl -X POST http://localhost:5006/chat/stream \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"测试问题$i\"}" &
done
wait

# 3. 压力测试（5个，会有2个等待）
for i in {1..5}; do
  curl -X POST http://localhost:5006/chat/stream \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"测试问题$i\"}" &
done
wait
```

### 观察日志

```bash
tail -f logs/api_server.log

# 期待看到：
⏳ [Session abc12345] 等待获取处理槽位... (当前活跃: 0)
🚀 [Session abc12345] 获取槽位成功，开始处理...
⏳ [Session def67890] 等待获取处理槽位... (当前活跃: 1)
🚀 [Session def67890] 获取槽位成功，开始处理...
⏳ [Session ghi13579] 等待获取处理槽位... (当前活跃: 2)
🚀 [Session ghi13579] 获取槽位成功，开始处理...
⏳ [Session jkl24680] 等待获取处理槽位... (当前活跃: 3)  # 第4个在等待
✅ [Session abc12345] 处理完成，释放槽位
🔓 [Session abc12345] 槽位已释放
🚀 [Session jkl24680] 获取槽位成功，开始处理...  # 第4个开始处理
```

## ⚙️ 配置建议

### 根据服务器配置调整

#### 高性能服务器（GPU充足）
```bash
export MAX_CONCURRENT_REQUESTS=5
# vLLM也支持批处理，可以适当提高并发
```

#### 中等服务器（单GPU）
```bash
export MAX_CONCURRENT_REQUESTS=3  # 默认值，推荐
```

#### 低配服务器
```bash
export MAX_CONCURRENT_REQUESTS=1  # 等同于旧版Lock
```

### 监控和调优

1. **观察vLLM资源使用**
```bash
nvidia-smi -l 1  # 观察GPU使用率
```

2. **观察API服务器负载**
```bash
htop  # 观察CPU和内存
```

3. **调整并发数**
```bash
# 如果GPU使用率低（<70%），可以增加并发
export MAX_CONCURRENT_REQUESTS=5

# 如果出现OOM（内存不足），减少并发
export MAX_CONCURRENT_REQUESTS=2
```

## 🎯 适用场景

### 推荐使用信号量的场景 ✅

- 多用户系统
- 需要快速响应
- vLLM服务器资源充足
- 有多个GPU或高性能GPU

### 可能需要串行的场景 ⚠️

- 单用户系统
- GPU资源极度受限
- 需要绝对的请求隔离
- 调试和开发环境

## 🔍 故障排查

### 问题1：所有请求都在等待

**症状**：`available_slots` 始终为0

**原因**：某个请求卡住未释放槽位

**解决**：
```bash
# 重启API服务
./stop_api.sh
./start_api_only.sh
```

### 问题2：请求返回503错误

**症状**：`服务器繁忙，请稍后重试`

**原因**：等待超过5分钟（300秒）

**解决**：
1. 增加并发数
2. 优化单个请求的处理时间
3. 增加超时时间（不推荐）

### 问题3：内存不足（OOM）

**症状**：服务器崩溃或响应极慢

**原因**：并发数过高，每个Agent占用内存

**解决**：
```bash
# 减少并发数
export MAX_CONCURRENT_REQUESTS=2
./start_api_only.sh
```

## 📝 升级步骤

1. **停止服务**
```bash
./stop_api.sh
```

2. **配置并发数**（可选）
```bash
# 编辑 .env 文件
echo "MAX_CONCURRENT_REQUESTS=3" >> .env
```

3. **重启服务**
```bash
./start_api_only.sh
```

4. **验证配置**
```bash
curl http://localhost:5006/health | jq '.max_concurrent'
```

5. **测试并发**
```bash
# 同时发送2个请求，观察是否并发处理
```

## 🎉 预期收益

- ✅ 响应速度提升50-70%
- ✅ 用户体验显著改善
- ✅ 更好的资源利用
- ✅ 支持更多并发用户
- ✅ 可根据硬件灵活调整

