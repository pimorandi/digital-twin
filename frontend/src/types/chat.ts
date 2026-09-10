export type MessageRole = 'user' | 'assistant'

export type MessageStatus = 'complete' | 'streaming' | 'error'

export interface Message {
  id: string
  role: MessageRole
  text: string
  status: MessageStatus
}

export type ConnectionStatus = 'idle' | 'sending' | 'streaming' | 'error'
