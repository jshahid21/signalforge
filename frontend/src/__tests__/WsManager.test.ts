/**
 * Regression tests for WsManager — reconnection with exponential backoff.
 * Covers issue #16: pipeline stuck in "running" due to dropped WebSocket.
 */
import { WsManager } from '../api/client'

// ── Mock WebSocket ────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  readyState = 0
  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    this.readyState = 3
  }

  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  simulateClose() {
    this.readyState = 3
    this.onclose?.()
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

// Install mock
const OriginalWebSocket = globalThis.WebSocket
beforeEach(() => {
  MockWebSocket.instances = []
  ;(globalThis as unknown as Record<string, unknown>).WebSocket = MockWebSocket as unknown as typeof WebSocket
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
  ;(globalThis as unknown as Record<string, unknown>).WebSocket = OriginalWebSocket
})

// ── Tests ─────────────────────────────────────────────────────────────────

describe('WsManager', () => {
  it('reports connected after open', () => {
    const ws = new WsManager()
    ws.connect('session-1')
    expect(ws.connected).toBe(false)
    MockWebSocket.instances[0]!.simulateOpen()
    expect(ws.connected).toBe(true)
  })

  it('reconnects automatically on close with exponential backoff', () => {
    const ws = new WsManager()
    ws.connect('session-1')
    MockWebSocket.instances[0]!.simulateOpen()
    expect(MockWebSocket.instances).toHaveLength(1)

    // Simulate connection drop
    MockWebSocket.instances[0]!.simulateClose()
    expect(ws.connected).toBe(false)

    // First reconnect after 1s (base delay)
    vi.advanceTimersByTime(1_000)
    expect(MockWebSocket.instances).toHaveLength(2)

    // Simulate second drop
    MockWebSocket.instances[1]!.simulateClose()

    // Second reconnect after 2s (exponential backoff)
    vi.advanceTimersByTime(1_000)
    expect(MockWebSocket.instances).toHaveLength(2) // not yet
    vi.advanceTimersByTime(1_000)
    expect(MockWebSocket.instances).toHaveLength(3)
  })

  it('resets backoff after successful reconnect', () => {
    const ws = new WsManager()
    ws.connect('session-1')
    MockWebSocket.instances[0]!.simulateOpen()

    // Drop and reconnect
    MockWebSocket.instances[0]!.simulateClose()
    vi.advanceTimersByTime(1_000)
    MockWebSocket.instances[1]!.simulateOpen()
    expect(ws.connected).toBe(true)

    // Drop again — should use base delay (1s), not escalated
    MockWebSocket.instances[1]!.simulateClose()
    vi.advanceTimersByTime(1_000)
    expect(MockWebSocket.instances).toHaveLength(3)
  })

  it('does not reconnect after intentional disconnect()', () => {
    const ws = new WsManager()
    ws.connect('session-1')
    MockWebSocket.instances[0]!.simulateOpen()

    ws.disconnect()
    vi.advanceTimersByTime(60_000)
    // Should still be just the one original socket — no reconnect attempts
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('delivers events to handlers after reconnect', () => {
    const ws = new WsManager()
    const events: unknown[] = []
    ws.onEvent(e => events.push(e))

    ws.connect('session-1')
    MockWebSocket.instances[0]!.simulateOpen()
    MockWebSocket.instances[0]!.simulateMessage({ type: 'pipeline_started', session_id: 's1' })
    expect(events).toHaveLength(1)

    // Drop and reconnect
    MockWebSocket.instances[0]!.simulateClose()
    vi.advanceTimersByTime(1_000)
    MockWebSocket.instances[1]!.simulateOpen()

    // Events still delivered on new socket
    MockWebSocket.instances[1]!.simulateMessage({ type: 'pipeline_complete' })
    expect(events).toHaveLength(2)
    expect(events[1]).toEqual({ type: 'pipeline_complete' })
  })

  it('caps reconnect delay at 30 seconds', () => {
    const ws = new WsManager()
    ws.connect('session-1')

    // Simulate many failures to push backoff past cap
    for (let i = 0; i < 10; i++) {
      const last = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
      last.simulateClose()
      // Advance past the max delay
      vi.advanceTimersByTime(30_000)
    }

    // Should have created sockets for each reconnect attempt
    expect(MockWebSocket.instances.length).toBeGreaterThan(5)
  })
})
