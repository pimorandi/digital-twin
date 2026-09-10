export default function ErrorBanner() {
  return (
    <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
      Couldn't reach the backend. It may not be running yet — try again shortly.
    </div>
  )
}
