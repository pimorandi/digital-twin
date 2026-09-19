import { useChatStream } from '../hooks/useChatStream'
import ErrorBanner from './ErrorBanner'
import LoggingNotice from './LoggingNotice'
import MessageInput from './MessageInput'
import MessageList from './MessageList'

export default function ChatWindow() {
  const { messages, connectionStatus, errorMessage, sendMessage } = useChatStream()
  const disabled = connectionStatus === 'sending' || connectionStatus === 'streaming'

  return (
    <div className="flex h-svh w-full max-w-2xl flex-col bg-white shadow-sm dark:bg-gray-900 sm:my-6 sm:h-[85svh] sm:rounded-xl sm:border sm:border-gray-200 dark:sm:border-gray-800">
      <header className="border-b border-gray-200 px-4 py-3 dark:border-gray-800">
        <h1 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Digital Twin
        </h1>
      </header>
      <LoggingNotice />
      <MessageList messages={messages} />
      {connectionStatus === 'error' && <ErrorBanner message={errorMessage} />}
      <MessageInput disabled={disabled} onSend={sendMessage} />
    </div>
  )
}
