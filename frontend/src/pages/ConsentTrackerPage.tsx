import { useEffect, useState } from 'react'
import { getConsents, createConsent, dispatchConsent, cancelConsent, remindConsent } from '../api/counsellor'
import { getStudents } from '../api/counsellor'
import type { Consent, ConsentStatus } from '../types'
import type { StudentDTO } from '../api/counsellor'

function formatDate(d?: string) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const STATUS_STYLE: Record<ConsentStatus, string> = {
  DRAFT: 'bg-[#f1f5f9] text-[#6b7280]',
  PENDING: 'bg-[#fef3c7] text-[#92400e]',
  VIEWED: 'bg-[#dbeafe] text-[#1e40af]',
  ACCEPTED: 'bg-[#d1fae5] text-[#065f46]',
  DECLINED: 'bg-[#fee2e2] text-[#991b1b]',
  EXPIRED: 'bg-[#f1f5f9] text-[#6b7280]',
  REVOKED: 'bg-[#fee2e2] text-[#991b1b]',
  RENEWAL_DUE: 'bg-[#fff7ed] text-[#9a3412]',
}

const FILTER_TABS: Array<{ key: string; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'ACCEPTED', label: 'Accepted' },
  { key: 'DECLINED', label: 'Declined' },
  { key: 'EXPIRED', label: 'Expired' },
]

const PLATFORMS = ['Reddit', 'Bluesky', 'Mastodon', 'YouTube']

// ─── New Consent Modal ────────────────────────────────────────────────────────

interface NewConsentModalProps {
  students: StudentDTO[]
  onClose: () => void
  onCreated: (consent: Consent) => void
}

