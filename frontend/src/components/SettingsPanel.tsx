/**
 * Settings panel — tabs: Seller Profile, API Keys, Session Budget, Memory Store, Capability Map.
 */
import { useEffect, useState } from 'react'
import type { CapabilityMapEntry } from '../api/client'
import { memoryApi, settingsApi } from '../api/client'

type Tab = 'seller-profile' | 'api-keys' | 'session-budget' | 'memory' | 'capability-map'

const TABS: { id: Tab; label: string }[] = [
  { id: 'seller-profile', label: 'Seller Profile' },
  { id: 'api-keys', label: 'API Keys' },
  { id: 'session-budget', label: 'Budget' },
  { id: 'memory', label: 'Memory' },
  { id: 'capability-map', label: 'Capability Map' },
]

// ── Seller Profile Tab ─────────────────────────────────────────────────────

interface SalesPlay { play: string; category: string }
interface ProofPoint { customer: string; summary: string }
interface SellerIntelligenceData {
  differentiators: string[]
  sales_plays: SalesPlay[]
  proof_points: ProofPoint[]
  competitive_positioning: string[]
  last_scraped: string | null
}

function SellerProfileTab() {
  const [companyName, setCompanyName] = useState('')
  const [portfolioSummary, setPortfolioSummary] = useState('')
  const [portfolioItems, setPortfolioItems] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [intelligence, setIntelligence] = useState<SellerIntelligenceData | null>(null)
  const [saved, setSaved] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)

  useEffect(() => {
    settingsApi.getSellerProfile().then((d: Record<string, unknown>) => {
      setCompanyName(d.company_name as string ?? '')
      setPortfolioSummary(d.portfolio_summary as string ?? '')
      setPortfolioItems(((d.portfolio_items as string[]) ?? []).join('\n'))
      setWebsiteUrl(d.website_url as string ?? '')
      if (d.seller_intelligence) setIntelligence(d.seller_intelligence as SellerIntelligenceData)
    }).catch(() => {})
  }, [])

  async function save() {
    const url = websiteUrl.trim()
    if (url && !url.startsWith('https://')) return
    await settingsApi.putSellerProfile({
      company_name: companyName,
      portfolio_summary: portfolioSummary,
      portfolio_items: portfolioItems.split('\n').map(s => s.trim()).filter(Boolean),
      ...(url ? { website_url: url } : {}),
      ...(intelligence ? { seller_intelligence: intelligence } : {}),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function rescrape() {
    const url = websiteUrl.trim()
    if (!url) return
    setExtracting(true); setExtractError(null)
    try {
      const result = await settingsApi.extractSellerIntelligence({ website_url: url })
      setIntelligence(result.seller_intelligence as SellerIntelligenceData)
    } catch (e) {
      setExtractError(String(e))
    } finally {
      setExtracting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">Company Name</label>
        <input value={companyName} onChange={e => setCompanyName(e.target.value)}
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">Portfolio Summary</label>
        <textarea value={portfolioSummary} onChange={e => setPortfolioSummary(e.target.value)} rows={3}
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">Portfolio Items (one per line)</label>
        <textarea value={portfolioItems} onChange={e => setPortfolioItems(e.target.value)} rows={4}
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">Website URL</label>
        <div className="flex gap-2 mt-1">
          <input value={websiteUrl} onChange={e => setWebsiteUrl(e.target.value)}
            placeholder="https://www.yourcompany.com"
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <button onClick={() => void rescrape()}
            disabled={extracting || !websiteUrl.trim() || !websiteUrl.trim().startsWith('https://')}
            className="rounded-md bg-gray-100 border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 disabled:opacity-50">
            {extracting ? 'Extracting...' : 'Re-scrape'}
          </button>
        </div>
        {extractError && <p className="mt-1 text-xs text-red-500">{extractError}</p>}
      </div>

      {/* Seller Intelligence Section */}
      {intelligence && (intelligence.differentiators?.length > 0 || intelligence.sales_plays?.length > 0 || intelligence.proof_points?.length > 0 || intelligence.competitive_positioning?.length > 0) && (
        <div className="border border-gray-200 rounded-md p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-800">Seller Intelligence</h3>
            {intelligence.last_scraped && (
              <span className="text-xs text-gray-400">
                Last scraped: {new Date(intelligence.last_scraped).toLocaleDateString()}
              </span>
            )}
          </div>

          {intelligence.differentiators?.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Differentiators</label>
              <textarea
                value={intelligence.differentiators.join('\n')}
                onChange={e => setIntelligence({ ...intelligence, differentiators: e.target.value.split('\n').filter(Boolean) })}
                rows={Math.min(intelligence.differentiators.length + 1, 5)}
                className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
          )}

          {intelligence.sales_plays?.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Sales Plays</label>
              {intelligence.sales_plays.map((sp, i) => (
                <div key={i} className="flex gap-2 mb-1">
                  <input value={sp.play}
                    onChange={e => { const plays = [...intelligence.sales_plays]; plays[i] = { ...sp, play: e.target.value }; setIntelligence({ ...intelligence, sales_plays: plays }) }}
                    className="flex-1 rounded border border-gray-200 px-2 py-1 text-sm" placeholder="Play" />
                  <input value={sp.category}
                    onChange={e => { const plays = [...intelligence.sales_plays]; plays[i] = { ...sp, category: e.target.value }; setIntelligence({ ...intelligence, sales_plays: plays }) }}
                    className="w-40 rounded border border-gray-200 px-2 py-1 text-sm" placeholder="Category" />
                </div>
              ))}
            </div>
          )}

          {intelligence.proof_points?.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Proof Points</label>
              {intelligence.proof_points.map((pp, i) => (
                <div key={i} className="flex gap-2 mb-1">
                  <input value={pp.customer}
                    onChange={e => { const pts = [...intelligence.proof_points]; pts[i] = { ...pp, customer: e.target.value }; setIntelligence({ ...intelligence, proof_points: pts }) }}
                    className="w-32 rounded border border-gray-200 px-2 py-1 text-sm" placeholder="Customer" />
                  <input value={pp.summary}
                    onChange={e => { const pts = [...intelligence.proof_points]; pts[i] = { ...pp, summary: e.target.value }; setIntelligence({ ...intelligence, proof_points: pts }) }}
                    className="flex-1 rounded border border-gray-200 px-2 py-1 text-sm" placeholder="Summary" />
                </div>
              ))}
            </div>
          )}

          {intelligence.competitive_positioning?.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Competitive Positioning</label>
              <textarea
                value={intelligence.competitive_positioning.join('\n')}
                onChange={e => setIntelligence({ ...intelligence, competitive_positioning: e.target.value.split('\n').filter(Boolean) })}
                rows={Math.min(intelligence.competitive_positioning.length + 1, 4)}
                className="w-full rounded border border-gray-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
          )}
        </div>
      )}

      <button onClick={() => void save()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
        {saved ? 'Saved!' : 'Save'}
      </button>
    </div>
  )
}

