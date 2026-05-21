import { useEffect, useState, useRef, useCallback } from 'react'
import { useAuthStore, useNotificationStore } from '../store'
import {
  getMyConversations, sendDirectMessage, getDirectConversation,
  getGroupMessages, sendGroupMessage, markGroupRead,
} from '../api/counsellor'
import type { GroupConversationPreview, GroupMessage } from '../types'
import NewMessageDialog from '../components/shared/NewMessageDialog'

function formatTime(d: string) {
  if (!d) return ''
  const dt = new Date(d)
  const now = new Date()
  const diff = now.getTime() - dt.getTime()
  if (diff < 86400000) return dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

type ChatMode = 'direct' | 'group'

export default function StudentCommunicationsPage() {
  const user = useAuthStore((s) => s.user)
  const isGroupMuted = useNotificationStore((s) => s.isGroupMuted)
  const [conversations, setConversations] = useState<any[]>([])
  const [groupConversations, setGroupConversations] = useState<GroupConversationPreview[]>([])
  const [activeConversation, setActiveConversation] = useState<string | null>(null)
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null)
  const [chatMode, setChatMode] = useState<ChatMode>('direct')
  const [directMessages, setDirectMessages] = useState<any[]>([])
  const [groupMessages, setGroupMessages] = useState<GroupMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [showNewMessage, setShowNewMessage] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadData = useCallback(async () => {
    try {
      const data = await getMyConversations()
      setConversations(data.direct || [])
      setGroupConversations(data.groups || [])
    } catch {}
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [directMessages, groupMessages])

  useEffect(() => {
    if (!activeConversation || chatMode !== 'direct') return
    getDirectConversation(activeConversation).then((data) => {
      setDirectMessages(data || [])
    }).catch(() => {})
  }, [activeConversation, chatMode])

  useEffect(() => {
    if (!activeGroupId || chatMode !== 'group') return
    getGroupMessages(activeGroupId).then((data) => {
      setGroupMessages(data.messages || [])
      markGroupRead(activeGroupId).catch(() => {})
      loadData()
    }).catch(() => {})
  }, [activeGroupId, chatMode, loadData])

  const handleSend = async () => {
    if (!input.trim() || sending) return
    setSending(true)
    try {
      if (chatMode === 'group' && activeGroupId) {
        const msg = await sendGroupMessage(activeGroupId, input.trim())
        setGroupMessages((prev) => [...prev, msg])
      } else if (chatMode === 'direct' && activeConversation) {
        const msg = await sendDirectMessage(activeConversation, input.trim())
        setDirectMessages((prev: any) => [...prev, msg])
        loadData()
      }
      setInput('')
    } catch {}
    setSending(false)
  }

  const handleSelectConversation = (otherId: string) => {
    setActiveGroupId(null)
    setChatMode('direct')
    setActiveConversation(otherId)
  }

  const handleSelectGroup = (groupId: string) => {
    setActiveConversation(null)
    setChatMode('group')
    setActiveGroupId(groupId)
  }

  const handleNewMessage = (selectedUser: any) => {
    setShowNewMessage(false)
    handleSelectConversation(selectedUser.id)
  }

  const activeConv = conversations.find((c) => c.other_id === activeConversation)
  const activeGroup = groupConversations.find((g) => g.group_id === activeGroupId)

  return (
    <div className="flex flex-col gap-[16px] h-[calc(100vh-130px)]">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[1.3rem] font-bold text-[#1f2937]">Messages</h2>
          <p className="text-[0.82rem] text-[#6b7280] mt-[2px]">
            Chat with counsellors and groups
          </p>
        </div>
        <button
          onClick={() => setShowNewMessage(true)}
          className="px-[14px] py-[8px] bg-[#0F766E] text-white rounded-[8px] cursor-pointer hover:bg-[#115E59] flex items-center gap-[6px] text-[0.82rem] font-semibold border-none"
        >
          <i className="ti ti-plus text-[15px]" />
          New Message
        </button>
      </div>

      <div className="flex gap-[12px] flex-1 min-h-0">
        {/* Conversation list */}
        <div className="w-[260px] flex-shrink-0 bg-white rounded-xl border border-[rgba(229,231,235,0.7)] flex flex-col">
          <div className="flex-1 overflow-y-auto">
            {conversations.length === 0 && groupConversations.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-[40px] text-[#9ca3af]">
                <i className="ti ti-messages text-[28px] mb-[6px]" />
                <span className="text-[0.78rem]">No conversations</span>
              </div>
            ) : (
              <>
                {conversations.map((c) => (
                  <div
                    key={c.other_id}
                    onClick={() => handleSelectConversation(c.other_id)}
                    className={`px-[14px] py-[10px] cursor-pointer border-b border-[#f8fafc] transition-colors ${
                      activeConversation === c.other_id && chatMode === 'direct'
                        ? 'bg-[#f0fdfa] border-l-[3px] border-l-[#0F766E]'
                        : 'hover:bg-[#f9fafb]'
                    }`}
                  >
                    <div className="flex items-center gap-[10px]">
                      <div className="w-[32px] h-[32px] rounded-full bg-gradient-to-br from-[#0F766E] to-[#1D9E75] flex items-center justify-center text-white font-bold text-[0.7rem] flex-shrink-0">
                        {c.other_name?.charAt(0) || '?'}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-[0.78rem] font-semibold text-[#1f2937] truncate">{c.other_name}</span>
                          <span className="text-[0.62rem] text-[#9ca3af] flex-shrink-0">{formatTime(c.last_time)}</span>
                        </div>
                        <span className="text-[0.7rem] text-[#6b7280] truncate block">{c.last_message || 'No messages'}</span>
                      </div>
                    </div>
                  </div>
                ))}
                {groupConversations.map((g) => {
                  const muted = isGroupMuted(g.group_id)
                  return (
                    <div
                      key={g.group_id}
                      onClick={() => handleSelectGroup(g.group_id)}
                      className={`px-[14px] py-[10px] cursor-pointer border-b border-[#f8fafc] transition-colors ${
                        activeGroupId === g.group_id && chatMode === 'group'
                          ? 'bg-[#f0fdfa] border-l-[3px] border-l-[#7c3aed]'
                          : 'hover:bg-[#f9fafb]'
                      }`}
                    >
                      <div className="flex items-center gap-[10px]">
                        <div className="w-[32px] h-[32px] rounded-full bg-gradient-to-br from-[#7c3aed] to-[#a78bfa] flex items-center justify-center text-white font-bold text-[0.7rem] flex-shrink-0">
                          <i className="ti ti-users text-[14px]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-[0.78rem] font-semibold text-[#1f2937] truncate flex items-center gap-[4px]">
                              {g.name}
                              {muted && <i className="ti ti-bell-off text-[11px] text-[#9ca3af]" />}
                            </span>
                          </div>
                          <div className="flex items-center gap-[4px]">
                            {g.last_sender && (
                              <span className="text-[0.65rem] text-[#4b5563]">{g.last_sender}: </span>
                            )}
                            <span className="text-[0.7rem] text-[#6b7280] truncate flex-1">{g.last_message}</span>
                            {g.unread > 0 && (
                              <span className="bg-[#7c3aed] text-white text-[0.55rem] font-bold px-[5px] py-[1px] rounded-full">
                                {g.unread}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        </div>

        {/* Chat area */}
        <div className="flex-1 bg-white rounded-xl border border-[rgba(229,231,235,0.7)] flex flex-col">
          {!activeConversation && !activeGroupId ? (
            <div className="flex flex-col items-center justify-center flex-1 text-[#9ca3af]">
              <i className="ti ti-message text-[40px] mb-[10px]" />
              <span className="text-[0.9rem] font-medium">Select a conversation</span>
              <span className="text-[0.78rem]">Choose a counsellor or group to message</span>
            </div>
          ) : (
            <>
              <div className="px-[18px] py-[12px] border-b border-[#f1f5f9] flex items-center gap-[10px]">
                <div className={`w-[34px] h-[34px] rounded-full flex items-center justify-center text-white font-bold text-[0.72rem] ${
                  chatMode === 'group'
                    ? 'bg-gradient-to-br from-[#7c3aed] to-[#a78bfa]'
                    : 'bg-gradient-to-br from-[#0F766E] to-[#1D9E75]'
                }`}>
                  {chatMode === 'group' ? (
                    <i className="ti ti-users text-[15px]" />
                  ) : (
                    activeConv?.other_name?.charAt(0) || '?'
                  )}
                </div>
                <div>
                  <div className="text-[0.85rem] font-semibold text-[#1f2937]">
                    {chatMode === 'group' ? activeGroup?.name : activeConv?.other_name || 'Unknown'}
                  </div>
                  <div className="text-[0.68rem] text-[#6b7280]">
                    {chatMode === 'group' ? `${activeGroup?.member_count || 0} members` : activeConv?.other_email || ''}
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-[18px] space-y-[8px]">
                {(chatMode === 'direct' ? directMessages : groupMessages).length === 0 ? (
                  <div className="flex items-center justify-center h-full text-[#9ca3af] text-[0.78rem]">
                    No messages yet. Send a message to start.
                  </div>
                ) : (
                  (chatMode === 'direct' ? directMessages : groupMessages).map((msg: any) => {
                    const isMyMessage = chatMode === 'direct'
                      ? msg.sender_id !== activeConversation
                      : msg.sender_id === user?.id
                    return (
                      <div key={msg.id} className={`flex ${isMyMessage ? 'justify-end' : 'justify-start'}`}>
                        <div className="max-w-[70%]">
                          {!isMyMessage && chatMode === 'group' && (
                            <div className="text-[0.68rem] font-medium text-[#4b5563] mb-[2px] ml-[2px]">
                              {msg.sender_name}
                            </div>
                          )}
                          <div className={`px-[14px] py-[9px] rounded-[14px] text-[0.82rem] ${
                            isMyMessage
                              ? 'bg-[#0F766E] text-white rounded-br-[4px]'
                              : 'bg-[#f3f4f6] text-[#1f2937] rounded-bl-[4px]'
                          }`}>
                            {msg.message}
                            <div className={`text-[0.6rem] mt-[3px] ${isMyMessage ? 'text-[#a7f3d0]' : 'text-[#9ca3af]'}`}>
                              {formatTime(msg.created_at)}
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })
                )}
                <div ref={bottomRef} />
              </div>

              <div className="px-[18px] py-[12px] border-t border-[#f1f5f9] flex items-center gap-[10px]">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                  placeholder="Type a message..."
                  className="flex-1 px-[14px] py-[9px] rounded-[10px] border border-[#e5e7eb] text-[0.82rem] outline-none focus:border-[#0F766E]"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || sending}
                  className="px-[14px] py-[9px] bg-[#0F766E] text-white rounded-[10px] cursor-pointer hover:bg-[#115E59] disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-[6px] text-[0.82rem] font-semibold border-none"
                >
                  <i className="ti ti-send text-[14px]" />
                  Send
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {showNewMessage && (
        <NewMessageDialog
          roleFilter="counsellor"
          excludeId={user?.id}
          onSelect={handleNewMessage}
          onClose={() => setShowNewMessage(false)}
        />
      )}
    </div>
  )
}
