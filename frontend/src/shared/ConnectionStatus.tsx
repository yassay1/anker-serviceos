import { useQuery } from '@tanstack/react-query'
import { readHealth } from '../api/client'
import { queryKeys } from '../app/queryKeys'

export function ConnectionStatus() {
  const health = useQuery({ queryKey: queryKeys.health, queryFn: ({ signal }) => readHealth(signal) })
  return (
    <div className="connection" aria-label="本地服务连接状态">
      <span role="status" aria-live="polite">
        <span className={`status-dot ${health.isError ? 'offline' : ''}`} aria-hidden="true" />
        {health.isFetching ? '正在检查服务' : health.isError ? '本地服务未连接' : '本地服务已连接'}
      </span>
      <button type="button" disabled={health.isFetching} onClick={() => void health.refetch()}>重新检查</button>
    </div>
  )
}
