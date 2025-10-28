import { motion } from 'framer-motion'
import { User, Bot, Lightbulb, Wrench, CheckCircle, XCircle, Target, AlertCircle, FileText } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import { Message as MessageType } from '../types'
import CollapsibleSection from './CollapsibleSection'
import 'highlight.js/styles/tokyo-night-dark.css'
import 'katex/dist/katex.min.css'

interface Citation {
  id: number | string
  title: string
  full_content?: string
  preview?: string
}

interface MessageProps {
  message: MessageType
  onCitationClick: (citation: Citation) => void
}

const messageIcons = {
  user: User,
  assistant: Bot,
  thinking: Lightbulb,
  'tool-call': Wrench,
  'tool-result': CheckCircle,
  error: XCircle,
  'final-answer': Target,
  system: AlertCircle,
}

const messageColors = {
  user: 'from-primary-600/20 to-purple-600/20 border-primary-500/30',
  assistant: 'from-dark-700/50 to-dark-800/50 border-dark-600/30',
  thinking: 'from-yellow-600/20 to-orange-600/20 border-yellow-500/30',
  'tool-call': 'from-blue-600/20 to-cyan-600/20 border-blue-500/30',
  'tool-result': 'from-green-600/20 to-emerald-600/20 border-green-500/30',
  error: 'from-red-600/20 to-pink-600/20 border-red-500/30',
  'final-answer': 'from-purple-600/20 to-pink-600/20 border-purple-500/30',
  system: 'from-dark-700/50 to-dark-800/50 border-dark-600/30',
}

const messageLabels: Record<string, string> = {
  user: '用户',
  assistant: '助手',
  thinking: '思考中',
  'tool-call': '工具调用',
  'tool-result': '工具结果',
  error: '错误',
  'final-answer': '最终答案',
  'answer-streaming': '正在生成答案',
  system: '系统',
  init: '初始化',
  'round-start': '推理轮次开始',
  'round-end': '推理轮次结束',
  'thinking-start': '开始思考',
  'tool-call-start': '准备工具',
  'tool-execution': '执行工具',
  'python-execution': 'Python执行',
  'tool-error': '工具错误',
  timeout: '超时',
  'token-limit': 'Token限制',
  'no-answer': '无答案',
  'cancelled': '已取消',
  'retrieval-judgment': '检索判断',
  'judgment-streaming': '判断结果',
  'judgment-result': '判断结果',
  'judgment-error': '判断错误',
  'answer-generation': '生成答案',
  'continue-reasoning': '继续推理',
}

