import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { createJob, subscribeJob, JobStage, getJob } from './api'

interface ProgressEvent {
  stage?: JobStage
  message?: string
  words?: number
  chunk?: string
  raw_text?: string
  formatted_text?: string
  error?: string
}

type DisplayStage = {
  label: string
  key: JobStage
}

const stages: DisplayStage[] = [
  { key: 'downloading', label: '下载音频' },
  { key: 'transcribing', label: '转录中' },
  { key: 'formatting', label: '整理中' },
  { key: 'done', label: '完成' },
  { key: 'error', label: '失败' },
]

function StageBadge({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 10,
        height: 10,
        borderRadius: '50%',
        background: active ? '#4caf50' : '#ccc',
        marginRight: 6,
      }}
    ></span>
  )
}

export default function App() {
  const [url, setUrl] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [stage, setStage] = useState<JobStage | 'pending'>('pending')
  const [wordCount, setWordCount] = useState(0)
  const [formatted, setFormatted] = useState('')
  const [raw, setRaw] = useState('')
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const stageRef = useRef<JobStage | 'pending'>('pending')
  const [searchParams] = useSearchParams()

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  const resetView = () => {
    setError(null)
    setFormatted('')
    setRaw('')
    setWordCount(0)
  }

  const handleStreamMessage = (payload: ProgressEvent) => {
    if (payload.stage) {
      setStage(payload.stage)
      stageRef.current = payload.stage
    }
    const currentStage = payload.stage ?? stageRef.current
    if (payload.words !== undefined) setWordCount(payload.words)
    if (payload.chunk && currentStage === 'transcribing') setRaw((prev) => prev + payload.chunk)
    if (payload.chunk && currentStage === 'formatting') setFormatted((prev) => prev + payload.chunk)
    if (payload.raw_text) setRaw(payload.raw_text)
    if (payload.formatted_text) setFormatted(payload.formatted_text)
    if (payload.error) setError(payload.error)
  }

  const connectWebSocket = (id: string) => {
    wsRef.current?.close()
    const ws = subscribeJob(id, handleStreamMessage)
    wsRef.current = ws
  }

  const startJob = async (e: FormEvent) => {
    e.preventDefault()
    resetView()
    try {
      const job = await createJob(url)
      setJobId(job.id)
      setStage('downloading')
      stageRef.current = 'downloading'
      connectWebSocket(job.id)
    } catch (err: any) {
      setError(err?.response?.data?.detail || '创建任务失败')
    }
  }

  const loadJobFromQuery = async (id: string) => {
    resetView()
    setJobId(id)
    try {
      const job = await getJob(id)
      setStage(job.status)
      stageRef.current = job.status
      setRaw(job.raw_text || '')
      setFormatted(job.formatted_text || '')
      const baseText = job.formatted_text || job.raw_text || ''
      setWordCount(baseText ? baseText.split(/\s+/).filter(Boolean).length : 0)
      if (job.error) setError(job.error)
      if (job.status !== 'done' && job.status !== 'error') {
        connectWebSocket(id)
      }
    } catch (err) {
      setError('任务不存在或获取失败')
    }
  }

  useEffect(() => {
    const q = searchParams.get('job')
    if (q) {
      loadJobFromQuery(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const stageMap = useMemo(() => Object.fromEntries(stages.map((s) => [s.key, s.label])), [])

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 16 }}>
      <form onSubmit={startJob} style={{ display: 'flex', gap: 12 }}>
        <input
          type="url"
          placeholder="输入 bilibili 视频链接"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ flex: 1, padding: 10, fontSize: 16 }}
          required
        />
        <button type="submit" style={{ padding: '10px 16px' }}>
          开始
        </button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {jobId && (
        <section style={{ marginTop: 20 }}>
          <h3>任务 ID: {jobId}</h3>
          <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
            {stages.map((s) => (
              <span key={s.key} style={{ display: 'inline-flex', alignItems: 'center' }}>
                <StageBadge active={stage === s.key || stage === 'done'} />
                {s.label}
              </span>
            ))}
          </div>
          <p>当前阶段: {stageMap[stage as JobStage] || stage}</p>
          <p>已处理字数: {wordCount}</p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <h4>原始转录</h4>
              <pre style={{ whiteSpace: 'pre-wrap', background: '#f7f7f7', padding: 12, minHeight: 200 }}>{raw}</pre>
            </div>
            <div>
              <h4>整理后文本</h4>
              <pre style={{ whiteSpace: 'pre-wrap', background: '#f0f7ff', padding: 12, minHeight: 200 }}>{formatted}</pre>
            </div>
          </div>
        </section>
      )}
    </main>
  )
}
