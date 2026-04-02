'use client'

import { useState, useCallback, useEffect } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface ProfileData {
  profile: {
    id: string
    name: string
    email?: string
    phone?: string
    location?: string
    summary?: string
  } | null
  skills: Array<{
    name: string
    level: string
    context?: string
  }>
  experiences: Array<{
    id: string
    company: string
    title: string
    location?: string
    start_date?: string
    end_date?: string
    is_visible: boolean
    bullets: Array<{
      raw_text: string
      type: string
      star_data?: Record<string, string>
      tech_stack?: Array<{ name: string; role?: string }>
    }>
  }>
  projects: Array<{
    name: string
    description?: string
    role?: string
    tech_stack?: Array<{ name: string }>
    bullets?: Array<{ text: string }>
  }>
  education: Array<{
    institution: string
    degree?: string
    field?: string
    start_date?: string
    end_date?: string
  }>
}

export interface Toast {
  id: string
  message: string
  type: 'success' | 'info' | 'error'
}

interface UseProfileOptions {
  autoRefresh?: boolean
  refreshInterval?: number
}

export function useProfile(options: UseProfileOptions = {}) {
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [highlightedSection, setHighlightedSection] = useState<string | null>(null)

  const fetchProfile = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/profile`)
      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }
      const data = await response.json()
      setProfile(data)
      setError(null)
    } catch (e: any) {
      setError(e.message || 'Failed to fetch profile')
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchProfile()
  }, [fetchProfile])

  // Auto refresh
  useEffect(() => {
    if (options.autoRefresh && options.refreshInterval) {
      const interval = setInterval(fetchProfile, options.refreshInterval)
      return () => clearInterval(interval)
    }
  }, [options.autoRefresh, options.refreshInterval, fetchProfile])

  const addToast = useCallback((message: string, type: Toast['type'] = 'success') => {
    const id = `toast-${Date.now()}`
    setToasts(prev => [...prev, { id, message, type }])

    // Auto remove after 3 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 3000)
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const highlightSection = useCallback((section: string) => {
    setHighlightedSection(section)
    setTimeout(() => setHighlightedSection(null), 1500)
  }, [])

  const refresh = useCallback(async () => {
    setIsLoading(true)
    await fetchProfile()
  }, [fetchProfile])

  // Helper to notify about new experience (bilingual support)
  const notifyNewExperience = useCallback((company: string, bulletsCount: number, language: 'zh' | 'en' = 'zh') => {
    const message = language === 'en'
      ? `Saved: ${company} experience (${bulletsCount} highlights)`
      : `已保存：${company} 的经历 (${bulletsCount} 条亮点)`
    addToast(message, 'success')
    highlightSection('experiences')
  }, [addToast, highlightSection])

  return {
    profile,
    isLoading,
    error,
    toasts,
    highlightedSection,
    refresh,
    addToast,
    removeToast,
    highlightSection,
    notifyNewExperience,
  }
}
