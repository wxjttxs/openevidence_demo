#!/bin/bash
# 加载 .env 文件中的环境变量
set -a  # 自动导出所有变量
source .env
set +a  # 关闭自动导出
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
export WEB_PORT=${WEB_PORT:-8088}

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
echo "注意：此模式启动推理API服务，不启动vLLM服务器"
echo "如需完整功能，请先手动启动vLLM服务器"
echo ""
echo "步骤1: 启动推理API服务 (端口 $API_PORT)"
echo ""

cd "$( dirname -- "${BASH_SOURCE[0]}" )"

# 定义日志和PID文件路径
LOG_FILE="./logs/api_server.log"
PID_FILE="./api_server.pid"

# 创建日志目录
mkdir -p logs

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

# 检查是否已有服务在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 $OLD_PID 2>/dev/null; then
        echo "❌ API服务已在运行 (PID: $OLD_PID)"
        echo "   如需重启，请先运行: ./stop_api.sh"
        exit 1
    else
        # PID文件存在但进程已死，清理旧文件
        rm -f "$PID_FILE"
    fi
fi

# 检查端口可用性
if ! check_port $API_PORT "API服务"; then
    exit 1
fi

# 启动API服务（后台守护进程）
echo "🚀 启动推理API服务..."
echo "   日志文件: $LOG_FILE"

# 使用 nohup 启动服务，输出重定向到日志文件
nohup python3 -u api_server.py > "$LOG_FILE" 2>&1 &
API_PID=$!

# 保存PID到文件
echo $API_PID > "$PID_FILE"

# 等待API服务启动
if wait_for_api; then
    echo ""
    echo "✅ API服务启动成功！"
    echo "   PID: $API_PID"
    echo "   端口: $API_PORT"
    echo "   访问地址: http://$(hostname -I | awk '{print $1}'):$API_PORT"
    echo "   日志文件: $LOG_FILE"
    echo ""
    echo "服务已在后台运行，关闭终端不影响服务"
    echo ""
    echo "查看日志: tail -f $LOG_FILE"
    echo "停止服务: ./stop_api.sh 或 kill \$(cat $PID_FILE)"
    echo ""
else
    echo "❌ API服务启动失败，请查看日志: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
