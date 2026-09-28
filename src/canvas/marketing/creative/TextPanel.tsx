import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, Pencil, ShieldQuestion, Sparkles } from 'lucide-react';
import { Note, btnGhost, btnPrimary, errText, field, label } from '../../admin/ui';
import { copyText } from '../../editorial/studio/marketing/parts';
import { creativeApi, type Asset, type Channel, type Check, type Meta, type RequestDetail, type TextKind } from './api';
import { ApprovalLine, Block, Checks, JobBar, chip, smallBtn } from './parts';
import { AssetActions } from './VisualPanel';
import { invalidateCreative } from './useMeta';

/** Sağ sütun: metin varyantları (Zeki AI taslağı). Kod denetler: platform sınırı ve alıntı (hata — onay verilmez),
 *  yasaklı kalıp, kaynakta olmayan sayı, kanıtsız iddia (uyarı — onaycı karar verir). Düzeltme yeni sürüm açar. */

function TextCard({ a, meta, onVersions }: { a: Asset; meta: Meta | undefined; onVersions: (a: Asset) => void }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(a.metin ?? '');
  useEffect(() => { if (!edit) setText(a.metin ?? ''); }, [a.metin, edit]);
  const lim = meta?.sinirlar[a.format ?? '']?.[a.metinTuru ?? ''];
  const save = useMutation({
    mutationFn: () => creativeApi.reviseText(a.id, text),
    onSuccess: () => { toast.success('Yeni sürüm kaydedildi; onaylar sıfırlandı.'); setEdit(false); return invalidateCreative(qc); },
  });
  const over = lim?.sinir != null && text.length > lim.sinir;
  return (
    <li className="flex min-w-0 flex-col gap-1.5 rounded-xl border border-slate-100 bg-white p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <span className="text-[11.5px] font-extrabold">{a.varyant} · {a.formatAdi}</span>
        <ApprovalLine a={a} />
      </div>
      {edit ? (
        <>
          <textarea className={field} rows={Math.min(14, Math.max(3, Math.ceil(text.length / 60)))} value={text} onChange={(e) => setText(e.target.value)} maxLength={20000} />
          <span className={`font-mono text-[11px] font-bold tabular-nums ${over ? 'text-red-700' : 'text-canvas-muted'}`}>
            {text.length}{lim?.sinir != null ? ` / ${lim.sinir}` : ''} karakter
          </span>
          {save.error && <Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note>}
          <div className="flex flex-wrap justify-end gap-1.5">
            <button type="button" className={smallBtn()} onClick={() => setEdit(false)}>Vazgeç</button>
            <button type="button" className={smallBtn('ok')} disabled={save.isPending || !text.trim() || text === a.metin} onClick={() => save.mutate()}>Yeni sürüm olarak kaydet</button>
          </div>
        </>
      ) : (
        <p className="whitespace-pre-line break-words text-[13px] leading-snug">{a.metin}</p>
      )}
      <Checks c={a.dogrulama} />
      {a.red?.not && <p className="text-[11.5px] text-red-700">Ret notu: {a.red.not}</p>}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" className={smallBtn()} onClick={async () => {
          if (await copyText(a.metin ?? '')) toast.success('Kopyalandı.');
          else toast.error('Kopyalanamadı.');
        }}>
          <Copy className="h-4 w-4" aria-hidden />Kopyala
        </button>
        {meta?.me.uret && !edit && !a.mesajOnay && (
          <button type="button" className={smallBtn()} onClick={() => setEdit(true)}><Pencil className="h-4 w-4" aria-hidden />Düzelt</button>
        )}
      </div>
      <AssetActions a={a} meta={meta} onVersions={onVersions} />
    </li>
  );
}

function FreeCheck({ stok, platform }: { stok: string; platform: string }) {
  const [text, setText] = useState('');
  const [res, setRes] = useState<Check | null>(null);
  const run = useMutation({ mutationFn: () => creativeApi.check({ metin: text, platform, tur: 'aciklama', stokKodu: stok }), onSuccess: setRes });
  return (
    <details className="rounded-xl bg-slate-50 p-2.5">
      <summary className="flex cursor-pointer items-center gap-1.5 text-[12px] font-bold"><ShieldQuestion className="h-4 w-4" aria-hidden />Bir metni denetle (kanıtsız iddia, yasaklı kalıp, sayı, alıntı)</summary>
      <div className="mt-2 flex flex-col gap-2">
        <textarea className={field} rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Metni yapıştırın" />
        <button type="button" className={btnGhost} disabled={!text.trim() || run.isPending} onClick={() => run.mutate()}>{run.isPending ? 'Denetleniyor…' : 'Denetle'}</button>
        {run.error && <Note tone="err">{errText(run.error, 'Denetlenemedi.')}</Note>}
        {res && (res.sorunlar.length ? <Checks c={res} /> : <Note tone="ok">Sorun bulunmadı ({res.karakter} karakter).</Note>)}
      </div>
    </details>
  );
}

