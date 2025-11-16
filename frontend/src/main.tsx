import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import App from './App'
import History from './pages/History'

const client = new QueryClient()

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <header style={{ padding: '12px', borderBottom: '1px solid #ddd', marginBottom: 12 }}>
          <nav style={{ display: 'flex', gap: 12 }}>
            <Link to="/">首页</Link>
            <Link to="/history">历史记录</Link>
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
