import { useState } from 'react'
import type { KeyboardEvent } from 'react'

// Keep in sync with MAX_MESSAGE_CHARS in backend/app/presentation/schemas/chat.py.
const MAX_MESSAGE_CHARS = 2000

interface MessageInputProps {
  disabled: boolean
  onSend: (text: string) => void
}

export default function MessageInput({ disabled, onSend }: MessageInputProps) {
  const [value, setValue] = useState('')

  const submit = () => {
    if (disabled || !value.trim()) return
    onSend(value)
    setValue('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex items-end gap-2 border-t border-gray-200 p-3 dark:border-gray-800">
      <textarea
        className="max-h-32 flex-1 resize-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        rows={1}
        maxLength={MAX_MESSAGE_CHARS}
        placeholder="Ask about the candidate's experience..."
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button
        type="button"
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        disabled={disabled || !value.trim()}
        onClick={submit}
      >
        Send
      </button>
    </div>
  )
}
