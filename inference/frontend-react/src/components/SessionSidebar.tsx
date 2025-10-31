import { useState, useEffect } from 'react'
import { Plus, MessageSquare, Clock } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface Session {
  session_id: string
  created_at: string
  message_count: number
}

interface SessionSidebarProps {
  currentSessionId: string | null
  onSessionSelect: (sessionId: string) => void
  onNewSession: () => void
}

export default function SessionSidebar({ 
  currentSessionId, 
  onSessionSelect, 
  onNewSession 
}: SessionSidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(false)

  // 加载会话列表
  const loadSessions = async () => {
    try {
      setLoading(true)
      const response = await fetch('http://10.27.127.33:5006/api/sessions')
      const data = await response.json()
      // 过滤掉没有消息的会话（message_count为0）
      const sessionsWithMessages = (data.sessions || []).filter(
        (session: Session) => session.message_count > 0
      )
      setSessions(sessionsWithMessages)
    } catch (error) {
      console.error('加载会话列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSessions()
    // 每30秒刷新一次会话列表
    const interval = setInterval(loadSessions, 30000)
    return () => clearInterval(interval)
  }, [])

  const formatTime = (isoString: string) => {
    const date = new Date(isoString)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  return (
    <div className="w-64 bg-dark-800 border-r border-dark-700 flex flex-col h-full">
      {/* 新建会话按钮 - 添加顶部margin避免被Header遮挡 */}
      <div className="p-4 pt-20 border-b border-dark-700">
        <button
          onClick={onNewSession}
          className="w-full flex items-center justify-center space-x-2 px-4 py-3 bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors font-medium"
        >
          <Plus className="w-5 h-5" />
          <span>新建会话</span>
        </button>
      </div>

      {/* 会话历史 */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-4">
          <h3 className="text-sm font-semibold text-dark-400 mb-3">会话历史</h3>
          
          {loading && (
            <div className="text-center py-8 text-dark-500">加载中...</div>
          )}

          {!loading && sessions.length === 0 && (
            <div className="text-center py-8 text-dark-500 text-sm">
              暂无会话历史
            </div>
          )}

          <AnimatePresence>
            {sessions.map((session) => (
              <motion.div
                key={session.session_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                onClick={() => onSessionSelect(session.session_id)}
                className={`p-3 mb-2 rounded-lg cursor-pointer transition-all ${
                  currentSessionId === session.session_id
                    ? 'bg-primary-600/20 border border-primary-500/50'
                    : 'bg-dark-700/50 hover:bg-dark-700 border border-transparent'
                }`}
              >
                <div className="flex items-start space-x-2">
                  <MessageSquare className={`w-4 h-4 mt-0.5 ${
                    currentSessionId === session.session_id 
                      ? 'text-primary-400' 
                      : 'text-dark-500'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-xs font-mono truncate ${
                        currentSessionId === session.session_id
                          ? 'text-primary-300'
                          : 'text-dark-400'
                      }`}>
                        {session.session_id.substring(0, 8)}...
                      </span>
                    </div>
                    <div className="flex items-center space-x-2 text-xs text-dark-500">
                      <Clock className="w-3 h-3" />
                      <span>{formatTime(session.created_at)}</span>
                      {session.message_count > 0 && (
                        <>
                          <span>•</span>
                          <span>{session.message_count}条消息</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

