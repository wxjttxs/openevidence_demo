import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Header from './components/Header'
import ChatContainer from './components/ChatContainer'
import MessageInput from './components/MessageInput'
import CitationPanel from './components/CitationPanel'
import { Message, ConnectionStatus } from './types'
import { checkAPIHealth, sendStreamingChat } from './services/api'

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
      content: `欢迎使用 openEvidence 深度研究系统！

我可以帮助您进行深度研究，包括：

🔍 专业的医疗知识库搜索
📊 数据分析与可视化
🧠 智能推理与决策支持

请提出您的问题，我将为您进行深度研究并提供详细答案。`,
      timestamp: new Date().toISOString(),
    },
  ])
  const [isProcessing, setIsProcessing] = useState(false)
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [statusText, setStatusText] = useState('正在连接...')
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null)

  // 检查API状态
  useEffect(() => {
    const checkHealth = async () => {
      const healthy = await checkAPIHealth()
      if (healthy) {
        setStatus('connected')
        setStatusText('API连接正常')
      } else {
        setStatus('error')
        setStatusText('无法连接到API服务')
      }
    }
    
    checkHealth()
    const interval = setInterval(checkHealth, 30000) // 每30秒检查一次
    
    return () => clearInterval(interval)
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
        }
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
        {/* 左侧主内容 - 根据是否有 citation 动态调整宽度 */}
        <motion.div 
          className="flex flex-col h-full bg-dark-900/50"
          animate={{ 
            width: selectedCitation ? '60%' : '100%' 
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