// ── API Keys Tab ───────────────────────────────────────────────────────────

function ApiKeysTab() {
  const [jsearch, setJsearch] = useState('')
  const [tavily, setTavily] = useState('')
  const [llmProvider, setLlmProvider] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    settingsApi.getApiKeys().then((d) => {
      // Keys are masked by backend (e.g. "***4321"); show as-is for provider/model
      setLlmProvider(d.llm_provider as string ?? '')
      setLlmModel(d.llm_model as string ?? '')
    }).catch(() => {})
  }, [])

  async function save() {
    await settingsApi.putApiKeys({ jsearch, tavily, llm_provider: llmProvider, llm_model: llmModel })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="space-y-4">
      {[
        { label: 'JSearch API Key', value: jsearch, set: setJsearch, type: 'password' as const, placeholder: '•••••••••' },
        { label: 'Tavily API Key', value: tavily, set: setTavily, type: 'password' as const, placeholder: '•••••••••' },
        { label: 'LLM Provider', value: llmProvider, set: setLlmProvider, type: 'text' as const, placeholder: 'openai' },
        { label: 'LLM Model', value: llmModel, set: setLlmModel, type: 'text' as const, placeholder: 'gpt-4o-mini (lowercase)' },
      ].map(({ label, value, set, type, placeholder }) => (
        <div key={label}>
          <label className="block text-sm font-medium text-gray-700">{label}</label>
          <input type={type} value={value} onChange={e => set(e.target.value)} placeholder={placeholder}
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>
      ))}
      <button onClick={() => void save()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
        {saved ? 'Saved!' : 'Save'}
      </button>
    </div>
  )
}

