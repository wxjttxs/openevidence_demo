import { motion } from 'framer-motion'
import { Brain, Circle } from 'lucide-react'
import { ConnectionStatus } from '../types'

interface HeaderProps {
  status: ConnectionStatus
  statusText: string
}

const statusConfig = {
  connected: {
    color: 'bg-green-500',
    textColor: 'text-green-400',
    pulse: true,
  },
  disconnected: {
    color: 'bg-gray-500',
    textColor: 'text-gray-400',
    pulse: false,
  },
  error: {
    color: 'bg-red-500',
    textColor: 'text-red-400',
    pulse: false,
  },
  processing: {
    color: 'bg-yellow-500',
    textColor: 'text-yellow-400',
    pulse: true,
  },
}

export default function Header({ status, statusText }: HeaderProps) {
  const config = statusConfig[status]

  return (
    <header className="border-b border-dark-700/50 bg-dark-800/80 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center space-x-3"
          >
            <div className="relative">
              <motion.div
                animate={{
                  rotate: 360,
                }}
                transition={{
                  duration: 20,
                  repeat: Infinity,
                  ease: "linear",
                }}
                className="absolute inset-0 bg-gradient-to-r from-primary-500 to-purple-500 rounded-xl blur-lg opacity-50"
              />
              <div className="relative bg-gradient-to-br from-primary-600 to-purple-600 p-2 rounded-xl">
                <Brain className="w-6 h-6 text-white" />
              </div>
            </div>
            <div>
              <h1 className="text-xl font-bold text-gradient">
                openEvidence
              </h1>
              <p className="text-xs text-dark-400">深度研究助手</p>
            </div>
          </motion.div>

          {/* Status */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center space-x-2"
          >
            <div className="relative">
              <Circle
                className={`w-3 h-3 ${config.color} rounded-full ${
                  config.pulse ? 'animate-pulse' : ''
                }`}
                fill="currentColor"
              />
              {config.pulse && (
                <motion.div
                  animate={{
                    scale: [1, 2, 2],
                    opacity: [0.5, 0, 0],
                  }}
                  transition={{
                    duration: 2,
                    repeat: Infinity,
                  }}
                  className={`absolute inset-0 ${config.color} rounded-full`}
                />
              )}
            </div>
            <span className={`text-sm font-medium ${config.textColor}`}>
              {statusText}
            </span>
          </motion.div>
        </div>
      </div>
    </header>
  )
}

