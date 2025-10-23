export interface StreamEvent {
  type: string;
  content: string;
  timestamp?: string;
  session_id?: string; // 会话ID
  round?: number;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  result?: string;
  code?: string;
  judgment?: {
    can_answer: boolean;
    confidence: number;
    reason: string;
    missing_info?: string;
  };
  answer_data?: {
    answer: string;
    citations?: Citation[];
  };
  accumulated?: string; // 流式答案累积内容
  is_streaming?: boolean; // 是否正在流式生成
}

export interface Citation {
  id: string;
  full_content: string;
  preview: string;
}

export interface Message {
  id: string;
  type: 'user' | 'assistant' | 'thinking' | 'tool-call' | 'tool-result' | 'error' | 'final-answer' | 'answer-streaming' | 'system';
  content: string;
  timestamp: string;
  sessionId?: string; // 会话ID
  metadata?: {
    round?: number;
    tool_name?: string;
    tool_args?: Record<string, unknown>;
    result?: string;
    code?: string;
    judgment?: StreamEvent['judgment'];
    answer_data?: StreamEvent['answer_data'];
  };
  eventType?: string;
  isStreaming?: boolean; // 标记是否正在流式生成
}

export type ConnectionStatus = 'connected' | 'disconnected' | 'error' | 'processing';

