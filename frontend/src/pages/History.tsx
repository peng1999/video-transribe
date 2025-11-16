import { useQuery } from '@tanstack/react-query'
import { listJobs } from '../api'
import { Link } from 'react-router-dom'

export default function History() {
  const { data, isLoading, error } = useQuery({ queryKey: ['jobs'], queryFn: listJobs })

  if (isLoading) return <p>加载中...</p>
  if (error) return <p>加载失败</p>

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: 16 }}>
      <h3>历史记录</h3>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {data?.map((job) => (
          <li key={job.id} style={{ padding: '8px 0', borderBottom: '1px solid #eee' }}>
            <strong>{job.status}</strong> · {job.url}
            <div style={{ fontSize: 12, color: '#555' }}>创建时间: {new Date(job.created_at).toLocaleString()}</div>
            {job.formatted_text && <p style={{ margin: '6px 0', color: '#222' }}>{job.formatted_text.slice(0, 120)}...</p>}
            <Link to={`/?job=${job.id}`}>查看</Link>
          </li>
        ))}
      </ul>
    </main>
  )
}
