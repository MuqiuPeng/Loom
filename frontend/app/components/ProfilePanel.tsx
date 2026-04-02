'use client'

import { useState } from 'react'
import { ProfileData, Toast } from '../hooks/useProfile'
import { useLanguage } from '../i18n'

interface ProfilePanelProps {
  profile: ProfileData | null
  isLoading: boolean
  highlightedSection: string | null
  toasts: Toast[]
  onRemoveToast: (id: string) => void
}

interface CollapsibleSectionProps {
  title: string
  count: number
  isHighlighted: boolean
  defaultOpen?: boolean
  children: React.ReactNode
}

function CollapsibleSection({
  title,
  count,
  isHighlighted,
  defaultOpen = false,
  children,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div
      className={`border rounded-lg transition-all ${
        isHighlighted ? 'highlight-new border-green-300' : 'border-gray-200'
      }`}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-800">{title}</span>
          <span className="text-sm text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
            {count}
          </span>
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform ${
            isOpen ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>
      {isOpen && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

function SkeletonLoader() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-20 bg-gray-200 rounded-lg" />
      <div className="h-32 bg-gray-200 rounded-lg" />
      <div className="h-24 bg-gray-200 rounded-lg" />
      <div className="h-24 bg-gray-200 rounded-lg" />
    </div>
  )
}

interface EmptyStateProps {
  t: (key: string) => string
}

function EmptyState({ t }: EmptyStateProps) {
  return (
    <div className="text-center py-12">
      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg
          className="w-8 h-8 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
          />
        </svg>
      </div>
      <h3 className="text-gray-600 font-medium mb-2">{t('noContent')}</h3>
      <p className="text-gray-400 text-sm whitespace-pre-line">
        {t('noContentHint')}
      </p>
    </div>
  )
}

export function ProfilePanel({
  profile,
  isLoading,
  highlightedSection,
  toasts,
  onRemoveToast,
}: ProfilePanelProps) {
  const { language, t } = useLanguage()

  if (isLoading) {
    return (
      <div className="h-full bg-white p-4">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">{t('myResume')}</h2>
        <SkeletonLoader />
      </div>
    )
  }

  const hasContent =
    profile &&
    (profile.skills.length > 0 ||
      profile.experiences.length > 0 ||
      profile.projects.length > 0 ||
      profile.education.length > 0)

  return (
    <div className="h-full bg-white flex flex-col relative">
      {/* Toasts */}
      <div className="absolute top-4 right-4 z-10 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast-enter px-4 py-3 rounded-lg shadow-lg text-sm flex items-center gap-2 ${
              toast.type === 'success'
                ? 'bg-green-500 text-white'
                : toast.type === 'error'
                ? 'bg-red-500 text-white'
                : 'bg-blue-500 text-white'
            }`}
          >
            {toast.type === 'success' && (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            )}
            <span>{toast.message}</span>
            <button
              onClick={() => onRemoveToast(toast.id)}
              className="ml-2 hover:opacity-75"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800">{t('myResume')}</h2>
        <p className="text-sm text-gray-500">{t('realtimePreview')}</p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {!hasContent ? (
          <EmptyState t={t} />
        ) : (
          <div className="space-y-4">
            {/* Basic Info */}
            {profile.profile && (
              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-800 text-lg">
                  {profile.profile.name}
                </h3>
                <div className="mt-2 text-sm text-gray-600 space-y-1">
                  {profile.profile.email && (
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      {profile.profile.email}
                    </div>
                  )}
                  {profile.profile.location && (
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      {profile.profile.location}
                    </div>
                  )}
                </div>
                {profile.profile.summary && (
                  <p className="mt-3 text-sm text-gray-600">{profile.profile.summary}</p>
                )}
              </div>
            )}

            {/* Skills */}
            {profile.skills.length > 0 && (
              <CollapsibleSection
                title={t('skills')}
                count={profile.skills.length}
                isHighlighted={highlightedSection === 'skills'}
                defaultOpen
              >
                <div className="flex flex-wrap gap-2">
                  {profile.skills.map((skill, i) => (
                    <span
                      key={i}
                      className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm"
                      title={skill.context}
                    >
                      {skill.name}
                      <span className="ml-1 text-blue-400 text-xs">
                        {skill.level === 'expert' ? t('expert') : skill.level === 'proficient' ? t('proficient') : t('familiar')}
                      </span>
                    </span>
                  ))}
                </div>
              </CollapsibleSection>
            )}

            {/* Experiences */}
            {profile.experiences.length > 0 && (
              <CollapsibleSection
                title={t('workExperience')}
                count={profile.experiences.length}
                isHighlighted={highlightedSection === 'experiences'}
                defaultOpen
              >
                <div className="space-y-4">
                  {profile.experiences.map((exp) => (
                    <div key={exp.id} className="border-l-2 border-blue-200 pl-4">
                      <div className="flex items-start justify-between">
                        <div>
                          <h4 className="font-medium text-gray-800">{exp.title}</h4>
                          <p className="text-sm text-gray-600">{exp.company}</p>
                        </div>
                        <span className="text-xs text-gray-400">
                          {exp.start_date?.slice(0, 7)} - {exp.end_date?.slice(0, 7) || t('present')}
                        </span>
                      </div>
                      {exp.bullets.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {exp.bullets.map((bullet, i) => {
                            // Get bilingual text from star_data if available
                            const textZh = bullet.star_data?.raw_text_zh
                            const textEn = bullet.star_data?.raw_text_en
                            const displayText = language === 'en' && textEn
                              ? textEn
                              : textZh || bullet.raw_text
                            return (
                              <li
                                key={i}
                                className="text-sm text-gray-600 flex items-start gap-2"
                              >
                                <span className="text-blue-400 mt-1">•</span>
                                <span>{displayText}</span>
                              </li>
                            )
                          })}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            )}

            {/* Projects */}
            {profile.projects.length > 0 && (
              <CollapsibleSection
                title={t('projects')}
                count={profile.projects.length}
                isHighlighted={highlightedSection === 'projects'}
              >
                <div className="space-y-3">
                  {profile.projects.map((proj, i) => (
                    <div key={i} className="border-l-2 border-purple-200 pl-4">
                      <h4 className="font-medium text-gray-800">{proj.name}</h4>
                      {proj.role && (
                        <p className="text-sm text-gray-500">{proj.role}</p>
                      )}
                      {proj.description && (
                        <p className="text-sm text-gray-600 mt-1">{proj.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            )}

            {/* Education */}
            {profile.education.length > 0 && (
              <CollapsibleSection
                title={t('education')}
                count={profile.education.length}
                isHighlighted={highlightedSection === 'education'}
              >
                <div className="space-y-3">
                  {profile.education.map((edu, i) => (
                    <div key={i} className="border-l-2 border-green-200 pl-4">
                      <h4 className="font-medium text-gray-800">{edu.institution}</h4>
                      <p className="text-sm text-gray-600">
                        {edu.degree} {edu.field}
                      </p>
                      <span className="text-xs text-gray-400">
                        {edu.start_date?.slice(0, 7)} - {edu.end_date?.slice(0, 7) || t('present')}
                      </span>
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
