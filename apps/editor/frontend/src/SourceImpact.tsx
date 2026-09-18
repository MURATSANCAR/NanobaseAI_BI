import React, { useEffect, useRef, useState } from 'react';

type Props = { token: string; generationId: string; targetId: string; targetLabel: string };
type State = 'CURRENT' | 'STALE' | 'UNRESOLVED';
type RecordItem = { id: string; kind: string; record_key: string; pdf_pages: number[]; state: State; reasons: string[]; distance?: number };
type Result = { generation_id: string; target: RecordItem; items: RecordItem[]; offset: number; has_more: boolean; total: number; snapshot_sha256: string; graph_scope: string; complete: boolean; semantic_acceptance: boolean };
const states: Record<State, string> = { CURRENT: 'Bağları güncel', STALE: 'Yeniden değerlendirme gerekiyor', UNRESOLVED: 'Kaynak bağı belirsiz' };
const kinds: Record<string, string> = {
  source_spans: 'Metin bölgesi', source_fragments: 'Küçük metin bölgesi', page_claims: 'Sayfa bulguları',
  semantic_reviews: 'Anlam denetimi', semantic_synthesis: 'Analiz taslağı', source_passages: 'Yanıta kaynak olan bölüm',
  source_index: 'Kaynak araması', answers: 'Soru yanıtı', page_context_roles: 'Sayfanın amacı',
  evidence: 'Kaynak sayfası', layout_regions: 'Sayfa yerleşimi', figure_identity: 'Karakter kimliği incelemesi',
  cross_page_attributions: 'Sayfalar arası konuşmacı incelemesi', character_evidence: 'Karakter dayanakları',
};
const reasonLabels: Record<string, string> = {
  STRUCTURAL_REFERENCES_CURRENT: 'Bilinen kaynak bağlantıları mevcut kayıtlarla eşleşiyor.',
  SOURCE_READING_REQUIRES_REVIEW: 'Kaynak okumasındaki belirsizlik henüz çözülmemiş.',
  HUMAN_REVIEW_REJECTED: 'Editör incelemesi bu kaynağın kullanımını reddediyor.',
  HUMAN_REVIEW_REQUIRED: 'Kaynağın kullanımı için editör incelemesi istenmiş.',
  DEPENDENCY_REFERENCE_MISSING: 'Gerekli bir kaynak bağlantısı bulunamadı.',
  DEPENDENCY_HASH_MISMATCH: 'Dayanak kayıt değişmiş; sonuç yeniden değerlendirilmeli.',
  DEPENDENCY_REVIEW_CHANGED: 'Dayanağın inceleme kararı değişmiş.',
  DEPENDENCY_STALE: 'Bağlı dayanaklardan biri artık güncel değil.',
  DEPENDENCY_UNRESOLVED: 'Bağlı dayanaklardan birinin durumu belirsiz.',
  AUTHORITY_NOT_ESTABLISHED: 'Bu sonucu destekleyecek yeterli kaynak denetimi yok.',
  PAGE_CONTEXT_INPUT_INFERRED: 'Sayfa bağlamına ilişkin bazı bağlantılar kesinleştirilemedi.',
  MODEL_OUTPUT_NOT_ACCEPTED: 'Model çıktısı gerekli kontrollerden geçmemiş.',
  CODE_VERSION_CHANGED: 'İşleme yöntemi değiştiği için sonuç yeniden denetlenmeli.',
  EXPLICIT_REJECT: 'İnceleme kararı bu kaynağın kullanımını reddediyor.',
  EXPLICIT_NEEDS_REVIEW: 'Bu kaynak için inceleme istenmiş.',
  SOURCE_HASH_MISMATCH: 'Kaynak değiştiği için bu kayıt yeniden değerlendirilmeli.',
  MISSING_DEPENDENCY: 'Gerekli bir kaynak bağlantısı bulunamadı.',
  UNSUPPORTED_RECORD_KIND: 'Bu kayıt türünün bütün kaynak bağlantıları henüz denetlenemiyor.',
};
const reason = (value: string) => reasonLabels[value] ?? 'Bu bağlantının dayanakları ayrıca incelenmeli.';
function validRecord(value: any, descendant: boolean): value is RecordItem {
  return value && typeof value.id === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value.id)
    && typeof value.kind === 'string' && typeof value.record_key === 'string'
    && Object.prototype.hasOwnProperty.call(states, value.state) && Array.isArray(value.reasons) && value.reasons.every((r: unknown) => typeof r === 'string')
    && Array.isArray(value.pdf_pages) && value.pdf_pages.every((p: unknown) => Number.isInteger(p) && (p as number) > 0)
    && (!descendant || (Number.isInteger(value.distance) && value.distance > 0));
}

