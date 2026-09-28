import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ExternalLink, FileSpreadsheet, Loader2, Sparkles } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import {
  LOG_LABEL, ecomApi, fmtDay, fmtInt, fmtMoney, fmtPct, fmtWhen, isEan,
  type Diff, type Item, type Meta, type Proposal,
} from './api';
import { DiffCard, MarkSheet, ThreeValues } from './parts';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Kitabın üç kaynaktaki değerleri, farkları, fark günlüğü ve Zeki AI kart önerileri. 2 tıkla açılır (liste → kitap). */
export default function ItemDrawer({ itemKey, meta, onClose }: { itemKey: string | null; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['eticaret', 'item', itemKey], queryFn: () => ecomApi.item(itemKey!), enabled: !!itemKey });
  const [marking, setMarking] = useState<Diff | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ['eticaret'] });
  const mark = useMutation({
    mutationFn: (b: { id: string; durum: Diff['durum']; note: string; sahip: string | null }) =>
      ecomApi.mark(b.id, { durum: b.durum as Exclude<Diff['durum'], 'kapandi'>, note: b.note, sahip: b.sahip }),
    onSuccess: () => { setMarking(null); refresh(); toast.success('İşaret kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const propose = useMutation({
    mutationFn: () => ecomApi.propose(itemKey!),
    onSuccess: () => { refresh(); toast.success('Zeki AI önerisi hazır; onaycıya düştü.'); },
    onError: (e) => toast.error(errText(e, 'Öneri üretilemedi.') ?? ''),
  });
  const k = q.data?.kitap;
  return (
    <Sheet open={!!itemKey} modal wide onClose={onClose} title={k?.ad || k?.adSite || itemKey || ''}
      subtitle={k ? `${k.productKey}${k.stokKodu ? ` · stok kodu ${k.stokKodu}` : ''} · okundu ${fmtWhen(k.okundu)}` : undefined}>
      {q.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {q.error && <Note tone="err">{errText(q.error, 'Kitap okunamadı.')}</Note>}
      {k && q.data && (
        <div className="flex flex-col gap-4 text-[13px]">
          <Sources k={k} kk={q.data.kaynaklar} />
          <section className="flex flex-col gap-2">
            <h3 className="text-[14px] font-extrabold">Farklar</h3>
            {!q.data.farklar.length && <p className="text-[12px] text-canvas-muted">Bu kitapta kayıtlı fark yok.</p>}
            {q.data.farklar.map((d) => (
              <DiffCard key={d.id} d={d} onMark={meta.me.canMark ? setMarking : undefined} k={q.data.kaynaklar} alan="farklar" />
            ))}
          </section>
          <Proposals k={k} kk={q.data.kaynaklar} items={q.data.oneriler} meta={meta} busy={propose.isPending} onPropose={() => propose.mutate()} onDone={refresh} />
          {meta.me.canExport && isEan(k.productKey) && (
            <div className="flex flex-wrap gap-2">
              <a className={btnGhost} href={ecomApi.contentPackUrl([k.productKey])}>
                <FileSpreadsheet aria-hidden className="h-4 w-4" />
                İçerik paketi (Excel)
              </a>
            </div>
          )}
          <section className="flex flex-col gap-1.5">
            <h3 className="text-[14px] font-extrabold">Fark günlüğü</h3>
            {!q.data.gunluk.length && <p className="text-[12px] text-canvas-muted">Kayıt yok.</p>}
            <ol className="flex flex-col gap-1">
              {q.data.gunluk.map((g, i) => (
                <li key={i} className="grid grid-cols-1 gap-0.5 rounded-lg bg-slate-50 px-2.5 py-1.5 sm:grid-cols-[130px_120px_1fr] sm:gap-2">
                  <span className="font-mono text-[11px] text-canvas-muted">{fmtWhen(g.zaman)}</span>
                  <span className="text-[11.5px] font-bold">{LOG_LABEL[g.eylem] ?? g.eylem} · {g.kullanici}</span>
                  <span className="break-words text-[12px]">{g.turAdi ? `${g.turAdi}: ` : ''}{g.not}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
      {marking && (
        <MarkSheet key={marking.id} open meta={meta} count={1} initial={{ durum: marking.durum === 'kapandi' ? undefined : marking.durum, sahip: marking.sahip }}
          busy={mark.isPending} onClose={() => setMarking(null)} onSave={(b) => mark.mutate({ id: marking.id, ...b })} />
      )}
    </Sheet>
  );
}

function Sources({ k, kk }: { k: Item; kk?: Kaynaklar }) {
  const yesNo = (v: boolean) => (v ? 'Evet' : 'Hayır');
  const row = (label: string, crm: ReactNode, logo: ReactNode, site: ReactNode) => (
    <div className="grid grid-cols-1 gap-1 border-b border-slate-100 py-1.5 sm:grid-cols-[150px_1fr]">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <ThreeValues crm={crm} logo={logo} site={site} />
    </div>
  );
  return (
    <section className="flex flex-col">
      <h3 className="mb-1 inline-flex items-center gap-1 text-[14px] font-extrabold">
        Üç kaynak <SqlInfo k={kk} alan="kitap" label="Üç kaynak: fiyat, stok, satış, doluluk" />
      </h3>
      {row('Satışta / aktif', k.crmVar ? `TSOFT Aktif: ${yesNo(k.crmTsoftAktif)}${k.crmEtkin ? '' : ' (kart pasif)'}` : 'Kart yok', null,
        k.sitede ? (k.siteAktif ? 'Satışta' : 'Pasif') : 'Ürün yok')}
      {row('Ad', k.ad, null, k.adSite)}
      {row('Fiyat', fmtMoney(k.fiyatCrm), fmtMoney(k.fiyatLogo),
        `${fmtMoney(k.fiyatSite)}${k.fiyatSiteIndirimli ? ` · indirimli ${fmtMoney(k.fiyatSiteIndirimli)}` : ''}`)}
      {row('Stok', k.stokKodu, k.stokLogo === null ? null : `${fmtInt(k.stokLogo)} (kesim ${fmtDay(k.logoKesim)})`, k.stokSite === null ? 'alan yok' : fmtInt(k.stokSite))}
      {row('Satış', null, k.logoAdet === null ? null : `Son dönem ${fmtInt(k.logoAdet)} adet`,
        `${fmtInt(k.goruntulenme)} görüntülenme · ${fmtInt(k.siteSatis)} satış · dönüşüm ${fmtPct(k.donusum)}`)}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {k.doluluk !== null && <Pill tone={k.doluluk >= 80 ? 'ok' : k.doluluk >= 50 ? 'warn' : 'err'}>Kart doluluğu %{k.doluluk}</Pill>}
        {k.eksik.map((e) => <Pill key={e.alan} tone="muted">{e.ad} boş</Pill>)}
        {k.yayinDurumu && <Pill tone={k.yayinBayragi ? 'err' : 'muted'}>Yayın durumu: {k.yayinDurumu}</Pill>}
        {k.hak && <Pill tone={k.hak === 'var' ? 'ok' : 'warn'}>Hak kararı: {k.hak}</Pill>}
        {k.url && /^https?:/.test(k.url) && (
          <a className="inline-flex items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline" target="_blank" rel="noreferrer"
            href={k.url}>
            Sitede aç <ExternalLink aria-hidden className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </section>
  );
}

const FIELD_NAME: Record<string, string> = { SeoTitle: 'Başlık', SeoDescription: 'Meta açıklama', SearchKeywords: 'Anahtar kelimeler', Details: 'Açıklama' };

function Proposals({ k, kk, items, meta, busy, onPropose, onDone }: {
  k: Item; kk?: Kaynaklar; items: Proposal[]; meta: Meta; busy: boolean; onPropose: () => void; onDone: () => void;
}) {
  const [rejecting, setRejecting] = useState<Proposal | null>(null);
  const decide = useMutation({
    mutationFn: (b: { id: string; action: 'approve' | 'reject'; note?: string }) => ecomApi.decide(b.id, { action: b.action, note: b.note }),
    onSuccess: (p) => { setRejecting(null); onDone(); toast.success(p.status === 'onaylandi' ? 'Onaylandı; kayıt altında (siteye gönderilmez).' : 'Reddedildi.'); },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[14px] font-extrabold">Zeki AI kart önerisi</h3>
        {meta.me.canPropose && k.tsoftUrunId && (
          <button type="button" className={btnPrimary} disabled={busy} onClick={onPropose}>
            {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            Öneri iste
          </button>
        )}
      </div>
      <p className="text-[11.5px] leading-snug text-canvas-muted">
        Taslak yalnız kitabın kendi kaydından (site ve CRM kartı) yazılır; öneriyi isteyen onaylayamaz. Onaylanan metin kayıt altında durur,
        siteye ya da platforma gönderilmez.
      </p>
      {!items.length && <p className="text-[12px] text-canvas-muted">Bu kitap için öneri yok.</p>}
      {items.map((p) => (
        <div key={p.id} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
            <Pill tone={p.status === 'hazir' ? 'violet' : p.status === 'onaylandi' ? 'ok' : 'muted'}>
              {p.status === 'hazir' ? 'Onay bekliyor' : p.status === 'onaylandi' ? 'Onaylandı' : 'Reddedildi'}
            </Pill>
            <span>{p.createdBy} · {fmtWhen(p.createdAt)}</span>
            {p.scoreBefore !== null && p.scoreAfter !== null && (
              <span className="inline-flex items-center gap-1">SEO puanı {p.scoreBefore} → {p.scoreAfter}
                <SqlInfo k={kk} alan="oneriler" label="SEO puanı (önce → sonra)" />
              </span>
            )}
            {p.decidedBy && <span>Karar: {p.decidedBy}</span>}
          </div>
          <dl className="mt-2 flex flex-col gap-1.5">
            {Object.entries(p.fields).map(([f, v]) => (
              <div key={f} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[130px_1fr] sm:gap-2">
                <dt className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{FIELD_NAME[f] ?? f}</dt>
                <dd className="break-words text-[12.5px]">
                  <span className="block">{v}</span>
                  {p.before[f] && p.before[f] !== v && <span className="block text-[11.5px] text-canvas-muted line-through">{p.before[f].slice(0, 400)}</span>}
                </dd>
              </div>
            ))}
          </dl>
          {p.note && <p className="mt-1 text-[12px] text-canvas-muted">Not: {p.note}</p>}
          {p.status === 'hazir' && meta.me.canApprove && (
            <div className="mt-2 flex flex-wrap justify-end gap-2">
              <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => setRejecting(p)}>Reddet</button>
              <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, action: 'approve' })}>Onayla</button>
            </div>
          )}
        </div>
      ))}
      <AskSheet open={!!rejecting} title="Öneriyi reddet" message="Gerekçe öneriyi isteyen kişiye kayıtta görünür." confirm="Reddet" danger
        input="Gerekçe" required busy={decide.isPending} onClose={() => setRejecting(null)}
        onConfirm={(note) => rejecting && decide.mutate({ id: rejecting.id, action: 'reject', note })} />
      {items.some((p) => p.status === 'onaylandi') && (
        <Note tone="info">Onaylanan metni T-soft panelinde ya da CRM kartında siz işlersiniz; portal yazmaz.</Note>
      )}
    </section>
  );
}