export default function MessageComponent({ message, onCitationClick }: MessageProps) {
  // 调试：检查 tool-result 类型的消息
  if (message.type === 'tool-result' || message.eventType === 'tool-result') {
    console.log('[DEBUG] MessageComponent received tool-result:', {
      type: message.type,
      eventType: message.eventType,
      hasMetadata: !!message.metadata,
      hasResult: !!message.metadata?.result,
      resultLength: message.metadata?.result?.length,
      metadata: JSON.stringify(message.metadata).substring(0, 200)
    })
  }
  
  const Icon = messageIcons[message.type] || Bot
  const colorClass = messageColors[message.type] || messageColors.assistant
  
  // 动态计算 label：thinking 类型根据 isStreaming 状态显示不同文本
  let label = messageLabels[message.eventType || ''] || messageLabels[message.type] || '消息'
  if (message.type === 'thinking') {
    label = message.isStreaming ? '思考中' : '思考结束'
  }

  const formatTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    } catch {
      return ''
    }
  }

  const renderContent = () => {
    // 工具调用
    if (message.metadata?.tool_name) {
      return (
        <CollapsibleSection title={`工具: ${message.metadata.tool_name}`}>
          <div className="bg-dark-900/50 rounded-lg p-4">
            <div className="text-sm text-dark-300 font-mono">
              <pre className="overflow-x-auto">
                {JSON.stringify(message.metadata.tool_args, null, 2)}
              </pre>
            </div>
          </div>
        </CollapsibleSection>
      )
    }

    // Python代码执行
    if (message.metadata?.code) {
      return (
        <CollapsibleSection title="Python代码执行">
          <div className="bg-dark-900/50 rounded-lg overflow-hidden">
            <pre className="p-4 overflow-x-auto">
              <code className="language-python text-sm">
                {message.metadata.code}
              </code>
            </pre>
          </div>
        </CollapsibleSection>
      )
    }

    // 工具结果（检索结果等）- 强制渲染
    if (message.type === 'tool-result' || message.eventType === 'tool-result') {
      console.log('🔧 [TOOL-RESULT] 开始渲染工具结果卡片:', { 
        type: message.type, 
        eventType: message.eventType,
        content: message.content,
        hasMetadata: !!message.metadata,
        hasResult: !!message.metadata?.result,
        resultLength: message.metadata?.result?.length,
        resultPreview: message.metadata?.result?.substring(0, 200)
      })
      
      // 始终显示内容，无论是否有 result
      return (
        <div className="space-y-3">
          <p className="text-dark-200 font-medium">{message.content || '检索完成'}</p>
          {message.metadata?.result && (
            <CollapsibleSection title="查看详细检索结果" defaultExpanded={false}>
              <div className="bg-dark-900/50 rounded-lg p-4 max-h-96 overflow-y-auto">
                <pre className="text-sm text-dark-300 whitespace-pre-wrap font-mono leading-relaxed">
                  {message.metadata.result}
                </pre>
              </div>
            </CollapsibleSection>
          )}
        </div>
      )
    }

    // 流式判断结果（优雅渲染）
    if (message.eventType === 'judgment-streaming') {
      // 清理内容：移除JSON部分，只保留友好文本
      let cleanContent = message.content
      const jsonMatch = cleanContent.match(/\{[\s\S]*"can_answer"[\s\S]*\}/)
      if (jsonMatch) {
        cleanContent = cleanContent.substring(0, jsonMatch.index).trim()
      }
      
      // 处理文本：将"**分析**:"后的内容用小字体显示
      const processContent = (content: string) => {
        // 匹配 **分析**: 后面的所有内容
        const analysisMatch = content.match(/(\*\*分析\*\*:\s*)([\s\S]*)/)
        if (analysisMatch) {
          const beforeAnalysis = content.substring(0, analysisMatch.index! + analysisMatch[1].length)
          const analysisContent = analysisMatch[2]
          
          return (
            <>
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeHighlight, rehypeKatex]}
              >
                {beforeAnalysis}
              </ReactMarkdown>
              <div className="text-sm text-dark-300 mt-1">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeHighlight, rehypeKatex]}
                >
                  {analysisContent}
                </ReactMarkdown>
              </div>
            </>
          )
        }
        
        return (
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeHighlight, rehypeKatex]}
          >
            {content}
          </ReactMarkdown>
        )
      }
      
      return (
        <div className="space-y-3">
          <div className="prose prose-invert max-w-none">
            {processContent(cleanContent)}
          </div>
          {message.isStreaming && (
            <span className="inline-block w-2 h-5 bg-blue-400 animate-pulse ml-1" />
          )}
        </div>
      )
    }

    // 判断结果（结构化显示）
    if (message.metadata?.judgment) {
      const { judgment } = message.metadata
      return (
        <div className="space-y-3">
          <p className="text-dark-200">{message.content}</p>
          <CollapsibleSection 
            title={`检索内容评估完成: ${judgment.can_answer ? '✅ 可以回答' : '❌ 无法回答'} (置信度: ${Math.round(judgment.confidence * 100)}%)`}
            defaultExpanded={false}
          >
            <div className="bg-dark-900/50 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between p-3 bg-dark-800/50 rounded-lg">
                <span className="text-dark-400 font-medium">能否回答:</span>
                <span className={`font-bold text-lg ${judgment.can_answer ? 'text-green-400' : 'text-red-400'}`}>
                  {judgment.can_answer ? '是 ✓' : '否 ✗'}
                </span>
              </div>
              
              <div className="flex items-center justify-between p-3 bg-dark-800/50 rounded-lg">
                <span className="text-dark-400 font-medium">置信度:</span>
                <div className="flex items-center space-x-3">
                  <div className="w-32 h-2 bg-dark-700 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-primary-500 to-purple-500 rounded-full transition-all"
                      style={{ width: `${Math.round(judgment.confidence * 100)}%` }}
                    />
                  </div>
                  <span className="text-primary-400 font-bold text-lg">
                    {Math.round(judgment.confidence * 100)}%
                  </span>
                </div>
              </div>
              
              <div className="p-3 bg-dark-800/50 rounded-lg">
                <span className="text-dark-400 font-medium block mb-2">原因:</span>
                <p className="text-dark-200 leading-relaxed">{judgment.reason}</p>
              </div>
              
              {judgment.missing_info && (
                <div className="p-3 bg-yellow-900/20 border border-yellow-500/30 rounded-lg">
                  <span className="text-yellow-400 font-medium block mb-2">⚠️ 缺失信息:</span>
                  <p className="text-yellow-200 leading-relaxed">{judgment.missing_info}</p>
                </div>
              )}
            </div>
          </CollapsibleSection>
        </div>
      )
    }

    // 最终答案（Markdown渲染）
    if (message.type === 'final-answer') {
      // 提取答案主体和引用列表
      const citations = message.metadata?.answer_data?.citations || []
      
      // 从content中移除"参考文献:"部分（如果存在）
      let answerContent = message.content
      const refIndex = answerContent.indexOf('\n\n参考文献:')
      if (refIndex !== -1) {
        answerContent = answerContent.substring(0, refIndex)
      }
      
      // 修复数字范围中的波浪号（避免被 Markdown 解析为删除线）
      // 将 "14~17" 这样的格式转换为 "14-17"，避免渲染问题
      answerContent = answerContent.replace(/(\d+)\s*~\s*(\d+)/g, '$1-$2')
      
      return (
        <div className="space-y-6">
          {/* 答案主体 */}
          <div className="markdown prose prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex, rehypeHighlight]}
              components={{
                a: ({ node, ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" className="text-primary-400 hover:text-primary-300" />
                ),
                code: ({ node, className, children, ...props }) => {
                  const match = /language-(\w+)/.exec(className || '')
                  return match ? (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  ) : (
                    <code className="bg-dark-800 text-primary-400 px-1.5 py-0.5 rounded text-sm" {...props}>
                      {children}
                    </code>
                  )
                },
              }}
            >
              {answerContent}
            </ReactMarkdown>
            {/* 如果正在流式生成，显示闪烁光标 */}
            {message.isStreaming && (
              <motion.span
                animate={{ opacity: [1, 0, 1] }}
                transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
                className="inline-block w-2 h-5 ml-1 bg-primary-500 rounded-sm align-middle"
              />
            )}
          </div>

          {/* 引用列表 - 有citations时立即显示（不等待任何条件） */}
          {citations.length > 0 && (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="border-t border-dark-700 pt-6"
            >
              <h3 className="text-lg font-semibold text-dark-50 mb-4 flex items-center">
                <FileText className="w-5 h-5 mr-2 text-primary-400" />
                参考文献
              </h3>
              <div className="space-y-4">
                {citations.map((citation: any, index: number) => {
                  // 使用后端提供的 preview 字段（前30字）
                  const preview = citation.preview || ''
                  return (
                    <motion.div
                      key={citation.id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: index * 0.05 }}
                      whileHover={{ scale: 1.02 }}
                      className="group bg-dark-800/50 rounded-lg p-4 border border-dark-700 hover:border-primary-500/50 transition-all cursor-pointer"
                      onClick={() => onCitationClick({
                        id: citation.id,
                        title: citation.title,
                      })}
                    >
                      {/* 文章标题 */}
                      <div className="flex items-start space-x-3 mb-2">
                        <span className="inline-flex items-center justify-center px-2 py-0.5 bg-primary-500/20 border border-primary-500/30 rounded text-primary-400 font-mono text-xs font-semibold">
                          [{citation.id}]
                        </span>
                        <h4 className="text-base font-semibold text-dark-50 leading-tight flex-1">
                          {citation.title}
                        </h4>
                      </div>
                      {/* 参考片段（前30字，比标题小两号） */}
                      <p className="text-xs text-dark-400 leading-relaxed pl-9">
                        {preview}{preview.length >= 30 ? '...' : ''}
                      </p>
                      {/* 点击提示 */}
                      <div className="text-xs text-primary-400 pl-9 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        点击查看完整内容 →
                      </div>
                    </motion.div>
                  )
                })}
              </div>
            </motion.div>
          )}
        </div>
      )
    }

    // 对于流式答案，添加打字效果
    if (message.eventType === 'answer-streaming') {
      return (
        <div className="text-dark-200 whitespace-pre-wrap">
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex, rehypeHighlight]}
            components={{
              code: ({ inline, children, ...props }: any) => (
                inline ? (
                  <code className="bg-dark-800 px-1.5 py-0.5 rounded text-primary-400 font-mono text-sm" {...props}>
                    {children}
                  </code>
                ) : (
                  <pre className="bg-dark-900 p-4 rounded-lg overflow-x-auto my-2">
                    <code className="text-primary-300 font-mono text-sm" {...props}>
                      {children}
                    </code>
                  </pre>
                )
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
          {/* 闪烁光标 */}
          <motion.span
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
            className="inline-block w-2 h-5 ml-1 bg-primary-500 rounded-sm"
          />
        </div>
      )
    }
    
    // 默认文本内容
    // 对于错误消息，使用特殊样式
    if (message.type === 'error') {
      return (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
          <div className="text-red-200 whitespace-pre-wrap font-mono text-sm leading-relaxed">
            {message.content}
          </div>
        </div>
      )
    }
    
    // 对于thinking消息
    if (message.type === 'thinking') {
      // 流式生成中：直接显示，带光标
      if (message.isStreaming) {
        return (
          <div className="text-dark-200 whitespace-pre-wrap">
            {message.content}
            {/* 流式thinking中显示闪烁光标 */}
            <motion.span
              animate={{ opacity: [1, 0, 1] }}
              transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
              className="inline-block w-2 h-5 ml-1 bg-yellow-500 rounded-sm align-middle"
            />
          </div>
        )
      }
      
      // 生成完成：使用折叠组件，默认折叠
      return (
        <CollapsibleSection 
          title="查看完整思考过程" 
          defaultExpanded={false}
        >
          <div className="bg-dark-900/50 rounded-lg p-4">
            <div className="text-dark-200 whitespace-pre-wrap leading-relaxed">
              {message.content}
            </div>
          </div>
        </CollapsibleSection>
      )
    }
    
    return (
      <div className="text-dark-200 whitespace-pre-wrap">
        {message.content}
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`relative rounded-2xl border backdrop-blur-sm overflow-hidden bg-gradient-to-br ${colorClass} ${
        message.type === 'user' ? 'max-w-2xl' : ''
      }`}
    >
      {/* 背景光晕效果 */}
      {message.type === 'final-answer' && !message.isStreaming && (
        <div className="absolute inset-0 bg-gradient-to-br from-purple-500/10 via-transparent to-pink-500/10 pointer-events-none" />
      )}
      
      {/* 流式生成时的微光效果 - 适用于 final-answer、answer-streaming 和 thinking */}
      {(message.isStreaming || message.eventType === 'answer-streaming') && (
        <motion.div
          animate={{ opacity: [0.3, 0.6, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
          className={`absolute inset-0 bg-gradient-to-r from-transparent to-transparent pointer-events-none ${
            message.type === 'thinking' 
              ? 'via-yellow-500/10' 
              : 'via-primary-500/10'
          }`}
        />
      )}

      <div className="relative p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-3">
            <motion.div
              initial={{ rotate: 0 }}
              animate={{ rotate: message.type === 'thinking' ? 360 : 0 }}
              transition={{ duration: 2, repeat: message.type === 'thinking' ? Infinity : 0, ease: 'linear' }}
              className={`p-2 rounded-xl bg-gradient-to-br ${
                message.type === 'user' 
                  ? 'from-primary-500 to-purple-500' 
                  : message.type === 'error'
                  ? 'from-red-500 to-pink-500'
                  : message.type === 'final-answer'
                  ? 'from-purple-500 to-pink-500'
                  : 'from-dark-600 to-dark-700'
              }`}
            >
              <Icon className="w-5 h-5 text-white" />
            </motion.div>
            <div>
              <div className="text-sm font-semibold text-dark-200">
                {label}
                {message.metadata?.round && (
                  <span className="ml-2 text-primary-400">#{message.metadata.round}</span>
                )}
              </div>
              <div className="text-xs text-dark-500">
                {formatTime(message.timestamp)}
              </div>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="pl-0">
          {renderContent()}
        </div>
      </div>
    </motion.div>
  )
}