export default function TextPanel({ r, meta, onVersions }: { r: RequestDetail; meta: Meta | undefined; onVersions: (a: Asset) => void }) {
  const qc = useQueryClient();
  const me = meta?.me;
  const texts = r.varliklar.filter((a) => a.tur === 'metin');
  const job = r.isler.find((j) => j.tur === 'metin');
  const running = job?.durum === 'suruyor';
  const reqKinds = r.metinTurleri.join(',');
  const [kinds, setKinds] = useState<TextKind[]>(r.metinTurleri);
  useEffect(() => setKinds((reqKinds ? reqKinds.split(',') : []) as TextKind[]), [reqKinds]);
  const [platform, setPlatform] = useState<Channel>(r.kanal);
  const [count, setCount] = useState('');
  const [seconds, setSeconds] = useState('45');
  const byKind = useMemo(() => {
    const m = new Map<string, Asset[]>();
    for (const a of texts) m.set(a.metinTuru ?? '', [...(m.get(a.metinTuru ?? '') ?? []), a]);
    return [...m.entries()];
  }, [texts]);
  const write = useMutation({
    mutationFn: () => creativeApi.copy(r.id, { turler: kinds, platform, adet: count ? Number(count) : undefined, sure: kinds.includes('video-senaryosu') ? Number(seconds) || 45 : undefined }),
    onSuccess: () => { toast.success('Zeki AI yazmaya başladı.'); return invalidateCreative(qc); },
  });
  const kindLabel = (k: string) => meta?.metinTurleri.find((x) => x.key === k)?.label ?? k;

  return (
    <Block title={`Metinler (${texts.length})`} aside={
      me?.uret ? (
        <button type="button" className={btnPrimary} disabled={running || write.isPending || kinds.length === 0} onClick={() => write.mutate()}>
          <Sparkles className="h-4 w-4" aria-hidden />Zeki AI ile yaz
        </button>
      ) : null}>
      {me?.uret && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-1.5">
            {meta?.metinTurleri.map((x) => (
              <button key={x.key} type="button" aria-pressed={kinds.includes(x.key)} className={chip(kinds.includes(x.key))}
                onClick={() => setKinds((o) => (o.includes(x.key) ? o.filter((y) => y !== x.key) : [...o, x.key]))}>{x.label}</button>
            ))}
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="flex flex-col gap-1"><span className={label}>Platform</span>
              <select className={field} value={platform} onChange={(e) => setPlatform(e.target.value as Channel)}>
                {meta?.kanallar.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select></label>
            <label className="flex flex-col gap-1"><span className={label}>Varyant sayısı</span>
              <input className={field} inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value.replace(/\D/g, ''))} placeholder="türe göre" /></label>
            {kinds.includes('video-senaryosu') && (
              <label className="flex flex-col gap-1"><span className={label}>Video süresi (sn)</span>
                <input className={field} inputMode="numeric" value={seconds} onChange={(e) => setSeconds(e.target.value.replace(/\D/g, ''))} /></label>
            )}
          </div>
        </div>
      )}
      {write.error && <Note tone="err">{errText(write.error, 'Başlatılamadı.')}</Note>}
      <JobBar job={job} what="Metin üretimi" k={r.kaynaklar} />
      {byKind.length === 0 && !running && (
        <p className="text-[12.5px] text-canvas-muted">Henüz metin yok. Tür ve platform seçip «Zeki AI ile yaz»a basın; sınırı aşan ya da alıntısı kaynakta olmayan varyant kaydedilmez.</p>
      )}
      {byKind.map(([k, items]) => (
        <section key={k} className="flex min-w-0 flex-col gap-2">
          <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{kindLabel(k)} ({items.length})</h3>
          <ul className="flex min-w-0 flex-col gap-2">
            {items.map((a) => <TextCard key={a.id} a={a} meta={meta} onVersions={onVersions} />)}
          </ul>
        </section>
      ))}
      <FreeCheck stok={r.stokKodu} platform={platform} />
    </Block>
  );
}
