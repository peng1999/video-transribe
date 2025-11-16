import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Container,
  Grid,
  Group,
  Loader,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { IconAlertCircle } from '@tabler/icons-react'
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
    <Container size="lg" py="md">
      <Card withBorder shadow="xs" padding="lg" radius="md">
        <form onSubmit={startJob}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-end">
              <Title order={3}>Bilibili 文字转录</Title>
              <Badge color="blue" variant="light">
                gpt-4o-mini-transcribe + DeepSeek
              </Badge>
            </Group>
            <Anchor size="sm" component={Link} to="/history" c="blue.6">
              查看历史记录
            </Anchor>
            <TextInput
              type="url"
              label="视频链接"
              placeholder="输入 bilibili 视频链接"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            <Group justify="flex-end">
              <Button type="submit">开始</Button>
            </Group>
          </Stack>
        </form>
      </Card>

      {error && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" mt="md">
          {error}
        </Alert>
      )}

      {jobId && (
        <Card withBorder shadow="xs" mt="md" padding="lg" radius="md">
          <Stack gap="sm">
            <Group justify="space-between">
              <div>
                <Text size="sm" c="dimmed">
                  任务 ID
                </Text>
                <Text fw={600}>{jobId}</Text>
              </div>
              <Group gap="xs">
                {stages.map((s) => (
                  <Badge key={s.key} color={stage === s.key ? 'blue' : 'gray'} variant={stage === s.key ? 'filled' : 'light'}>
                    {s.label}
                  </Badge>
                ))}
              </Group>
            </Group>

            <Group gap="md">
              <Text>当前阶段：{stageMap[stage as JobStage] || stage}</Text>
              <Text c="dimmed">已处理字数：{wordCount}</Text>
            </Group>

            <Grid gutter="md">
              <Grid.Col span={6}>
                <Card padding="md" radius="sm" withBorder>
                  <Group gap={6} mb="xs">
                    <Title order={5}>原始转录</Title>
                    {stage === 'transcribing' && <Loader size="sm" />}
                  </Group>
                  <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                    {raw || '（等待转录中...）'}
                  </Text>
                </Card>
              </Grid.Col>
              <Grid.Col span={6}>
                <Card padding="md" radius="sm" withBorder>
                  <Group gap={6} mb="xs">
                    <Title order={5}>整理后文本</Title>
                    {stage === 'formatting' && <Loader size="sm" />}
                  </Group>
                  <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                    {formatted || '（等待整理中...）'}
                  </Text>
                </Card>
              </Grid.Col>
            </Grid>
          </Stack>
        </Card>
      )}
    </Container>
  )
}
