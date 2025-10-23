#!/bin/bash

# 前端Web界面启动脚本 - React + TypeScript版本
cd "$( dirname -- "${BASH_SOURCE[0]}" )"

# 加载环境变量
if [ -f .env ]; then
    source .env
fi

# Web界面端口
export WEB_PORT=${WEB_PORT:-8088}
export API_PORT=${API_PORT:-5006}

# 前端目录
FRONTEND_DIR="./frontend-react"
PID_FILE="./web_server.pid"

echo "=== openEvidence 前端服务启动 ==="
echo ""
echo "注意：此脚本仅启动前端界面"
echo "请确保API服务已在端口 $API_PORT 上运行"
echo ""
echo "前端端口: $WEB_PORT"
echo "API端口: $API_PORT"
echo ""

# 检查frontend-react目录是否存在
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ 前端目录不存在: $FRONTEND_DIR"
    exit 1
fi

cd "$FRONTEND_DIR"

# 检查是否已安装依赖
if [ ! -d "node_modules" ]; then
    echo "📦 首次运行，正在安装依赖..."
    echo ""
    
    # 检查npm是否安装
    if ! command -v npm &> /dev/null; then
        echo "❌ 未找到npm，请先安装Node.js"
        exit 1
    fi
    
    npm install
    
    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败"
        exit 1
    fi
    
    echo ""
    echo "✅ 依赖安装完成"
    echo ""
fi

# 创建.env文件（如果不存在）
if [ ! -f ".env" ]; then
    echo "📝 创建.env配置文件..."
    cat > .env << EOF
VITE_API_URL=http://$(hostname -I | awk '{print $1}'):${API_PORT}
WEB_PORT=${WEB_PORT}
API_PORT=${API_PORT}
EOF
fi

# 清理旧的PID文件
if [ -f "../$PID_FILE" ]; then
    OLD_PID=$(cat "../$PID_FILE")
    if kill -0 $OLD_PID 2>/dev/null; then
        echo "⚠️  发现运行中的前端服务 (PID: $OLD_PID)"
        read -p "是否停止并重启? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill $OLD_PID 2>/dev/null
            sleep 2
        else
            exit 0
        fi
    fi
    rm -f "../$PID_FILE"
fi

# 检查端口是否被占用
if lsof -Pi :$WEB_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "❌ 端口 $WEB_PORT 已被占用"
    exit 1
fi

echo "🚀 启动前端开发服务器..."
echo ""

# 启动Vite开发服务器（后台运行）
WEB_PORT=$WEB_PORT npm run dev > ../logs/web_server.log 2>&1 &
WEB_PID=$!

# 保存PID
echo $WEB_PID > "../$PID_FILE"

# 等待服务启动
sleep 3

# 检查进程是否还在运行
if kill -0 $WEB_PID 2>/dev/null; then
    echo "✅ 前端服务启动成功！"
    echo ""
    echo "   PID: $WEB_PID"
    echo "   端口: $WEB_PORT"
    echo "   访问地址: http://$(hostname -I | awk '{print $1}'):$WEB_PORT"
    echo "   日志文件: ../logs/web_server.log"
    echo ""
    echo "服务已在后台运行，关闭终端不影响服务"
    echo ""
    echo "查看日志: tail -f logs/web_server.log"
    echo "停止服务: kill $WEB_PID 或 kill \$(cat ../$PID_FILE)"
    echo ""
else
    echo "❌ 前端服务启动失败，请查看日志: ../logs/web_server.log"
    rm -f "../$PID_FILE"
    exit 1
fi



