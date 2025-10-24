import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Loader2 } from 'lucide-react'
import { getCitationDetail } from '../services/api'

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
        const content = await getCitationDetail(citation.id)
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
                    <p className="text-dark-200 leading-relaxed whitespace-pre-wrap font-mono text-sm">
                      {fullContent || '暂无内容'}
                    </p>
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

