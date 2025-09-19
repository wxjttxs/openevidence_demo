#!/usr/bin/env python3
"""
前端Web服务器
端口: 8086
功能: 提供前端界面文件
"""

import os
import http.server
import socketserver
import webbrowser
from pathlib import Path

# 配置
WEB_PORT = int(os.getenv('WEB_PORT', 8086))
FRONTEND_DIR = Path(__file__).parent / 'frontend'

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)
    
    def end_headers(self):
        # 添加CORS头
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_GET(self):
        # 如果请求根路径，返回index.html
        if self.path == '/':
            self.path = '/index.html'
        return super().do_GET()

def start_web_server():
    """启动Web服务器"""
    print(f"🌐 启动前端Web服务器...")
    print(f"📁 前端目录: {FRONTEND_DIR}")
    print(f"🔗 访问地址: http://localhost:{WEB_PORT}")
    print()
    
    # 检查前端目录是否存在
    if not FRONTEND_DIR.exists():
        print(f"❌ 前端目录不存在: {FRONTEND_DIR}")
        return
    
    # 检查index.html是否存在
    index_file = FRONTEND_DIR / 'index.html'
    if not index_file.exists():
        print(f"❌ index.html文件不存在: {index_file}")
        return
    
    try:
        with socketserver.TCPServer(("", WEB_PORT), CustomHTTPRequestHandler) as httpd:
            print(f"✅ Web服务器启动成功，端口: {WEB_PORT}")
            print(f"🌐 请在浏览器中访问: http://localhost:{WEB_PORT}")
            print("按 Ctrl+C 停止服务器")
            print()
            
            # 尝试自动打开浏览器
            try:
                webbrowser.open(f'http://localhost:{WEB_PORT}')
                print("🚀 已自动打开浏览器")
            except Exception as e:
                print(f"⚠️  无法自动打开浏览器: {e}")
            
            httpd.serve_forever()
            
    except OSError as e:
        if e.errno == 98:  # Address already in use
            print(f"❌ 端口 {WEB_PORT} 已被占用，请检查是否有其他服务在使用该端口")
        else:
            print(f"❌ 启动Web服务器失败: {e}")
    except KeyboardInterrupt:
        print("\n🛑 Web服务器已停止")

if __name__ == "__main__":
    start_web_server()
