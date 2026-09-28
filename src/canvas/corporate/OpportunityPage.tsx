import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PackageSearch, Plus } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import { ENGINE_ENABLED } from '../engine';
import { LostSheet } from './Pipeline';
import QuoteEditor, { BookAdder } from './QuoteEditor';
import { CorporateFrame, StagePill } from './parts';
import {
  OPEN_STAGES,
  QUOTE_TONE,
  STAGE_ORDER,
  corporateApi,
  dueText,
  fmtMoney,
  fmtShort,
  growth,
  fmtPct,
  monthName,
  parseNum,
  type Opportunity,
  type OppInput,
  type Stage,
} from './api';

function Fields({ o, canEdit, seeAll, vocabulary, onSave, busy }: {
  o: Opportunity; canEdit: boolean; seeAll: boolean; vocabulary: string[]; onSave: (b: OppInput) => void; busy: boolean;
}) {
  const init = () => ({
    ad: o.ad, tema: o.tema ?? '', deger: o.deger !== null ? String(Math.round(o.deger)) : '', karar: o.kararTarihi ?? '',
    adim: o.sonrakiAdim ?? '', adimTarih: o.sonrakiTarih ?? '', notlar: o.notlar ?? '', sahip: o.sahip,
  });
  const [f, setF] = useState(init);
  useEffect(() => setF(init()), [o]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(f) !== JSON.stringify(init());
  const input = (k: keyof typeof f, lbl: string, type = 'text', mode?: 'decimal', info?: ReactNode) => (
    <label className="flex flex-col gap-1">
      <span className={`${labelCls} inline-flex items-center gap-1`}>{lbl}{info}</span>
      <input className={`${field} ${mode ? 'font-mono tabular-nums' : ''}`} type={type} inputMode={mode} value={f[k]} readOnly={!canEdit}
        onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </label>
  );
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          ad: f.ad, tema: f.tema || null, deger: parseNum(f.deger), kararTarihi: f.karar || null, sonrakiAdim: f.adim || null,
          sonrakiTarih: f.adimTarih || null, notlar: f.notlar || null, ...(seeAll && f.sahip !== o.sahip ? { sahip: f.sahip } : {}),
        });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {input('ad', 'Fırsat')}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Tema</span>
          <select className={field} value={f.tema} disabled={!canEdit} onChange={(e) => setF({ ...f, tema: e.target.value })}>
            <option value="">Seçilmedi</option>
            {[...new Set([...(f.tema ? [f.tema] : []), ...vocabulary])].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        {input('deger', 'Tahmini değer (₺)', 'text', 'decimal', <SqlInfo k={o.kaynaklar} alan="deger" label="Fırsatın tahmini değeri" />)}
        {input('karar', 'Karar tarihi', 'date')}
        {input('adim', 'Sonraki adım')}
        {input('adimTarih', 'Sonraki adım tarihi', 'date')}
        {seeAll && input('sahip', 'Sahip (portal hesabı)')}
      </div>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Notlar</span>
        <textarea className={`${field} min-h-[80px]`} value={f.notlar} readOnly={!canEdit} onChange={(e) => setF({ ...f, notlar: e.target.value })} />
      </label>
      {canEdit && (
        <div className="flex justify-end">
          <button type="submit" className={btnPrimary} disabled={!dirty || busy}>Kaydet</button>
        </div>
      )}
    </form>
  );
}

