/**
 * First-run setup wizard — seller profile + API keys + capability map.
 * Three steps: Seller Profile → API Keys → Capability Map.
 */
import { useState } from 'react'
import { setupApi, settingsApi } from '../api/client'

type Step = 'seller-profile' | 'api-keys' | 'capability-map' | 'done'
type GenMode = 'product_list' | 'product_url' | 'territory_text'

interface Props {
  onComplete: () => void
}

export function SetupWizard({ onComplete }: Props) {
  const [step, setStep] = useState<Step>('seller-profile')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Seller profile fields
  const [companyName, setCompanyName] = useState('')
  const [portfolioSummary, setPortfolioSummary] = useState('')
  const [portfolioItems, setPortfolioItems] = useState('')

  // API key fields
  const [jsearch, setJsearch] = useState('')
  const [tavily, setTavily] = useState('')
  const [llmProvider, setLlmProvider] = useState('anthropic')
  const [llmModel, setLlmModel] = useState('claude-sonnet-4-6')

  // Capability map fields
  const [genMode, setGenMode] = useState<GenMode>('product_list')
  const [genInput, setGenInput] = useState('')
  const [generating, setGenerating] = useState(false)
  const [capGenerated, setCapGenerated] = useState(false)

  async function saveSellerProfile() {
    if (!companyName.trim()) { setError('Company name is required'); return }
    setSaving(true); setError(null)
    try {
      await settingsApi.putSellerProfile({
        company_name: companyName.trim(),
        portfolio_summary: portfolioSummary.trim(),
        portfolio_items: portfolioItems.split('\n').map(s => s.trim()).filter(Boolean),
      })
      setStep('api-keys')
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function saveApiKeys() {
    setSaving(true); setError(null)
    try {
      await settingsApi.putApiKeys({ jsearch, tavily, llm_provider: llmProvider, llm_model: llmModel })
      setStep('capability-map')
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function generateCapabilityMap() {
    if (!genInput.trim()) { setError('Input is required'); return }
    setGenerating(true); setError(null)
    try {
      await settingsApi.generateCapabilityMap({ [genMode]: genInput.trim() })
      setCapGenerated(true)
    } catch (e) {
      setError(String(e))
    } finally {
      setGenerating(false)
    }
  }

  async function completeSetup() {
    setSaving(true); setError(null)
    try {
      // Mark setup as complete by saving a valid config
      await setupApi.saveConfig({})
      onComplete()
    } catch {
      onComplete() // proceed even if save fails
    } finally {
      setSaving(false)
    }
  }

  const STEP_LABELS: Record<Step, string> = {
    'seller-profile': '1. Seller Profile',
    'api-keys': '2. API Keys',
    'capability-map': '3. Capability Map',
    done: 'Done',
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-100">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Welcome to SignalForge</h1>
          <p className="mt-1 text-sm text-gray-500">
            Let's set up your workspace. This takes about 2 minutes.
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex gap-2 mb-8 text-xs">
          {(['seller-profile', 'api-keys', 'capability-map'] as const).map(s => (
            <div key={s} className={[
              'flex-1 rounded py-1 text-center font-medium',
              step === s ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-400',
            ].join(' ')}>
              {STEP_LABELS[s]}
            </div>
          ))}
        </div>

        {error && (
          <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* ── Step 1: Seller Profile ── */}
        {step === 'seller-profile' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Your Company Name *</label>
              <input value={companyName} onChange={e => setCompanyName(e.target.value)}
                placeholder="Acme Corp"
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Portfolio Summary</label>
              <textarea value={portfolioSummary} onChange={e => setPortfolioSummary(e.target.value)}
                placeholder="Brief description of what you sell…"
                rows={3}
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Products / Services (one per line)</label>
              <textarea value={portfolioItems} onChange={e => setPortfolioItems(e.target.value)}
                placeholder="Kubernetes Optimizer&#10;Cost Analytics&#10;Security Scanner"
                rows={4}
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <button onClick={() => void saveSellerProfile()} disabled={saving}
              className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
              {saving ? 'Saving…' : 'Next →'}
            </button>
          </div>
        )}

        {/* ── Step 2: API Keys ── */}
        {step === 'api-keys' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Keys are stored locally in <code>~/.signalforge/config.json</code> and never sent to SignalForge servers.
            </p>
            {[
              { label: 'JSearch API Key', value: jsearch, set: setJsearch },
              { label: 'Tavily API Key', value: tavily, set: setTavily },
              { label: 'LLM Provider (e.g. anthropic)', value: llmProvider, set: setLlmProvider },
              { label: 'LLM Model (e.g. claude-sonnet-4-6)', value: llmModel, set: setLlmModel },
            ].map(({ label, value, set }) => (
              <div key={label}>
                <label className="block text-sm font-medium text-gray-700">{label}</label>
                <input type={label.includes('Key') ? 'password' : 'text'}
                  value={value} onChange={e => set(e.target.value)}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            ))}
            <div className="flex gap-3">
              <button onClick={() => setStep('seller-profile')}
                className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
                ← Back
              </button>
              <button onClick={() => void saveApiKeys()} disabled={saving}
                className="flex-1 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {saving ? 'Saving…' : 'Next →'}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Capability Map ── */}
        {step === 'capability-map' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Generate a capability map so SignalForge can match signals to your solutions.
            </p>
            <div className="flex gap-2">
              {(['product_list', 'product_url', 'territory_text'] as const).map(m => (
                <button key={m} onClick={() => setGenMode(m)}
                  className={`flex-1 px-2 py-1.5 text-xs rounded border ${genMode === m ? 'bg-blue-600 text-white border-blue-600' : 'border-gray-300 text-gray-600'}`}>
                  {m === 'product_list' ? 'Product List' : m === 'product_url' ? 'Product URL' : 'Territory Text'}
                </button>
              ))}
            </div>
            <textarea value={genInput} onChange={e => setGenInput(e.target.value)} rows={4}
              placeholder={
                genMode === 'product_url' ? 'https://example.com/products' :
                genMode === 'product_list' ? 'Kubernetes Optimizer\nCost Analytics' :
                'We focus on cloud cost management for enterprise teams…'
              }
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />

            {capGenerated && (
              <div className="rounded-md bg-green-50 border border-green-300 px-3 py-2 text-sm text-green-700">
                ✓ Capability map generated successfully!
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={() => setStep('api-keys')}
                className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
                ← Back
              </button>
              {!capGenerated ? (
                <button onClick={() => void generateCapabilityMap()} disabled={generating || !genInput.trim()}
                  className="flex-1 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                  {generating ? 'Generating…' : 'Generate'}
                </button>
              ) : (
                <button onClick={() => void completeSetup()} disabled={saving}
                  className="flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50">
                  {saving ? 'Finishing…' : 'Get Started →'}
                </button>
              )}
            </div>
            <button onClick={() => void completeSetup()} className="w-full text-sm text-gray-400 hover:text-gray-600">
              Skip for now
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
