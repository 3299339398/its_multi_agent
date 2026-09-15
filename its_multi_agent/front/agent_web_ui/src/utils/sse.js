export const parseSSELine = line => {
  if (typeof line !== 'string' || !line.startsWith('data:')) return null
  const payload = line.slice(5).trim()
  if (!payload) return null

  try {
    return JSON.parse(payload)
  } catch {
    throw new Error('服务返回的数据不完整，请稍后重试')
  }
}
