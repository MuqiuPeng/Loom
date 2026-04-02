'use client'

import { useState, useCallback, useRef, useEffect } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export interface SSEEvent {
  type: 'message' | 'organizing' | 'organized' | 'error'
  content: string
  saved?: {
    experience_id: string
    company: string
    title: string
    bullets_count: number
  }
}

interface UseChatOptions {
  language?: 'zh' | 'en'
  onOrganizing?: () => void
  onOrganized?: (saved: SSEEvent['saved']) => void
  onError?: (error: string) => void
}

export function useChat(options: UseChatOptions = {}) {
  const { language = 'zh' } = options
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOrganizing, setIsOrganizing] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const currentAssistantMessageRef = useRef<string>('')

  // Use ref to always have the latest language value in callbacks
  const languageRef = useRef(language)
  languageRef.current = language

  // Load session from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('loom_session_id')
    if (stored) {
      setSessionId(stored)
      loadHistory(stored)
    }
  }, [])

  // Save session to localStorage when it changes
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('loom_session_id', sessionId)
    }
  }, [sessionId])

  const loadHistory = async (sid: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/chat/history?session_id=${sid}`)
      if (response.ok) {
        const data = await response.json()
        setMessages(
          data.messages.map((m: any, i: number) => ({
            id: `${i}-${m.timestamp}`,
            role: m.role,
            content: m.content,
            timestamp: new Date(m.timestamp),
          }))
        )
      }
    } catch (e) {
      console.error('Failed to load history:', e)
    }
  }

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return

    // Cancel any existing request before starting a new one
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    setError(null)
    setIsLoading(true)
    setIsOrganizing(false)
    currentAssistantMessageRef.current = ''

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMessage])

    // Create assistant message placeholder
    const assistantMessageId = `assistant-${Date.now()}`
    setMessages(prev => [
      ...prev,
      {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      },
    ])

    try {
      abortControllerRef.current = new AbortController()

      // Use languageRef to always get the latest language value
      const currentLanguage = languageRef.current
      console.log('[useChat] Sending message with language:', currentLanguage)

      const response = await fetch(`${API_BASE}/api/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: content.trim(),
          session_id: sessionId,
          language: currentLanguage,
        }),
        signal: abortControllerRef.current.signal,
      })

      // Get session ID from response header
      const newSessionId = response.headers.get('X-Session-Id')
      if (newSessionId && newSessionId !== sessionId) {
        setSessionId(newSessionId)
      }

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: SSEEvent = JSON.parse(line.slice(6))

              switch (event.type) {
                case 'message':
                  currentAssistantMessageRef.current += event.content
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === assistantMessageId
                        ? { ...m, content: currentAssistantMessageRef.current }
                        : m
                    )
                  )
                  break

                case 'organizing':
                  setIsOrganizing(true)
                  options.onOrganizing?.()
                  break

                case 'organized':
                  setIsOrganizing(false)
                  options.onOrganized?.(event.saved)
                  break

                case 'error':
                  setError(event.content)
                  options.onError?.(event.content)
                  break
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e)
            }
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        const errorMsg = e.message || 'Failed to send message'
        setError(errorMsg)
        options.onError?.(errorMsg)

        // Remove empty assistant message on error
        setMessages(prev => prev.filter(m => m.id !== assistantMessageId))
      }
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [sessionId, language, options])

  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
    setIsOrganizing(false)
  }, [])

  const clearSession = useCallback(() => {
    // Cancel any ongoing request first
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    if (sessionId) {
      fetch(`${API_BASE}/api/chat/session/${sessionId}`, { method: 'DELETE' })
    }
    localStorage.removeItem('loom_session_id')
    setSessionId(null)
    setMessages([])
    setError(null)
    setIsLoading(false)
    setIsOrganizing(false)
  }, [sessionId])

  // Rollback last exchange (user message + assistant response) and optionally resend
  const rollbackAndRetry = useCallback(async (newMessage?: string) => {
    // Cancel any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    setIsLoading(false)
    setIsOrganizing(false)
    setError(null)

    // Get the last user message content before rollback
    const lastUserMessage = [...messages].reverse().find(m => m.role === 'user')
    const messageToResend = newMessage ?? lastUserMessage?.content

    // Remove last 2 messages from local state (user + assistant)
    setMessages(prev => {
      const newMessages = [...prev]
      // Remove from the end: assistant response (if exists) and user message
      let removed = 0
      while (removed < 2 && newMessages.length > 0) {
        newMessages.pop()
        removed++
      }
      return newMessages
    })

    // Tell backend to rollback
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/api/chat/session/${sessionId}/rollback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ count: 2 }),
        })
      } catch (e) {
        console.error('Failed to rollback session:', e)
      }
    }

    // Resend if we have a message
    if (messageToResend) {
      // Small delay to ensure state is updated
      setTimeout(() => {
        sendMessage(messageToResend)
      }, 100)
    }
  }, [sessionId, messages, sendMessage])

  // Edit and resend a specific message (rolls back to that point)
  const editMessage = useCallback(async (messageId: string, newContent: string) => {
    // Find the message index
    const messageIndex = messages.findIndex(m => m.id === messageId)
    if (messageIndex === -1) return

    // Cancel any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    setIsLoading(false)
    setIsOrganizing(false)
    setError(null)

    // Calculate how many messages to remove (from this message onwards)
    const messagesToRemove = messages.length - messageIndex

    // Remove messages from local state
    setMessages(prev => prev.slice(0, messageIndex))

    // Tell backend to rollback
    if (sessionId && messagesToRemove > 0) {
      try {
        await fetch(`${API_BASE}/api/chat/session/${sessionId}/rollback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ count: messagesToRemove }),
        })
      } catch (e) {
        console.error('Failed to rollback session:', e)
      }
    }

    // Send the edited message
    if (newContent.trim()) {
      setTimeout(() => {
        sendMessage(newContent)
      }, 100)
    }
  }, [sessionId, messages, sendMessage])

  return {
    messages,
    isLoading,
    isOrganizing,
    sessionId,
    error,
    sendMessage,
    cancelRequest,
    clearSession,
    rollbackAndRetry,
    editMessage,
  }
}
