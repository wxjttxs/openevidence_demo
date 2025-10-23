#!/bin/bash

# 停止前端服务脚本

cd "$( dirname -- "${BASH_SOURCE[0]}" )"

PID_FILE="./web_server.pid"
WEB_PORT=${WEB_PORT:-8088}

echo "🛑 停止前端服务..."

# 从PID文件读取进程ID
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    
    if kill -0 $PID 2>/dev/null; then
        echo "   找到运行中的服务 (PID: $PID)"
        
        # 优雅停止
        echo "   发送终止信号..."
        kill -TERM $PID 2>/dev/null
        
        # 等待进程结束
        for i in {1..10}; do
            if ! kill -0 $PID 2>/dev/null; then
                echo "✅ 服务已停止"
                rm -f "$PID_FILE"
                exit 0
            fi
            sleep 1
        done
        
        # 如果还没停止，强制杀死
        echo "   进程未响应，强制终止..."
        kill -9 $PID 2>/dev/null
        sleep 1
        
        if ! kill -0 $PID 2>/dev/null; then
            echo "✅ 服务已强制停止"
            rm -f "$PID_FILE"
        else
            echo "❌ 无法停止进程"
            exit 1
        fi
    else
        echo "   进程不存在，清理PID文件"
        rm -f "$PID_FILE"
    fi
else
    echo "   未找到PID文件"
    
    # 尝试通过端口查找进程
    PORT_PID=$(lsof -ti:$WEB_PORT 2>/dev/null)
    if [ ! -z "$PORT_PID" ]; then
        echo "   发现端口 $WEB_PORT 被进程 $PORT_PID 占用"
        read -p "   是否停止该进程? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill -9 $PORT_PID
            echo "✅ 进程已停止"
        fi
    else
        echo "   没有发现运行中的前端服务"
    fi
fi