export default function OpportunityPage() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [losing, setLosing] = useState(false);
  const [blank, setBlank] = useState(false);
  const meta = useQuery({ queryKey: ['corporate', 'meta'], queryFn: corporateApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const opp = useQuery({ queryKey: ['corporate', 'opp', id], queryFn: () => corporateApi.opportunity(id), enabled: ENGINE_ENABLED && !!id });
  const acc = useQuery({
    queryKey: ['corporate', 'account', opp.data?.accountRef],
    queryFn: () => corporateApi.account(opp.data!.accountRef!),
    enabled: ENGINE_ENABLED && !!opp.data?.accountRef,
  });
  const o = opp.data;
  const m = meta.data;
  const quotes = o?.teklifler ?? [];
  const selected = quotes.find((q) => q.id === params.get('teklif')) ?? quotes[0];
  const isOpen = !!o && OPEN_STAGES.includes(o.asama);
  const canEdit = !!m?.me.canQuote && !!o && (m.me.seeAll || o.sahip.toLowerCase() === m.me.username.toLowerCase());

  const invalidate = () => qc.invalidateQueries({ queryKey: ['corporate'] });
  const update = useMutation({
    mutationFn: (b: OppInput) => corporateApi.updateOpportunity(id, b),
    onSuccess: () => {
      setLosing(false);
      invalidate();
      toast.success('Fırsat güncellendi.');
    },
    onError: (e) => toast.error(errText(e, 'Fırsat güncellenemedi.') ?? ''),
  });
  const createQuote = useMutation({
    mutationFn: (stok: string) => corporateApi.createQuote(id, { kalemler: [{ stok, adet: 1 }] }),
    onSuccess: (q) => {
      setBlank(false);
      invalidate();
      setParams({ teklif: q.id }, { replace: true });
      toast.success('Teklif taslağı açıldı.');
    },
    onError: (e) => toast.error(errText(e, 'Teklif açılamadı.') ?? ''),
  });

  const err = errText(opp.error, 'Fırsat okunamadı.') ?? errText(meta.error, 'Ekran bilgisi okunamadı.');
  const a = acc.data;
  const g = a ? growth(a.buYil, a.gecenYilAyni) : null;

  return (
    <CorporateFrame
      title={o ? o.kurum : 'Fırsat'}
      lead={o ? `${o.ad}${o.tema ? ` · ${o.tema}` : ''} — ${o.sahip}` : 'Kurumsal satış fırsatı'}
      source={a?.dataEnd ? `Logo · ${a.dataEnd} tarihine kadar` : 'Portal kaydı'}
      presence={o ? o.asamaLabel : '—'}
      detail={o ? `${o.kurum} · ${o.ad}` : undefined}
      back={{ to: '/kurumsal-satis', label: 'Fırsatlar' }}
    >
      {err && <Note tone="err">{err}</Note>}
      {(opp.isLoading || meta.isLoading) && <Loading />}
      {o && m && (
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-4">
          <div className="flex min-w-0 flex-col gap-3">
            <Panel>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <StagePill stage={o.asama} label={o.asamaLabel} />
                  {o.kararTarihi && isOpen && (
                    <span className="inline-flex items-center text-[12px] font-bold text-canvas-muted">
                      Karar {dueText(o.kararTarihi)}
                      <SqlInfo k={o.kaynaklar} alan="kalanGun" label="Karara kalan gün" className="ml-0.5" />
                    </span>
                  )}
                  {o.kayipSinifLabel && (
                    <Pill tone="err">{o.kayipSinifLabel}{o.kayipSinifKaynak === 'oneri' ? ' (ZEKİ AI önerisi)' : ''}</Pill>
                  )}
                </div>
                {canEdit && (
                  <label className="flex items-center gap-2">
                    <span className={labelCls}>Aşama</span>
                    <select
                      className={`${field} !w-auto`}
                      value={o.asama}
                      onChange={(e) => {
                        const s = e.target.value as Stage;
                        if (s === 'kaybedildi') setLosing(true);
                        else update.mutate({ asama: s });
                      }}
                    >
                      {STAGE_ORDER.map((s) => <option key={s} value={s}>{m.stages[s]}</option>)}
                    </select>
                  </label>
                )}
              </div>
              {o.kaybetmeNedeni && <p className="mt-2 text-[12px] text-canvas-muted">Neden: {o.kaybetmeNedeni}</p>}
              <div className="mt-3">
                <Fields o={o} canEdit={canEdit} seeAll={m.me.seeAll} vocabulary={m.vocabulary} busy={update.isPending} onSave={(b) => update.mutate(b)} />
              </div>
            </Panel>

            <Panel>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-[16px] font-extrabold">Teklifler</h2>
                {canEdit && isOpen && (
                  <div className="flex flex-wrap gap-2">
                    <Link className={btnGhost} to={`/kurumsal-satis?sekme=paket&firsat=${o.id}${o.tema ? `&tema=${encodeURIComponent(o.tema)}` : ''}`}>
                      <PackageSearch aria-hidden className="h-4 w-4" /> Paket önerisiyle
                    </Link>
                    <button type="button" className={btnGhost} onClick={() => setBlank(true)}>
                      <Plus aria-hidden className="h-4 w-4" /> Boş teklif
                    </button>
                  </div>
                )}
              </div>
              {quotes.length > 1 && (
                <div className="mt-2 flex flex-wrap gap-1.5" role="tablist" aria-label="Teklif sürümleri">
                  {quotes.map((q) => (
                    <button
                      key={q.id}
                      type="button"
                      role="tab"
                      aria-selected={selected?.id === q.id}
                      onClick={() => setParams({ teklif: q.id }, { replace: true })}
                      className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${selected?.id === q.id ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}
                    >
                      v{q.surum}
                      <span className="opacity-80">{q.durumLabel}</span>
                    </button>
                  ))}
                </div>
              )}
              <div className="mt-3">
                {selected ? (
                  <QuoteEditor key={selected.id} quote={selected} meta={m} oppOpen={isOpen} k={o.kaynaklar} />
                ) : (
                  <p className="text-[12.5px] text-canvas-muted">Henüz teklif yok. Paket önerisiyle ya da boş bir teklifle başlayın.</p>
                )}
              </div>
              {quotes.length > 0 && (
                <ul className="mt-3 flex flex-wrap gap-2 text-[11.5px] text-canvas-muted">
                  {quotes.map((q) => (
                    <li key={q.id} className="inline-flex items-center gap-1">
                      v{q.surum} <Pill tone={QUOTE_TONE[q.durum]}>{q.durumLabel}</Pill> {fmtMoney(q.toplamNet)}
                      <SqlInfo k={o.kaynaklar} alan="teklifler[].toplamNet" label={`Teklif v${q.surum}: teklif tutarı`} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <aside className="flex flex-col gap-3">
            <Panel>
              <h2 className="text-[14px] font-extrabold">Kurum</h2>
              {!o.accountRef && <p className="mt-1 text-[12px] text-canvas-muted">Fırsat bir kurum kartına bağlı değil; alım geçmişi yok.</p>}
              {acc.isLoading && <Loading />}
              {a && (
                <div className="mt-1 flex flex-col gap-2 text-[12.5px]">
                  <div className="text-canvas-muted">
                    {[a.logoKod, a.il, a.segmentLabel, a.temsilci ? `temsilci ${a.temsilci}` : null].filter(Boolean).join(' · ')}
                  </div>
                  {a.window && (
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <div className={`${labelCls} inline-flex items-center gap-1`}>
                          {a.window.year} {a.window.label}
                          <SqlInfo k={a.kaynaklar} alan="buYil" label="Kurumun dönem cirosu" />
                        </div>
                        <div className="font-mono font-bold tabular-nums">{fmtShort(a.buYil)}</div>
                      </div>
                      <div>
                        <div className={`${labelCls} inline-flex items-center gap-1`}>
                          Geçen yıl aynı dönem
                          <SqlInfo k={a.kaynaklar} alan="buyume" label="Geçen yıl aynı dönem ve büyüme" />
                        </div>
                        <div className="font-mono font-bold tabular-nums">{fmtShort(a.gecenYilAyni)}{g !== null ? ` (${g >= 0 ? '+' : ''}${fmtPct(g)})` : ''}</div>
                      </div>
                    </div>
                  )}
                  {a.yillar.length > 0 && (
                    <div className={`${labelCls} inline-flex items-center gap-1`}>
                      Yıl başına ciro ve fatura
                      <SqlInfo k={a.kaynaklar} alan="yillar[]" label="Yıl başına net ciro ve satış faturası" />
                    </div>
                  )}
                  <ul className="flex flex-col gap-1">
                    {a.yillar.slice().reverse().map((y) => (
                      <li key={y.yil} className="flex items-center justify-between">
                        <span>{y.yil}</span>
                        <span className="font-mono tabular-nums">{fmtShort(y.ciro)} · {y.fatura} fatura</span>
                      </li>
                    ))}
                  </ul>
                  {a.enCokAy && (
                    <p className="text-[11.5px] text-canvas-muted">
                      En çok alım yaptığı ay: {monthName(a.enCokAy)}.
                      <SqlInfo k={a.kaynaklar} alan="enCokAy" label="En çok alım yapılan ay" className="ml-0.5" />
                    </p>
                  )}
                  {a.epostaIzni === false && <Note tone="warn">Kurumun e-posta izni yok (İYS); toplu e-postaya eklenmez.</Note>}
                </div>
              )}
            </Panel>
          </aside>
        </div>
      )}

      {m && <LostSheet open={losing} loss={m.loss} busy={update.isPending} onClose={() => setLosing(false)}
        onConfirm={(cls, text) => update.mutate({ asama: 'kaybedildi', kayipSinif: cls, kaybetmeNedeni: text })} />}
      <Sheet open={blank} modal onClose={() => setBlank(false)} title="Boş teklif" subtitle="İlk kitabı seçin; diğerlerini teklifte eklersiniz.">
        <BookAdder taken={new Set()} onAdd={(d) => createQuote.mutate(d.stok)} />
      </Sheet>
    </CorporateFrame>
  );
}
