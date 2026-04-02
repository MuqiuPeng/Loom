'use client'

interface LoadingBubbleProps {
  message?: string
  isOrganizing?: boolean
}

export function LoadingBubble({
  message = 'Thinking...',
  isOrganizing = false,
}: LoadingBubbleProps) {
  if (isOrganizing) {
    return (
      <div className="flex justify-start animate-fade-in">
        <div className="bg-green-50 border border-green-200 rounded-2xl rounded-bl-md px-4 py-3 max-w-[80%]">
          <div className="flex items-center gap-3">
            <div className="relative">
              <svg
                className="w-5 h-5 text-green-500 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            </div>
            <div>
              <p className="text-green-700 font-medium">{message}</p>
              <div className="mt-2 h-1.5 w-48 bg-green-100 rounded-full overflow-hidden">
                <div className="h-full bg-green-500 rounded-full animate-pulse w-3/4" />
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start animate-fade-in">
      <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3">
        <div className="flex items-center gap-1">
          <span className="loading-dot w-2 h-2 bg-gray-400 rounded-full" />
          <span className="loading-dot w-2 h-2 bg-gray-400 rounded-full" />
          <span className="loading-dot w-2 h-2 bg-gray-400 rounded-full" />
        </div>
      </div>
    </div>
  )
}
