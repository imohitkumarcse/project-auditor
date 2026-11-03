
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowUpRight, CheckCircle2, ChevronRight,
  Clock3, FileArchive, FileCode2, FileText, FolderOpen, Gauge,
  RefreshCw, Search, ShieldCheck, UploadCloud, XCircle, Zap,
BrainCircuit, Sparkles, CircleAlert,
} from 'lucide-react'
import './App.css'

const API = 'http://127.0.0.1:8000'

const MODELS = [
  'qwen2.5-coder:7b',
  'qwen3:8b',
  'personalai-test:latest',
]

type Finding = {
  type: string
  severity: string
  file?: string
  line?: number
  message: string
}

type AIFinding = {
  title?: string
  type?: string
  severity?: string
  file?: string
  line?: number
  evidence?: string
  explanation?: string
  message?: string
  recommendation?: string
}

type AIAudit = {
  status?: string
  model?: string
  summary?: string
  architecture_review?: Record<string, unknown> | string
  strengths?: string[]
  limitations?: string[]
  findings?: AIFinding[]
files_reviewed?: {
  path: string
  line_count: number
}[]
  files_reviewed_count?: number
  error?: string
}

type Project = {
  project_id: string
  filename: string
  file_size_bytes?: number
  status?: string
  audit_status?: string
  audit_score?: number
  category?: string
  languages?: Record<string, number>
  frameworks?: string[]
  findings?: Finding[]
  finding_summary?: Record<string, number>
  scores?: Record<string, number>
  metrics?: Record<string, number>
  file_count?: number
  suspicious_entries?: string[]
  execution_performed?: boolean
  ai_audit?: AIAudit
  ai_audit_status?: string
}

type Health = {
  backend?: string
  ollama?: string
  version?: string
}

