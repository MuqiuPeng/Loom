'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Types ──────────────────────────────────────────────────

interface Job {
  id: string
  company: string | null
  title: string
  raw_text: string
  required_skills: string[]
  preferred_skills: string[]
  key_requirements: string[]
  match_score: number | null
  has_resume: boolean
  created_at: string
}

interface TaskStatus {
  task_id: string
  type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  output_data: any | null
  error: string | null
  created_at: string
  updated_at: string
}

interface AnalyzeOutput {
  jd_record_id: string
  company: string | null
  title: string
  required_skills: string[]
  preferred_skills: string[]
  match_score: number
  matched: Array<{ requirement: string; evidence: string }>
  hard_skill_gaps: string[]
  reasoning: string
}

interface GenerateOutput {
  resume_artifact_id: string
  download_url?: string
}

// ── useTaskPoller hook ─────────────────────────────────────

function useTaskPoller(
  taskId: string | null,
  onComplete: (output: any) => void,
  onError: (error: string) => void,
  interval = 2000,
) {
  useEffect(() => {
    if (!taskId) return
    let cancelled = false

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/tasks/${taskId}`)
        if (!res.ok) return
        const data: TaskStatus = await res.json()
        if (cancelled) return

        if (data.status === 'completed') {
          onComplete(data.output_data)
          return
        }
        if (data.status === 'failed') {
          onError(data.error || 'Task failed')
          return
        }
        // Still running - poll again
        setTimeout(poll, interval)
      } catch {
        if (!cancelled) setTimeout(poll, interval)
      }
    }

    // Start polling after initial delay
    const timer = setTimeout(poll, interval)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [taskId, onComplete, onError, interval])
}

// ── Main Page ──────────────────────────────────────────────

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [jdText, setJdText] = useState('')

  // Analyze state
  const [analyzeTaskId, setAnalyzeTaskId] = useState<string | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeOutput | null>(null)

  // Generate state
  const [generateTaskId, setGenerateTaskId] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [genLanguage, setGenLanguage] = useState<'en' | 'zh'>('en')
  const [genFormat, setGenFormat] = useState<'markdown' | 'latex' | 'pdf'>('pdf')
  const [genSuccess, setGenSuccess] = useState(false)
  const [lastArtifactId, setLastArtifactId] = useState<string | null>(null)

  const [error, setError] = useState<string | null>(null)

  // Load jobs on mount
  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs`)
      if (res.ok) {
        const data = await res.json()
        setJobs(data)
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchJobs()
  }, [fetchJobs])

  const selectedJob = jobs.find((j) => j.id === selectedJobId) || null

  // ── Analyze JD ──────────────────────────────────────────

  const handleAnalyze = async () => {
    if (!jdText.trim()) return
    setIsAnalyzing(true)
    setError(null)
    setAnalyzeResult(null)

    try {
      const res = await fetch(`${API_BASE}/api/tasks/analyze-jd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_text: jdText }),
      })
      if (!res.ok) throw new Error('Failed to start analysis')
      const data = await res.json()
      setAnalyzeTaskId(data.task_id)
    } catch (e: any) {
      setError(e.message)
      setIsAnalyzing(false)
    }
  }

  const handleAnalyzeComplete = useCallback(
    (output: AnalyzeOutput) => {
      setAnalyzeTaskId(null)
      setIsAnalyzing(false)
      setAnalyzeResult(output)
      setJdText('')
      // Refresh jobs list and select the new one
      fetchJobs().then(() => {
        if (output.jd_record_id) {
          setSelectedJobId(output.jd_record_id)
        }
      })
    },
    [fetchJobs],
  )

  const handleAnalyzeError = useCallback((err: string) => {
    setAnalyzeTaskId(null)
    setIsAnalyzing(false)
    setError(err)
  }, [])

  useTaskPoller(analyzeTaskId, handleAnalyzeComplete, handleAnalyzeError)

  // ── Generate Resume ─────────────────────────────────────

  const handleGenerate = async () => {
    if (!selectedJobId) return
    setIsGenerating(true)
    setGenSuccess(false)
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/api/tasks/generate-resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jd_record_id: selectedJobId,
          language: genLanguage,
          format: genFormat,
        }),
      })
      if (!res.ok) throw new Error('Failed to start generation')
      const data = await res.json()
      setGenerateTaskId(data.task_id)
    } catch (e: any) {
      setError(e.message)
      setIsGenerating(false)
    }
  }

  const handleGenerateComplete = useCallback(
    (output: GenerateOutput) => {
      setGenerateTaskId(null)
      setIsGenerating(false)
      setGenSuccess(true)
      setLastArtifactId(output.resume_artifact_id)

      if (genFormat === 'pdf' && output.download_url) {
        window.open(`${API_BASE}${output.download_url}`, '_blank')
      } else if (output.resume_artifact_id) {
        // Download markdown/latex
        const url = `${API_BASE}/api/resumes/${output.resume_artifact_id}/markdown`
        window.open(url, '_blank')
      }
      fetchJobs()
    },
    [genFormat, fetchJobs],
  )

  const handleGenerateError = useCallback((err: string) => {
    setGenerateTaskId(null)
    setIsGenerating(false)
    setError(err)
  }, [])

  useTaskPoller(generateTaskId, handleGenerateComplete, handleGenerateError)

  // ── Delete Job ──────────────────────────────────────────

  const handleDeleteJob = async (jobId: string) => {
    try {
      await fetch(`${API_BASE}/api/jobs/${jobId}`, { method: 'DELETE' })
      if (selectedJobId === jobId) {
        setSelectedJobId(null)
        setAnalyzeResult(null)
      }
      fetchJobs()
    } catch {
      // ignore
    }
  }

  // When selecting a job from list, clear the analyze result overlay
  const handleSelectJob = (jobId: string) => {
    setSelectedJobId(jobId)
    setAnalyzeResult(null)
    setGenSuccess(false)
    setError(null)
  }

  // Detail data: either from analyzeResult (fresh analysis) or from selected job
  const detailData = analyzeResult
    ? {
        title: analyzeResult.title,
        company: analyzeResult.company,
        matchScore: analyzeResult.match_score,
        requiredSkills: analyzeResult.required_skills,
        preferredSkills: analyzeResult.preferred_skills,
        matched: analyzeResult.matched,
        gaps: analyzeResult.hard_skill_gaps,
        reasoning: analyzeResult.reasoning,
      }
    : selectedJob
      ? {
          title: selectedJob.title,
          company: selectedJob.company,
          matchScore: selectedJob.match_score,
          requiredSkills: selectedJob.required_skills,
          preferredSkills: selectedJob.preferred_skills,
          matched: null,
          gaps: null,
          reasoning: null,
        }
      : null

  return (
    <main className="h-screen flex bg-gray-50">
      {/* Left Panel: JD List + Input */}
      <div className="w-[380px] border-r border-gray-200 bg-white flex flex-col">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200">
          <h1 className="text-lg font-semibold text-gray-900">Jobs</h1>
          <p className="text-xs text-gray-500 mt-0.5">Paste a JD to analyze and generate resume</p>
        </div>

        {/* JD Input Area */}
        <div className="px-4 py-3 border-b border-gray-200">
          <textarea
            className="w-full h-[120px] px-3 py-2 border border-gray-300 rounded-lg text-sm
                       resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                       placeholder-gray-400"
            placeholder="Paste JD here..."
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            disabled={isAnalyzing}
          />
          <button
            className="mt-2 w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg
                       hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed
                       transition-colors"
            onClick={handleAnalyze}
            disabled={!jdText.trim() || isAnalyzing}
          >
            {isAnalyzing ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Analyzing... (~10-15s)
              </span>
            ) : (
              'Analyze'
            )}
          </button>
        </div>

        {/* Job List */}
        <div className="flex-1 overflow-y-auto">
          {isAnalyzing && (
            <div className="px-4 py-3 border-b border-gray-100 bg-blue-50">
              <div className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4 text-blue-600" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                <span className="text-sm text-blue-700 font-medium">Analyzing...</span>
              </div>
              <p className="text-xs text-blue-500 mt-1">Just now</p>
            </div>
          )}

          {jobs.map((job) => (
            <div
              key={job.id}
              className={`px-4 py-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50
                         transition-colors ${selectedJobId === job.id ? 'bg-blue-50 border-l-2 border-l-blue-600' : ''}`}
              onClick={() => handleSelectJob(job.id)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {job.title}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {job.company || 'Unknown Company'}
                  </p>
                </div>
                <div className="flex items-center gap-2 ml-2">
                  {job.match_score != null && (
                    <span
                      className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                        job.match_score >= 7
                          ? 'bg-green-100 text-green-700'
                          : job.match_score >= 4
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {job.match_score}/10
                    </span>
                  )}
                  {job.has_resume && (
                    <span className="text-xs text-green-600">&#10003;</span>
                  )}
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                {new Date(job.created_at).toLocaleDateString()}
              </p>
            </div>
          ))}

          {jobs.length === 0 && !isAnalyzing && (
            <div className="px-4 py-8 text-center text-gray-400 text-sm">
              No jobs yet. Paste a JD above to get started.
            </div>
          )}
        </div>
      </div>

      {/* Right Panel: Job Detail + Generate */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="mx-6 mt-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
            <button
              className="ml-2 text-red-500 hover:text-red-700"
              onClick={() => setError(null)}
            >
              &#x2715;
            </button>
          </div>
        )}

        {detailData ? (
          <div className="p-6 max-w-2xl">
            {/* Title & Company */}
            <h2 className="text-2xl font-bold text-gray-900">{detailData.title}</h2>
            <p className="text-gray-600 mt-1">{detailData.company || 'Unknown Company'}</p>

            {/* Match Score */}
            {detailData.matchScore != null && (
              <div className="mt-4 flex items-center gap-3">
                <span className="text-sm text-gray-500">Match Score:</span>
                <span
                  className={`text-lg font-bold ${
                    detailData.matchScore >= 7
                      ? 'text-green-600'
                      : detailData.matchScore >= 4
                        ? 'text-yellow-600'
                        : 'text-red-600'
                  }`}
                >
                  {detailData.matchScore}/10
                </span>
                {detailData.matchScore >= 7 && (
                  <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                    Recommend
                  </span>
                )}
              </div>
            )}

            {/* Required Skills */}
            {detailData.requiredSkills.length > 0 && (
              <div className="mt-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Required Skills</h3>
                <div className="flex flex-wrap gap-1.5">
                  {detailData.requiredSkills.map((skill, i) => (
                    <span
                      key={i}
                      className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-md"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Matched */}
            {detailData.matched && detailData.matched.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Matched</h3>
                <div className="space-y-1">
                  {detailData.matched.map((m, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <span className="text-green-600 mt-0.5">&#10003;</span>
                      <span className="text-gray-700">{m.requirement}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Gaps */}
            {detailData.gaps && detailData.gaps.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Gaps</h3>
                <div className="space-y-1">
                  {detailData.gaps.map((gap, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <span className="text-red-500 mt-0.5">&#10007;</span>
                      <span className="text-gray-700">{gap}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Reasoning */}
            {detailData.reasoning && (
              <div className="mt-4 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs text-gray-500 mb-1">Analysis</p>
                <p className="text-sm text-gray-700">{detailData.reasoning}</p>
              </div>
            )}

            {/* Divider */}
            <hr className="my-6 border-gray-200" />

            {/* Generate Resume Section */}
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Generate Resume</h3>

              <div className="flex items-center gap-6 mb-4">
                {/* Language */}
                <div>
                  <label className="text-xs text-gray-500 block mb-1.5">Language</label>
                  <div className="flex gap-1">
                    {(['en', 'zh'] as const).map((lang) => (
                      <button
                        key={lang}
                        className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                          genLanguage === lang
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                        onClick={() => setGenLanguage(lang)}
                      >
                        {lang === 'en' ? 'EN' : '\u4E2D\u6587'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Format */}
                <div>
                  <label className="text-xs text-gray-500 block mb-1.5">Format</label>
                  <div className="flex gap-1">
                    {(['markdown', 'latex', 'pdf'] as const).map((fmt) => (
                      <button
                        key={fmt}
                        className={`px-3 py-1.5 text-sm rounded-md capitalize transition-colors ${
                          genFormat === fmt
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                        onClick={() => setGenFormat(fmt)}
                      >
                        {fmt === 'pdf' ? 'PDF' : fmt === 'latex' ? 'LaTeX' : 'Markdown'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <button
                className="px-6 py-2.5 bg-green-600 text-white text-sm font-medium rounded-lg
                           hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed
                           transition-colors"
                onClick={handleGenerate}
                disabled={isGenerating || !selectedJobId}
              >
                {isGenerating ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                        fill="none"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    Generating...{' '}
                    {genFormat === 'pdf' ? '(~20-25s)' : '(~15-20s)'}
                  </span>
                ) : (
                  'Generate'
                )}
              </button>

              {genSuccess && (
                <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
                  <span>&#10003; Resume generated</span>
                  <a
                    href="/"
                    className="text-blue-600 hover:text-blue-800 underline"
                  >
                    View in Resumes &rarr;
                  </a>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <p className="text-lg mb-1">Select a job to view details</p>
              <p className="text-sm">or paste a new JD on the left to analyze</p>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
