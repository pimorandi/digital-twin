import type { Message } from '../types/chat'

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? 'bg-blue-600 text-white'
            : message.status === 'error'
              ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'
              : 'bg-gray-200 text-gray-900 dark:bg-gray-800 dark:text-gray-100'
        }`}
      >
        {message.text}
        {message.status === 'streaming' && (
          <span className="ml-0.5 inline-block w-1.5 animate-pulse">▍</span>
        )}
      </div>
    </div>
  )
}
