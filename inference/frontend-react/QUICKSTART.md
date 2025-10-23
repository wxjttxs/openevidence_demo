# 快速入门指南

## 📋 前置要求

1. **Node.js**: 版本 >= 16.0.0
   ```bash
   node --version
   npm --version
   ```

2. **API服务**: 确保API服务在端口5006上运行
   ```bash
   # 在 inference 目录下启动API服务
   ./start_api_only.sh
   ```

## 🚀 快速启动

### 方法1: 使用启动脚本（推荐）

```bash
# 在 inference 目录下
./start_web_only.sh
```

脚本会自动：
- 检查并安装依赖
- 创建环境配置文件
- 启动Vite开发服务器
- 在后台运行（关闭终端不影响）

### 方法2: 手动启动

```bash
cd frontend-react

# 首次运行：安装依赖
npm install

# 创建.env文件
cat > .env << EOF
VITE_API_URL=http://10.27.127.33:5006
WEB_PORT=8088
API_PORT=5006
EOF

# 启动开发服务器
npm run dev
```

## 🌐 访问应用

启动成功后，在浏览器中访问：
```
http://YOUR_IP:8088
```

## 🛑 停止服务

### 使用脚本停止
```bash
# 在 inference 目录下
./stop_web.sh
```

### 手动停止
```bash
# 方法1: 使用PID文件
kill $(cat web_server.pid)

# 方法2: 终止端口占用的进程
kill $(lsof -ti:8088)
```

## 📦 生产部署

### 1. 构建生产版本
```bash
cd frontend-react
npm run build
```

构建完成后，`dist/` 目录包含优化后的静态文件。

### 2. 使用Nginx部署

安装Nginx并配置：

```nginx
server {
    listen 8088;
    server_name your_domain.com;

    root /path/to/DeepResearch-openevidence/inference/frontend-react/dist;
    index index.html;

    # 处理单页应用路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API代理
    location /api/ {
        proxy_pass http://localhost:5006/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 3. 使用预览服务器（简单部署）
```bash
cd frontend-react
npm run preview
```

## 🔧 常见问题

### Q1: 端口8088已被占用
```bash
# 查看占用端口的进程
lsof -ti:8088

# 杀死进程
kill $(lsof -ti:8088)

# 或者修改端口
export WEB_PORT=8089
./start_web_only.sh
```

### Q2: API连接失败
检查：
1. API服务是否在运行：`lsof -ti:5006`
2. 防火墙设置
3. `.env`文件中的`VITE_API_URL`是否正确

### Q3: npm安装依赖失败
```bash
# 清理npm缓存
npm cache clean --force

# 删除node_modules重新安装
rm -rf node_modules package-lock.json
npm install
```

### Q4: 编译错误
```bash
# 检查Node.js版本（需要>=16）
node --version

# 升级依赖
npm update
```

## 📊 性能优化建议

### 开发环境
- 使用Chrome DevTools的React Developer Tools
- 启用React StrictMode（已默认开启）

### 生产环境
- 启用Gzip/Brotli压缩
- 配置CDN加速静态资源
- 使用HTTP/2
- 启用浏览器缓存

## 🎨 自定义配置

### 修改主题颜色
编辑 `tailwind.config.js`:
```js
theme: {
  extend: {
    colors: {
      primary: {
        // 自定义主色调
      }
    }
  }
}
```

### 修改API地址
编辑 `.env`:
```
VITE_API_URL=http://your-api-server:5006
```

## 📝 开发模式特性

- 🔥 **热模块替换(HMR)**: 代码修改实时更新
- 🎯 **TypeScript**: 类型检查和智能提示
- 🎨 **Tailwind CSS**: 快速样式开发
- 🎭 **Framer Motion**: 流畅动画效果
- 📱 **响应式设计**: 自适应各种屏幕尺寸

## 🔗 相关链接

- [React文档](https://react.dev)
- [Vite文档](https://vitejs.dev)
- [Tailwind CSS文档](https://tailwindcss.com)
- [Framer Motion文档](https://www.framer.com/motion)

