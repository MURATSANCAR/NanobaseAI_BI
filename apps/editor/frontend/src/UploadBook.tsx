import React, { useEffect, useRef, useState } from "react";

type Props = { token: string; onStarted: (work: string) => Promise<void> };
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
    request('/uploads').then(r => { if (alive.current) setRecent(r.items); }).catch(e => { if (alive.current) setError(e.message); });
  }, []);
  useEffect(() => {
    if (!upload) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request("/uploads/" + upload);
        if (!active) return;
        setState(next); setError("");
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
  }, [upload, token]);

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
      const a = attempt.current;
      await request(`/content-versions/${state.content_version_id}/analyses`, { purpose: "validation" }, 'upload:' + upload + ':analysis');
      await onStarted(state.work_id);
      if (alive.current) { setMessage("Analiz başladı. Sayfa ilerlemesini aşağıdan takip edebilirsiniz."); setState(null); }
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
    {!!recent.length && !busy && <label>Önceki yüklemeyi takip et<select value={upload} onChange={e => { setUpload(e.target.value); setState(null); setMessage(''); setError(''); }}>
      <option value="">Yeni yükleme</option>{recent.map(r => <option key={r.id} value={r.id}>{r.title} · {({ CREATED: 'Dosya bekliyor', RECEIVED: 'Dosya alındı', PARSING: 'Hazırlanıyor', COMPLETED: 'Kaynak hazır', FAILED: 'Hata', CANCELLED:'İptal edildi' } as any)[r.status] ?? r.status}</option>)}
    </select></label>}
    {!upload && <form onSubmit={submit}>
      <label>Kitap adı<input required maxLength={300} value={title} disabled={busy || !!attempt.current.key} onChange={e => setTitle(e.target.value)} /></label>
      <label>Baskı / sürüm<input required maxLength={200} value={label} disabled={busy || !!attempt.current.key} onChange={e => setLabel(e.target.value)} /></label>
      <label>PDF dosyası<input type="file" accept="application/pdf,.pdf" required disabled={busy || !!attempt.current.key} onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
      <p className="hint">En fazla 50 MB ve 100 sayfa. Kaynak hazırlama ve kitap analizi ayrı aşamalardır.</p>
      {!upload && <button className="primary" disabled={busy || !file}>{busy ? "İşleniyor…" : "Yükle ve kaynağı hazırla"}</button>}
    </form>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {state?.status === "COMPLETED" && <button className="primary" disabled={busy} onClick={start}>Kitap analizini başlat</button>}
    {state?.status === "PARSING" && <button disabled={busy} onClick={cancel}>Kaynak hazırlamayı iptal et</button>}
    {!busy && (error || upload) && <button onClick={() => { attempt.current = {}; setUpload(''); setState(null); setError(''); setMessage(''); setFile(null); }}>Yeni yükleme aç</button>}
  </details>;
}
