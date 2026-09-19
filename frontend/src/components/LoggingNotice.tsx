// Keep in sync with `chat_log_retention_days` in terraform/variables.tf.
const RETENTION_DAYS = 90

export default function LoggingNotice() {
  return (
    <p className="border-b border-gray-200 bg-gray-50 px-4 py-2 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400">
      Chat messages are logged and automatically deleted after {RETENTION_DAYS} days.
    </p>
  )
}
