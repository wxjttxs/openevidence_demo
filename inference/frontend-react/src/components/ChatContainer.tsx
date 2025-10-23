import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import MessageComponent from './Message'
import { Message } from '../types'

interface Citation {
  id: number | string
  title: string
  full_content?: string
}

interface ChatContainerProps {
  messages: Message[]
  isProcessing: boolean
  onCitationClick: (citation: Citation) => void
}

export default function ChatContainer({ messages, isProcessing, onCitationClick }: ChatContainerProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-4 py-6"
    >
      <div className="max-w-4xl mx-auto space-y-6">
        <AnimatePresence initial={false}>
          {messages.map((message, index) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{
                duration: 0.3,
                delay: index === messages.length - 1 ? 0 : 0,
              }}
            >
              <MessageComponent message={message} onCitationClick={onCitationClick} />
            </motion.div>
          ))}
        </AnimatePresence>

        {isProcessing && messages.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center space-x-3 px-6 py-3 bg-dark-800/50 rounded-xl border border-primary-500/30"
          >
            <div className="flex space-x-1">
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 0.6, repeat: Infinity, delay: 0 }}
                className="w-2 h-2 bg-primary-500 rounded-full"
              />
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 0.6, repeat: Infinity, delay: 0.2 }}
                className="w-2 h-2 bg-primary-500 rounded-full"
              />
              <motion.div
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 0.6, repeat: Infinity, delay: 0.4 }}
                className="w-2 h-2 bg-primary-500 rounded-full"
              />
            </div>
            <span className="text-sm text-primary-400 font-medium">任务执行中...</span>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}

