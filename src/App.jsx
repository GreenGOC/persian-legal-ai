import { useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'legal-ai-conversations'
const THEME_KEY = 'legal-ai-theme'

function Icon({ name, size = 24 }) {
  const paths = {
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></>,
    moon: <path d="M20.4 15.1A8.4 8.4 0 0 1 8.9 3.6 8.4 8.4 0 1 0 20.4 15.1Z" />,
    settings: <><circle cx="12" cy="12" r="3.6" /><path d="M12 2.8v2.3M12 18.9v2.3M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2.8 12h2.3M18.9 12h2.3M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6" /></>,
    send: <path d="m21 3-7.3 18-3.8-7.2L3 10.2 21 3Zm-11 10.8L15 9" />,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" /><path d="M4 19a2.5 2.5 0 0 1 2.5-2.5H20M8 7h8" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    plus: <path d="M12 5v14M5 12h14" />,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function newConversation() {
  return { id: crypto.randomUUID(), title: 'گفت‌وگوی جدید', messages: [] }
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || 'light')
  const [conversations, setConversations] = useState(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [newConversation()] } catch { return [newConversation()] }
  })
  const [activeId, setActiveId] = useState(() => conversations[0].id)
  const [question, setQuestion] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const inputRef = useRef(null)
  const messagesRef = useRef(null)
  const activeConversation = conversations.find((item) => item.id === activeId) || conversations[0]

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])
  useEffect(() => localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations)), [conversations])

  const updateConversation = (id, update) => setConversations((items) => items.map((item) => item.id === id ? update(item) : item))
  const startConversation = () => {
    const conversation = newConversation()
    setConversations((items) => [conversation, ...items])
    setActiveId(conversation.id)
    setHistoryOpen(false)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  async function submit(event) {
    event?.preventDefault()
    const text = question.trim()
    if (!text || isSending) return
    const userMessage = { id: crypto.randomUUID(), role: 'user', text }
    updateConversation(activeId, (item) => ({ ...item, title: item.messages.length ? item.title : text.slice(0, 42), messages: [...item.messages, userMessage] }))
    setQuestion('')
    setIsSending(true)
    console.log('React: sending chat request to Django', { question: text })
    try {
      const response = await fetch('/api/chat/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text }) })
      const payload = await response.json()
      console.log('React: received chat response from Django', { status: response.status, payload })
      if (!response.ok) throw new Error(payload.error || 'پاسخی از سرور دریافت نشد.')
      const answer = { id: crypto.randomUUID(), role: 'assistant', text: payload.answer, citations: payload.citations || [] }
      updateConversation(activeId, (item) => ({ ...item, messages: [...item.messages, answer] }))
    } catch (error) {
      console.error('React: chat request failed', error)
      updateConversation(activeId, (item) => ({ ...item, messages: [...item.messages, { id: crypto.randomUUID(), role: 'assistant', error: true, text: error.message || 'ارتباط با سامانه برقرار نشد.' }] }))
    } finally { setIsSending(false) }
  }

  useEffect(() => {
    const el = messagesRef.current
    if (!el) return
    if (!activeConversation || activeConversation.messages.length === 0) return
    setTimeout(() => {
      el.scrollTop = el.scrollHeight
      inputRef.current?.focus()
    }, 0)
  }, [activeConversation?.messages.length, isSending, activeId])

  const deleteConversation = (id) => {
    const ok = window.confirm('آیا مطمئن هستید که می‌خواهید این گفتگو را حذف کنید؟')
    if (!ok) return
    setConversations((items) => {
      const next = items.filter((c) => c.id !== id)
      if (next.length === 0) {
        const created = [newConversation()]
        setActiveId(created[0].id)
        return created
      }
      if (id === activeId) {
        setActiveId(next[0].id)
      }
      return next
    })
  }

  return <main className="app-shell" dir="rtl">
    <header className="topbar">
      <button className="icon-button menu-button" onClick={() => setHistoryOpen(true)} aria-label="تاریخچه گفتگوها"><Icon name="menu" /></button>
      <div className="topbar-actions">
        <button className="theme-button" onClick={() => setTheme((value) => value === 'light' ? 'dark' : 'light')} aria-label="تغییر رنگ‌بندی">{theme === 'light' ? <Icon name="moon" size={21} /> : <Icon name="sun" size={21} />}</button>
      </div>
    </header>

    {historyOpen && <aside className="history-panel"><div className="history-heading"><h2>گفت‌وگوها</h2><button className="icon-button" onClick={() => setHistoryOpen(false)} aria-label="بستن"><Icon name="close" /></button></div><button className="new-chat" onClick={startConversation}><Icon name="plus" size={18} /> گفت‌وگوی جدید</button><div className="conversation-list">{conversations.map((conversation) => <div key={conversation.id} className={conversation.id === activeId ? 'conversation-row active' : 'conversation-row'}><button onClick={() => { setActiveId(conversation.id); setHistoryOpen(false) }} className={conversation.id === activeId ? 'conversation active' : 'conversation'}>{conversation.title}</button><button className="icon-button small delete-button" title="حذف گفتگو" onClick={(e) => { e.stopPropagation(); deleteConversation(conversation.id) }} aria-label="حذف"><Icon name="close" size={16} /></button></div>)}</div></aside>}

    <section className={activeConversation.messages.length ? 'chat-view has-messages' : 'chat-view'}>
      {activeConversation.messages.length > 0 && <div className="messages" ref={messagesRef}>{activeConversation.messages.map((message) => <article className={`message ${message.role}${message.error ? ' error' : ''}`} key={message.id}><p>{message.text}</p>{message.citations?.length > 0 && <div className="citations">{message.citations.map((citation, index) => <span key={`${citation.provision_id}-${index}`}>{citation.document_title}{citation.provision_number ? `، ${citation.provision_number}` : ''}</span>)}</div>}</article>)}{isSending && <div className="typing" aria-label="در حال دریافت پاسخ"><i /><i /><i /></div>}</div>}
      <form className="question-area" onSubmit={submit}><h1>سوال قانونی دارید؟</h1><div className="input-wrap"><textarea ref={inputRef} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="اینجا بنویسید" rows="1" aria-label="سوال قانونی شما" onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} /><button type="submit" disabled={!question.trim() || isSending} aria-label="ارسال سوال"><Icon name="send" size={21} /></button></div>{activeConversation.messages.length > 0 && <small>برای ارسال، Enter را بزنید</small>}</form>
    </section>


  </main>
}
