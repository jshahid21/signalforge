/**
 * Settings panel — tabs: Seller Profile, API Keys, Session Budget, Memory Store, Capability Map.
 */
import React, { useEffect, useRef, useState } from 'react'
import type { CapabilityMapEntry, SalesPlayEntry, ProofPointEntry } from '../api/client'
import { memoryApi, settingsApi } from '../api/client'

type Tab = 'seller-profile' | 'api-keys' | 'session-budget' | 'langsmith' | 'memory' | 'capability-map'

const TABS: { id: Tab; label: string }[] = [
  { id: 'seller-profile', label: 'Seller Profile' },
  { id: 'api-keys', label: 'API Keys' },
  { id: 'session-budget', label: 'Budget' },
  { id: 'langsmith', label: 'LangSmith' },
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

type ExtractSource = 'url' | 'files' | 'text'

function SellerProfileTab() {
  const [companyName, setCompanyName] = useState('')
  const [portfolioSummary, setPortfolioSummary] = useState('')
  const [portfolioItems, setPortfolioItems] = useState('')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [intelligence, setIntelligence] = useState<SellerIntelligenceData | null>(null)
  const [saved, setSaved] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)
  const [extractSource, setExtractSource] = useState<ExtractSource>('url')
  const [pasteText, setPasteText] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  async function extractIntelligence() {
    setExtracting(true); setExtractError(null)
    try {
      let result: Record<string, unknown>
      if (extractSource === 'url') {
        const url = websiteUrl.trim()
        if (!url) return
        result = await settingsApi.extractSellerIntelligence({ website_url: url })
      } else if (extractSource === 'files') {
        if (selectedFiles.length === 0) return
        result = await settingsApi.extractFromFiles(selectedFiles)
      } else {
        if (!pasteText.trim()) return
        result = await settingsApi.extractSellerIntelligence({ text: pasteText.trim() })
      }
      setIntelligence(result!.seller_intelligence as SellerIntelligenceData)
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

      {/* Intelligence extraction — multi-source */}
      <div className="border border-gray-200 rounded-md p-4 space-y-3">
        <label className="block text-sm font-medium text-gray-700">Extract Intelligence</label>
        <div className="flex gap-2">
          {([['url', 'Website URL'], ['files', 'Upload Files'], ['text', 'Paste Text']] as const).map(([value, label]) => (
            <button key={value} type="button" onClick={() => setExtractSource(value)}
              className={`px-3 py-1.5 text-xs rounded border ${
                extractSource === value ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}>
              {label}
            </button>
          ))}
        </div>

        {extractSource === 'url' && (
          <div className="flex gap-2">
            <input value={websiteUrl} onChange={e => setWebsiteUrl(e.target.value)}
              placeholder="https://www.yourcompany.com"
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        )}
        {extractSource === 'files' && (
          <div>
            <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.pptx,.xlsx,.html,.htm,.txt"
              onChange={e => setSelectedFiles(Array.from(e.target.files || []))}
              className="w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" />
            <p className="mt-1 text-xs text-gray-400">PDF, DOCX, PPTX, XLSX, HTML, TXT (max 5 files, 10MB each)</p>
            {selectedFiles.length > 0 && (
              <p className="mt-1 text-xs text-green-600">{selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected</p>
            )}
          </div>
        )}
        {extractSource === 'text' && (
          <textarea value={pasteText} onChange={e => setPasteText(e.target.value)}
            placeholder="Paste content from pitch decks, case studies, battlecards..."
            rows={4}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        )}

        <button onClick={() => void extractIntelligence()}
          disabled={extracting || (extractSource === 'url' && (!websiteUrl.trim() || !websiteUrl.trim().startsWith('https://')))
            || (extractSource === 'files' && selectedFiles.length === 0)
            || (extractSource === 'text' && !pasteText.trim())}
          className="rounded-md bg-gray-100 border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-200 disabled:opacity-50">
          {extracting ? 'Extracting...' : extractSource === 'url' ? 'Re-scrape' : extractSource === 'files' ? 'Extract from Files' : 'Extract from Text'}
        </button>
        {extractError && <p className="mt-1 text-xs text-red-500">{extractError}</p>}
      </div>

      {/* Seller Intelligence Section */}
      {intelligence && (
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

          {!intelligence.differentiators?.length && !intelligence.sales_plays?.length && !intelligence.proof_points?.length && !intelligence.competitive_positioning?.length && (
            <p className="text-sm text-gray-400">No intelligence extracted yet. Enter a website URL above and click Re-scrape.</p>
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

// ── LangSmith Tab ─────────────────────────────────────────────────────────

function LangSmithTab() {
  const [enabled, setEnabled] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [project, setProject] = useState('signalforge')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    settingsApi.getLangsmith().then((d: Record<string, unknown>) => {
      setEnabled(d.enabled as boolean ?? false)
      setProject(d.project as string ?? 'signalforge')
      // api_key comes back masked; leave field empty so user can type a new one
    }).catch(() => {})
  }, [])

  async function save() {
    await settingsApi.putLangsmith({ enabled, api_key: apiKey, project })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        Enable LangSmith tracing to send all LLM calls and pipeline runs to{' '}
        <a href="https://smith.langchain.com" target="_blank" rel="noreferrer"
          className="text-blue-600 hover:underline">smith.langchain.com</a>.
        Free tier available.
      </p>
      <div className="flex items-center gap-3">
        <label className="relative inline-flex cursor-pointer items-center">
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}
            className="peer sr-only" />
          <div className="h-6 w-11 rounded-full bg-gray-200 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all peer-checked:bg-blue-600 peer-checked:after:translate-x-full peer-checked:after:border-white" />
        </label>
        <span className="text-sm font-medium text-gray-700">{enabled ? 'Enabled' : 'Disabled'}</span>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">LangSmith API Key</label>
        <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
          placeholder="lsv2_pt_••••••••"
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">Project Name</label>
        <input value={project} onChange={e => setProject(e.target.value)}
          placeholder="signalforge"
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
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

// ── Capability Intelligence Editor ─────────────────────────────────────────

function CapabilityIntelligenceEditor({
  entry,
  onSave,
}: {
  entry: CapabilityMapEntry
  onSave: (entryId: string, data: { differentiators?: string[]; sales_plays?: SalesPlayEntry[]; proof_points?: ProofPointEntry[] }) => Promise<void>
}) {
  const [diffs, setDiffs] = useState((entry.differentiators ?? []).join('\n'))
  const [plays, setPlays] = useState(
    (entry.sales_plays ?? []).map(sp => `${sp.play} | ${sp.category}`).join('\n')
  )
  const [proofs, setProofs] = useState(
    (entry.proof_points ?? []).map(pp => `${pp.customer} | ${pp.summary}`).join('\n')
  )
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      const differentiators = diffs.split('\n').map(s => s.trim()).filter(Boolean)
      const sales_plays: SalesPlayEntry[] = plays.split('\n').map(s => s.trim()).filter(Boolean).map(line => {
        const [play, category] = line.split('|').map(p => p.trim())
        return { play: play || line, category: category || 'general' }
      })
      const proof_points: ProofPointEntry[] = proofs.split('\n').map(s => s.trim()).filter(Boolean).map(line => {
        const [customer, summary] = line.split('|').map(p => p.trim())
        return { customer: customer || '', summary: summary || line }
      })
      await onSave(entry.id, { differentiators, sales_plays, proof_points })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 text-xs">
      <div>
        <label className="block font-medium text-gray-600 mb-1">Differentiators (one per line)</label>
        <textarea value={diffs} onChange={e => setDiffs(e.target.value)} rows={2}
          className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:ring-1 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block font-medium text-gray-600 mb-1">Sales Plays (format: play | category, one per line)</label>
        <textarea value={plays} onChange={e => setPlays(e.target.value)} rows={2}
          className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:ring-1 focus:ring-blue-500" />
      </div>
      <div>
        <label className="block font-medium text-gray-600 mb-1">Proof Points (format: customer | summary, one per line)</label>
        <textarea value={proofs} onChange={e => setProofs(e.target.value)} rows={2}
          className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:ring-1 focus:ring-blue-500" />
      </div>
      <button onClick={() => void save()} disabled={saving}
        className="px-3 py-1 text-xs bg-gray-800 text-white rounded hover:bg-gray-700 disabled:opacity-50">
        {saving ? 'Saving...' : 'Save Intelligence'}
      </button>
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
  const [expandedEntry, setExpandedEntry] = useState<string | null>(null)
  const [autoLinking, setAutoLinking] = useState(false)
  const [autoLinkResult, setAutoLinkResult] = useState<string | null>(null)

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

  async function triggerAutoLink() {
    setAutoLinking(true)
    setAutoLinkResult(null)
    try {
      const result = await settingsApi.autoLinkIntelligence()
      setAutoLinkResult(`Linked intelligence to ${result.entries_updated} entries`)
      const d = await settingsApi.getCapabilityMap()
      setEntries(d)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Auto-link failed'
      setAutoLinkResult(msg)
    } finally {
      setAutoLinking(false)
    }
  }

  async function saveIntelligence(entryId: string, data: { differentiators?: string[]; sales_plays?: Array<{ play: string; category: string }>; proof_points?: Array<{ customer: string; summary: string }> }) {
    await settingsApi.patchCapabilityIntelligence(entryId, data)
    const d = await settingsApi.getCapabilityMap()
    setEntries(d)
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

      {/* Auto-link button */}
      {entries.length > 0 && (
        <div className="flex items-center gap-3">
          <button onClick={() => void triggerAutoLink()} disabled={autoLinking}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">
            {autoLinking ? 'Auto-linking...' : 'Auto-Link Intelligence'}
          </button>
          {autoLinkResult && <span className="text-xs text-gray-500">{autoLinkResult}</span>}
        </div>
      )}

      {/* Entry list */}
      {entries.length > 0 && (
        <div className="border border-gray-200 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Category</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Problem Signals</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Intelligence</th>
                <th className="px-3 py-2 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map(e => {
                const hasIntel = (e.differentiators?.length ?? 0) > 0 || (e.sales_plays?.length ?? 0) > 0 || (e.proof_points?.length ?? 0) > 0
                const isExpanded = expandedEntry === e.id
                return (
                  <React.Fragment key={e.id}>
                    <tr>
                      <td className="px-3 py-2 font-medium">{e.label}</td>
                      <td className="px-3 py-2 text-gray-600 text-xs">{e.problem_signals.join(', ')}</td>
                      <td className="px-3 py-2">
                        <button onClick={() => setExpandedEntry(isExpanded ? null : e.id)}
                          className="text-xs text-blue-600 hover:underline">
                          {hasIntel ? `${(e.differentiators?.length ?? 0) + (e.sales_plays?.length ?? 0) + (e.proof_points?.length ?? 0)} items` : 'none'} {isExpanded ? '[-]' : '[+]'}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => void deleteEntry(e.id)}
                          className="text-xs text-red-500 hover:underline" aria-label={`Delete ${e.label}`}>
                          Delete
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={4} className="px-3 py-3 bg-gray-50">
                          <CapabilityIntelligenceEditor entry={e} onSave={saveIntelligence} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
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
          {activeTab === 'langsmith' && <LangSmithTab />}
          {activeTab === 'memory' && <MemoryTab />}
          {activeTab === 'capability-map' && <CapabilityMapTab />}
        </div>
      </div>
    </div>
  )
}
