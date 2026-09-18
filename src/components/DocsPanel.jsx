import { useEffect, useMemo, useState } from 'react'
export default function DocsPanel({ open, onClose }) {
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [query, setQuery] = useState('')
  const [documents, setDocuments] = useState([])
  const [page, setPage] = useState(1)
  const [perPage] = useState(100)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [loadingDocs, setLoadingDocs] = useState(false)

  useEffect(() => {
    if (!open) { setSelectedDoc(null); setQuery('') }
  }, [open])

  useEffect(() => {
    async function load() {
      try {
        setLoadingDocs(true)
        const params = new URLSearchParams({ page: String(page), per_page: String(perPage) })
        if (query) params.set('q', query)
        const res = await fetch(`/api/documents/?${params.toString()}`)
        if (!res.ok) return
        const payload = await res.json()
        setDocuments(payload.results || [])
        setTotalPages(payload.total_pages || 1)
        setTotalCount(payload.total_count || 0)
      } catch (e) { console.error(e) } finally { setLoadingDocs(false) }
    }
    if (open) load()
  }, [open, page, query, perPage])

  return (
    <aside className={open ? 'docs-panel open' : 'docs-panel'} aria-hidden={!open}>
      <div className="docs-header">
        <button className="icon-button small back-button" onClick={onClose} aria-label="بازگشت">⇦</button>
        <h3>اسناد قانونی</h3>
        <button className="close-panel" onClick={onClose} aria-label="بستن پنل">✕</button>
      </div>
      <div className="docs-body">
        <div className="docs-list">
            <div className="search-top">
              <input className="search-input" placeholder="جستجو (کلمات را با ویرگوم یا فاصله جدا کنید)" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1) }} />
            </div>
          {loadingDocs && <div className="docs-loading">در حال بارگذاری...</div>}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingTop: 6 }}>
            <label style={{ fontSize: 13, color: '#6f7c73' }}>برو به صفحه:</label>
            <input className="page-jump" type="number" min={1} max={totalPages} value={page} onChange={(e) => {
              const v = Number(e.target.value) || 1; setPage(Math.max(1, Math.min(totalPages, v)))
            }} />
          </div>
          {!loadingDocs && documents.length === 0 && <div className="empty">موردی یافت نشد</div>}
          {!loadingDocs && documents.map((doc) => (
            <div key={doc.id} className="docs-list-item" onClick={async () => {
              try {
                const res = await fetch(`/api/documents/${doc.id}/provisions/`)
                if (!res.ok) throw new Error('failed')
                const payload = await res.json()
                setSelectedDoc(payload)
              } catch (e) { console.error(e) }
            }}>
              <div className="docs-list-title">{doc.title}</div>
              <div className="docs-list-desc">{doc.description}</div>
            </div>
          ))}

          <div className="docs-pagination">
            <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p-1))}>Prev</button>
            <span>صفحه {page} از {totalPages} ({totalCount} مورد)</span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p+1))}>Next</button>
          </div>
        </div>
        <div className="docs-view">
          {selectedDoc ? <DocView doc={selectedDoc} onClose={() => setSelectedDoc(null)} /> : <div className="placeholder">یکی از اسناد را انتخاب کنید</div>}
        </div>
      </div>
    </aside>
  )
}

function DocView({ doc }) {
  const [relationshipsCache, setRelationshipsCache] = useState({})
  const [visibleRels, setVisibleRels] = useState({})

  async function fetchRelationships(provisionId) {
    try {
      const res = await fetch(`/api/relationships/?provision_id=${encodeURIComponent(provisionId)}`)
      if (!res.ok) return null
      return await res.json()
    } catch (e) { console.error(e); return null }
  }

  async function ensureRelationships(provision) {
    if (relationshipsCache[provision.id]) return relationshipsCache[provision.id]
    const payload = await fetchRelationships(provision.id)
    const value = payload || { incoming: [], outgoing: [] }
    setRelationshipsCache((s) => ({ ...s, [provision.id]: value }))
    return value
  }

  // modal state for displaying relationships
  const [relModal, setRelModal] = useState({ open: false, provision: null, kind: null, data: null })

  async function openRelationshipsModal(provision, kind) {
    const data = await ensureRelationships(provision)
    setRelModal({ open: true, provision, kind, data })
  }

  function closeRelModal() { setRelModal({ open: false, provision: null, kind: null, data: null }) }

  return (
    <div className="doc-view-root">
      <h2 className="doc-title">{doc.title}</h2>
      <div className="struct-groups">
        {doc.sections && doc.sections.map((section, sidx) => (
          <section key={sidx} className="struct-group">
            {section.title ? <h3 className="group-title">{section.title}</h3> : null}
            <div className="group-items">
              {section.provisions.map((item) => (
                <article key={item.id} className="provision">
                  <div className="provision-head">
                    <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
                      <div className="provision-number">{item.display_label || item.number}</div>
                    </div>
                    <div className="provision-actions">
                      <button className="rel-button" onClick={() => openRelationshipsModal(item, 'outgoing')}>روابط (منبع)</button>
                      <button className="rel-button" onClick={() => openRelationshipsModal(item, 'incoming')}>روابط (مقصد)</button>
                    </div>
                  </div>
                  <div className="provision-text">
                    {Array.isArray(item.sentences) ? item.sentences.map((s, i) => <p key={i}>{s}</p>) : (item.sentences || '').split('\n\n').map((s, i) => <p key={i}>{s}</p>)}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>

      {relModal.open && (
        <div className="rel-modal" role="dialog" aria-modal="true">
          <div className="rel-modal-backdrop" onClick={closeRelModal} />
          <div className="rel-modal-body">
            <div className="rel-modal-header">
              <h3>روابط — {relModal.kind === 'outgoing' ? 'منبع' : 'مقصد'}</h3>
              <button className="icon-button" onClick={closeRelModal}>×</button>
            </div>
            <div className="rel-modal-content">
              {relModal.data && relModal.data.outgoing && relModal.kind === 'outgoing' && relModal.data.outgoing.length === 0 && <div>روابتی یافت نشد</div>}
              {relModal.data && relModal.data.incoming && relModal.kind === 'incoming' && relModal.data.incoming.length === 0 && <div>روابتی یافت نشد</div>}
              {relModal.data && relModal.kind === 'outgoing' && relModal.data.outgoing.map(r => (
                <div key={r.id} className="relationship-row">{r.relationship_type} → {r.target?.number || r.target?.id} <div className="rel-context">{(r.contexts||[]).map(c=>c.source_text).join(' — ')}</div></div>
              ))}
              {relModal.data && relModal.kind === 'incoming' && relModal.data.incoming.map(r => (
                <div key={r.id} className="relationship-row">{r.relationship_type} ← {r.source?.number || r.source?.id} <div className="rel-context">{(r.contexts||[]).map(c=>c.target_text).join(' — ')}</div></div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
// Doc view now expects provisions to include `display_label` and `sentences`.
