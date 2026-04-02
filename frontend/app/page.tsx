'use client'

import { useCallback } from 'react'
import { ChatPanel } from './components/ChatPanel'
import { ProfilePanel } from './components/ProfilePanel'
import { useChat, SSEEvent } from './hooks/useChat'
import { useProfile } from './hooks/useProfile'
import { useLanguage } from './i18n'

export default function Home() {
  const { language } = useLanguage()

  const {
    profile,
    isLoading: profileLoading,
    toasts,
    highlightedSection,
    refresh: refreshProfile,
    removeToast,
    notifyNewExperience,
  } = useProfile()

  const handleOrganizing = useCallback(() => {
    // Optional: could show a different loading state
  }, [])

  const handleOrganized = useCallback(
    (saved: SSEEvent['saved']) => {
      if (saved) {
        // Refresh profile to show new data
        refreshProfile()
        // Show toast notification with language
        notifyNewExperience(saved.company, saved.bullets_count, language)
      }
    },
    [refreshProfile, notifyNewExperience, language]
  )

  const handleError = useCallback((error: string) => {
    console.error('Chat error:', error)
  }, [])

  const {
    messages,
    isLoading: chatLoading,
    isOrganizing,
    sendMessage,
    clearSession,
    rollbackAndRetry,
    editMessage,
  } = useChat({
    language,
    onOrganizing: handleOrganizing,
    onOrganized: handleOrganized,
    onError: handleError,
  })

  return (
    <main className="h-screen flex">
      {/* Chat Panel - 60% */}
      <div className="w-[60%] border-r border-gray-200 bg-white">
        <ChatPanel
          messages={messages}
          isLoading={chatLoading}
          isOrganizing={isOrganizing}
          onSendMessage={sendMessage}
          onClearSession={clearSession}
          onEditMessage={editMessage}
          onRetry={() => rollbackAndRetry()}
        />
      </div>

      {/* Profile Panel - 40% */}
      <div className="w-[40%] bg-gray-50">
        <ProfilePanel
          profile={profile}
          isLoading={profileLoading}
          highlightedSection={highlightedSection}
          toasts={toasts}
          onRemoveToast={removeToast}
        />
      </div>
    </main>
  )
}
