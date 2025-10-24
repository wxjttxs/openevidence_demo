import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import { getCitationDetail } from '../services/api'
import 'highlight.js/styles/tokyo-night-dark.css'
import 'katex/dist/katex.min.css'

interface Citation {
  id: number | string
  title: string
  full_content?: string
}

interface CitationPanelProps {
  citation: Citation | null
  sessionId?: string  // 保留但不使用，为了兼容性
  onClose: () => void
}

export default function CitationPanel({ citation, onClose }: CitationPanelProps) {
  const [fullContent, setFullContent] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  // 当 citation 变化时，加载完整内容
  useEffect(() => {
    if (!citation) {
      setFullContent('')
      setError('')
      return
    }

    const loadFullContent = async () => {
      setLoading(true)
      setError('')
      try {
        console.log('📡 获取引用详情:', { citationId: citation.id })
        let content = await getCitationDetail(citation.id)
        
        // 修复数字范围中的波浪号（避免被 Markdown 解析为删除线）
        // 将 "14~17" 这样的格式转换为 "14-17"
        content = content.replace(/(\d+)\s*~\s*(\d+)/g, '$1-$2')
        
        setFullContent(content)
      } catch (err) {
        console.error('获取引用详情失败:', err)
        setError(err instanceof Error ? err.message : '获取引用详情失败')
      } finally {
        setLoading(false)
      }
    }

    loadFullContent()
  }, [citation])
  return (
    <AnimatePresence>
      {citation && (
        <motion.div
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: '40%', opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="h-full bg-dark-800 shadow-2xl flex flex-col border-l border-dark-700 overflow-hidden"
        >
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-dark-700">
              <div className="flex items-center space-x-3">
                <div className="w-2 h-2 bg-primary-500 rounded-full animate-pulse" />
                <h2 className="text-lg font-semibold text-dark-50">
                  参考文献详情
                </h2>
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-dark-700 rounded-lg transition-colors text-dark-400 hover:text-dark-50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* 引用编号 */}
              <div className="inline-flex items-center px-3 py-1 bg-primary-500/20 border border-primary-500/30 rounded-full">
                <span className="text-primary-400 font-mono font-semibold">
                  [{citation.id}]
                </span>
              </div>

              {/* 文章标题 */}
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-dark-400 uppercase tracking-wide">
                  文章标题
                </h3>
                <p className="text-base font-semibold text-dark-50 leading-relaxed">
                  {citation.title}
                </p>
              </div>

              {/* 分隔线 */}
              <div className="h-px bg-gradient-to-r from-transparent via-dark-600 to-transparent" />

              {/* 完整内容 */}
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-dark-400 uppercase tracking-wide">
                  参考内容
                </h3>
                <div className="bg-dark-900/50 rounded-lg p-4 border border-dark-700">
                  {loading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-6 h-6 text-primary-400 animate-spin" />
                      <span className="ml-2 text-dark-400">加载中...</span>
                    </div>
                  ) : error ? (
                    <div className="text-red-400 text-sm">
                      <p className="font-semibold mb-1">⚠️ 加载失败</p>
                      <p>{error}</p>
                    </div>
                  ) : (
                    <div className="prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex, rehypeHighlight]}
                        components={{
                          // 链接在新标签页打开
                          a: ({ node, ...props }) => (
                            <a {...props} target="_blank" rel="noopener noreferrer" className="text-primary-400 hover:text-primary-300" />
                          ),
                          // 代码块样式
                          code: ({ node, className, children, ...props }) => {
                            const match = /language-(\w+)/.exec(className || '')
                            const inline = !match
                            return inline ? (
                              <code className="bg-dark-800 text-primary-400 px-1.5 py-0.5 rounded text-xs" {...props}>
                                {children}
                              </code>
                            ) : (
                              <code className={className} {...props}>
                                {children}
                              </code>
                            )
                          },
                          // 表格样式
                          table: ({ node, ...props }) => (
                            <div className="overflow-x-auto">
                              <table className="min-w-full divide-y divide-dark-700" {...props} />
                            </div>
                          ),
                          th: ({ node, ...props }) => (
                            <th className="px-3 py-2 bg-dark-800 text-left text-xs font-semibold text-dark-300" {...props} />
                          ),
                          td: ({ node, ...props }) => (
                            <td className="px-3 py-2 text-sm text-dark-200 border-t border-dark-700" {...props} />
                          ),
                        }}
                      >
                        {fullContent || '暂无内容'}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-dark-700 bg-dark-900/50">
              <button
                onClick={onClose}
                className="w-full py-2 px-4 bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors font-medium"
              >
                关闭
              </button>
            </div>
          </motion.div>
      )}
    </AnimatePresence>
  )
}

