#!/bin/bash
source .env
# 简化启动脚本 - 仅用于测试Web界面，不启动vLLM
# 加载conda的初始化脚本
source ~/anaconda3/etc/profile.d/conda.sh  # 或者你的conda安装路径

# 激活conda环境
conda activate react_infer_env
export TORCHDYNAMO_VERBOSE=1
export TORCHDYNAMO_DISABLE=1
export PYTHONDONTWRITEBYTECODE=1

##############参数配置################
export MODEL_PATH=${MODEL_PATH:-"/path/to/your/model"}
export TEMPERATURE=${TEMPERATURE:-0.85}
export PRESENCE_PENALTY=${PRESENCE_PENALTY:-1.1}
export TOP_P=${TOP_P:-0.95}

# API服务端口
export API_PORT=${API_PORT:-5006}
# Web界面端口
export WEB_PORT=${WEB_PORT:-8086}

# 设置vLLM端口信息 - 确保与已启动的vLLM服务器端口一致
export PLANNING_PORTS=${PLANNING_PORTS:-6001}

## API密钥配置 - 请设置环境变量或修改为您的密钥
export SERPER_KEY_ID=${SERPER_KEY_ID:-"your_serper_key_here"}
export JINA_API_KEYS=${JINA_API_KEYS:-"your_jina_key_here"}
export API_KEY=${API_KEY:-"your_api_key_here"}
export API_BASE=${API_BASE:-"https://api.huatuogpt.cn/v1"}
export SUMMARY_MODEL_NAME=${SUMMARY_MODEL_NAME:-"qwen3-32b"}
export DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:-"your_dashscope_key_here"}
export DASHSCOPE_API_BASE=${DASHSCOPE_API_BASE:-"https://dashscope.aliyuncs.com/compatible-mode/v1"}
export VIDEO_MODEL_NAME=${VIDEO_MODEL_NAME:-"qwen-vl-max"}
export VIDEO_ANALYSIS_MODEL_NAME=${VIDEO_ANALYSIS_MODEL_NAME:-"qwen-vl-max"}

# 沙盒配置
ENDPOINTS_STRING=${SANDBOX_ENDPOINT:-"your_sandbox_endpoint"}
export SANDBOX_FUSION_ENDPOINT="$ENDPOINTS_STRING"
export TORCH_COMPILE_CACHE_DIR="./cache"

# IDP配置
export USE_IDP=${USE_IDP:-"True"}
export IDP_KEY_ID=${IDP_KEY_ID:-"your_idp_key_id_here"}
export IDP_KEY_SECRET=${IDP_KEY_SECRET:-"your_idp_key_secret_here"}

echo "=== Tongyi DeepResearch 完整服务启动 ==="
echo ""
echo "注意：此模式启动推理API服务和前端界面，不启动vLLM服务器"
echo "如需完整功能，请先手动启动vLLM服务器"
echo ""
echo "步骤1: 启动推理API服务 (端口 $API_PORT)"
echo "步骤2: 启动前端界面 (端口 $WEB_PORT)"
echo ""

cd "$( dirname -- "${BASH_SOURCE[0]}" )"

# 函数：检查端口是否可用
check_port() {
    local port=$1
    local service_name=$2
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "❌ 端口 $port 已被占用，无法启动 $service_name"
        return 1
    fi
    return 0
}

# 函数：等待API服务启动
wait_for_api() {
    local max_attempts=30
    local attempt=0
    
    echo "⏳ 等待API服务启动..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://localhost:$API_PORT/health >/dev/null 2>&1; then
            echo "✅ API服务启动成功"
            return 0
        fi
        attempt=$((attempt + 1))
        echo "   尝试 $attempt/$max_attempts..."
        sleep 2
    done
    
    echo "❌ API服务启动超时"
    return 1
}

# 检查端口可用性
if ! check_port $API_PORT "API服务"; then
    exit 1
fi

if ! check_port $WEB_PORT "前端服务"; then
    exit 1
fi

# 启动API服务（后台运行）
echo "🚀 启动推理API服务..."
python3 -u api_server.py &
API_PID=$!

# 等待API服务启动
if wait_for_api; then
    echo ""
    echo "🌐 启动前端界面..."
    echo "前端界面将在 http://localhost:$WEB_PORT 上运行"
    echo "API服务运行在 http://localhost:$API_PORT"
    echo ""
    echo "按 Ctrl+C 停止所有服务"
    echo ""
    
    # 启动前端服务
    python3 -u web_server.py &
    WEB_PID=$!
    
    # 等待用户中断
    trap "echo ''; echo '🛑 正在停止服务...'; kill $API_PID $WEB_PID 2>/dev/null; exit 0" INT
    
    # 等待进程结束
    wait
else
    echo "❌ 无法启动前端界面，因为API服务启动失败"
    kill $API_PID 2>/dev/null
    exit 1
fi



