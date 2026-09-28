import { Fragment, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ChevronLeft, ChevronRight, Loader2, Send, Sparkles, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { STATUS_TONE, donemLabel, fmtInt, pazarApi, type Brief, type Source } from './api';
import { ROOT, useMeta } from './parts';

/** Aylık yönetim özeti (DYK'ya). Zeki AI taslak yazar; her madde bir kaynağa ([K3]) bağlıdır ve maddedeki her sayı o
 *  kaynağın değeriyle tutmalıdır — tutmayan madde taslağa girmez, düzenlemede de onaya gönderilemez. Onay yönetimde
 *  (yazan ya da gönderen onaylayamaz). */
export default function BriefEditor({ donem }: { donem: string }) {
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const valid = /^20\d\d-(0[1-9]|1[0-2])$/.test(donem);
  const q = useQuery({ queryKey: ['pazar', 'brief', donem], queryFn: () => pazarApi.briefByPeriod(donem), enabled: ENGINE_ENABLED && valid });
  const b = q.data?.brief ?? null;
  const preview = useQuery({ queryKey: ['pazar', 'brief-sources'], queryFn: pazarApi.briefSources, enabled: ENGINE_ENABLED && valid && q.isSuccess && !b });
  const [text, setText] = useState('');
  useEffect(() => setText(b?.taslak ?? ''), [b?.id, b?.taslak]);
  const [note, setNote] = useState('');

  const done = (msg: string) => (r: Brief) => {
    toast.success(msg);
    qc.setQueryData(['pazar', 'brief', donem], { brief: r, donem });
    qc.invalidateQueries({ queryKey: ['pazar', 'overview'] });
    qc.invalidateQueries({ queryKey: ['pazar', 'briefs'] });
  };
  const fail = (fallback: string) => (e: unknown) => toast.error(errText(e, fallback) ?? '');
  const draft = useMutation({ mutationFn: () => pazarApi.draftBrief(donem), onSuccess: done('Taslak yazıldı.'), onError: fail('Taslak yazılamadı.') });
  const save = useMutation({ mutationFn: () => pazarApi.updateBrief(b!.id, text), onSuccess: done('Kaydedildi.'), onError: fail('Kaydedilemedi.') });
  const submit = useMutation({ mutationFn: () => pazarApi.submitBrief(b!.id), onSuccess: done('Onaya gönderildi.'), onError: fail('Onaya gönderilemedi.') });
  const approve = useMutation({ mutationFn: () => pazarApi.approveBrief(b!.id, note || undefined), onSuccess: done('Onaylandı; kurul paketine eklendi.'), onError: fail('Onaylanamadı.') });
  const reject = useMutation({ mutationFn: () => pazarApi.rejectBrief(b!.id, note), onSuccess: done('Gerekçeyle geri gönderildi.'), onError: fail('Geri gönderilemedi.') });
  const busy = draft.isPending || save.isPending || submit.isPending || approve.isPending || reject.isPending;

  const [y, m] = donem.split('-').map(Number);
  const shift = (k: number) => {
    const d = new Date(y, m - 1 + k, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  };
  const dirty = !!b && text !== b.taslak;
  const mine = !!b && !!me && [b.yazan, b.gonderen, b.guncelleyen].some((x) => x && x.toLowerCase() === me.username.toLowerCase());

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <Link to={`${ROOT}/ozet/${shift(-1)}`} className={btnGhost} aria-label="Önceki ay"><ChevronLeft aria-hidden className="h-4 w-4" /></Link>
            <h2 className="px-1 text-[17px] font-extrabold">Pazar özeti — {valid ? donemLabel(donem) : donem}</h2>
            <Link to={`${ROOT}/ozet/${shift(1)}`} className={btnGhost} aria-label="Sonraki ay"><ChevronRight aria-hidden className="h-4 w-4" /></Link>
          </div>
          {b && <Pill tone={STATUS_TONE[b.durum]}>{b.durumAd}</Pill>}
        </div>
        {!valid && <Note tone="err">Dönem YYYY-AA biçiminde olmalı.</Note>}
        {q.isLoading && <Loading />}
        {q.error && <Note tone="err">{errText(q.error, 'Özet açılamadı.')}</Note>}
        {b && (
          <p className="mt-1 text-[11.5px] text-canvas-muted">
            {b.yazan} yazdı ({fmtDate(b.yazildiAt)}){b.guncelleyen ? ` · ${b.guncelleyen} düzenledi (${fmtDate(b.guncellendiAt)})` : ''}
            {b.gonderen ? ` · ${b.gonderen} onaya gönderdi (${fmtDate(b.gonderildiAt)})` : ''}
            {b.onaylayan ? ` · ${b.onaylayan} onayladı (${fmtDate(b.onaylandiAt)}), kurul paketine gönderildi` : ''}
          </p>
        )}
        {b?.kararNotu && <Note tone="warn">Geri gönderme gerekçesi: {b.kararNotu}</Note>}
      </Panel>

      {q.isSuccess && !b && (
        <Panel>
          <h3 className="text-[15px] font-extrabold">Bu dönemin özeti yazılmadı</h3>
          <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
            Zeki AI aşağıdaki kaynaklardan fırsat, tehdit ve öncelikli aksiyon taslağı yazar. Kaynağa bağlanmayan ya da kaynakta olmayan sayı
            içeren madde taslağa girmez; ne çıkarıldığı ayrıca listelenir.
          </p>
          {preview.data && (
            <>
              {preview.data.dis === 0 && <Note tone="info">Onaylı sektör raporu rakamı yok: özette pazar büyüklüğü için «kaynak yok» yazılacak.</Note>}
              <SourceList sources={preview.data.kaynaklar} />
              {preview.data.disarida > 0 && <p className="mt-1 text-[11.5px] text-canvas-muted">Kaynak sınırı nedeniyle {fmtInt(preview.data.disarida)} kaynak taslağa verilmeyecek.</p>}
            </>
          )}
          {me?.canWrite && (
            <button type="button" className={`${btnPrimary} mt-3`} disabled={busy || !meta.data?.modelVar || !valid} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Zeki AI taslağı yaz
            </button>
          )}
        </Panel>
      )}

      {b && (
        <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
          <Panel>
            <h3 className="text-[15px] font-extrabold">Özet</h3>
            <div className="mt-2">
              <BriefView md={dirty ? text : b.taslak} sources={b.kaynaklar} />
            </div>
            {b.sorunlar.length > 0 && (
              <Note tone="err">
                {fmtInt(b.sorunlar.length)} madde onaya gönderilemez:
                <ul className="mt-1 list-disc pl-4">
                  {b.sorunlar.map((s) => <li key={`${s.satir}`}>Satır {s.satir}: {s.neden} — «{s.metin}»</li>)}
                </ul>
              </Note>
            )}
          </Panel>
          <div className="flex flex-col gap-3 lg:gap-4">
            {me?.canWrite && b.durum !== 'onaylandi' && (
              <Panel>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Düzenle</span>
                  <textarea value={text} onChange={(e) => setText(e.target.value)} rows={16} className={`${field} resize-y font-mono text-[12px] leading-relaxed`} />
                </label>
                <p className="mt-1 text-[11px] leading-snug text-canvas-muted">
                  Her madde en az bir kaynak kimliği taşımalı (örn. [K3]); maddedeki sayılar o kaynağın değeriyle tutmalı. Kaynak listesi değiştirilemez.
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className={btnGhost} disabled={busy || !dirty} onClick={() => save.mutate()}>Kaydet</button>
                  {b.durum === 'taslak' && (
                    <button type="button" className={btnPrimary} disabled={busy || dirty || b.sorunlar.length > 0} onClick={() => submit.mutate()}>
                      <Send aria-hidden className="h-4 w-4" /> Onaya gönder
                    </button>
                  )}
                  <button
                    type="button"
                    className={btnGhost}
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm('Taslak Zeki AI ile yeniden yazılsın mı? Düzenlemeler kaybolur.')) draft.mutate();
                    }}
                  >
                    {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />} Yeniden yaz
                  </button>
                </div>
              </Panel>
            )}
            {me?.canApprove && b.durum === 'onay_bekliyor' && (
              <Panel>
                <h3 className="text-[15px] font-extrabold">Onay</h3>
                {mine && meta.data?.settings.twoEyes ? (
                  <p className="mt-1 text-[12.5px] text-canvas-muted">Bu özeti siz yazdınız ya da onaya gönderdiniz; onayı başka bir yönetici verir.</p>
                ) : (
                  <>
                    <label className="mt-2 flex flex-col gap-1">
                      <span className={labelCls}>Not (geri gönderirken şart)</span>
                      <input value={note} onChange={(e) => setNote(e.target.value)} className={field} />
                    </label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button type="button" className={btnPrimary} disabled={busy} onClick={() => approve.mutate()}>
                        <Check aria-hidden className="h-4 w-4" /> Onayla ve kurula gönder
                      </button>
                      <button type="button" className={btnGhost} disabled={busy || !note.trim()} onClick={() => reject.mutate()}>
                        <Undo2 aria-hidden className="h-4 w-4" /> Geri gönder
                      </button>
                    </div>
                  </>
                )}
              </Panel>
            )}
            {b.reddedilen.length > 0 && (
              <Panel>
                <h3 className="text-[15px] font-extrabold">Taslağa girmeyen maddeler</h3>
                <ul className="mt-2 space-y-1.5 text-[12px] leading-snug">
                  {b.reddedilen.map((x, i) => (
                    <li key={i}>
                      <span className="font-semibold">{x.bolum}:</span> {x.metin} <span className="text-red-700">({x.neden})</span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            <Panel>
              <h3 className="text-[15px] font-extrabold">Kaynaklar</h3>
              <SourceList sources={b.kaynaklar} />
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

const TUR: Record<Source['tur'], string> = { ic: 'TİMAŞ (Logo)', dis: 'Sektör raporu', rakip: 'Rakip (CRM)', tazelik: 'Veri tazeliği' };

function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return <p className="mt-1 text-[12.5px] text-canvas-muted">Kaynak yok.</p>;
  return (
    <ul className="mt-2 divide-y divide-slate-100">
      {sources.map((s) => (
        <li key={s.id} id={`kaynak-${s.id}`} className="flex items-start justify-between gap-3 py-1.5">
          <div className="min-w-0">
            <div className="text-[12px] font-semibold leading-snug">
              <span className="mr-1 font-mono text-[11px] font-bold text-canvas-violet">{s.id}</span>
              {s.baslik}
            </div>
            <div className="text-[11px] text-canvas-muted">{TUR[s.tur]} · {s.donem} · {s.kaynak}</div>
          </div>
          <div className="shrink-0 font-mono text-[12.5px] font-bold tabular-nums">{s.degerMetin}</div>
        </li>
      ))}
    </ul>
  );
}

/** Özetin Markdown'u: başlıklar, maddeler, [Kn] kaynak işaretleri (üzerine gelince kaynağın değeri). */
export function BriefView({ md, sources, compact = false }: { md: string; sources: Source[]; compact?: boolean }) {
  const by = new Map(sources.map((s) => [s.id, s]));
  const inline = (t: string): ReactNode[] =>
    t.split(/(\[K\d+\])/g).map((part, i) => {
      const m = part.match(/^\[(K\d+)\]$/);
      if (!m) return <Fragment key={i}>{part}</Fragment>;
      const s = by.get(m[1]);
      return (
        <a
          key={i}
          href={`#kaynak-${m[1]}`}
          title={s ? `${s.baslik}: ${s.degerMetin} (${s.donem})` : 'Bilinmeyen kaynak'}
          className={`mx-0.5 inline-flex items-center rounded px-1 align-baseline font-mono text-[10.5px] font-bold ${s ? 'bg-canvas-violet/10 text-canvas-violet' : 'bg-red-50 text-red-700'}`}
        >
          {m[1]}
        </a>
      );
    });
  const lines = md.split('\n');
  const out: ReactNode[] = [];
  let list: ReactNode[] = [];
  let skip = false;
  const flush = (k: number) => {
    if (list.length) out.push(<ul key={`u${k}`} className="mb-2 list-disc space-y-1 pl-5">{list}</ul>);
    list = [];
  };
  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flush(i);
      skip = compact && h[2].trim() === 'Kaynaklar';
      if (skip) return;
      if (h[1].length === 1) {
        if (!compact) out.push(<h4 key={i} className="mb-2 text-[16px] font-extrabold">{h[2]}</h4>);
      } else out.push(<h5 key={i} className="mb-1 mt-2 text-[13px] font-extrabold uppercase tracking-wide text-canvas-muted">{h[2]}</h5>);
      return;
    }
    if (skip) return;
    const b = line.match(/^\s*[-*]\s+(.*)$/);
    if (b) {
      list.push(<li key={i} className="text-[12.5px] leading-snug">{inline(b[1])}</li>);
      return;
    }
    flush(i);
    if (!line.trim()) return;
    const it = line.match(/^_(.*)_$/);
    out.push(
      <p key={i} className={`mb-2 text-[12.5px] leading-snug ${it ? 'italic text-canvas-muted' : ''}`}>
        {inline(it ? it[1] : line)}
      </p>,
    );
  });
  flush(lines.length);
  return <div>{out}</div>;
}
