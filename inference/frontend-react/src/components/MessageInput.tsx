import { useState, useRef, KeyboardEvent } from 'react'
import { motion } from 'framer-motion'
import { Send } from 'lucide-react'

interface MessageInputProps {
  onSend: (message: string) => void
  disabled: boolean
  isProcessing: boolean
}

const MAX_LENGTH = 4000

export default function MessageInput({ onSend, disabled, isProcessing }: MessageInputProps) {
  const [message, setMessage] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message)
      setMessage('')
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value)
    // 自动调整高度
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  const charCount = message.length
  const charPercentage = (charCount / MAX_LENGTH) * 100

  return (
    <div className="max-w-4xl mx-auto w-full p-4">
      <div className="relative">
        {/* 输入框背景效果 */}
        <div className="absolute inset-0 bg-gradient-to-r from-primary-600/20 to-purple-600/20 rounded-2xl blur-xl" />
        
        <div className="relative bg-dark-800/90 backdrop-blur-sm rounded-2xl border border-dark-700/50 shadow-2xl">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="请输入您的问题..."
            disabled={disabled}
            maxLength={MAX_LENGTH}
            rows={1}
            className="w-full px-6 py-4 pr-14 bg-transparent text-dark-50 placeholder-dark-500 resize-none focus:outline-none"
            style={{ minHeight: '56px', maxHeight: '120px' }}
          />

          {/* 发送按钮 */}
          <motion.button
            whileHover={{ scale: disabled ? 1 : 1.05 }}
            whileTap={{ scale: disabled ? 1 : 0.95 }}
            onClick={handleSend}
            disabled={disabled || !message.trim()}
            className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-xl bg-gradient-to-r from-primary-600 to-purple-600 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
          >
            <Send className="w-5 h-5" />
          </motion.button>
        </div>

        {/* 底部信息 */}
        <div className="flex items-center justify-between mt-2 px-2 text-xs text-dark-500">
          <span className="flex items-center space-x-2">
            <kbd className="px-2 py-1 bg-dark-800 rounded border border-dark-700">Enter</kbd>
            <span>发送</span>
            <kbd className="px-2 py-1 bg-dark-800 rounded border border-dark-700">Shift + Enter</kbd>
            <span>换行</span>
          </span>
          <span className={charPercentage > 90 ? 'text-red-400' : charPercentage > 70 ? 'text-yellow-400' : ''}>
            {charCount}/{MAX_LENGTH}
          </span>
        </div>
      </div>

      {/* 移除输入框下方的处理提示，统一在消息流中显示 */}
    </div>
  )
}