// ── Session Budget Tab ─────────────────────────────────────────────────────

function SessionBudgetTab() {
  const [maxUsd, setMaxUsd] = useState('0.50')
  const [tier3Limit, setTier3Limit] = useState('1')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    settingsApi.getSessionBudget().then((d: Record<string, unknown>) => {
      setMaxUsd(String(d.max_usd ?? '0.50'))
      setTier3Limit(String(d.tier3_limit ?? '1'))
    }).catch(() => {})
  }, [])

  async function save() {
    await settingsApi.putSessionBudget({ max_usd: parseFloat(maxUsd), tier3_limit: parseInt(tier3Limit, 10) })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">Max cost per session ($)</label>
        <input type="number" step="0.01" min="0.01" value={maxUsd} onChange={e => setMaxUsd(e.target.value)}
          className="mt-1 w-40 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">Tier 3 enrichment limit</label>
        <input type="number" min="0" value={tier3Limit} onChange={e => setTier3Limit(e.target.value)}
          className="mt-1 w-40 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <button onClick={() => void save()}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
        {saved ? 'Saved!' : 'Save'}
      </button>
    </div>
  )
}

// ── Memory Tab ─────────────────────────────────────────────────────────────

function MemoryTab() {
  const [records, setRecords] = useState<Array<Record<string, unknown>>>([])

  useEffect(() => {
    memoryApi.list().then((d: Array<Record<string, unknown>>) => setRecords(d)).catch(() => {})
  }, [])

  async function deleteRecord(id: string) {
    await memoryApi.delete(id)
    setRecords(prev => prev.filter(r => r.record_id !== id))
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-600">{records.length} records</span>
        <a href={memoryApi.exportCsv()} download="memory.csv"
          className="text-sm text-blue-600 hover:underline">
          Export CSV
        </a>
      </div>
      {records.length === 0 ? (
        <p className="text-sm text-gray-400">No memory records yet.</p>
      ) : (
        <div className="divide-y divide-gray-100 border border-gray-200 rounded-md overflow-hidden">
          {records.map(r => (
            <div key={String(r.record_id)} className="flex items-center justify-between px-3 py-2 text-sm">
              <div>
                <span className="font-medium">{String(r.company_name ?? '')}</span>
                <span className="mx-1 text-gray-400">—</span>
                <span className="text-gray-600">{String(r.persona_title ?? '')}</span>
              </div>
              <button onClick={() => void deleteRecord(String(r.record_id))}
                className="text-xs text-red-500 hover:underline">Delete</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Capability Map Tab ─────────────────────────────────────────────────────

function CapabilityMapTab() {
  const [entries, setEntries] = useState<CapabilityMapEntry[]>([])
  const [generating, setGenerating] = useState(false)
  const [genInput, setGenInput] = useState('')
  const [genMode, setGenMode] = useState<'product_list' | 'product_url' | 'territory_text'>('product_list')
  const [addingEntry, setAddingEntry] = useState(false)
  const [newId, setNewId] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newSignals, setNewSignals] = useState('')

  useEffect(() => {
    settingsApi.getCapabilityMap().then(setEntries).catch(() => {})
  }, [])

  async function regenerate() {
    setGenerating(true)
    try {
      await settingsApi.generateCapabilityMap({ [genMode]: genInput })
      const d = await settingsApi.getCapabilityMap()
      setEntries(d)
    } finally {
      setGenerating(false)
    }
  }

  async function addEntry() {
    if (!newId.trim() || !newLabel.trim()) return
    const entry: CapabilityMapEntry = {
      id: newId.trim(),
      label: newLabel.trim(),
      problem_signals: newSignals.split('\n').map(s => s.trim()).filter(Boolean),
      solution_areas: [],
    }
    await settingsApi.addCapabilityMapEntry(entry)
    setEntries(prev => [...prev, entry])
    setNewId(''); setNewLabel(''); setNewSignals('')
    setAddingEntry(false)
  }

  async function deleteEntry(id: string) {
    await settingsApi.deleteCapabilityMapEntry(id)
    setEntries(prev => prev.filter(e => e.id !== id))
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Regenerate from</label>
        <div className="flex gap-2 mb-2">
          {(['product_list', 'product_url', 'territory_text'] as const).map(m => (
            <button key={m} onClick={() => setGenMode(m)}
              className={`px-2 py-1 text-xs rounded ${genMode === m ? 'bg-blue-600 text-white' : 'border border-gray-300 text-gray-600'}`}>
              {m.replace('_', ' ')}
            </button>
          ))}
        </div>
        <textarea value={genInput} onChange={e => setGenInput(e.target.value)} rows={3}
          placeholder={genMode === 'product_url' ? 'https://example.com/products' : genMode === 'product_list' ? 'Product A\nProduct B' : 'Describe your focus area…'}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        <button onClick={() => void regenerate()} disabled={generating || !genInput.trim()}
          className="mt-2 rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50">
          {generating ? 'Generating…' : 'Regenerate'}
        </button>
      </div>

      {/* Entry list */}
      {entries.length > 0 && (
        <div className="border border-gray-200 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Category</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Problem Signals</th>
                <th className="px-3 py-2 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map(e => (
                <tr key={e.id}>
                  <td className="px-3 py-2 font-medium">{e.label}</td>
                  <td className="px-3 py-2 text-gray-600 text-xs">{e.problem_signals.join(', ')}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => void deleteEntry(e.id)}
                      className="text-xs text-red-500 hover:underline" aria-label={`Delete ${e.label}`}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add entry */}
      {addingEntry ? (
        <div className="rounded-md border border-gray-200 p-3 space-y-2">
          <input value={newId} onChange={e => setNewId(e.target.value)} placeholder="ID (e.g. cost-management)"
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
          <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Label (e.g. Cost Management)"
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
          <textarea value={newSignals} onChange={e => setNewSignals(e.target.value)} rows={3}
            placeholder="Problem signals (one per line)"
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
          <div className="flex gap-2">
            <button onClick={() => void addEntry()} disabled={!newId.trim() || !newLabel.trim()}
              className="px-3 py-1 text-sm bg-gray-800 text-white rounded hover:bg-gray-700 disabled:opacity-50">
              Add
            </button>
            <button onClick={() => setAddingEntry(false)} className="px-3 py-1 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAddingEntry(true)} className="text-sm text-blue-600 hover:underline">
          + Add entry
        </button>
      )}
    </div>
  )
}

// ── SettingsPanel ──────────────────────────────────────────────────────────

interface Props {
  onClose: () => void
}

export function SettingsPanel({ onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('seller-profile')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Settings</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600" aria-label="Close settings">✕</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 px-6">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={[
                'px-4 py-3 text-sm font-medium border-b-2 -mb-px',
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700',
              ].join(' ')}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {activeTab === 'seller-profile' && <SellerProfileTab />}
          {activeTab === 'api-keys' && <ApiKeysTab />}
          {activeTab === 'session-budget' && <SessionBudgetTab />}
          {activeTab === 'memory' && <MemoryTab />}
          {activeTab === 'capability-map' && <CapabilityMapTab />}
        </div>
      </div>
    </div>
  )
}
