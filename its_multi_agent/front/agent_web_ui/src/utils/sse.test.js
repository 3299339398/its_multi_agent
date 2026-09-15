import { describe, expect, it } from 'vitest'
import { parseSSELine } from './sse'

describe('SSE response parser', () => {
  it('parses a complete data line', () => {
    expect(parseSSELine('data: {"status":"FINISHED"}')).toEqual({ status: 'FINISHED' })
  })

  it('ignores non-data and empty lines', () => {
    expect(parseSSELine('event: message')).toBeNull()
    expect(parseSSELine('data: ')).toBeNull()
  })

  it('reports truncated JSON in Chinese', () => {
    expect(() => parseSSELine('data: {"status":')).toThrow('服务返回的数据不完整')
  })
})
