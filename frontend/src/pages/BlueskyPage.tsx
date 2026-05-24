import { useState } from 'react'
import { usePlatformStore } from '../store'
import { analyzeBluesky } from '../api/analysis'
import TimelineChart from '../components/analysis/TimelineChart'
import PostCards from '../components/analysis/PostCards'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import RiskBadge from '../components/shared/RiskBadge'
import type { PlatformResult } from '../types'

export default function BlueskyPage() {
  const [handle, setHandle] = useState('')
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(20)
  const [error, setError] = useState('')
  const [warning, setWarning] = useState('')
  const [status, setStatus] = useState('')
  const [activeTab, setActiveTab] = useState<'timeline' | 'posts' | 'socio'>('timeline')
  const { bluesky, loading, setPlatformResult } = usePlatformStore()

  const handleAnalyze = async () => {
    const targetHandle = handle.trim()
    const loginHandle = identifier.trim()
    if (!targetHandle) {
      setWarning('Enter the Bluesky handle you want to analyse.')
      return
    }
    if (!loginHandle || !password.trim()) {
      setWarning('Enter your Bluesky handle and App Password.')
      return
    }

    setError('')
    setWarning('')
    setStatus(`Fetching posts for ${targetHandle}...`)
    try {
      usePlatformStore.getState().setLoading(true)
      const result = await analyzeBluesky(targetHandle, loginHandle, password, minRisk, nShow)
      setStatus(`Running Mental-RoBERTa on ${result.n_posts} posts...`)
      setPlatformResult('bluesky', result)
      setActiveTab('timeline')
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Bluesky analysis failed'
      if (String(message).toLowerCase().includes('no posts found')) {
        setWarning(message)
      } else {
        setError(message)
      }
    } finally {
      setStatus('')
      usePlatformStore.getState().setLoading(false)
    }
  }

  const result = bluesky as PlatformResult | null
  const displayedPosts = result?.df.filter((p) => p.risk_score >= result.min_risk) ?? []
  const resultHandle = result?.handle || handle.trim()

  return (
    <div className="flex flex-col gap-[18px]">
      <div>
        <h2 className="text-[1.15rem] font-bold text-[#111827]">Bluesky Analysis</h2>
        <p className="text-[0.78rem] text-[#4b5563] mt-[14px]">
          Fetches 3 months of posts for any public Bluesky account. Requires your Bluesky credentials to authenticate.
        </p>
      </div>

      <div className="border-t border-[#d1d5db]" />

      <div className="grid grid-cols-1 lg:grid-cols-[460px_1fr] gap-[32px] items-start">
        <section className="flex flex-col gap-[14px]">
          <label className="flex flex-col gap-[6px] text-[0.78rem] text-[#4b5563]">
            Bluesky handle to analyse
            <input
              type="text"
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              placeholder="e.g. bsky.app"
              className="w-full bg-white border border-[#d1d5db] rounded-[7px] px-[12px] py-[10px] text-[0.82rem] text-[#111827] outline-none focus:border-[#0F766E]"
            />
          </label>

          <div className="mt-[6px]">
            <p className="text-[0.83rem] font-bold uppercase tracking-[0.04em] text-[#4b5563]">Your Credentials</p>
            <p className="text-[0.68rem] text-[#4b5563] mt-[8px]">
              Bluesky Settings -&gt; Privacy -&gt; App Passwords -&gt; Add App Password
            </p>
          </div>

          <label className="flex flex-col gap-[6px] text-[0.78rem] text-[#4b5563]">
            Your Bluesky handle
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="your.handle.bsky.social"
              className="w-full bg-white border border-[#d1d5db] rounded-[7px] px-[12px] py-[10px] text-[0.82rem] text-[#111827] outline-none focus:border-[#0F766E]"
            />
          </label>

          <label className="flex flex-col gap-[6px] text-[0.78rem] text-[#4b5563]">
            App Password
            <div className="flex">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="xxxx-xxxx-xxxx-xxxx"
                className="min-w-0 flex-1 bg-white border border-[#d1d5db] rounded-l-[7px] px-[12px] py-[10px] text-[0.82rem] text-[#111827] outline-none focus:border-[#0F766E]"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                title={showPassword ? 'Hide password' : 'Show password'}
                className="w-[48px] border border-l-0 border-[#d1d5db] rounded-r-[7px] bg-[#f8fafc] text-[#374151] flex items-center justify-center"
              >
                <i className={showPassword ? 'ti ti-eye-off' : 'ti ti-eye'} />
              </button>
            </div>
          </label>

          <label className="flex flex-col gap-[4px] text-[0.78rem] text-[#4b5563]">
            Min risk score to display
            <span className="text-[0.7rem] text-[#4b5563]">{minRisk.toFixed(2)}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minRisk}
              onChange={(e) => setMinRisk(Number(e.target.value))}
              className="w-full accent-[#ef4444]"
            />
          </label>

          <label className="flex flex-col gap-[4px] text-[0.78rem] text-[#4b5563]">
            Max posts to display
            <span className="text-[0.7rem] text-[#4b5563] text-center">{nShow}</span>
            <input
              type="range"
              min={5}
              max={50}
              step={5}
              value={nShow}
              onChange={(e) => setNShow(Number(e.target.value))}
              className="w-full accent-[#ef4444]"
            />
          </label>

          <button
            onClick={handleAnalyze}
            disabled={loading}
            className="w-full bg-[#0F766E] text-white border-none rounded-[7px] py-[12px] text-[0.86rem] font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_14px_26px_rgba(15,118,110,0.18)]"
          >
            Analyse Bluesky User
          </button>

          {loading && <LoadingSpinner text={status || 'Fetching posts and running Mental-RoBERTa...'} />}
          {warning && (
            <div className="text-[0.82rem] text-[#4b5563] bg-[#fefce8] rounded-[7px] px-[14px] py-[12px] border border-[#fef3c7]">
              {warning}
            </div>
          )}
          {error && (
            <div className="text-[0.78rem] text-[#dc2626] bg-[#fef2f2] rounded-[7px] px-[14px] py-[12px] border border-[#fecaca]">
              {error}
            </div>
          )}
        </section>

        <section className="min-h-[240px]">
          {!loading && !result ? (
            <div className="h-[220px] flex items-center justify-center text-center text-[#9ca3af] text-[0.9rem]">
              Enter a handle and credentials, then click Analyse Bluesky User.
            </div>
          ) : result ? (
            <div className="flex flex-col gap-[18px]">
              <div>
                <h3 className="text-[0.92rem] font-bold text-[#111827]">
                  Results for {resultHandle}
                  {resultHandle && (
                    <a
                      href={`https://bsky.app/profile/${resultHandle}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-[8px] text-[#9ca3af] hover:text-[#0F766E]"
                      title="Open Bluesky profile"
                    >
                      <i className="ti ti-link" />
                    </a>
                  )}
                </h3>
              </div>

              <div className="grid grid-cols-2 xl:grid-cols-4 gap-[18px]">
                <Metric label="Overall Risk" value={`${(result.overall * 100).toFixed(1)}%`} />
                <Metric label="Posts Analysed" value={String(result.n_posts)} />
                <Metric label="High-Risk Posts" value={String(result.n_high)} />
                <Metric label="Period" value="3 months" />
              </div>

              <div>
                <RiskBadge score={result.overall} />
                {result.overall >= 0.55 && (
                  <div className="mt-[8px] bg-[#fee2e2] text-[#4b5563] rounded-[7px] px-[14px] py-[10px] text-[0.82rem]">
                    CRISIS ALERT - High-risk content detected. Please direct to crisis resources.
                  </div>
                )}
              </div>

              <div className="border-t border-[#d1d5db]" />

              <div className="bg-white border border-[#d1d5db] rounded-[8px] overflow-hidden">
                <div className="flex bg-white px-[8px] overflow-x-auto border-b border-[#e5e7eb]">
                  {(['timeline', 'posts', 'socio'] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-[14px] py-[10px] text-[0.78rem] border-b-2 ${
                        activeTab === tab
                          ? 'text-white bg-[#0F766E] border-[#ef4444] font-semibold rounded-t-[7px]'
                          : 'text-[#4b5563] border-transparent hover:text-[#0F766E]'
                      }`}
                    >
                      {tab === 'timeline' ? 'Timeline' : tab === 'posts' ? 'Posts' : 'Socio-Economic'}
                    </button>
                  ))}
                </div>
                <div className="p-[14px]">
                  {activeTab === 'timeline' && <TimelineChart posts={result.df} />}
                  {activeTab === 'posts' && <PostCards posts={displayedPosts} n={result.n_show} />}
                  {activeTab === 'socio' && <SocioEconomicPanel signals={result.signals} />}
                </div>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[0.78rem] text-[#4b5563]">{label}</div>
      <div className="text-[2rem] leading-tight text-[#4b5563]">{value}</div>
    </div>
  )
}
