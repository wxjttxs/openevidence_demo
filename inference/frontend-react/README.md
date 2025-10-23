# openEvidence Frontend

基于 React 18 + TypeScript + Vite 的现代化深度研究助手前端界面。

## 特性

- 🚀 **React 18**: 使用最新的 React 特性
- 📘 **TypeScript**: 类型安全的开发体验
- ⚡ **Vite**: 极速的开发服务器和构建工具
- 🎨 **Tailwind CSS**: 现代化的样式系统
- 🎭 **Framer Motion**: 流畅的动画效果
- 💬 **流式响应**: 支持实时流式对话
- 🌈 **科技感设计**: 渐变、光晕、动画等现代UI元素

## 开发

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

### 构建生产版本

```bash
npm run build
```

### 预览生产构建

```bash
npm run preview
```

## 环境变量

创建 `.env` 文件并配置：

```
VITE_API_URL=http://10.27.127.33:5006
WEB_PORT=8088
API_PORT=5006
```

## 项目结构

```
src/
├── components/        # React组件
│   ├── Header.tsx
│   ├── ChatContainer.tsx
│   ├── MessageInput.tsx
│   ├── Message.tsx
│   └── CollapsibleSection.tsx
├── services/         # API服务
│   └── api.ts
├── types.ts          # TypeScript类型定义
├── App.tsx           # 主应用组件
├── main.tsx          # 应用入口
└── index.css         # 全局样式
```

## 技术栈

- **React 18**: UI框架
- **TypeScript**: 类型系统
- **Vite**: 构建工具
- **Tailwind CSS**: CSS框架
- **Framer Motion**: 动画库
- **React Markdown**: Markdown渲染
- **Lucide React**: 图标库
- **Highlight.js**: 代码高亮

