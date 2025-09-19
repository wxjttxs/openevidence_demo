// 应用配置
const CONFIG = {
    API_BASE_URL: 'http://localhost:5006',
    MAX_MESSAGE_LENGTH: 4000,
    TYPING_SPEED: 30, // 毫秒
    AUTO_SCROLL_DELAY: 100
};

// 全局状态
let isProcessing = false;
let currentStream = null;

// DOM 元素
const elements = {
    chatMessages: document.getElementById('chatMessages'),
    messageInput: document.getElementById('messageInput'),
    sendButton: document.getElementById('sendButton'),
    charCount: document.getElementById('charCount'),
    statusIndicator: document.getElementById('statusIndicator'),
    statusText: document.getElementById('statusText'),
    loadingOverlay: document.getElementById('loadingOverlay'),
    welcomeTime: document.getElementById('welcomeTime')
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    checkAPIStatus();
});

function initializeApp() {
    // 设置欢迎消息时间
    elements.welcomeTime.textContent = new Date().toLocaleTimeString();
    
    // 设置输入框自动调整高度
    elements.messageInput.addEventListener('input', autoResizeTextarea);
    
    // 设置字符计数
    elements.messageInput.addEventListener('input', updateCharCount);
    
    // 设置发送按钮状态
    elements.messageInput.addEventListener('input', updateSendButton);
}

function setupEventListeners() {
    // 发送按钮点击
    elements.sendButton.addEventListener('click', sendMessage);
    
    // 输入框键盘事件
    elements.messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // 自动滚动
    const observer = new MutationObserver(autoScroll);
    observer.observe(elements.chatMessages, { childList: true });
}

function autoResizeTextarea() {
    const textarea = elements.messageInput;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

function updateCharCount() {
    const count = elements.messageInput.value.length;
    elements.charCount.textContent = `${count}/${CONFIG.MAX_MESSAGE_LENGTH}`;
    
    if (count > CONFIG.MAX_MESSAGE_LENGTH * 0.9) {
        elements.charCount.style.color = '#ef4444';
    } else if (count > CONFIG.MAX_MESSAGE_LENGTH * 0.7) {
        elements.charCount.style.color = '#f59e0b';
    } else {
        elements.charCount.style.color = '#64748b';
    }
}

function updateSendButton() {
    const hasText = elements.messageInput.value.trim().length > 0;
    const canSend = hasText && !isProcessing;
    elements.sendButton.disabled = !canSend;
}

async function checkAPIStatus() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/health`);
        if (response.ok) {
            updateStatus('connected', 'API连接正常');
        } else {
            updateStatus('error', 'API服务异常');
        }
    } catch (error) {
        updateStatus('error', '无法连接到API服务');
    }
}

function updateStatus(type, text) {
    elements.statusIndicator.className = `status-indicator ${type}`;
    elements.statusText.textContent = text;
}

async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message || isProcessing) return;
    
    // 添加用户消息
    addMessage('user', message);
    
    // 清空输入框
    elements.messageInput.value = '';
    autoResizeTextarea();
    updateCharCount();
    updateSendButton();
    
    // 开始处理
    isProcessing = true;
    updateStatus('warning', '正在处理...');
    elements.loadingOverlay.style.display = 'flex';
    
    try {
        await streamChat(message);
    } catch (error) {
        console.error('发送消息失败:', error);
        addMessage('error', `发送失败: ${error.message}`);
        updateStatus('error', '处理失败');
    } finally {
        isProcessing = false;
        elements.loadingOverlay.style.display = 'none';
        updateSendButton();
        checkAPIStatus();
    }
}

async function streamChat(message) {
    const response = await fetch(`${CONFIG.API_BASE_URL}/chat/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            question: message,
            temperature: 0.85,
            top_p: 0.95,
            presence_penalty: 1.1,
            max_tokens: 10000
        })
    });
    
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentMessageElement = null;
    
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // 保留最后一个不完整的行
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        currentMessageElement = handleStreamEvent(data, currentMessageElement);
                    } catch (e) {
                        console.warn('解析流数据失败:', e, line);
                    }
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}

function handleStreamEvent(event, currentElement) {
    const { type, content, timestamp, round, tool_name, tool_args, result, code } = event;
    
    switch (type) {
        case 'init':
            return addMessage('assistant', content, 'init');
            
        case 'round_start':
            return addMessage('assistant', content, 'round-start', { round });
            
        case 'thinking_start':
            return addMessage('thinking', '正在思考...', 'thinking-start');
            
        case 'thinking':
            return updateMessage(currentElement, content, 'thinking');
            
        case 'tool_call_start':
            return addMessage('tool-call', content, 'tool-call-start');
            
        case 'tool_execution':
            return addMessage('tool-call', content, 'tool-execution', { tool_name, tool_args });
            
        case 'python_execution':
            return addMessage('python-exec', content, 'python-execution', { code });
            
        case 'tool_result':
            return addMessage('tool-result', content, 'tool-result', { result });
            
        case 'tool_error':
            return addMessage('error', content, 'tool-error');
            
        case 'final_answer':
            return addMessage('final-answer', content, 'final-answer');
            
        case 'completed':
            updateStatus('connected', '处理完成');
            return currentElement;
            
        case 'error':
            updateStatus('error', '处理出错');
            return addMessage('error', content, 'error');
            
        case 'timeout':
            updateStatus('error', '处理超时');
            return addMessage('error', content, 'timeout');
            
        case 'token_limit':
            return addMessage('assistant', content, 'token-limit');
            
        case 'no_answer':
            return addMessage('assistant', content, 'no-answer');
            
        default:
            console.log('未知事件类型:', type, event);
            return currentElement;
    }
}