function NewConsentModal({ students, onClose, onCreated }: NewConsentModalProps) {
  const [studentId, setStudentId] = useState('')
  const [recipientEmail, setRecipientEmail] = useState('')
  const [recipientRole, setRecipientRole] = useState<'student' | 'parent'>('student')
  const [platforms, setPlatforms] = useState<string[]>([])
  const [mode, setMode] = useState<'ON_DEMAND' | 'CONTINUOUS'>('ON_DEMAND')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const togglePlatform = (p: string) => {
    setPlatforms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])
  }

  const handleSubmit = async () => {
    if (!studentId || !recipientEmail || platforms.length === 0) {
      setError('Please fill in all required fields and select at least one platform.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const consent = await createConsent(studentId, {
        recipient_email: recipientEmail,
        recipient_role: recipientRole,
        platforms,
        mode,
      })
      onCreated(consent)
      onClose()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-[480px] max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-[20px] py-[14px] border-b border-[#f1f5f9]">
          <h3 className="text-[0.95rem] font-bold text-[#1f2937]">New Consent</h3>
          <button onClick={onClose} className="text-[#9ca3af] hover:text-[#6b7280] cursor-pointer bg-transparent border-none">
            <i className="ti ti-x text-[18px]" />
          </button>
        </div>

        <div className="flex flex-col gap-[14px] p-[20px]">
          {/* Student */}
          <div>
            <label className="block text-[0.78rem] font-semibold text-[#374151] mb-[4px]">Student *</label>
            <select
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              className="w-full rounded-[8px] border border-[#e5e7eb] px-[10px] py-[8px] text-[0.82rem] text-[#1f2937] bg-white focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
            >
              <option value="">Select student...</option>
              {students.map((s) => (
                <option key={s.id} value={s.id}>{s.name} ({s.email})</option>
              ))}
            </select>
          </div>

          {/* Recipient email */}
          <div>
            <label className="block text-[0.78rem] font-semibold text-[#374151] mb-[4px]">Recipient Email *</label>
            <input
              type="email"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              placeholder="recipient@example.com"
              className="w-full rounded-[8px] border border-[#e5e7eb] px-[10px] py-[8px] text-[0.82rem] text-[#1f2937] placeholder-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
            />
          </div>

          {/* Recipient role */}
          <div>
            <label className="block text-[0.78rem] font-semibold text-[#374151] mb-[4px]">Recipient Role</label>
            <div className="flex gap-[8px]">
              {(['student', 'parent'] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setRecipientRole(r)}
                  className={`px-[14px] py-[6px] rounded-[7px] text-[0.8rem] font-semibold cursor-pointer border transition-colors capitalize ${
                    recipientRole === r
                      ? 'bg-[#0F766E] text-white border-[#0F766E]'
                      : 'bg-white text-[#6b7280] border-[#e5e7eb] hover:bg-[#f9fafb]'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {/* Platforms */}
          <div>
            <label className="block text-[0.78rem] font-semibold text-[#374151] mb-[6px]">Platforms * (select at least one)</label>
            <div className="flex flex-wrap gap-[8px]">
              {PLATFORMS.map((p) => (
                <button
                  key={p}
                  onClick={() => togglePlatform(p)}
                  className={`px-[12px] py-[5px] rounded-[7px] text-[0.8rem] font-semibold cursor-pointer border transition-colors ${
                    platforms.includes(p)
                      ? 'bg-[#0F766E] text-white border-[#0F766E]'
                      : 'bg-white text-[#6b7280] border-[#e5e7eb] hover:bg-[#f9fafb]'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Mode */}
          <div>
            <label className="block text-[0.78rem] font-semibold text-[#374151] mb-[4px]">Mode</label>
            <div className="flex gap-[8px]">
              <button
                onClick={() => setMode('ON_DEMAND')}
                className={`px-[14px] py-[6px] rounded-[7px] text-[0.8rem] font-semibold cursor-pointer border transition-colors ${
                  mode === 'ON_DEMAND'
                    ? 'bg-[#0F766E] text-white border-[#0F766E]'
                    : 'bg-white text-[#6b7280] border-[#e5e7eb] hover:bg-[#f9fafb]'
                }`}
              >
                On-demand
              </button>
              <button
                onClick={() => setMode('CONTINUOUS')}
                className={`px-[14px] py-[6px] rounded-[7px] text-[0.8rem] font-semibold cursor-pointer border transition-colors ${
                  mode === 'CONTINUOUS'
                    ? 'bg-[#0F766E] text-white border-[#0F766E]'
                    : 'bg-white text-[#6b7280] border-[#e5e7eb] hover:bg-[#f9fafb]'
                }`}
              >
                Continuous
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-[6px] text-[#ef4444] text-[0.82rem]">
              <i className="ti ti-alert-circle" /> {error}
            </div>
          )}

          <div className="flex gap-[8px] pt-[4px]">
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-[6px] px-[14px] py-[8px] bg-[#0F766E] text-white rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#0d5c56] transition-colors disabled:opacity-50"
            >
              {submitting ? (
                <div className="w-[14px] h-[14px] border-2 border-white/40 border-t-white rounded-full animate-spin" />
              ) : (
                <i className="ti ti-send text-[14px]" />
              )}
              {submitting ? 'Creating & Dispatching...' : 'Create & Dispatch'}
            </button>
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-[14px] py-[8px] border border-[#e5e7eb] text-[#6b7280] rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#f9fafb] transition-colors bg-white disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

export default function ConsentTrackerPage() {
  const [filterTab, setFilterTab] = useState('all')
  const [consents, setConsents] = useState<Consent[]>([])
  const [students, setStudents] = useState<StudentDTO[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [dispatchNotice, setDispatchNotice] = useState<Consent | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [consentData, studentData] = await Promise.all([getConsents(), getStudents()])
      setConsents(consentData)
      setStudents(studentData)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAction = async (action: () => Promise<any>, id: string) => {
    setActionLoading(id)
    try {
      const result = await action()
      if (result?.email_sent !== undefined || result?.consent_url) {
        setDispatchNotice(result)
      }
      await load()
    } catch (e: any) {
      alert(e.message)
    } finally {
      setActionLoading(null)
    }
  }

  const filtered = filterTab === 'all'
    ? consents
    : consents.filter((c) => c.status === filterTab)

  return (
    <div className="flex flex-col gap-[16px]">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-[1.3rem] font-bold text-[#1f2937]">Consent Tracker</h2>
          <p className="text-[0.82rem] text-[#6b7280] mt-[2px]">
            Manage data-sharing consents for your students
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-[6px] px-[14px] py-[8px] bg-[#0F766E] text-white rounded-[8px] text-[0.82rem] font-semibold cursor-pointer hover:bg-[#0d5c56] transition-colors"
        >
          <i className="ti ti-plus text-[14px]" />
          New Consent
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-[2px] bg-[#f1f5f9] rounded-[8px] p-[4px] w-fit">
        {FILTER_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setFilterTab(t.key)}
            className={`px-[12px] py-[5px] rounded-[6px] text-[0.8rem] font-semibold cursor-pointer transition-colors border-none ${
              filterTab === t.key
                ? 'bg-white text-[#1f2937] shadow-sm'
                : 'bg-transparent text-[#6b7280] hover:text-[#374151]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {dispatchNotice && (
        <div className={`rounded-[10px] border px-[16px] py-[12px] text-[0.84rem] ${
          dispatchNotice.email_sent
            ? 'bg-[#ecfdf5] border-[#bbf7d0] text-[#065f46]'
            : 'bg-[#fff7ed] border-[#fed7aa] text-[#9a3412]'
        }`}>
          <div className="font-bold">
            {dispatchNotice.email_sent ? 'Consent email sent.' : 'Consent created, but email was not sent.'}
          </div>
          {!dispatchNotice.email_sent && dispatchNotice.email_error && (
            <div className="mt-[4px]">{dispatchNotice.email_error}</div>
          )}
          {dispatchNotice.consent_url && (
            <div className="mt-[6px] break-all">
              Consent link: <a className="underline font-semibold" href={dispatchNotice.consent_url} target="_blank" rel="noreferrer">{dispatchNotice.consent_url}</a>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-xl border border-[rgba(229,231,235,0.7)] overflow-hidden">
        <div className="flex items-center justify-between px-[20px] py-[14px] border-b border-[#f1f5f9]">
          <div className="flex items-center gap-[8px]">
            <i className="ti ti-file-check text-[16px] text-[#6b7280]" />
            <span className="text-[0.9rem] font-bold text-[#1f2937]">Consents</span>
            {!loading && (
              <span className="text-[0.78rem] text-[#9ca3af] ml-[4px]">({filtered.length})</span>
            )}
          </div>
          <button
            onClick={load}
            className="flex items-center gap-[6px] px-[12px] py-[6px] bg-[#0F766E] text-white rounded-[7px] text-[0.78rem] font-semibold cursor-pointer hover:bg-[#115E59] transition-colors"
          >
            <i className="ti ti-refresh text-[14px]" />
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-[60px] text-[#6b7280]">
            <div className="w-[24px] h-[24px] border-2 border-[#e5e7eb] border-t-[#0F766E] rounded-full animate-spin mr-[10px]" />
            <span className="text-[0.82rem]">Loading consents...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-[60px] text-[#ef4444]">
            <i className="ti ti-alert-circle text-[32px] mb-[8px]" />
            <span className="text-[0.82rem]">{error}</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-[60px] text-[#9ca3af]">
            <i className="ti ti-file-x text-[32px] mb-[8px]" />
            <span className="text-[0.82rem]">No consents found</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[0.82rem]">
              <thead className="bg-[#f9fafb]">
                <tr className="text-[#6b7280] font-semibold text-[0.72rem] uppercase tracking-wider">
                  <th className="text-left py-[10px] px-[20px]">Student</th>
                  <th className="text-left py-[10px] px-[20px]">Recipient</th>
                  <th className="text-left py-[10px] px-[20px]">Mode</th>
                  <th className="text-left py-[10px] px-[20px]">Status</th>
                  <th className="text-left py-[10px] px-[20px]">Dispatched</th>
                  <th className="text-left py-[10px] px-[20px]">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f1f5f9]">
                {filtered.map((consent) => {
                  const isActing = actionLoading === consent.id
                  return (
                    <tr key={consent.id} className="hover:bg-[#f8fafc] transition-colors">
                      <td className="py-[12px] px-[20px] font-medium text-[#1f2937]">
                        {consent.student_name || consent.student_id}
                      </td>
                      <td className="py-[12px] px-[20px]">
                        <div className="text-[#1f2937]">{consent.recipient_email}</div>
                        <div className="text-[0.7rem] text-[#9ca3af] capitalize">{consent.recipient_role}</div>
                      </td>
                      <td className="py-[12px] px-[20px] text-[#6b7280]">
                        {consent.mode === 'ON_DEMAND' ? 'On-demand' : 'Continuous'}
                      </td>
                      <td className="py-[12px] px-[20px]">
                        <span className={`inline-block px-[8px] py-[2px] rounded-full text-[0.7rem] font-semibold ${STATUS_STYLE[consent.status]}`}>
                          {consent.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-[12px] px-[20px] text-[#6b7280]">
                        {formatDate(consent.dispatched_at)}
                      </td>
                      <td className="py-[12px] px-[20px]">
                        <div className="flex items-center gap-[6px]">
                          {consent.status === 'DRAFT' && (
                            <button
                              onClick={() => handleAction(() => dispatchConsent(consent.id), consent.id)}
                              disabled={isActing}
                              className="px-[10px] py-[4px] bg-[#0F766E] text-white rounded-[6px] text-[0.72rem] font-semibold cursor-pointer hover:bg-[#0d5c56] transition-colors disabled:opacity-50"
                            >
                              {isActing ? '...' : 'Dispatch'}
                            </button>
                          )}
                          {(consent.status === 'PENDING' || consent.status === 'VIEWED') && (
                            <>
                              <button
                                onClick={() => handleAction(() => remindConsent(consent.id), consent.id)}
                                disabled={isActing}
                                className="px-[10px] py-[4px] bg-[#dbeafe] text-[#1e40af] rounded-[6px] text-[0.72rem] font-semibold cursor-pointer hover:bg-[#bfdbfe] transition-colors disabled:opacity-50"
                              >
                                {isActing ? '...' : 'Remind'}
                              </button>
                              <button
                                onClick={() => handleAction(() => cancelConsent(consent.id), consent.id)}
                                disabled={isActing}
                                className="px-[10px] py-[4px] bg-[#fee2e2] text-[#991b1b] rounded-[6px] text-[0.72rem] font-semibold cursor-pointer hover:bg-[#fecaca] transition-colors disabled:opacity-50"
                              >
                                Cancel
                              </button>
                            </>
                          )}
                          {(consent.status === 'DECLINED' || consent.status === 'EXPIRED') && (
                            <button
                              onClick={() => handleAction(() => dispatchConsent(consent.id), consent.id)}
                              disabled={isActing}
                              className="px-[10px] py-[4px] bg-[#0F766E] text-white rounded-[6px] text-[0.72rem] font-semibold cursor-pointer hover:bg-[#0d5c56] transition-colors disabled:opacity-50"
                            >
                              {isActing ? '...' : 'Re-dispatch'}
                            </button>
                          )}
                          {consent.status === 'ACCEPTED' && (
                            <span className="text-[0.72rem] text-[#22c55e] font-semibold flex items-center gap-[4px]">
                              <i className="ti ti-check" /> Accepted
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <NewConsentModal
          students={students}
          onClose={() => setShowModal(false)}
          onCreated={(consent) => {
            setDispatchNotice(consent)
            load()
          }}
        />
      )}
    </div>
  )
}
