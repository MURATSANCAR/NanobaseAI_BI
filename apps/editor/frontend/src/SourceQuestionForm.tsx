import React, { useEffect, useRef, useState } from 'react';

type Props = { token: string; generationId: string; onQueued: (jobId: string) => Promise<void> };
type Readiness = { ready: boolean; scope: string; reason?: string };
type Attempt = { question: string; key: string; jobId?: string };
const statusLabels: Record<string, string> = {
  QUEUED: 'Soru sırada.', RUNNING: 'Soru işleniyor.', COMPLETED: 'Soru işlemesi tamamlandı. Sonucu inceleyebilirsiniz.',
  FAILED: 'Soru işlenemedi. İş kaydı inceleme için korundu.', CANCELLED: 'Soru işlemesi iptal edildi.',
};
const reasonLabels: Record<string, string> = {
  GENERATION_NOT_READY: 'Bu analizin kaynak hazırlığı henüz tamamlanmadı.',
  SOURCE_PREVIEW_NOT_READY: 'Kaynak destekli soru taslağı henüz hazır değil.',
  NO_ELIGIBLE_CLAIMS: 'Bu analizde soruya kaynak olabilecek doğrulanmış bir bulgu henüz yok.',
  NO_SOURCE_SUPPORTED_CLAIMS: 'Bu analizde soruya kaynak olabilecek doğrulanmış bir bulgu henüz yok.',
  EDITOR_REVIEW_REQUIRED: 'Bu işlem için editör incelemesi gerekiyor.',
};

