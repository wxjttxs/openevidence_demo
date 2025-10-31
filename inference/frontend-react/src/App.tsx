import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Header from './components/Header'
import ChatContainer from './components/ChatContainer'
import MessageInput from './components/MessageInput'
import CitationPanel from './components/CitationPanel'
import SessionSidebar from './components/SessionSidebar'
import { Message, ConnectionStatus } from './types'
import { checkAPIHealth, sendStreamingChat, createNewSession, getSession } from './services/api'

interface Citation {
  id: number | string
  title: string
  full_content?: string
}

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      type: 'system',
      content: '我是您的循证医学助手，请说出您的问题：',
      timestamp: new Date().toISOString(),
    },
  ])
  const [isProcessing, setIsProcessing] = useState(false)
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [statusText, setStatusText] = useState('正在连接...')
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)

  // 检查API状态并创建初始会话
  useEffect(() => {
    const init = async () => {
      const healthy = await checkAPIHealth()
      if (healthy) {
        setStatus('connected')
        setStatusText('API连接正常')
        
        // 自动创建初始会话
        if (!currentSessionId) {
          try {
            const session = await createNewSession()
            setCurrentSessionId(session.session_id)
          } catch (error) {
            console.error('创建初始会话失败:', error)
          }
        }
      } else {
        setStatus('error')
        setStatusText('无法连接到API服务')
      }
    }
    
    init()
    const interval = setInterval(async () => {
      const healthy = await checkAPIHealth()
      if (healthy) {
        setStatus('connected')
        setStatusText('API连接正常')
      } else {
        setStatus('error')
        setStatusText('无法连接到API服务')
      }
    }, 30000) // 每30秒检查一次
    
    return () => clearInterval(interval)
  }, [currentSessionId])

  // 创建新会话
  const handleNewSession = useCallback(async () => {
    try {
      // 检查当前会话是否有实际问答（排除系统消息）
      const hasActualMessages = messages.some(msg => 
        msg.type === 'user' || msg.type === 'assistant' || msg.type === 'final-answer'
      )
      
      if (!hasActualMessages && currentSessionId) {
        // 如果当前会话没有实际问答，复用当前session_id，只清空消息
        setMessages([
          {
            id: 'welcome',
            type: 'system',
            content: '我是您的循证医学助手，请说出您的问题：',
            timestamp: new Date().toISOString(),
          },
        ])
        return
      }
      
      // 如果有实际问答，创建新会话
      const session = await createNewSession()
      setCurrentSessionId(session.session_id)
      setMessages([
        {
          id: 'welcome',
          type: 'system',
          content: '我是您的循证医学助手，请说出您的问题：',
          timestamp: new Date().toISOString(),
        },
      ])
    } catch (error) {
      console.error('创建新会话失败:', error)
    }
  }, [messages, currentSessionId])

  // 选择会话
  const handleSessionSelect = useCallback(async (sessionId: string) => {
    try {
      setCurrentSessionId(sessionId)
      
      // 加载会话的历史消息
      const sessionData = await getSession(sessionId)
      
      // 将历史消息转换为前端的 Message 格式
      const historyMessages: Message[] = []
      
      // 添加系统欢迎消息
      historyMessages.push({
        id: 'welcome',
        type: 'system',
        content: '我是您的循证医学助手，请说出您的问题：',
        timestamp: sessionData.created_at,
      })
      
      // 转换历史消息
      if (sessionData.messages && sessionData.messages.length > 0) {
        const baseTime = new Date(sessionData.created_at).getTime()
        sessionData.messages.forEach((msg, index) => {
          // 为每条消息分配递增的时间戳（确保顺序正确）
          const messageTime = new Date(baseTime + index * 1000).toISOString()
          
          if (msg.role === 'user') {
            historyMessages.push({
              id: `user-${sessionId}-${index}`,
              type: 'user',
              content: msg.content,
              timestamp: messageTime,
            })
          } else if (msg.role === 'assistant') {
            historyMessages.push({
              id: `assistant-${sessionId}-${index}`,
              type: 'final-answer',
              content: msg.content,
              eventType: 'final-answer',
              isStreaming: false,
              timestamp: messageTime,
            })
          }
        })
      }
      
      setMessages(historyMessages)
    } catch (error) {
      console.error('加载会话历史失败:', error)
      // 如果加载失败，至少切换到该会话并显示欢迎消息
      setMessages([
        {
          id: 'welcome',
          type: 'system',
          content: '我是您的循证医学助手，请说出您的问题：',
          timestamp: new Date().toISOString(),
        },
      ])
    }
  }, [])

  const handleSendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isProcessing) return

    // 添加用户消息
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      type: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    }

    setMessages(prev => [...prev, userMessage])
    setIsProcessing(true)
    setStatus('processing')
    setStatusText('正在处理...')

    try {
      await sendStreamingChat(
        content.trim(),
        (newMessage) => {
          // 调试日志：thinking 消息的状态
          if (newMessage.type === 'thinking') {
            console.log(`📝 Thinking消息更新:`, {
              id: newMessage.id,
              eventType: newMessage.eventType,
              isStreaming: newMessage.isStreaming,
              contentLength: newMessage.content.length
            })
          }
          
          // 调试日志：tool-result 消息
          if (newMessage.type === 'tool-result' || newMessage.eventType === 'tool-result') {
            console.log(`🔧 Tool-result消息:`, {
              id: newMessage.id,
              type: newMessage.type,
              eventType: newMessage.eventType,
              hasMetadata: !!newMessage.metadata,
              metadataKeys: newMessage.metadata ? Object.keys(newMessage.metadata) : [],
              hasResult: !!newMessage.metadata?.result,
              resultLength: newMessage.metadata?.result?.length,
              metadata: newMessage.metadata
            })
          }
          
          setMessages(prev => {
            // 在整个消息列表中查找相同ID的消息
            const existingIndex = prev.findIndex(msg => msg.id === newMessage.id)
            
            if (existingIndex !== -1) {
              // 找到了，更新现有消息
              const updated = [...prev]
              const existingMessage = updated[existingIndex]
              
              // 对于流式消息（增量chunk），需要累积content
              const isStreamingChunk = newMessage.isStreaming && (
                newMessage.eventType === 'judgment-streaming' || 
                newMessage.eventType === 'final-answer'
              )
              
              if (isStreamingChunk) {
                // 累积流式内容：如果后端提供了accumulated字段，使用它；否则追加
                const accumulatedContent = (newMessage as any).accumulated || 
                  (existingMessage.content + newMessage.content)
                
                updated[existingIndex] = {
                  ...newMessage,
                  content: accumulatedContent
                }
              } else {
                // 非流式消息，直接替换
                updated[existingIndex] = newMessage
              }
              
              // 调试：tool-result 更新
              if (newMessage.type === 'tool-result') {
                console.log('🔄 Tool-result 更新现有消息:', existingIndex, newMessage)
              }
              
              return updated
            }
            
            // 没找到，添加新消息
            const newList = [...prev, newMessage]
            
            // 调试：tool-result 添加新消息
            if (newMessage.type === 'tool-result') {
              console.log('➕ Tool-result 添加新消息:', newList.length - 1, {
                id: newMessage.id,
                type: newMessage.type,
                eventType: newMessage.eventType,
                content: newMessage.content,
                hasMetadata: !!newMessage.metadata,
                metadataKeys: newMessage.metadata ? Object.keys(newMessage.metadata) : [],
                metadataResult: newMessage.metadata?.result ? `${newMessage.metadata.result.substring(0, 100)}...` : 'undefined'
              })
            }
            
            return newList
          })
          
          // 检查是否是完成事件（各种结束情况）
          const endEvents = ['final-answer', 'answer_complete', 'no-answer', 'timeout', 'cancelled', 'error']
          if (endEvents.includes(newMessage.eventType || '')) {
            console.log(`📌 收到结束事件: ${newMessage.eventType}，停止处理状态`)
            setIsProcessing(false)  // ← 关键：立即停止处理状态
            setStatus('connected')
            
            // 根据事件类型设置状态文本
            switch (newMessage.eventType) {
              case 'final-answer':
              case 'answer_complete':
                setStatusText('处理完成')
                break
              case 'no-answer':
                setStatusText('推理完成（未找到答案）')
                break
              case 'timeout':
                setStatusText('处理超时')
                break
              case 'cancelled':
                setStatusText('已取消')
                break
              case 'error':
                setStatus('error')
                setStatusText('处理失败')
                break
              default:
                setStatusText('就绪')
            }
          }
        },
        (error) => {
          console.error('Stream error:', error)
          setIsProcessing(false)  // ← 关键：出错时也要停止处理状态
          
          const errorMessage: Message = {
            id: `error-${Date.now()}`,
            type: 'error',
            content: error.message,
            timestamp: new Date().toISOString(),
          }
          setMessages(prev => [...prev, errorMessage])
          
          // 更新状态栏
          setStatus('error')
          if (error.message.includes('无法连接')) {
            setStatusText('API连接失败')
          } else if (error.message.includes('中断')) {
            setStatusText('连接中断')
          } else if (error.message.includes('超时')) {
            setStatusText('请求超时')
          } else {
            setStatusText('处理失败')
          }
        },
        currentSessionId
      )

      // 流式传输完成
      setStatus('connected')
      setStatusText('就绪')
    } catch (error) {
      console.error('Send message error:', error)
      setStatus('error')
      setStatusText('发生异常')
      
      // 显示异常消息
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        type: 'error',
        content: error instanceof Error ? error.message : '发生未知错误',
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsProcessing(false)
    }
  }, [isProcessing])

  const handleCitationClick = useCallback((citation: Citation) => {
    setSelectedCitation(citation)
  }, [])

  const handleCloseCitation = useCallback(() => {
    setSelectedCitation(null)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-dark-900 bg-tech-grid overflow-hidden">
      {/* 背景渐变效果 */}
      <div className="fixed inset-0 bg-gradient-to-br from-primary-900/20 via-purple-900/20 to-pink-900/20 pointer-events-none" />
      <div className="fixed inset-0 bg-gradient-radial from-transparent via-dark-900/50 to-dark-900 pointer-events-none" />
      
      {/* Header - 全宽 */}
      <div className="relative z-10">
        <Header status={status} statusText={statusText} />
      </div>

      {/* 主内容区域 - 使用 flex 布局实现并列显示 */}
      <div className="relative z-10 flex flex-1 overflow-hidden">
        {/* 左侧边栏 - 会话管理 */}
        <SessionSidebar
          currentSessionId={currentSessionId}
          onSessionSelect={handleSessionSelect}
          onNewSession={handleNewSession}
        />
        
        {/* 左侧主内容 - 根据是否有 citation 动态调整宽度 */}
        <motion.div 
          className="flex flex-col h-full bg-dark-900/50 flex-1"
          animate={{
            width: selectedCitation ? 'calc(60% - 16rem)' : 'calc(100% - 16rem)' 
          }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
        >
          <main className="flex-1 overflow-hidden">
            <ChatContainer 
              messages={messages} 
              isProcessing={isProcessing}
              onCitationClick={handleCitationClick}
            />
          </main>

          <div className="border-t border-dark-700/50 bg-dark-800/80 backdrop-blur-sm">
            <MessageInput 
              onSend={handleSendMessage} 
              disabled={isProcessing}
              isProcessing={isProcessing}
            />
          </div>
        </motion.div>

        {/* 右侧引用详情面板 - 并列显示，不遮挡主内容 */}
        <CitationPanel 
          citation={selectedCitation}
          onClose={handleCloseCitation}
        />
      </div>
    </div>
  )
}

export default App

