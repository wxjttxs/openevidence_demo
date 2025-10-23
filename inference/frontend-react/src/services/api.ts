import { StreamEvent, Message } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://10.27.127.33:5006'

export async function checkAPIHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
    })
    return response.ok
  } catch (error) {
    console.error('Health check failed:', error)
    return false
  }
}

export async function sendStreamingChat(
  question: string,
  onMessage: (message: Message) => void,
  onError: (error: Error) => void
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        temperature: 0.85,
        top_p: 0.95,
        presence_penalty: 1.1,
        max_tokens: 10000,
      }),
    })

    if (!response.ok) {
      // 根据HTTP状态码提供更详细的错误信息
      let errorMessage = ''
      switch (response.status) {
        case 400:
          errorMessage = '请求参数错误，请检查输入内容'
          break
        case 401:
          errorMessage = 'API认证失败，请检查授权配置'
          break
        case 403:
          errorMessage = '没有访问权限，请联系管理员'
          break
        case 404:
          errorMessage = 'API接口不存在，请检查API服务版本'
          break
        case 500:
          errorMessage = 'API服务内部错误，请查看服务器日志'
          break
        case 502:
          errorMessage = 'API网关错误，请检查API服务是否正常运行'
          break
        case 503:
          errorMessage = 'API服务暂时不可用，请稍后重试'
          break
        case 504:
          errorMessage = 'API请求超时，请稍后重试'
          break
        default:
          errorMessage = `API返回错误 (HTTP ${response.status}): ${response.statusText}`
      }
      throw new Error(errorMessage)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('无法读取响应流，浏览器可能不支持流式传输')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let currentMessageId: string | null = null
    let hasCompleted = false
    let hasFinalAnswer = false  // 标记是否已收到最终答案

    try {
      let chunkCount = 0
      while (true) {
        const { done, value } = await reader.read()
        chunkCount++
        
        if (done) {
          console.log(`✅ Stream 读取完成 (共 ${chunkCount} 个chunk)`, { hasCompleted })
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data: StreamEvent = JSON.parse(line.slice(6))
              
              // 标记是否收到最终答案
              if (data.type === 'final_answer') {
                hasFinalAnswer = true
              }
              
              // 如果已经有最终答案，忽略后续的 error 事件（避免重复错误卡片）
              if (data.type === 'error' && hasFinalAnswer) {
                console.log('⚠️ 已有最终答案，忽略error事件:', data.content)
                continue  // 跳过这个 error 事件
              }
              
              // 标记是否收到完成事件（包括所有结束情况）
              const endEventTypes = ['completed', 'error', 'timeout', 'no_answer', 'cancelled']
              if (endEventTypes.includes(data.type)) {
                console.log(`📌 收到完成事件: ${data.type}`, data.content)
                hasCompleted = true
              }
              
              const message = handleStreamEvent(data, currentMessageId)
              if (message) {
                currentMessageId = message.id
                onMessage(message)
              }
            } catch (e) {
              console.warn('流数据解析失败:', e, line)
            }
          }
        }
      }
      
      // 检查流是否正常完成
      if (!hasCompleted) {
        console.warn('流未正常完成：未收到 completed 或 error 事件')
      }
      
    } catch (readError) {
      console.error('读取流时发生错误:', readError)
      
      // 如果已经收到completed事件，说明流正常结束，忽略后续的读取错误
      if (hasCompleted) {
        console.log('流已正常完成，忽略后续读取错误')
        return
      }
      
      // 如果是流被中断，抛出更友好的错误信息
      if (readError instanceof TypeError && readError.message.includes('network')) {
        throw new Error('网络连接中断，请检查网络或稍后重试')
      }
      throw readError
    } finally {
      reader.releaseLock()
    }
  } catch (error) {
    // 区分不同类型的错误
    if (error instanceof TypeError) {
      // 网络错误
      if (error.message.includes('fetch') || error.message.includes('Failed to fetch')) {
        const networkError = new Error(
          `无法连接到API服务 (${API_BASE_URL})\n` +
          '可能原因：\n' +
          '1. API服务未启动（请运行 ./start_api_only.sh）\n' +
          '2. 端口配置错误（检查 .env 文件）\n' +
          '3. 防火墙阻止连接\n' +
          '4. 网络连接问题'
        )
        onError(networkError)
      } else {
        onError(new Error(`类型错误: ${error.message}`))
      }
    } else if (error instanceof SyntaxError) {
      // JSON解析错误
      onError(new Error('响应数据格式错误，API可能返回了无效的数据'))
    } else if (error instanceof Error) {
      // 其他已知错误
      onError(error)
    } else {
      // 未知错误
      onError(new Error('发生未知错误，请查看浏览器控制台了解详情'))
    }
  }
}

