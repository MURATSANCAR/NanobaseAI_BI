import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ExternalLink } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { SEND_TONE, TONE_TONE, fmtDay, prApi } from './api';
import { Block, Empty, PrFrame } from './parts';
import { ContactForm } from './PrContacts';

/** Medya kişisi kartı: iletişim, konular, CRM haber arşivinde yaptığı haberler, gönderimler ve portal yansımaları.
 *  «Haberdar olmak istemiyor» işareti buradan konur (bir daha önerilmez, e-posta gitmez). */
export default function PrContact() {
  const { key = '' } = useParams();
  const qc = useQueryClient();
  const nav = useNavigate();
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['pr', 'contact', key], queryFn: () => prApi.contact(key), enabled: ENGINE_ENABLED && !!key });
  const [editing, setEditing] = useState(false);
  const [ask, setAsk] = useState<null | 'dnc' | 'delete'>(null);
  const upd = useMutation({
    mutationFn: (b: Record<string, unknown>) => prApi.updateContact(key, b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['pr', 'contact', key] }); qc.invalidateQueries({ queryKey: ['pr', 'contacts'] }); setAsk(null); toast.success('Kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => prApi.deleteContact(key),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['pr', 'contacts'] }); toast.success('Silindi.'); nav('/basin-iliskileri/kisiler'); },
    onError: (e) => { setAsk(null); toast.error(errText(e, 'Silinemedi.') ?? ''); },
  });
  const m = meta.data;
  const d = q.data;
  const c = d?.contact;

  return (
    <PrFrame
      crumb="Medya kişisi"
      title={c?.name ?? 'Medya kişisi'}
      lead={c ? [c.outlet, c.outletType && m?.outletTypes[c.outletType], c.role, c.region && m?.regions[c.region]].filter(Boolean).join(' · ') : undefined}
      source={c?.source === 'crm' ? 'CRM kişisi (yalnız okunur) + portal notu' : 'Portalda eklendi'}
      presence={d ? `${d.sends.length} gönderim` : '…'}
      back={{ to: '/basin-iliskileri/kisiler', label: 'Medya kişileri' }}
      aside={c && m?.me.canEdit ? (
        <div className="flex flex-wrap gap-1.5">
          <button type="button" className={btnPrimary} onClick={() => setEditing(true)}>Düzenle</button>
          {c.doNotContact
            ? (c.crm && c.dncReason?.startsWith('CRM') ? null : <button type="button" className={btnGhost} disabled={upd.isPending} onClick={() => upd.mutate({ doNotContact: false })}>İletişim iznini geri aç</button>)
            : <button type="button" className={btnGhost} onClick={() => setAsk('dnc')}>Haberdar olmak istemiyor</button>}
          {c.source === 'portal' && <button type="button" className={btnGhost} onClick={() => setAsk('delete')}>Sil</button>}
        </div>
      ) : undefined}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kişi açılamadı.')}</Note>}
      {d?.note && <Note tone="warn">{d.note}</Note>}
      {c && (
        <>
          {c.doNotContact && <Note tone="err">Haberdar olmak istemiyor{c.dncReason ? `: ${c.dncReason}` : ''}. Öneriye girmez, e-posta gönderilmez.</Note>}
          <Block title="İletişim">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-[12.5px] sm:grid-cols-2 lg:grid-cols-3">
              <Item k="E-posta" v={c.email} />
              <Item k="Telefon" v={c.phone} />
              <Item k="Konular" v={c.topics.join(', ') || null} />
              {c.crm && <Item k="CRM'de mecra" v={c.crm.mecra} />}
              {c.crm && <Item k="CRM'de kurum" v={c.crm.kurum} />}
              {c.crm && <Item k="İleti izni (İYS)" v={c.crm.iys === null ? null : c.crm.iys ? 'Var' : 'Yok'} />}
              <Item k="Son temas" v={d.history?.last ? fmtDay(d.history.last) : null} />
            </dl>
            {c.note && <p className="mt-2 whitespace-pre-line rounded-xl bg-white/70 p-3 text-[12.5px]">{c.note}</p>}
          </Block>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            <Block title={`Gönderimler (${d.sends.length})`}>
              {d.sends.length === 0 && <Empty>Portaldan bu kişiye gönderim yok.</Empty>}
              <ul className="flex flex-col divide-y divide-slate-100">
                {d.sends.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <Link to={`/basin-iliskileri/dosya/${encodeURIComponent(s.kitId)}`} className="min-w-0 break-words text-[12.5px] font-bold hover:underline">{s.bookTitle}</Link>
                    <span className="flex items-center gap-1.5 text-[11.5px] text-canvas-muted">
                      {fmtDay(s.sentAt)} <Pill tone={SEND_TONE[s.status]}>{s.statusLabel}</Pill>
                    </span>
                  </li>
                ))}
              </ul>
            </Block>
            <Block title={`Yansımalar (${d.coverage.length})`} help="Portalda bu kişiye bağlanmış haberler.">
              {d.coverage.length === 0 && <Empty>Kayıtlı yansıma yok.</Empty>}
              <ul className="flex flex-col divide-y divide-slate-100">
                {d.coverage.map((x) => (
                  <li key={x.id} className="flex flex-wrap items-start justify-between gap-2 py-2">
                    <span className="min-w-0 break-words text-[12.5px] font-bold">{x.title} <span className="font-normal text-canvas-muted">· {fmtDay(x.publishedAt)}</span></span>
                    {x.tone && <Pill tone={TONE_TONE[x.tone]}>{x.toneLabel}</Pill>}
                  </li>
                ))}
              </ul>
            </Block>
          </div>

          <Block title={`CRM haber arşivi (${d.archive.length})`} help="Bu kişinin haberi yaptığı ya da basında görüşüldüğü Timaş haberleri (CRM, 2025-06'ya kadar).">
            {d.archive.length === 0 && <Empty>CRM haber arşivinde bu kişiye bağlı kayıt yok.</Empty>}
            <ul className="flex flex-col divide-y divide-slate-100">
              {d.archive.map((a) => (
                <li key={a.id} className="py-2">
                  <div className="break-words text-[12.5px] font-bold">
                    {a.link ? (
                      <a href={a.link} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 hover:underline">
                        {a.baslik ?? '—'} <ExternalLink aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                      </a>
                    ) : (a.baslik ?? '—')}
                  </div>
                  <div className="text-[11.5px] text-canvas-muted">{[fmtDay(a.tarih), a.mecra, a.books.map((b) => b.ad).filter(Boolean).join(', ')].filter((x) => x && x !== '—').join(' · ')}</div>
                </li>
              ))}
            </ul>
          </Block>
        </>
      )}
      {m && c && editing && (
        <ContactForm meta={m} contactKey={c.key} onClose={() => setEditing(false)}
          initial={{ name: c.name, outlet: c.outlet, outletType: c.outletType, role: c.role, email: c.email, phone: c.phone, region: c.region, note: c.note, topics: c.topics }} />
      )}
      <AskSheet open={ask === 'dnc'} title="Haberdar olmak istemiyor" message="Kişi öneriye girmez ve ona portaldan e-posta gönderilmez. Geçmiş kayıtları durur."
        confirm="İşaretle" input="Nedeni (isteğe bağlı)" busy={upd.isPending} onClose={() => setAsk(null)}
        onConfirm={(reason) => upd.mutate({ doNotContact: true, dncReason: reason })} />
      <AskSheet open={ask === 'delete'} title="Kişiyi sil" message="Portalda eklenen bu kişi silinir. Gönderim ya da yansıma kaydı varsa silinmez; «haberdar olmak istemiyor» işaretleyin."
        confirm="Sil" danger busy={del.isPending} onClose={() => setAsk(null)} onConfirm={() => del.mutate()} />
    </PrFrame>
  );
}

function Item({ k, v }: { k: string; v: string | null | undefined }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{k}</dt>
      <dd className="break-words font-semibold">{v || '—'}</dd>
    </div>
  );
}