export function SourceQuestionForm({ token, generationId, onQueued }: Props) {
  const [question, setQuestion] = useState('');
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [trackingError, setTrackingError] = useState('');
  const [status, setStatus] = useState('');
  const [jobId, setJobId] = useState('');
  const [trackedQuestion, setTrackedQuestion] = useState('');
  const [refresh, setRefresh] = useState(0);
  const attempts = useRef(new Map<string, Attempt>());
  const attemptsToken = useRef(token);
  const controller = useRef<AbortController | null>(null);
  const controllerVersion = useRef(-1);
  const observedJob = useRef<{ id: string; version: number } | null>(null);
  const scope = useRef({ generationId, token, version: 0 });
  if (scope.current.generationId !== generationId || scope.current.token !== token) {
    scope.current = { generationId, token, version: scope.current.version + 1 };
  }

  async function request(path: string, signal: AbortSignal, body?: object, key?: string) {
    const response = await fetch('/v1' + path, {
      method: body ? 'POST' : 'GET', cache: 'no-store', signal,
      headers: { Authorization: 'Bearer ' + token, ...(body ? { 'Content-Type': 'application/json', 'Idempotency-Key': key! } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      const explanation = typeof result?.detail === 'string' ? reasonLabels[result.detail] : undefined;
      throw new Error(explanation ?? (response.status === 401 ? 'Oturum doğrulanamadı. Erişim bilginizi kontrol edin.' :
        response.status === 403 ? 'Bu analizde soru sormak için editör yetkisi gerekiyor.' :
        `İşlem tamamlanamadı (${response.status}). Aynı soruyu güvenle tekrar gönderebilirsiniz.`));
    }
    if (!result || typeof result !== 'object') throw new Error('Sunucu yanıtı okunamadı. Aynı isteği tekrar deneyebilirsiniz.');
    return result;
  }

  async function checkReadiness(active: AbortController, version: number) {
    setChecking(true); setError('');
    try {
      const result = await request(`/generations/${encodeURIComponent(generationId)}/source-preview`, active.signal);
      if (active.signal.aborted || version !== scope.current.version) return;
      if (typeof result.ready !== 'boolean' || result.scope !== 'PARTIAL_SOURCE_SUPPORTED_DRAFT')
        throw new Error('Kaynak önizlemesinin kapsamı doğrulanamadı. Soru gönderimi kapalı.');
      setReadiness(result);
    } catch (e) {
      if (!active.signal.aborted && version === scope.current.version) { setReadiness(null); setError((e as Error).message); }
    } finally {
      if (!active.signal.aborted && version === scope.current.version) setChecking(false);
    }
  }

  useEffect(() => {
    const active = new AbortController();
    controller.current = active;
    const version = scope.current.version;
    controllerVersion.current = version;
    observedJob.current = null;
    if (attemptsToken.current !== token) { attempts.current.clear(); attemptsToken.current = token; }
    setQuestion(''); setJobId(''); setTrackedQuestion(''); setStatus(''); setError(''); setTrackingError(''); setReadiness(null); setBusy(false);
    setChecking(Boolean(generationId));
    if (generationId) void checkReadiness(active, version);
    return () => active.abort();
  }, [generationId, token]);

  useEffect(() => {
    if (!jobId || observedJob.current?.id !== jobId || observedJob.current.version !== scope.current.version) return;
    const active = new AbortController();
    const version = scope.current.version;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const result = await request(`/answers/${encodeURIComponent(jobId)}`, active.signal);
        if (active.signal.aborted || version !== scope.current.version) return;
        if (result.job_id !== jobId || result.generation_id !== generationId || !Object.prototype.hasOwnProperty.call(statusLabels, result.job_status))
          throw new Error('Soru işinin kimliği veya durumu doğrulanamadı.');
        setTrackingError('');
        setStatus(statusLabels[result.job_status]);
        if (!['QUEUED', 'RUNNING'].includes(result.job_status)) return;
      } catch (e) {
        if (active.signal.aborted || version !== scope.current.version) return;
        setTrackingError((e as Error).message);
      }
      timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { active.abort(); clearTimeout(timer); };
  }, [jobId, generationId, token, refresh]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (Array.from(text).length < 3 || Array.from(text).length > 1000) { setError('Sorunuz 3–1000 karakter olmalı.'); return; }
    if (!readiness?.ready || readiness.scope !== 'PARTIAL_SOURCE_SUPPORTED_DRAFT' || busy) return;
    const active = controller.current;
    if (!active || active.signal.aborted || controllerVersion.current !== scope.current.version) return;
    const version = scope.current.version;
    const current = () => !active.signal.aborted && version === scope.current.version;
    setBusy(true); setError('');
    try {
      const questionKey = JSON.stringify([generationId, text]);
      let attempt = attempts.current.get(questionKey);
      if (!attempt) {
        if (!crypto.randomUUID) throw new Error('Güvenli soru gönderimi için HTTPS bağlantısı gerekiyor.');
        attempt = { question: text, key: crypto.randomUUID() }; attempts.current.set(questionKey, attempt);
      }
      if (!attempt.jobId) {
        const result = await request('/questions', active.signal,
          { generation_id: generationId, question: attempt.question, mode: 'editor_preview' }, attempt.key);
        if (!current()) return;
        if (typeof result.job_id !== 'string' || !result.job_id || result.generation_id !== generationId || result.mode !== 'editor_preview')
          throw new Error('Soru kaydı doğrulanamadı. Aynı soruyu tekrar deneyebilirsiniz.');
        attempt.jobId = result.job_id;
      }
      if (!current()) return;
      const queuedJob = attempt.jobId;
      if (!queuedJob) throw new Error('Soru işinin kimliği alınamadı. Aynı soruyu tekrar deneyebilirsiniz.');
      observedJob.current = { id: queuedJob, version };
      setTrackedQuestion(attempt.question);
      setJobId(queuedJob); setStatus('Soru kaydı alındı. Sunucudan iş durumu kontrol ediliyor.');
      await onQueued(queuedJob);
      if (current()) setRefresh(value => value + 1);
    } catch (e) { if (current()) setError((e as Error).message); }
    finally { if (current()) setBusy(false); }
  }

  const ready = readiness?.ready === true && readiness.scope === 'PARTIAL_SOURCE_SUPPORTED_DRAFT';
  const existing = attempts.current.get(JSON.stringify([generationId, question.trim()]))?.jobId;
  const characters = Array.from(question.trim()).length;
  return <section className="upload-book" aria-label="Kaynak destekli soru taslağı">
    <h2>Kaynaklara soru sor</h2>
    <p className="hint">Yanıt, yalnız kaynakla desteklenen sınırlı bulgulardan hazırlanan bir editör taslağıdır. Kitabın tamamının doğrulandığı veya yanıtın yayıma hazır olduğu anlamına gelmez.</p>
    {!ready && <p role="status">{!generationId ? 'Önce bir analiz seçin.' : readiness ?
      (reasonLabels[readiness.reason ?? ''] ?? 'Bu analiz için kaynak destekli soru taslağı henüz kullanılamıyor.') : checking ? 'Kaynakların soru için hazır olup olmadığı kontrol ediliyor.' : 'Kaynakların soru için hazır olduğu doğrulanamadı.'}</p>}
    {!ready && generationId && <button disabled={checking || busy} onClick={() => {
      const active = controller.current;
      if (active && !active.signal.aborted && controllerVersion.current === scope.current.version)
        void checkReadiness(active, scope.current.version);
    }}>{checking ? 'Kontrol ediliyor…' : 'Kaynak durumunu yeniden kontrol et'}</button>}
    <form onSubmit={submit}>
      <label>Sorunuz<textarea required minLength={3} maxLength={2000} rows={4} value={question} disabled={busy}
        style={{ width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box', resize: 'vertical', font: 'inherit', overflowWrap: 'anywhere' }}
        onChange={event => { setQuestion(event.target.value); setError(''); }} /></label>
      <p className="hint">{characters}/1000 karakter</p>
      <button className="primary" disabled={!ready || busy || characters < 3 || characters > 1000}>{busy ? 'İstek gönderiliyor…' : existing ? 'Soru kaydını görüntüle' : 'Kaynaklardan yanıt iste'}</button>
    </form>
    {status && <p role="status">Son gönderilen soru: {trackedQuestion}<br />{status}</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {trackingError && <p role="alert" className="error">İş durumu yenilenemedi: {trackingError}</p>}
  </section>;
}
