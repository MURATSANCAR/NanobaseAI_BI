import React, { useEffect, useRef, useState } from "react";

type Props = { token: string; onStarted: (work: string, job: string) => Promise<void> };
export function UploadBook({ token, onStarted }: Props) {
  const [title, setTitle] = useState("");
  const [label, setLabel] = useState("İlk yükleme");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [upload, setUpload] = useState("");
  const [state, setState] = useState<any>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [recentOffset, setRecentOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [startedJob, setStartedJob] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [refresh, setRefresh] = useState(0);
  const attempt = useRef<any>({});
  const alive = useRef(true);
  const controller = useRef(new AbortController());
  useEffect(() => () => { alive.current = false; controller.current.abort(); }, []);

  async function request(path: string, body?: object, key?: string) {
    const response = await fetch("/v1" + path, {
      method: body ? "POST" : "GET", cache: "no-store",
      signal: controller.current.signal,
      headers: { Authorization: "Bearer " + token, ...(body ? { "Content-Type": "application/json", "Idempotency-Key": key! } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(`İşlem tamamlanamadı (${response.status}): ${result.detail ?? "Bağlantıyı kontrol edin"}`);
    return result;
  }
  useEffect(() => {
    request('/uploads').then(r => { if (alive.current) { setRecent(r.items); setRecentOffset(r.items.length); setHasMore(r.has_more); } }).catch(e => { if (alive.current) setError(e.message); });
  }, []);
  async function loadMore() {
    setLoadingRecent(true);
    try {
      const result = await request('/uploads?offset=' + recentOffset);
      if (result.has_more && !result.items.length) throw new Error('Yükleme listesi ilerlemedi. Tekrar deneyin.');
      if (alive.current) {
        setRecent(previous => Array.from(new Map([...previous, ...result.items].map(row => [row.id, row])).values()));
        setRecentOffset(previous => previous + result.items.length);
        setHasMore(result.has_more);
      }
    } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setLoadingRecent(false); }
  }
  useEffect(() => {
    if (!upload) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request("/uploads/" + upload);
        if (!active) return;
        setState(next); setError("");
        if (next.status === "CREATED") { setMessage("Dosya aktarımı tamamlanmamış. Aynı PDF dosyasını seçerek yüklemeyi sürdürebilirsiniz."); return; }
        if (next.status === "RECEIVED") { setMessage("PDF alındı. Kaynak hazırlamayı başlatabilirsiniz."); return; }
        if (next.status === "COMPLETED") { setMessage("Kaynak hazır. Kitap analizini başlatabilirsiniz."); return; }
        if (next.status === "FAILED") { setError("Kaynak hazırlanamadı: " + next.error_code); return; }
        if (next.status === "CANCELLED") { setMessage("Kaynak hazırlama iptal edildi. Önceki kayıtlar korundu."); return; }
        const p=next.progress?.progress;
        setMessage(p?.page_local_ocr_completed ? `Konumlu metin okuma: ${p.page_local_ocr_completed}/${p.total} sayfa.` : p?.rendered_pages ? `Sayfa görüntüleri: ${p.rendered_pages}/${p.total_pages}. Kaynak hazırlanıyor.` : "Kaynak hazırlanıyor. Bu işlem sayfa sayısına göre sürebilir.");
      } catch (e) { if (active) setError((e as Error).message); }
      if (active) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [upload, token, refresh]);

  async function resume() {
    const selectedUpload = upload;
    setBusy(true); setError("");
    try {
      // Recheck server state: another browser may have completed this upload.
      const current = await request("/uploads/" + selectedUpload);
      if (alive.current) setState(current);
      if (current.status === "CREATED") {
        if (!resumeFile) throw new Error("Bu yüklemeyi başlatırken kullandığınız PDF dosyasını seçin.");
        setMessage("PDF gönderiliyor; dosya boyutu ve bütünlüğü sunucuda doğrulanıyor…");
        // The server checks the retained expected byte count and SHA-256 before
        // publishing the file. A mismatching file cannot replace this source.
        const response = await fetch(`/v1/uploads/${selectedUpload}/content`, {
          method: "PUT", signal: controller.current.signal,
          headers: { Authorization: "Bearer " + token, "Content-Type": "application/pdf" }, body: resumeFile,
        });
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          if (["SOURCE_HASH_MISMATCH", "INCOMPLETE_UPLOAD", "SOURCE_LIMIT_EXCEEDED"].includes(result.detail))
            throw new Error("Seçilen dosya bu yüklemenin özgün PDF dosyasıyla eşleşmiyor. Aynı dosyayı seçip tekrar deneyin.");
          throw new Error(`PDF yüklenemedi (${response.status}). Tekrar deneyebilirsiniz.`);
        }
      } else if (current.status !== "RECEIVED") {
        if (alive.current) setRefresh(value => value + 1);
        return;
      }
      // A failed /complete request leaves RECEIVED recoverable without another PUT.
      if (alive.current) { setState({ ...current, status: "RECEIVED" }); setResumeFile(null); }
      await request(`/uploads/${selectedUpload}/complete`, { confirm: true }, 'upload:' + selectedUpload + ':resume-complete');
      if (alive.current) setRefresh(value => value + 1);
    } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setBusy(false); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError("");
    try {
      if (!file.size || file.size > 52428800) throw new Error("PDF dosyası en fazla 50 MB olabilir.");
      if (!crypto.subtle) throw new Error("Güvenli dosya yüklemek için HTTPS bağlantısı gereklidir.");
      const a = attempt.current;
      a.key ??= crypto.randomUUID();
      setMessage("Dosya bütünlüğü kontrol ediliyor…");
      a.hash ??= Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map(b => b.toString(16).padStart(2, "0")).join("");
      a.work ??= await request("/works", { title }, a.key + ":work");
      a.edition ??= await request("/editions", { work_id: a.work.id, label }, a.key + ":edition");
      a.upload ??= await request(`/editions/${a.edition.id}/uploads`, { expected_bytes: file.size, expected_sha256: a.hash }, a.key + ":upload");
      if (!a.sent) {
        setMessage("PDF yükleniyor…");
        const response = await fetch(a.upload.upload_url, { method: "PUT", signal: controller.current.signal, headers: { Authorization: "Bearer " + token, "Content-Type": "application/pdf" }, body: file });
        if (!response.ok) throw new Error(`PDF yüklenemedi (${response.status}). Tekrar deneyebilirsiniz.`);
        a.sent = true;
      }
      await request(`/uploads/${a.upload.id}/complete`, { confirm: true }, a.key + ":complete");
      if (alive.current) setUpload(a.upload.id);
    } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setBusy(false); }
  }
  async function start() {
    setBusy(true); setError("");
    try {
      // Retain the server's exact job even if refreshing the workspace fails.
      // Reopening it must not start another analysis or select a newer edition.
      const result = startedJob ? { job_id: startedJob } : await request(`/content-versions/${state.content_version_id}/analyses`, { purpose: "validation" }, 'upload:' + upload + ':analysis');
      if (alive.current) setStartedJob(result.job_id);
      await onStarted(state.work_id, result.job_id);
      if (alive.current) setMessage("Analiz kaydı açıldı. Sayfa ilerlemesini aşağıdan takip edebilirsiniz. İşlemenin bitmesi kitabın doğrulandığı anlamına gelmez.");
    } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setBusy(false); }
  }
  async function cancel() {
    setBusy(true);setError('');
    try { await request(`/jobs/${upload}/cancel`, { purpose:'validation' }, 'upload:'+upload+':cancel'); if(alive.current) setMessage('İptal isteği alındı. İşlemin durması bekleniyor.'); }
    catch(e) { if(alive.current) setError((e as Error).message); }
    finally { if(alive.current) setBusy(false); }
  }
  return <details className="upload-book">
    <summary>Yeni kitap yükle</summary>
    {!!recent.length && !busy && <label>Önceki yüklemeyi takip et<select value={upload} onChange={e => { setUpload(e.target.value); setStartedJob(''); setState(null); setResumeFile(null); setMessage(''); setError(''); }}>
      <option value="">Yeni yükleme</option>{recent.map(r => <option key={r.id} value={r.id}>{r.title} · {({ CREATED: 'Dosya bekliyor', RECEIVED: 'Dosya alındı', PARSING: 'Hazırlanıyor', COMPLETED: 'Kaynak hazır', FAILED: 'Hata', CANCELLED:'İptal edildi' } as any)[r.status] ?? r.status}</option>)}
    </select></label>}
    {hasMore && !busy && <button disabled={loadingRecent} onClick={loadMore}>{loadingRecent ? 'Yüklemeler getiriliyor…' : 'Daha eski yüklemeleri getir'}</button>}
    {!upload && <form onSubmit={submit}>
      <label>Kitap adı<input required maxLength={300} value={title} disabled={busy || !!attempt.current.key} onChange={e => setTitle(e.target.value)} /></label>
      <label>Baskı / sürüm<input required maxLength={200} value={label} disabled={busy || !!attempt.current.key} onChange={e => setLabel(e.target.value)} /></label>
      <label>PDF dosyası<input type="file" accept="application/pdf,.pdf" required disabled={busy || !!attempt.current.key} onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
      <p className="hint">En fazla 50 MB ve 100 sayfa. Kaynak hazırlama ve kitap analizi ayrı aşamalardır.</p>
      {!upload && <button className="primary" disabled={busy || !file}>{busy ? "İşleniyor…" : "Yükle ve kaynağı hazırla"}</button>}
    </form>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {state?.status === "CREATED" && <form onSubmit={e => { e.preventDefault(); void resume(); }}>
      <label>Özgün PDF dosyası<input key={upload} type="file" accept="application/pdf,.pdf" required disabled={busy} onChange={e => setResumeFile(e.target.files?.[0] ?? null)} /></label>
      <p className="hint">Dosya boyutu ve içeriği önceki yükleme kaydıyla doğrulanır. Farklı bir kitap için yeni yükleme açın.</p>
      <button className="primary" disabled={busy || !resumeFile}>{busy ? "İşleniyor…" : "Yüklemeyi sürdür"}</button>
    </form>}
    {state?.status === "RECEIVED" && <button className="primary" disabled={busy} onClick={resume}>{busy ? "İşleniyor…" : "Kaynak hazırlamayı başlat"}</button>}
    {state?.status === "COMPLETED" && <button className="primary" disabled={busy} onClick={start}>{startedJob ? 'Analizi görüntüle' : 'Kitap analizini başlat'}</button>}
    {state?.status === "PARSING" && <button disabled={busy} onClick={cancel}>Kaynak hazırlamayı iptal et</button>}
    {!busy && (error || upload) && <button onClick={() => { attempt.current = {}; setUpload(''); setStartedJob(''); setState(null); setResumeFile(null); setError(''); setMessage(''); setFile(null); }}>Yeni yükleme aç</button>}
  </details>;
}