function formatBytes(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function scoreColor(score?: number) {
  if (score === undefined) return 'muted'
  return score >= 80 ? 'good' : score >= 60 ? 'medium' : 'bad'
}

function severityClass(severity?: string) {
  return (severity || 'info').toLowerCase()
}

function readableKey(value: string) {
  return value.replaceAll('_', ' ').replaceAll('-', ' ')
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(displayValue).join(', ')
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${readableKey(key)}: ${displayValue(item)}`)
      .join('\n')
  }
  return ''
}

function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [health, setHealth] = useState<Health>({})
  const [selected, setSelected] = useState<Project | null>(null)
  const [search, setSearch] = useState('')
  const [uploading, setUploading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [aiModel, setAiModel] = useState(MODELS[0])
  const [runningAiProject, setRunningAiProject] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const loadData = useCallback(async () => {
    try {
      const [healthResponse, projectsResponse] = await Promise.all([
        fetch(`${API}/api/health`),
        fetch(`${API}/api/projects/`),
      ])

      if (!healthResponse.ok || !projectsResponse.ok) {
        throw new Error('The backend returned an error. Check the API server.')
      }

      const healthData: Health = await healthResponse.json()
      const projectData = await projectsResponse.json()
      const list: Project[] = Array.isArray(projectData)
        ? projectData
        : projectData.projects ?? projectData.results ?? []

      setHealth(healthData)
      setProjects(list)
      setError('')
    } catch {
      setHealth({})
      setError('Cannot connect to the backend. Start FastAPI on port 8000.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const uploadFiles = async (files: FileList | File[]) => {
    const zipFiles = Array.from(files).filter(file =>
      file.name.toLowerCase().endsWith('.zip'),
    )

    if (!zipFiles.length) {
      setError('Choose one or more .zip project archives.')
      return
    }

    if (zipFiles.length > 10) {
      setError('Upload a maximum of 10 ZIP files at a time.')
      return
    }

    setUploading(true)
    setError('')
    setNotice('')

    try {
      const formData = new FormData()
      zipFiles.forEach(file => formData.append('files', file))

      const response = await fetch(`${API}/api/projects/upload`, {
        method: 'POST',
        body: formData,
      })
      const result = await response.json()

      if (!response.ok) {
        throw new Error(
          typeof result.detail === 'string' ? result.detail : 'Upload failed.',
        )
      }

      const rejected = result.total_rejected ?? 0
      setNotice(
        `Processed ${result.total_uploaded ?? zipFiles.length} archive(s). ${rejected} rejected.`,
      )
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const openReport = async (project: Project) => {
    setSelected(project)
    setError('')

    try {
      const response = await fetch(
        `${API}/api/projects/${project.project_id}/report`,
      )
      if (!response.ok) {
        throw new Error('Could not load the saved report.')
      }
      const report: Project = await response.json()
      setSelected(report)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Report unavailable.')
    }
  }

  const runAiAudit = async (project: Project) => {
    if (runningAiProject) return

    setRunningAiProject(project.project_id)
    setError('')
    setNotice('')

    try {
      const response = await fetch(
        `${API}/api/projects/${project.project_id}/ai-audit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: aiModel }),
        },
      )

      const result = await response.json()

      if (!response.ok) {
        const detail = typeof result.detail === 'string'
          ? result.detail
          : 'AI audit failed. Check the backend and Ollama.'
        throw new Error(detail)
      }

      const reportResponse = await fetch(
        `${API}/api/projects/${project.project_id}/report`,
      )

      if (!reportResponse.ok) {
        throw new Error('AI audit finished, but the saved report could not be loaded.')
      }

      const report: Project = await reportResponse.json()
      setSelected(report)
      setNotice(`AI review completed for ${project.filename}.`)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI audit failed.')
    } finally {
      setRunningAiProject(null)
    }
  }

  const filtered = projects.filter(project =>
    `${project.filename} ${project.category ?? ''} ${(project.frameworks ?? []).join(' ')}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )

  const averageScore = projects.length
    ? Math.round(
        projects.reduce((sum, project) => sum + (project.audit_score ?? 0), 0)
        / projects.length,
      )
    : 0

  const highFindings = projects.reduce(
    (sum, project) => sum + (project.finding_summary?.high ?? 0),
    0,
  )

  const aiCompleted = projects.filter(
    project => project.ai_audit_status === 'completed'
      || project.ai_audit?.status === 'completed',
  ).length

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview">
          <span className="brand-icon"><ShieldCheck size={23} /></span>
          <span>PROJECT<span className="brand-accent">AUDITOR</span>
            <small>LOCAL INTELLIGENCE PLATFORM</small>
          </span>
        </a>

        <div className="side-label">WORKSPACE</div>
        <a className="nav-item active" href="#overview"><Gauge size={18} /> Overview</a>
        <a className="nav-item" href="#projects"><FolderOpen size={18} /> Projects</a>
        <a className="nav-item" href="#findings"><AlertTriangle size={18} /> Findings</a>

        <div className="sidebar-bottom">
          <div className="privacy-icon"><ShieldCheck size={18} /></div>
          <strong>Local-first analysis</strong>
          <p>Project files are inspected without executing their code. AI review uses your local Ollama runtime.</p>
          <div className="privacy-status"><span /> Local analysis enabled</div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace <ChevronRight size={14} /> <b>Overview</b></div>
          <div className="topbar-right">
            <span className={`connection-dot ${health.backend ? 'online' : ''}`} />
            {health.backend ? 'API connected' : 'API disconnected'}
            <button className="icon-button" onClick={() => void loadData()} title="Refresh">
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        <div className="page-content" id="overview">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><Zap size={14} /> PROJECT INTELLIGENCE</div>
              <h1>Project <span>Overview</span></h1>
              <p>Inspect, evaluate and understand your codebases from one workspace.</p>
            </div>

            <div className="heading-actions">
              <label className="model-selector">
                <span>AI MODEL</span>
                <select
                  value={aiModel}
                  onChange={event => setAiModel(event.target.value)}
                  disabled={Boolean(runningAiProject)}
                >
                  {MODELS.map(model => (
                    <option value={model} key={model}>{model}</option>
                  ))}
                </select>
              </label>

              <button
                className="primary-button"
                onClick={() => fileInput.current?.click()}
                disabled={uploading}
              >
                <UploadCloud size={18} />
                {uploading ? 'Analyzing...' : 'Upload projects'}
              </button>
            </div>

            <input
              ref={fileInput}
              type="file"
              accept=".zip,application/zip"
              multiple
              hidden
              onChange={event => {
                if (event.target.files) void uploadFiles(event.target.files)
              }}
            />
          </div>

          {error && (
            <div className="alert error-alert">
              <AlertTriangle size={18} />
              {error}
              <button onClick={() => setError('')}><XCircle size={16} /></button>
            </div>
          )}
          {notice && (
            <div className="alert success-alert">
              <CheckCircle2 size={18} />
              {notice}
              <button onClick={() => setNotice('')}><XCircle size={16} /></button>
            </div>
          )}

          <div
            className="upload-zone"
            onDragOver={event => event.preventDefault()}
            onDrop={event => {
              event.preventDefault()
              void uploadFiles(event.dataTransfer.files)
            }}
          >
            <div className="upload-icon"><FileArchive size={25} /></div>
            <div className="upload-copy">
              <strong>Drop project ZIP files here</strong>
              <p>Upload up to 10 archives per batch · Maximum 100 MB per archive</p>
            </div>
            <button className="secondary-button" onClick={() => fileInput.current?.click()}>
              Browse files
            </button>
          </div>

          <div className="section-heading">
            <div><h2>Audit snapshot</h2><p>Overview of your analyzed projects</p></div>
            <span className="live-label"><span /> LIVE DATA</span>
          </div>

          <div className="stats-grid">
            <article className="stat-card">
              <div className="stat-top"><span>Total projects</span><FolderOpen size={19} /></div>
              <div className="stat-value">{loading ? '—' : projects.length.toString().padStart(2, '0')}</div>
              <div className="stat-foot">Archives in your workspace</div>
            </article>

            <article className="stat-card">
              <div className="stat-top"><span>Average score</span><Gauge size={19} /></div>
              <div className="stat-value">{projects.length ? averageScore : '—'}<small>{projects.length ? '/100' : ''}</small></div>
              <div className="stat-foot">Across uploaded projects</div>
            </article>

            <article className="stat-card">
              <div className="stat-top"><span>High-severity findings</span><AlertTriangle size={19} /></div>
              <div className="stat-value">{highFindings}</div>
              <div className="stat-foot">Reported by static audit rules</div>
            </article>

            <article className="stat-card">
              <div className="stat-top"><span>AI reviews completed</span><BrainCircuit size={19} /></div>
              <div className="stat-value">{aiCompleted.toString().padStart(2, '0')}</div>
              <div className="stat-foot">
                Ollama · {health.ollama === 'online' ? 'Runtime online' : 'Runtime offline'}
              </div>
            </article>
          </div>

          <div className="section-heading projects-heading" id="projects">
            <div><h2>Project inventory</h2><p>Your uploaded codebases and audit results</p></div>
            <label className="search-box">
              <Search size={17} />
              <input
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder="Search projects..."
              />
            </label>
          </div>

          <div className="project-list">
            {loading ? (
              <div className="empty-state">
                <RefreshCw className="spin" size={24} />
                <p>Loading projects...</p>
              </div>
            ) : filtered.length === 0 ? (
              <div className="empty-state">
                <FolderOpen size={31} />
                <strong>{search ? 'No matching projects' : 'Your workspace is ready'}</strong>
                <p>{search ? 'Try another search term.' : 'Upload a ZIP archive to run your first static audit.'}</p>
              </div>
            ) : filtered.map(project => {
              const isRunning = runningAiProject === project.project_id
              const hasAiReport = project.ai_audit_status === 'completed'
                || project.ai_audit?.status === 'completed'

              return (
                <article className="project-row" key={project.project_id}>
                  <div className="project-file-icon"><FileCode2 size={22} /></div>

                  <div className="project-info">
                    <strong>{project.filename}</strong>
                    <p>{project.category ?? 'Project'} <span>·</span> {formatBytes(project.file_size_bytes)}</p>
                    <div className="tag-list">
                      {(project.frameworks ?? []).slice(0, 3).map(framework => (
                        <span className="tag" key={framework}>{framework}</span>
                      ))}
                      {Object.keys(project.languages ?? {}).slice(0, 2).map(language => (
                        <span className="tag language-tag" key={language}>{language}</span>
                      ))}
                    </div>
                  </div>

                  <div className="project-audit">
                    <span className={`score-pill ${scoreColor(project.audit_score)}`}>
                      {project.audit_score ?? '—'}
                      <small>{project.audit_score !== undefined ? '/100' : ''}</small>
                    </span>
                    <span className="audit-status">
                      <CheckCircle2 size={13} />
                      {project.audit_status === 'completed' ? 'Audited' : project.status ?? 'Uploaded'}
                    </span>
                    {hasAiReport && <span className="ai-completed-label"><Sparkles size={11} /> AI reviewed</span>}
                  </div>

                  <div className="project-actions">
                    <button
                      className="ai-audit-button"
                      onClick={() => void runAiAudit(project)}
                      disabled={Boolean(runningAiProject) || health.ollama !== 'online'}
                      title={health.ollama !== 'online' ? 'Ollama is offline' : 'Run local AI review'}
                    >
                      {isRunning
                        ? <><RefreshCw className="spin" size={14} /> Reviewing</>
                        : <><Sparkles size={14} /> AI Audit</>}
                    </button>
                    <button
                      className="row-action"
                      onClick={() => void openReport(project)}
                      title="Open report"
                    >
                      <ArrowUpRight size={19} />
                    </button>
                  </div>
                </article>
              )
            })}
          </div>

          <div className="bottom-grid" id="findings">
            <section className="panel">
              <div className="panel-heading">
                <div><h3>Latest findings</h3><p>Items that may need attention</p></div>
                <AlertTriangle size={19} />
              </div>
              {projects.flatMap(project =>
                (project.findings ?? []).map(finding => ({
                  ...finding,
                  filename: project.filename,
                  project_id: project.project_id,
                })),
              ).slice(0, 4).length === 0 ? (
                <p className="muted-text">No finding details in the inventory response. Open a project report to inspect its findings.</p>
              ) : projects.flatMap(project =>
                (project.findings ?? []).map(finding => ({
                  ...finding,
                  filename: project.filename,
                  project_id: project.project_id,
                })),
              ).slice(0, 4).map((finding, index) => (
                <div className="finding-row" key={`${finding.project_id}-${finding.type}-${index}`}>
                  <span className={`severity-mark ${severityClass(finding.severity)}`} />
                  <div>
                    <strong>{readableKey(finding.type)}</strong>
                    <p>{finding.filename}</p>
                  </div>
                  <span className={`severity-text ${severityClass(finding.severity)}`}>{finding.severity}</span>
                </div>
              ))}
            </section>

            <section className="panel">
              <div className="panel-heading">
                <div><h3>System status</h3><p>Local analysis services</p></div>
                <Activity size={19} />
              </div>
              <div className="service-row">
                <span className="service-icon"><Activity size={17} /></span>
                <div><strong>FastAPI backend</strong><p>Project upload and reports</p></div>
                <span className={`service-state ${health.backend ? 'up' : 'down'}`}>
                  {health.backend ? 'Connected' : 'Offline'}
                </span>
              </div>
              <div className="service-row">
                <span className="service-icon"><Zap size={17} /></span>
                <div><strong>Ollama runtime</strong><p>Local model availability</p></div>
                <span className={`service-state ${health.ollama === 'online' ? 'up' : 'down'}`}>
                  {health.ollama === 'online' ? 'Connected' : 'Offline'}
                </span>
              </div>
              <div className="service-row">
                <span className="service-icon"><FileText size={17} /></span>
                <div><strong>Static audit engine</strong><p>ZIP and source inspection</p></div>
                <span className="service-state up">Available</span>
              </div>
              <div className="service-row">
                <span className="service-icon"><Clock3 size={17} /></span>
                <div><strong>Code execution</strong><p>Untrusted projects are not run</p></div>
                <span className="service-state neutral">Disabled</span>
              </div>
            </section>
          </div>

          <footer>
            <span>PROJECT AUDITOR <b>·</b> LOCAL-FIRST</span>
            <span>Static analysis + local AI review · No project code executed</span>
          </footer>
        </div>
      </section>

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <section className="report-modal" onClick={event => event.stopPropagation()}>
            <div className="modal-heading">
              <div>
                <div className="eyebrow">PROJECT AUDIT REPORT</div>
                <h2>{selected.filename}</h2>
                <p>{selected.category ?? 'Project'} · {selected.project_id}</p>
              </div>
              <button className="icon-button" onClick={() => setSelected(null)}>
                <XCircle size={20} />
              </button>
            </div>

            <div className="report-score">
              <span className={`score-pill large ${scoreColor(selected.audit_score)}`}>
                {selected.audit_score ?? '—'}<small>/100</small>
              </span>
              <div>
                <strong>Static audit score</strong>
                <p>Heuristic static analysis; findings require verification.</p>
              </div>
            </div>

            <div className="report-metrics">
              {Object.entries(selected.scores ?? {}).map(([name, score]) => (
                <div key={name}>
                  <span>{readableKey(name)}</span>
                  <strong>{score}/100</strong>
                </div>
              ))}
            </div>

            <h3>Static findings ({selected.findings?.length ?? 0})</h3>
            <div className="report-findings">
              {(selected.findings ?? []).length ? selected.findings?.map((finding, index) => (
                <article className="report-finding" key={`${finding.type}-${index}`}>
                  <div>
                    <span className={`severity-text ${severityClass(finding.severity)}`}>
                      {finding.severity.toUpperCase()}
                    </span>
                    <strong>{readableKey(finding.type)}</strong>
                  </div>
                  <p>{finding.message}</p>
                  {finding.file && <code>{finding.file}{finding.line ? `:${finding.line}` : ''}</code>}
                </article>
              )) : <p className="muted-text">No findings returned in this report.</p>}
            </div>

            {selected.ai_audit && (
              <section className="ai-report-section">
                <div className="ai-report-heading">
                  <div>
                    <div className="eyebrow"><BrainCircuit size={14} /> LOCAL MODEL REVIEW</div>
                    <h3>AI Architecture & Code Review</h3>
                    <p>{selected.ai_audit.model || 'Local Ollama model'} · Advisory review</p>
                  </div>
                  <span className={`ai-status ${selected.ai_audit.status === 'completed' ? 'success' : 'warning'}`}>
                    {selected.ai_audit.status || 'Available'}
                  </span>
                </div>

                {selected.ai_audit.summary && (
                  <div className="ai-summary">
                    <h4><Sparkles size={15} /> Executive summary</h4>
                    <p>{selected.ai_audit.summary}</p>
                  </div>
                )}

                {selected.ai_audit.architecture_review && (
                  <>
                    <h4 className="ai-section-title">Architecture review</h4>
                    <div className="ai-architecture">
                      {typeof selected.ai_audit.architecture_review === 'string' ? (
                        <article><p>{selected.ai_audit.architecture_review}</p></article>
                      ) : Object.entries(selected.ai_audit.architecture_review).map(([key, value]) => (
                        <article key={key}>
                          <strong>{readableKey(key)}</strong>
                          <p>{displayValue(value)}</p>
                        </article>
                      ))}
                    </div>
                  </>
                )}

                {(selected.ai_audit.strengths ?? []).length > 0 && (
                  <>
                    <h4 className="ai-section-title">Identified strengths</h4>
                    <div className="ai-strengths">
                      {selected.ai_audit.strengths?.map((strength, index) => (
                        <p key={index}><CheckCircle2 size={15} />{strength}</p>
                      ))}
                    </div>
                  </>
                )}

                <h4 className="ai-section-title">
                  AI findings ({selected.ai_audit.findings?.length ?? 0})
                </h4>
                {(selected.ai_audit.findings ?? []).length > 0 ? (
                  selected.ai_audit.findings?.map((finding, index) => (
                    <article className="report-finding ai-finding" key={index}>
                      <div>
                        <span className={`severity-text ${severityClass(finding.severity)}`}>
                          {(finding.severity || 'info').toUpperCase()}
                        </span>
                        <strong>{finding.title || finding.type || 'Review note'}</strong>
                      </div>
                      {(finding.explanation || finding.message) && (
                        <p>{finding.explanation || finding.message}</p>
                      )}
                      {finding.evidence && <code>{finding.evidence}</code>}
                      {finding.file && <code>{finding.file}{finding.line ? `:${finding.line}` : ''}</code>}
                      {finding.recommendation && (
                        <p><strong>Recommendation:</strong> {finding.recommendation}</p>
                      )}
                    </article>
                  ))
                ) : (
                  <p className="muted-text">The AI review returned no structured findings. This does not prove the project is issue-free.</p>
                )}

                {(selected.ai_audit.files_reviewed ?? []).length > 0 && (
                  <>
                    <h4 className="ai-section-title">
                      Files reviewed ({selected.ai_audit.files_reviewed_count ?? selected.ai_audit.files_reviewed?.length})
                    </h4>
 
<div className="ai-file-list">
  {selected.ai_audit.files_reviewed?.map((file, index) => (
    <code key={`${file.path}-${index}`}>
      <FileCode2 size={13} />
      {file.path} ({file.line_count} lines)
    </code>
  ))}
</div>

                  </>
                )}

                {(selected.ai_audit.limitations ?? []).length > 0 && (
                  <>
                    <h4 className="ai-section-title">Review limitations</h4>
                    <ul className="ai-limitations">
                      {selected.ai_audit.limitations?.map((limitation, index) => (
                        <li key={index}>{limitation}</li>
                      ))}
                    </ul>
                  </>
                )}

                <div className="ai-disclaimer">
                  <CircleAlert size={15} />
                  AI-generated observations are advisory, not verified test results. The model only reviewed the selected source files; no project code was executed.
                </div>
              </section>
            )}

            <div className="modal-footer">
              <span><ShieldCheck size={15} /> No code execution performed</span>
              <button className="secondary-button" onClick={() => setSelected(null)}>
                Close report
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  )
}

export default App
