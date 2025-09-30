#!/bin/bash

# Tongyi DeepResearch 交互式Web界面启动脚本

# 信号处理函数
cleanup() {
    echo -e "\n正在清理进程..."
    pkill -f "vllm serve" || true
    pkill -f "web_interface.py" || true
    echo "清理完成"
    exit 0
}

# 注册信号处理器
trap cleanup SIGINT SIGTERM

export TORCHDYNAMO_VERBOSE=1
export TORCHDYNAMO_DISABLE=1
export NCCL_IB_TC=16
export NCCL_IB_SL=5
export NCCL_IB_GID_INDEX=3
export NCCL_SOCKET_IFNAME=eth
export NCCL_DEBUG=INFO
export NCCL_IB_HCA=mlx5
export NCCL_IB_TIMEOUT=22
export NCCL_IB_QPS_PER_CONNECTION=8
export NCCL_MIN_NCHANNELS=4
export NCCL_NET_PLUGIN=none
export GLOO_SOCKET_IFNAME=eth0

## autodetect active interface and override defaults
IFACE=$(ip route get 1.1.1.1 2>/dev/null | awk '/dev/ {for(i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')
if [ -z "$IFACE" ]; then
    IFACE=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(eth|en|eno|ens|enp)' | head -n1)
fi
if [ -n "$IFACE" ]; then
    export GLOO_SOCKET_IFNAME="$IFACE"
    export NCCL_SOCKET_IFNAME="$IFACE"
fi

export QWEN_DOC_PARSER_USE_IDP=false
export QWEN_IDP_ENABLE_CSI=false
export NLP_WEB_SEARCH_ONLY_CACHE=false
export NLP_WEB_SEARCH_ENABLE_READPAGE=false
export NLP_WEB_SEARCH_ENABLE_SFILTER=false
export QWEN_SEARCH_ENABLE_CSI=false
export SPECIAL_CODE_MODE=false
export PYTHONDONTWRITEBYTECODE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

##############hyperparams################
export MODEL_PATH=/mnt/data6t/wangxiaojing/models/opensource_models/Alibaba-NLP/Tongyi-DeepResearch-30B-A3B
export TEMPERATURE=0.85 
export PRESENCE_PENALTY=1.1
export TOP_P=0.95

# Web界面端口
export WEB_PORT=8086

# vLLM服务器配置
VLLM_ARGS="--gpu-memory-utilization 0.6"
SERVER_GPUS=${SERVER_GPUS:-"2,3,4,5"}

# 检查GPU内存使用情况
echo "Checking GPU memory usage..."
nvidia-smi --query-gpu=index,memory.free,memory.total --format=csv,noheader,nounits | while read line; do
    gpu_id=$(echo $line | cut -d',' -f1 | tr -d ' ')
    free_mem=$(echo $line | cut -d',' -f2 | tr -d ' ')
    total_mem=$(echo $line | cut -d',' -f3 | tr -d ' ')
    echo "GPU $gpu_id: ${free_mem}MB free / ${total_mem}MB total"
done




######################################
### 1. 清理现有进程并启动vLLM服务器    ###
######################################

# 清理可能存在的vLLM进程
echo "Cleaning up existing vLLM processes..."
pkill -f "vllm serve" || true
sleep 2

echo "Starting VLLM servers with args: $VLLM_ARGS"
IFS=',' read -ra GPU_LIST <<< "$SERVER_GPUS"
num_gpus=${#GPU_LIST[@]}
base_port=6001
# 加载conda的初始化脚本
source ~/anaconda3/etc/profile.d/conda.sh  # 或者你的conda安装路径

# 激活conda环境
conda activate react_infer_env
if [ $num_gpus -gt 1 ]; then
    # 多GPU张量并行
    tp_size=$num_gpus
    echo "Launching vLLM with tensor parallel across GPUs: ${GPU_LIST[*]}"
    CUDA_VISIBLE_DEVICES=$(IFS=','; echo "${GPU_LIST[*]}") \
    vllm serve $MODEL_PATH --host 0.0.0.0 --port $base_port --tensor-parallel-size $tp_size --disable-log-requests $VLLM_ARGS &
    export PLANNING_PORTS="$base_port"
    echo "Launched single vLLM with TP=$tp_size on GPUs ${GPU_LIST[*]} at port $base_port"
else
    # 单GPU或多个单GPU实例
    idx=0
    for gpu in "${GPU_LIST[@]}"; do
        port=$((base_port + idx))
        echo "Launching vLLM on GPU $gpu at port $port"
        CUDA_VISIBLE_DEVICES=$gpu vllm serve $MODEL_PATH --host 0.0.0.0 --port $port --disable-log-requests $VLLM_ARGS &
        idx=$((idx + 1))
    done
    # 导出端口用于Python端
    ports=()
    for ((i=0; i<num_gpus; i++)); do ports+=($((base_port + i))); done
    export PLANNING_PORTS="$(IFS=','; echo "${ports[*]}")"
fi

# 等待一下让vLLM进程启动
sleep 3

#######################################################
### 2. 等待服务器端口准备就绪                        ###
#######################################################

timeout=600  # 10分钟超时
start_time=$(date +%s)

IFS=',' read -ra PORT_ARR <<< "$PLANNING_PORTS"
main_ports=("${PORT_ARR[@]}")
num_servers=${#main_ports[@]}
echo "Mode: ${num_servers} port(s) used as main model: $PLANNING_PORTS"

declare -A server_status
for port in "${main_ports[@]}"; do
    server_status[$port]=false
done

echo "Waiting for vLLM servers to start..."

while true; do
    all_ready=true
    
    for port in "${main_ports[@]}"; do
        if [ "${server_status[$port]}" = "false" ]; then
            if curl -s -f http://localhost:$port/v1/models > /dev/null 2>&1; then
                echo "vLLM server (port $port) is ready!"
                server_status[$port]=true
            else
                all_ready=false
            fi
        fi
    done
    
    if [ "$all_ready" = "true" ]; then
        echo "All vLLM servers are ready!"
        break
    fi
    
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    if [ $elapsed -gt $timeout ]; then
        echo -e "\nError: vLLM server startup timeout after ${timeout} seconds"
        
        for port in "${main_ports[@]}"; do
            if [ "${server_status[$port]}" = "false" ]; then
                echo "vLLM server (port $port) failed to start"
            fi
        done
        
        exit 1
    fi
    
    printf 'Waiting for vLLM servers to start .....'
    sleep 5
done

failed_servers=()
for port in "${main_ports[@]}"; do
    if [ "${server_status[$port]}" = "false" ]; then

    
        failed_servers+=($port)
    fi
done

if [ ${#failed_servers[@]} -gt 0 ]; then
    echo "Error: The following vLLM servers failed to start: ${failed_servers[*]}"
    exit 1
else
    echo "All required vLLM servers are running successfully!"
fi
