import { useState, useRef } from 'react'
import { usePlatformStore } from '../store'
import { analyzeFile } from '../api/analysis'
import TimelineChart from '../components/analysis/TimelineChart'
import PostCards from '../components/analysis/PostCards'
import OverallBanner from '../components/analysis/OverallBanner'
import SocioEconomicPanel from '../components/analysis/SocioEconomicPanel'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import type { PlatformResult } from '../types'

export default function FileUploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [minRisk, setMinRisk] = useState(0)
  const [nShow, setNShow] = useState(30)
  const [fileName, setFileName] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'timeline' | 'posts' | 'socio'>('timeline')
  const { file, loading, setPlatformResult } = usePlatformStore()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) {
      setFileName(f.name)
      setSelectedFile(f)
    }
  }

  const handleAnalyze = async (file: File) => {
    setError('')
    try {
      usePlatformStore.getState().setLoading(true)
      const result = await analyzeFile(file, minRisk, nShow)
      setPlatformResult('file', result)
    } catch (err: any) {
      setError(err.message || 'File analysis failed')
    } finally {
      usePlatformStore.getState().setLoading(false)
    }
  }

  const result = file as PlatformResult | null

  return (
    <div className="flex flex-col gap-[14px]">
      <h2 className="text-[1.1rem] font-bold text-[#1f2937]">File Upload Analysis</h2>
      <p className="text-[0.74rem] text-[#6b7280] -mt-[10px]">
        Upload a WhatsApp export (.txt), CSV spreadsheet, Facebook JSON archive, or Twitter JSON archive.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-[14px]">
        <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] p-[16px_18px]">
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">File</div>
          <div className="bg-[#fafbfc] border-[1.5px] border-dashed border-[#e5e7eb] rounded-[8px] p-[12px] text-center mb-[8px]">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.csv,.json"
              onChange={handleFileChange}
              className="text-[0.72rem] text-[#6b7280] file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-[0.7rem] file:font-semibold file:bg-[#0F766E] file:text-white cursor-pointer"
            />
            {fileName && (
              <p className="text-[0.65rem] text-[#0F766E] mt-[6px] font-medium">{fileName}</p>
            )}
          </div>
          {error && (
            <div className="text-[0.65rem] text-[#dc2626] bg-[#fef2f2] rounded-[6px] px-[10px] py-[7px] mb-[8px] border border-[#fecaca]">
              {error}
            </div>
          )}
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px]">Min risk score</div>
          <div className="flex items-center gap-[8px]">
            <input
              type="range"
              min={0}
              max={100}
              value={minRisk * 100}
              onChange={(e) => setMinRisk(Number(e.target.value) / 100)}
              className="flex-1 h-[3px]"
            />
            <span className="text-[0.68rem] text-[#6b7280] font-semibold min-w-[32px]">{(minRisk * 100).toFixed(0)}%</span>
          </div>
          <div className="text-[0.62rem] font-bold text-[#374151] uppercase tracking-[0.06em] mb-[4px] mt-[8px]">Max entries to display</div>
          <div className="flex items-center gap-[8px] mb-[10px]">
            <input
              type="range"
              min={5}
              max={100}
              step={5}
              value={nShow}
              onChange={(e) => setNShow(Number(e.target.value))}
              className="flex-1 h-[3px]"
            />
            <span className="text-[0.68rem] text-[#6b7280] font-semibold min-w-[32px]">{nShow}</span>
          </div>
          <button
            onClick={() => selectedFile && handleAnalyze(selectedFile)}
            disabled={!selectedFile || loading}
            className="w-full bg-gradient-to-r from-[#0F766E] to-[#1D9E75] text-white border-none rounded-[7px] py-[7px] text-[0.72rem] font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Analyse File
          </button>
        </div>

        <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] overflow-hidden">
          <div className="flex bg-[#f8fafc] border-b border-[#f1f5f9] px-[14px] overflow-x-auto">
            {(['timeline', 'posts', 'socio'] as const).map((tab) => (
              <div
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-[10px] px-[14px] text-[0.7rem] cursor-pointer border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'text-[#0F766E] border-[#0F766E] font-semibold'
                    : 'text-[#94a3b8] border-transparent font-medium hover:text-[#6b7280]'
                }`}
              >
                {tab === 'timeline' ? 'Timeline' : tab === 'posts' ? 'Posts' : 'Socio-Economic'}
              </div>
            ))}
          </div>
          <div className="p-[14px_16px]">
            {loading ? (
              <LoadingSpinner text="Parsing and analysing file..." />
            ) : !result ? (
              <div className="flex flex-col items-center justify-center h-[200px] text-[#c4c9d0] gap-[5px]">
                <i className="ti ti-folder-open text-[22px]" />
                <span className="text-[0.65rem]">Upload a file to analyse</span>
              </div>
            ) : (
              <>
                {activeTab === 'timeline' && (
                  <>
                    <OverallBanner result={result} />
                    <div className="mt-[10px]">
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
