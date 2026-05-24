import { useState } from 'react'
import { usePlatformStore } from '../store'
import { analyzeReddit } from '../api/analysis'
import TimelineChart from '../components/analysis/TimelineChart'
import PostCards from '../components/analysis/PostCards'
import OverallBanner from '../components/analysis/OverallBanner'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import type { PlatformResult } from '../types'

export default function RedditPage() {
  const [username, setUsername] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(20)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'timeline' | 'posts' | 'socio'>('timeline')
  const { reddit, loading, setPlatformResult } = usePlatformStore()
  const usingApiMode = Boolean(clientId.trim() || clientSecret.trim())

  const handleAnalyze = async () => {
    if (!username.trim()) return
    if (usingApiMode && (!clientId.trim() || !clientSecret.trim())) {
      setError('Enter both Reddit API fields, or leave both blank to use API-free RSS mode.')
      return
    }
    setError('')
    try {
      usePlatformStore.getState().setLoading(true)
      setPlatformResult('reddit', null)
      const result = await analyzeReddit(username, clientId, clientSecret, minRisk, nShow)
      setPlatformResult('reddit', result)
      setActiveTab('timeline')
    } catch (err: any) {
      setError(err.message || 'Reddit analysis failed')
    } finally {
      usePlatformStore.getState().setLoading(false)
    }
  }

  const result = reddit as PlatformResult | null

  return (
    <div className="flex flex-col gap-[16px]">
      <div>
        <h2 className="text-[1.3rem] font-bold text-[#1f2937]">Reddit Analysis</h2>
        <p className="text-[0.82rem] text-[#6b7280] mt-[2px]">
          Enter a Reddit username to analyse their public posts and comments.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-[16px]">
        {/* Input column */}
        <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] p-[18px_20px]">
          <div className="text-[0.7rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[6px]">Reddit username</div>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. spez"
            className="w-full bg-[#fafbfc] border-[1.5px] border-[#e5e7eb] rounded-[8px] px-[12px] py-[9px] text-[0.82rem] text-[#4b5563] outline-none focus:border-[#0F766E] mb-[10px]"
          />
          <div className="text-[0.7rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[6px]">Reddit API credentials</div>
          <p className="text-[0.7rem] text-[#6b7280] mb-[8px]">
            Optional. Leave blank to use API-free Reddit RSS mode, or enter credentials for the richer API mode.
          </p>
          <input
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder="Client ID"
            className="w-full bg-[#fafbfc] border-[1.5px] border-[#e5e7eb] rounded-[8px] px-[12px] py-[9px] text-[0.82rem] text-[#4b5563] outline-none focus:border-[#0F766E] mb-[8px]"
          />
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder="Client Secret"
            className="w-full bg-[#fafbfc] border-[1.5px] border-[#e5e7eb] rounded-[8px] px-[12px] py-[9px] text-[0.82rem] text-[#4b5563] outline-none focus:border-[#0F766E] mb-[10px]"
          />
          <div className="text-[0.7rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[6px]">Min risk score</div>
          <div className="flex items-center gap-[8px] mb-[10px]">
            <input
              type="range"
              min={0}
              max={100}
              value={minRisk * 100}
              onChange={(e) => setMinRisk(Number(e.target.value) / 100)}
              className="flex-1 h-[4px]"
            />
            <span className="text-[0.78rem] text-[#6b7280] font-semibold min-w-[36px]">{(minRisk * 100).toFixed(0)}%</span>
          </div>
          <div className="text-[0.7rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[6px]">Max posts to display</div>
          <div className="flex items-center gap-[8px] mb-[10px]">
            <input
              type="range"
              min={5}
              max={50}
              step={5}
              value={nShow}
              onChange={(e) => setNShow(Number(e.target.value))}
              className="flex-1 h-[4px]"
            />
            <span className="text-[0.78rem] text-[#6b7280] font-semibold min-w-[36px]">{nShow}</span>
          </div>
          {error && (
            <div className="text-[0.72rem] text-[#dc2626] bg-[#fef2f2] rounded-[6px] px-[10px] py-[7px] mb-[8px] border border-[#fecaca]">
              {error}
            </div>
          )}
          <button
            onClick={handleAnalyze}
            disabled={!username.trim() || (usingApiMode && (!clientId.trim() || !clientSecret.trim())) || loading}
            className="w-full bg-gradient-to-r from-[#0F766E] to-[#1D9E75] text-white border-none rounded-[8px] py-[10px] text-[0.82rem] font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Analysing...' : usingApiMode ? 'Analyse Reddit User with API' : 'Analyse Reddit User with RSS'}
          </button>
          <p className="text-[0.68rem] text-[#6b7280] mt-[8px]">
            RSS mode fetches recent public submitted posts and comments from Reddit feeds. It may return fewer items than API mode.
          </p>
        </div>

        {/* Results column */}
        <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] overflow-hidden">
          <div className="flex bg-[#f8fafc] border-b border-[#f1f5f9] px-[16px] overflow-x-auto">
            {(['timeline', 'posts', 'socio'] as const).map((tab) => (
              <div
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-[12px] px-[16px] text-[0.82rem] cursor-pointer border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'text-[#0F766E] border-[#0F766E] font-semibold'
                    : 'text-[#94a3b8] border-transparent font-medium hover:text-[#6b7280]'
                }`}
              >
                {tab === 'timeline' ? 'Timeline' : tab === 'posts' ? 'Posts' : 'Socio-Economic'}
              </div>
            ))}
          </div>
          <div className="p-[16px_18px]">
            {loading ? (
              <LoadingSpinner text={usingApiMode ? 'Fetching and analysing Reddit posts with API...' : 'Fetching Reddit RSS feeds and analysing public posts/comments...'} />
            ) : !result ? (
              <div className="flex flex-col items-center justify-center h-[240px] text-[#c4c9d0] gap-[8px]">
                <i className="ti ti-brand-reddit text-[28px]" />
                <span className="text-[0.82rem]">Enter a username and click Analyse</span>
              </div>
            ) : (
              <>
                {activeTab === 'timeline' && (
                  <>
                    <OverallBanner result={result} />
                    <div className="mt-[12px]">
                      <TimelineChart posts={result.df} />
                    </div>
                  </>
                )}
                {activeTab === 'posts' && (
                  <PostCards posts={result.df.filter((p) => p.risk_score >= result.min_risk)} n={result.n_show} />
                )}
                {activeTab === 'socio' && <SocioEconomicPanel signals={result.signals} />}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