function addMessage(type, content, eventType = '', metadata = {}) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${type}`;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    const messageHeader = document.createElement('div');
    messageHeader.className = 'message-header';
    
    const messageType = document.createElement('span');
    messageType.className = 'message-type';
    messageType.textContent = getMessageTypeText(type, eventType);
    
    const messageTime = document.createElement('span');
    messageTime.className = 'message-time';
    messageTime.textContent = new Date().toLocaleTimeString();
    
    messageHeader.appendChild(messageType);
    messageHeader.appendChild(messageTime);
    
    const messageText = document.createElement('div');
    messageText.className = 'message-text';
    
    // 根据消息类型设置内容
    if (type === 'tool-call' && metadata.tool_name) {
        messageText.innerHTML = createToolCallContent(metadata.tool_name, metadata.tool_args);
    } else if (type === 'python-exec' && metadata.code) {
        messageText.innerHTML = createPythonExecutionContent(metadata.code);
    } else if (type === 'tool-result' && metadata.result) {
        messageText.innerHTML = createToolResultContent(metadata.result);
    } else {
        messageText.innerHTML = formatContent(content);
    }
    
    messageContent.appendChild(messageHeader);
    messageContent.appendChild(messageText);
    messageElement.appendChild(messageContent);
    
    elements.chatMessages.appendChild(messageElement);
    
    return messageElement;
}

function updateMessage(messageElement, content, type) {
    if (!messageElement) return null;
    
    const messageText = messageElement.querySelector('.message-text');
    if (messageText) {
        if (type === 'thinking') {
            messageText.innerHTML = formatContent(content);
        } else {
            messageText.innerHTML += formatContent(content);
        }
    }
    
    return messageElement;
}

function getMessageTypeText(type, eventType) {
    const typeMap = {
        'user': '👤 用户',
        'assistant': '🤖 助手',
        'thinking': '💭 思考中',
        'tool-call': '🛠️ 工具调用',
        'tool-result': '✅ 工具结果',
        'python-exec': '🐍 Python执行',
        'error': '❌ 错误',
        'final-answer': '🎯 最终答案',
        'init': '🚀 初始化',
        'round-start': '🔄 推理轮次',
        'thinking-start': '💭 开始思考',
        'tool-call-start': '🛠️ 准备工具',
        'tool-execution': '⚙️ 执行工具',
        'python-execution': '🐍 执行代码',
        'tool-error': '❌ 工具错误',
        'timeout': '⏰ 超时',
        'token-limit': '📊 Token限制',
        'no-answer': '❓ 无答案'
    };
    
    return typeMap[eventType] || typeMap[type] || '📝 消息';
}

function formatContent(content) {
    // 处理换行
    content = content.replace(/\n/g, '<br>');
    
    // 处理代码块
    content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const language = lang || 'text';
        return `<div class="code-block"><pre><code class="language-${language}">${escapeHtml(code.trim())}</code></pre></div>`;
    });
    
    // 处理行内代码
    content = content.replace(/`([^`]+)`/g, '<code style="background: #f1f5f9; padding: 0.2em 0.4em; border-radius: 4px; font-family: monospace;">$1</code>');
    
    // 处理链接
    content = content.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" style="color: #667eea; text-decoration: underline;">$1</a>');
    
    return content;
}

function createToolCallContent(toolName, toolArgs) {
    const argsStr = JSON.stringify(toolArgs, null, 2);
    return `
        <div class="tool-call-details">
            <div class="tool-name">工具: ${toolName}</div>
            <div class="tool-args">参数:\n${argsStr}</div>
        </div>
    `;
}

function createPythonExecutionContent(code) {
    return `
        <div class="collapsible" onclick="toggleCollapsible(this)">
            <div class="collapsible-header">
                <span class="collapsible-icon">▶</span>
                <span>Python代码执行</span>
            </div>
            <div class="collapsible-content">
                <div class="code-block">
                    <pre><code class="language-python">${escapeHtml(code)}</code></pre>
                </div>
            </div>
        </div>
    `;
}

function createToolResultContent(result) {
    return `
        <div class="collapsible" onclick="toggleCollapsible(this)">
            <div class="collapsible-header">
                <span class="collapsible-icon">▶</span>
                <span>查看结果</span>
            </div>
            <div class="collapsible-content">
                <div style="background: #f8fafc; padding: 0.75rem; border-radius: 8px; font-family: monospace; font-size: 0.9rem; white-space: pre-wrap; max-height: 300px; overflow-y: auto;">
                    ${escapeHtml(result)}
                </div>
            </div>
        </div>
    `;
}

function toggleCollapsible(element) {
    element.classList.toggle('expanded');
    const content = element.querySelector('.collapsible-content');
    if (content) {
        content.classList.toggle('expanded');
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function autoScroll() {
    setTimeout(() => {
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    }, CONFIG.AUTO_SCROLL_DELAY);
}

// 全局函数
window.toggleCollapsible = toggleCollapsible;
