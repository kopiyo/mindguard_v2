import { useEffect, useMemo, useState } from 'react'

type PortalConsent = {
  id: string
  recipient_email: string
  recipient_role: 'student' | 'parent'
  status: string
  platforms_json: string
  mode: string
  document_version: string
  dispatched_at?: string
  expires_at?: string
}

const apiBase =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? 'http://127.0.0.1:8000/api' : '/api')

function parsePlatforms(value: string) {
  try {
    const parsed = JSON.parse(value || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export default function ConsentPortalPage({ token }: { token: string }) {
  const [consent, setConsent] = useState<PortalConsent | null>(null)
  const [signatureName, setSignatureName] = useState('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'submitting' | 'done' | 'error'>('loading')
  const [message, setMessage] = useState('')

  const platforms = useMemo(() => parsePlatforms(consent?.platforms_json || '[]'), [consent])

  useEffect(() => {
    const load = async () => {
      setStatus('loading')
      setMessage('')
      try {
        const res = await fetch(`${apiBase}/v1/portal/consents/${token}`)
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data.detail || 'This consent link could not be opened.')
        setConsent(data)
        setStatus('ready')
      } catch (err: any) {
        setMessage(err.message || 'This consent link could not be opened.')
        setStatus('error')
      }
    }
    load()
  }, [token])

  const submit = async (action: 'accept' | 'decline') => {
    if (action === 'accept' && !signatureName.trim()) {
      setMessage('Please enter your name before accepting.')
      return
    }
    setStatus('submitting')
    setMessage('')
    try {
      const res = await fetch(`${apiBase}/v1/portal/consents/${token}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: action === 'accept' ? JSON.stringify({ signature_name: signatureName.trim(), platforms }) : undefined,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || `Could not ${action} consent.`)
      setConsent((prev) => prev ? { ...prev, status: data.status } : prev)
      setMessage(action === 'accept' ? 'Consent accepted. Thank you.' : 'Consent declined.')
      setStatus('done')
    } catch (err: any) {
      setMessage(err.message || `Could not ${action} consent.`)
      setStatus('ready')
    }
  }

  return (
    <div className="min-h-screen bg-[#f7f9fb] flex items-center justify-center px-[18px] py-[40px]">
      <div className="w-full max-w-[680px] bg-white rounded-[12px] border border-[#e5e7eb] shadow-sm overflow-hidden">
        <div className="bg-[#0F766E] px-[26px] py-[22px]">
          <div className="text-white text-[1.35rem] font-bold">MindGuard</div>
          <div className="text-[#ccfbf1] text-[0.88rem] mt-[4px]">Consent request</div>
        </div>

        <div className="p-[26px]">
          {status === 'loading' ? (
            <div className="flex items-center justify-center py-[52px] text-[#64748b]">
              <div className="w-[24px] h-[24px] border-2 border-[#e5e7eb] border-t-[#0F766E] rounded-full animate-spin mr-[10px]" />
              Loading consent request...
            </div>
          ) : status === 'error' ? (
            <div className="rounded-[10px] bg-[#fee2e2] text-[#991b1b] px-[16px] py-[14px]">{message}</div>
          ) : consent ? (
            <div className="flex flex-col gap-[18px]">
              <div>
                <h1 className="text-[1.25rem] font-bold text-[#111827]">Review consent request</h1>
                <p className="text-[0.9rem] text-[#64748b] mt-[6px]">
                  A school counsellor is requesting permission to analyse selected public social media information for wellbeing support.
                </p>
              </div>

              <div className="grid md:grid-cols-2 gap-[12px]">
                <div className="rounded-[10px] bg-[#f8fafc] border border-[#e5e7eb] p-[14px]">
                  <div className="text-[0.72rem] uppercase font-bold text-[#64748b]">Recipient</div>
                  <div className="text-[#111827] mt-[4px]">{consent.recipient_email}</div>
                  <div className="text-[0.78rem] text-[#64748b] capitalize">{consent.recipient_role}</div>
                </div>
                <div className="rounded-[10px] bg-[#f8fafc] border border-[#e5e7eb] p-[14px]">
                  <div className="text-[0.72rem] uppercase font-bold text-[#64748b]">Mode</div>
                  <div className="text-[#111827] mt-[4px]">{consent.mode.replace(/_/g, ' ').toLowerCase()}</div>
                  <div className="text-[0.78rem] text-[#64748b]">Document {consent.document_version}</div>
                </div>
              </div>

              <div>
                <div className="text-[0.78rem] uppercase font-bold text-[#0F766E] mb-[8px]">Platforms requested</div>
                <div className="flex flex-wrap gap-[8px]">
                  {platforms.map((platform) => (
                    <span key={platform} className="rounded-full bg-[#d1fae5] text-[#065f46] px-[10px] py-[4px] text-[0.78rem] font-semibold">
                      {platform}
                    </span>
                  ))}
                </div>
              </div>

              {consent.status === 'ACCEPTED' || consent.status === 'DECLINED' || status === 'done' ? (
                <div className="rounded-[10px] bg-[#ecfdf5] text-[#065f46] px-[16px] py-[14px] font-semibold">
                  {message || `This request is already ${consent.status.toLowerCase()}.`}
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-[0.78rem] font-bold text-[#374151] mb-[6px]">Your name</label>
                    <input
                      value={signatureName}
                      onChange={(e) => setSignatureName(e.target.value)}
                      placeholder="Type your full name"
                      className="w-full rounded-[8px] border border-[#d1d5db] px-[12px] py-[10px] text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
                    />
                  </div>

                  {message && (
                    <div className="rounded-[8px] bg-[#fff7ed] text-[#9a3412] px-[12px] py-[10px] text-[0.84rem]">{message}</div>
                  )}

                  <div className="flex flex-col sm:flex-row gap-[10px]">
                    <button
                      onClick={() => submit('accept')}
                      disabled={status === 'submitting'}
                      className="flex-1 rounded-[8px] bg-[#0F766E] text-white px-[16px] py-[11px] font-bold hover:bg-[#115E59] disabled:opacity-60"
                    >
                      Accept consent
                    </button>
                    <button
                      onClick={() => submit('decline')}
                      disabled={status === 'submitting'}
                      className="flex-1 rounded-[8px] bg-white text-[#991b1b] border border-[#fecaca] px-[16px] py-[11px] font-bold hover:bg-[#fef2f2] disabled:opacity-60"
                    >
                      Decline
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