export function SourceImpact(props: Props) {
  return <ImpactView key={props.generationId + ':' + props.targetId} {...props} />;
}
function ImpactView({ token, generationId, targetId, targetLabel }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<(Result & { token: string }) | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const request = useRef<AbortController | null>(null);
  const active = useRef({ token, serial: 0 });
  if (active.current.token !== token) active.current = { token, serial: active.current.serial + 1 };
  const current = data?.token === token ? data : null;

  async function load(offset: number, previous: typeof data) {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const serial = ++active.current.serial;
    const alive = () => !controller.signal.aborted && serial === active.current.serial;
    setLoading(true); setError('');
    try {
      const snapshot = previous ? '&expected_snapshot_sha256=' + encodeURIComponent(previous.snapshot_sha256) : '';
      const response = await fetch(`/v1/generations/${encodeURIComponent(generationId)}/records/${encodeURIComponent(targetId)}/impact?offset=${offset}&limit=50${snapshot}`, {
        cache: 'no-store', signal: controller.signal, headers: { Authorization: 'Bearer ' + token },
      });
      if (response.status === 409) {
        const failure = await response.json().catch(() => null);
        if (failure?.detail === 'IMPACT_SNAPSHOT_CHANGED') {
          if (alive()) setData(null);
          throw new Error('Kaynak bağlantıları değişti. Güncel sonuçlar için listeyi yeniden yükleyin.');
        }
      }
      if (!response.ok) throw new Error(response.status === 403 ? 'Bu kaydın kaynak bağlantılarını görme yetkiniz yok.' : 'Kaynak bağlantıları alınamadı. Yeniden deneyebilirsiniz.');
      const result: Result = await response.json();
      if (!alive()) return;
      if (!result || typeof result !== 'object' || result.generation_id !== generationId || !validRecord(result.target, false) || result.target.id !== targetId
          || result.graph_scope !== 'SOURCE_DEPENDENCIES' || result.complete !== false || result.semantic_acceptance !== false
          || typeof result.snapshot_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(result.snapshot_sha256)
          || result.offset !== offset || typeof result.has_more !== 'boolean' || !Number.isInteger(result.total) || result.total < 0
          || !Array.isArray(result.items) || result.items.length > 50 || result.items.some(item => !validRecord(item, true) || item.id === targetId)
          || new Set(result.items.map(item => item.id)).size !== result.items.length
          || offset + result.items.length > result.total || result.has_more !== (offset + result.items.length < result.total)
          || (result.has_more && !result.items.length)) throw new Error('Kaynak bağlantılarının kapsamı doğrulanamadı. Listeyi yeniden yükleyin.');
      if (previous && (previous.snapshot_sha256 !== result.snapshot_sha256 || previous.total !== result.total || JSON.stringify(previous.target) !== JSON.stringify(result.target)
          || result.items.some(item => previous.items.some(old => old.id === item.id))))
        throw new Error('Kaynak bağlantıları değişmiş olabilir. Karışık sonuç göstermemek için listeyi yeniden yükleyin.');
      setData({ ...result, items: [...(previous?.items ?? []), ...result.items], token });
    } catch (e) {
      if (alive()) setError(e instanceof Error && !(e instanceof SyntaxError) && !(e instanceof TypeError)
        ? e.message : 'Kaynak bağlantıları alınamadı. Yeniden deneyebilirsiniz.');
    }
    finally { if (alive()) setLoading(false); }
  }
  useEffect(() => {
    setData(null); setError('');
    if (open) void load(0, null);
    else { request.current?.abort(); setLoading(false); }
    return () => request.current?.abort();
  }, [open, token, refresh]);

  return <details className="source-impact" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Bu kaynağa bağlı sonuçları gör</summary>
    {open && <div>
      <p><b>{targetLabel}</b></p>
      <p className="hint">“Bağları güncel” yalnız kayıtların kaynak bağlantılarını anlatır; içerik doğruluğu veya editör onayı değildir. Bu görünüm bütün bağlantıları kapsamayabilir.</p>
      {current && <>
        <p data-testid="impact-target-state">{states[current.target.state]}</p>
        {!!current.target.reasons.length && <ul>{[...new Set(current.target.reasons.map(reason))].map(text => <li key={text}>{text}</li>)}</ul>}
        <p>{current.items.length}/{current.total} bağlı kayıt gösteriliyor.</p>
        <ul className="source-impact-list">{current.items.map(item => <li key={item.id} data-impact-record={item.id}>
          <b>{kinds[item.kind] ?? 'Bağlı kayıt'}</b> · {states[item.state]}
          {!!item.pdf_pages.length && <p>PDF sayfası: {item.pdf_pages.join(', ')}</p>}
          {[...new Set(item.reasons.map(reason))].map(text => <p className="hint" key={text}>{text}</p>)}
        </li>)}</ul>
        {!current.total && <p>Bu kapsamda bağlı sonuç bulunamadı. Bu, başka bağlantı olmadığı anlamına gelmez.</p>}
        {current.has_more && <button disabled={loading} onClick={() => void load(current.items.length, current)}>Diğer bağlı kayıtları göster</button>}
      </>}
      {loading && <p role="status">Kaynak bağlantıları alınıyor…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {!loading && <button onClick={() => setRefresh(value => value + 1)}>Listeyi yeniden yükle</button>}
    </div>}
  </details>;
}