function handleStreamEvent(event: StreamEvent, currentMessageId: string | null): Message | null {
  const { type, content, timestamp, session_id, round, tool_name, tool_args, result, code, judgment, answer_data, accumulated, is_streaming } = event

  const baseMessage = {
    id: currentMessageId || `msg-${Date.now()}-${Math.random()}`,
    timestamp: timestamp || new Date().toISOString(),
    sessionId: session_id, // 保存 session_id
  }

  switch (type) {
    case 'init':
      return {
        ...baseMessage,
        id: `init-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'init',
      }

    case 'round_start':
      return {
        ...baseMessage,
        id: `round-${round}-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'round-start',
        metadata: { round },
      }

    case 'round_end':
      return {
        ...baseMessage,
        id: `round-end-${round}-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'round-end',
        metadata: { round },
      }

    case 'thinking_start':
      return {
        ...baseMessage,
        id: `thinking-${Date.now()}`,
        type: 'thinking',
        content: '正在思考...',
        eventType: 'thinking-start',
      }

    case 'thinking':
      return {
        ...baseMessage,
        type: 'thinking',
        content,
        eventType: 'thinking',
      }

    case 'tool_call_start':
      return {
        ...baseMessage,
        id: `tool-call-${Date.now()}`,
        type: 'tool-call',
        content,
        eventType: 'tool-call-start',
      }

    case 'tool_execution':
      return {
        ...baseMessage,
        id: `tool-exec-${Date.now()}`,
        type: 'tool-call',
        content,
        eventType: 'tool-execution',
        metadata: { tool_name, tool_args },
      }

    case 'python_execution':
      return {
        ...baseMessage,
        id: `python-${Date.now()}`,
        type: 'tool-call',
        content,
        eventType: 'python-execution',
        metadata: { code },
      }

    case 'tool_result':
      return {
        ...baseMessage,
        id: `result-${Date.now()}`,
        type: 'tool-result',
        content,
        eventType: 'tool-result',
        metadata: { result },
      }

    case 'tool_error':
      return {
        ...baseMessage,
        id: `error-${Date.now()}`,
        type: 'error',
        content,
        eventType: 'tool-error',
      }

    case 'retrieval_judgment':
      return {
        ...baseMessage,
        id: `judgment-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'retrieval-judgment',
      }

    case 'judgment_result':
      return {
        ...baseMessage,
        id: `judgment-result-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'judgment-result',
        metadata: { judgment },
      }

    case 'judgment_error':
      return {
        ...baseMessage,
        id: `error-${Date.now()}`,
        type: 'error',
        content,
        eventType: 'judgment-error',
      }

    case 'answer_generation':
      return {
        ...baseMessage,
        id: `answer-gen-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'answer-generation',
      }

    case 'continue_reasoning':
      return {
        ...baseMessage,
        id: `continue-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'continue-reasoning',
      }

    case 'final_answer_chunk':
      // 流式最终答案片段 - 直接使用final-answer样式渲染
      return {
        ...baseMessage,
        id: currentMessageId || 'final-answer', // 使用固定ID
        type: 'final-answer',
        content: content, // 直接使用content（已是累积内容）
        eventType: 'final-answer',
        isStreaming: is_streaming !== false, // 标记为流式中
      }

    case 'answer_streaming':
      // 流式答案片段 - 使用固定ID以便更新同一条消息
      return {
        ...baseMessage,
        id: currentMessageId || 'streaming-answer', // 使用固定ID，所有流式片段更新同一条消息
        type: 'answer-streaming',
        content: accumulated || content, // 使用累积内容
        eventType: 'answer-streaming',
        isStreaming: true, // 标记为流式中
      }

    case 'final_answer':
      // 最终答案 - 使用相同的ID更新流式消息
      return {
        ...baseMessage,
        id: currentMessageId || 'final-answer', // 使用相同的固定ID
        type: 'final-answer',
        content,
        eventType: 'final-answer',
        metadata: { answer_data },
      }

    case 'completed':
      return null

    case 'error':
      return {
        ...baseMessage,
        id: `error-${Date.now()}`,
        type: 'error',
        content,
        eventType: 'error',
      }

    case 'timeout':
      return {
        ...baseMessage,
        id: `timeout-${Date.now()}`,
        type: 'error',
        content,
        eventType: 'timeout',
      }

    case 'token_limit':
      return {
        ...baseMessage,
        id: `limit-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'token-limit',
      }

    case 'no_answer':
      return {
        ...baseMessage,
        id: `no-answer-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'no-answer',
      }

    case 'cancelled':
      return {
        ...baseMessage,
        id: `cancelled-${Date.now()}`,
        type: 'assistant',
        content,
        eventType: 'cancelled',
      }

    default:
      console.log('Unknown event type:', type, event)
      return null
  }
}

/**
 * 获取引用的完整内容（公共接口）
 * @param citationId - 引用ID
 * @returns 完整的引用内容
 */
export async function getCitationDetail(
  citationId: string | number
): Promise<string> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/citation/${citationId}`,
      {
        method: 'GET',
      }
    )

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('引用内容不存在或会话已过期')
      }
      throw new Error(`获取引用详情失败 (HTTP ${response.status})`)
    }

    const data = await response.json()
    return data.full_content || ''
  } catch (error) {
    console.error('获取引用详情失败:', error)
    if (error instanceof Error) {
      throw error
    }
    throw new Error('获取引用详情失败，请稍后重试')
  }
}

