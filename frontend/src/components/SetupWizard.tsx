/**
 * First-run setup wizard — simplified to two steps.
 * Step 1: About You (company + products + intelligence source)
 * Step 2: API Keys
 * After Step 2: auto-generate capability map + extract intelligence + auto-link.
 */
import { useState, useRef } from 'react'
import { setupApi, settingsApi } from '../api/client'

type Step = 'about-you' | 'api-keys'
type IntelSource = 'none' | 'url' | 'files' | 'text'

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB
const MAX_FILES = 5
const ACCEPTED_EXTENSIONS = '.pdf,.docx,.pptx,.xlsx,.html,.htm,.txt'

interface Props {
  onComplete: () => void
}

export function SetupWizard({ onComplete }: Props) {
  const [step, setStep] = useState<Step>('about-you')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Step 1 fields
  const [companyName, setCompanyName] = useState('')
  const [portfolioItems, setPortfolioItems] = useState('')
  const [intelSource, setIntelSource] = useState<IntelSource>('none')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [pasteText, setPasteText] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Step 2 fields
  const [jsearch, setJsearch] = useState('')
  const [tavily, setTavily] = useState('')
  const [llmProvider, setLlmProvider] = useState('anthropic')
  const [llmModel, setLlmModel] = useState('claude-sonnet-4-6')

  // Post-setup orchestration state
  const [orchestrating, setOrchestrating] = useState(false)
  const [orchestrationStatus, setOrchestrationStatus] = useState<string | null>(null)

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || [])
    // Client-side validation
    if (files.length > MAX_FILES) {
      setError(`Maximum ${MAX_FILES} files allowed.`)
      return
    }
    const oversized = files.find(f => f.size > MAX_FILE_SIZE)
    if (oversized) {
      setError(`File "${oversized.name}" exceeds 10MB limit.`)
      return
    }
    setError(null)
    setSelectedFiles(files)
  }

  async function saveAboutYou() {
    if (!companyName.trim()) { setError('Company name is required'); return }
    if (intelSource === 'url') {
      const url = websiteUrl.trim()
      if (!url) { setError('Please enter a website URL or select a different source'); return }
      if (!url.startsWith('https://')) { setError('Website URL must start with https://'); return }
    }
    if (intelSource === 'files' && selectedFiles.length === 0) {
      setError('Please select at least one file or choose a different source'); return
    }
    if (intelSource === 'text' && !pasteText.trim()) {
      setError('Please paste some content or choose a different source'); return
    }

    setSaving(true); setError(null)
    try {
      await settingsApi.putSellerProfile({
        company_name: companyName.trim(),
        portfolio_summary: '',
        portfolio_items: portfolioItems.split('\n').map(s => s.trim()).filter(Boolean),
        ...(intelSource === 'url' && websiteUrl.trim() ? { website_url: websiteUrl.trim() } : {}),
      })
      setStep('api-keys')
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function saveApiKeysAndFinish() {
    setSaving(true); setError(null)
    try {
      await settingsApi.putApiKeys({ jsearch, tavily, llm_provider: llmProvider, llm_model: llmModel })
    } catch (e) {
      setError(String(e)); setSaving(false); return
    }
    setSaving(false)

    // Begin post-setup orchestration
    setOrchestrating(true)
    const products = portfolioItems.split('\n').map(s => s.trim()).filter(Boolean)

    try {
      // 1. Generate capability map from products
      if (products.length > 0) {
        setOrchestrationStatus('Generating capability map from your products...')
        try {
          await settingsApi.generateCapabilityMap({ product_list: products.join('\n') })
        } catch {
          // Soft failure — continue without capability map
        }
      }

      // 2. Extract intelligence from chosen source
      if (intelSource !== 'none') {
        try {
          if (intelSource === 'url') {
            setOrchestrationStatus('Scraping website — this may take 30-60 seconds...')
            await settingsApi.extractSellerIntelligence({ website_url: websiteUrl.trim() })
          } else if (intelSource === 'files') {
            const totalSize = selectedFiles.reduce((s, f) => s + f.size, 0)
            const sizeMB = (totalSize / (1024 * 1024)).toFixed(1)
            setOrchestrationStatus(`Uploading ${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''} (${sizeMB} MB) and analyzing with AI — large documents may take 30-60 seconds...`)
            await settingsApi.extractFromFiles(selectedFiles)
          } else if (intelSource === 'text') {
            setOrchestrationStatus('Analyzing pasted text with AI...')
            await settingsApi.extractSellerIntelligence({ text: pasteText.trim() })
          }

          // 3. Auto-link intelligence to capability map
          setOrchestrationStatus('Linking intelligence to capabilities...')
          try {
            await settingsApi.autoLinkIntelligence()
          } catch {
            // Soft failure — linking is optional
          }
        } catch (e) {
          const msg = String(e)
          if (msg.includes('blocked') || msg.includes('403') || msg.includes('crawler')) {
            setOrchestrationStatus('Your website blocked our crawler (common for enterprise sites). You can upload files from Settings later.')
          } else {
            setOrchestrationStatus('Could not extract intelligence — you can retry from Settings later.')
          }
          // Soft failure — continue to complete setup
        }
      }

      // 4. Mark setup complete
      setOrchestrationStatus('Finishing setup...')
      try { await setupApi.saveConfig({}) } catch { /* proceed anyway */ }
      onComplete()
    } finally {
      setOrchestrating(false)
    }
  }

  const STEP_LABELS: Record<Step, string> = {
    'about-you': '1. About You',
    'api-keys': '2. API Keys',
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
          {(['about-you', 'api-keys'] as const).map(s => (
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

        {/* Orchestration status */}
        {orchestrating && orchestrationStatus && (
          <div className="mb-4 rounded-md px-3 py-2 text-sm bg-blue-50 text-blue-700 border border-blue-200">
            <span className="inline-block animate-spin mr-2">&#9696;</span>
            {orchestrationStatus}
          </div>
        )}

        {/* ── Step 1: About You ── */}
        {step === 'about-you' && !orchestrating && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Company Name *</label>
              <input value={companyName} onChange={e => setCompanyName(e.target.value)}
                placeholder="Acme Corp"
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Products / Services (one per line)</label>
              <textarea value={portfolioItems} onChange={e => setPortfolioItems(e.target.value)}
                placeholder="Kubernetes Optimizer&#10;Cost Analytics&#10;Security Scanner"
                rows={3}
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>

            {/* Intelligence source selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Seller Intelligence Source (optional)</label>
              <div className="flex flex-wrap gap-2">
                {([
                  ['none', 'Skip'],
                  ['url', 'Website URL'],
                  ['files', 'Upload Files'],
                  ['text', 'Paste Text'],
                ] as const).map(([value, label]) => (
                  <button key={value} type="button" onClick={() => { setIntelSource(value); setError(null) }}
                    className={`px-3 py-1.5 text-xs rounded border ${
                      intelSource === value
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                    }`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Conditional inputs based on source */}
            {intelSource === 'url' && (
              <div>
                <input value={websiteUrl} onChange={e => setWebsiteUrl(e.target.value)}
                  placeholder="https://www.yourcompany.com"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                <p className="mt-1 text-xs text-gray-400">
                  We'll extract differentiators, sales plays, and proof points from your website.
                </p>
              </div>
            )}
            {intelSource === 'files' && (
              <div>
                <input ref={fileInputRef} type="file" multiple accept={ACCEPTED_EXTENSIONS}
                  onChange={handleFileSelect}
                  className="w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" />
                <p className="mt-1 text-xs text-gray-400">
                  PDF, DOCX, PPTX, XLSX, HTML, TXT — pitch decks, case studies, battlecards (max {MAX_FILES} files, 10MB each)
                </p>
                {selectedFiles.length > 0 && (
                  <p className="mt-1 text-xs text-green-600">
                    {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected
                  </p>
                )}
              </div>
            )}
            {intelSource === 'text' && (
              <div>
                <textarea value={pasteText} onChange={e => setPasteText(e.target.value)}
                  placeholder="Paste content from pitch decks, case studies, battlecards…"
                  rows={4}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            )}

            <button onClick={() => void saveAboutYou()} disabled={saving}
              className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
              {saving ? 'Saving…' : 'Next →'}
            </button>
          </div>
        )}

        {/* ── Step 2: API Keys ── */}
        {step === 'api-keys' && !orchestrating && (
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
              <button onClick={() => setStep('about-you')}
                className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">
                ← Back
              </button>
              <button onClick={() => void saveApiKeysAndFinish()} disabled={saving}
                className="flex-1 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {saving ? 'Saving…' : 'Finish Setup →'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
