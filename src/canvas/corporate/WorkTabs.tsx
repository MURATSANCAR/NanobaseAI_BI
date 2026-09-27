import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Plus, X } from 'lucide-react';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { Empty } from './parts';
import { corporateApi, fmtDay, fmtInt, fmtMoney, fmtMonth, fmtShort, type Meta } from './api';

/** Dönemsel hatırlatmalar: geçen yıl aynı ayda KURUM kanalında alımı olan kurumlar. */
export function RemindersTab({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [durum, setDurum] = useState<'acik' | 'firsat' | 'kapandi' | ''>('acik');
  const list = useQuery({ queryKey: ['corporate', 'reminders', durum], queryFn: () => corporateApi.reminders({ durum }), enabled: ENGINE_ENABLED });
  const toOpp = useMutation({
    mutationFn: corporateApi.reminderToOpportunity,
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ['corporate'] });
      toast.success('Fırsat açıldı.');
      nav(`/kurumsal-satis/firsat/${o.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Fırsat açılamadı.') ?? ''),
  });
  const close = useMutation({
    mutationFn: ({ id, d }: { id: string; d: 'acik' | 'kapandi' }) => corporateApi.updateReminder(id, d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['corporate'] }),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const d = list.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Durum">
          {([['acik', 'Açık'], ['firsat', 'Fırsat açıldı'], ['kapandi', 'Kapandı'], ['', 'Hepsi']] as const).map(([k, l]) => (
            <button key={k} type="button" role="radio" aria-checked={durum === k} onClick={() => setDurum(k)}
              className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold sm:min-h-9 ${durum === k ? 'bg-white shadow-sm' : ''}`}>{l}</button>
          ))}
        </div>
        {d && <span className="text-[12px] text-canvas-muted">{d.aylar.map(fmtMonth).join(', ')} · geçen yıl toplam {fmtShort(d.toplamGecenYil)}</span>}
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
        Bu ay ve başlangıcı {meta.settings.reminderLeadDays} gün içinde olan aylar için, geçen yıl aynı ayda net alımı olan kurumlar. Liste her gece Logo'dan yenilenir;
        e-posta ya da arama otomatik yapılmaz, temsilci arar.
      </p>
      {list.error && <Note tone="err">{errText(list.error, 'Hatırlatmalar okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {d && d.items.length === 0 && <div className="mt-3"><Empty title="Bu dönem için hatırlatma yok" /></div>}
      <ul className="mt-3 grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
        {(d?.items ?? []).map((r) => (
          <li key={r.id} className="flex flex-col gap-2 rounded-xl border border-slate-100 bg-white/90 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="break-words text-[13px] font-extrabold">{r.unvan ?? r.logoKod}</div>
                <div className="text-[11.5px] text-canvas-muted">{[fmtMonth(r.donemAyi), r.logoKod, r.temsilci].filter(Boolean).join(' · ')}</div>
              </div>
              <Pill tone={r.durum === 'acik' ? 'warn' : r.durum === 'firsat' ? 'violet' : 'muted'}>{r.durumLabel}</Pill>
            </div>
            <div className="text-[12px]">
              Geçen yıl bu ay: <b className="font-mono tabular-nums">{fmtMoney(r.gecenYilTutar)}</b>{r.gecenYilAdet ? ` · ${fmtInt(r.gecenYilAdet)} adet` : ''}
            </div>
            {meta.me.canQuote && (
              <div className="flex flex-wrap gap-2">
                {r.durum === 'acik' && (
                  <>
                    <button type="button" className={btnPrimary} disabled={toOpp.isPending} onClick={() => toOpp.mutate(r.id)}>
                      <Plus aria-hidden className="h-4 w-4" /> Fırsat aç
                    </button>
                    <button type="button" className={btnGhost} disabled={close.isPending} onClick={() => close.mutate({ id: r.id, d: 'kapandi' })}>Kapat</button>
                  </>
                )}
                {r.durum === 'kapandi' && (
                  <button type="button" className={btnGhost} disabled={close.isPending} onClick={() => close.mutate({ id: r.id, d: 'acik' })}>Yeniden aç</button>
                )}
                {r.durum === 'firsat' && r.firsatId && <Link className={btnGhost} to={`/kurumsal-satis/firsat/${r.firsatId}`}>Fırsata git</Link>}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** Satış müdürünün onay kuyruğu. */
export function ApprovalsTab() {
  const list = useQuery({ queryKey: ['corporate', 'approvals'], queryFn: corporateApi.approvals, enabled: ENGINE_ENABLED });
  return (
    <Panel>
      {list.error && <Note tone="err">{errText(list.error, 'Onay kuyruğu okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && list.data.items.length === 0 && <Empty title="Onay bekleyen teklif yok" />}
      <ul className="flex flex-col gap-2">
        {(list.data?.items ?? []).map((q) => (
          <li key={q.id}>
            <Link to={`/kurumsal-satis/firsat/${q.firsatId}?teklif=${q.id}`}
              className="flex flex-col gap-1 rounded-xl border border-slate-100 bg-white/90 p-3 transition-transform duration-150 ease-out active:scale-[0.99] sm:flex-row sm:items-center sm:justify-between">
              <span className="min-w-0">
                <span className="block break-words text-[13px] font-extrabold">{q.kurum} · {q.firsatAd}</span>
                <span className="block text-[11.5px] text-canvas-muted">v{q.surum} · gönderen {q.gonderen} · {fmtDay(q.gonderimAt)} · {q.onayNedenleri.map((r) => r.metin).join(' · ')}</span>
              </span>
              <span className="shrink-0 font-mono text-[13px] font-bold tabular-nums">{fmtMoney(q.toplamNet)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** ZEKİ AI'ın kitaplara önerdiği temalar: onaylanan tema paket önerisine girer. */
export function ThemesTab({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const [durum, setDurum] = useState<'onerildi' | 'onayli' | 'reddedildi'>('onerildi');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [addFor, setAddFor] = useState<{ stok: string; tema: string } | null>(null);
  const list = useQuery({
    queryKey: ['corporate', 'themes', durum, q, page],
    queryFn: () => corporateApi.themes({ durum, q, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const decide = useMutation({
    mutationFn: ({ stok, tema, karar }: { stok: string; tema: string; karar: 'onayla' | 'reddet' | 'ekle' | 'kaldir' }) => corporateApi.decideTheme(stok, tema, karar),
    onSuccess: () => {
      setAddFor(null);
      qc.invalidateQueries({ queryKey: ['corporate', 'themes'] });
      qc.invalidateQueries({ queryKey: ['corporate', 'summary'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const d = list.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Durum">
          {(['onerildi', 'onayli', 'reddedildi'] as const).map((k) => (
            <button key={k} type="button" role="radio" aria-checked={durum === k} onClick={() => { setDurum(k); setPage(0); }}
              className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold sm:min-h-9 ${durum === k ? 'bg-white shadow-sm' : ''}`}>
              {meta.themeStatus[k]} {d?.counts[k] ? <span className="font-mono tabular-nums opacity-70">{fmtInt(d.counts[k])}</span> : null}
            </button>
          ))}
        </div>
        <label className="min-w-[200px] flex-1">
          <span className="sr-only">Ara</span>
          <input className={field} value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Kitap, stok kodu ya da yazar" />
        </label>
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
        CRM'deki tema bağları doğrudan onaylıdır. ZEKİ AI stoktaki etiketsiz kitaplara her gece kapalı listeden ({meta.vocabulary.length} tema) öneri yapar; öneri onaylanana kadar paket önerisine girmez.
      </p>
      {list.error && <Note tone="err">{errText(list.error, 'Temalar okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {d && d.items.length === 0 && <div className="mt-3"><Empty title="Bu durumda tema yok" /></div>}
      <ul className="mt-3 flex flex-col gap-2">
        {(d?.items ?? []).map((b) => (
          <li key={b.stokKodu} className="rounded-xl border border-slate-100 bg-white/90 p-3">
            <div className="text-[13px] font-extrabold">{b.ad ?? b.stokKodu}</div>
            <div className="text-[11.5px] text-canvas-muted">{[b.stokKodu, b.yazar, b.turler ?? b.kitaplik, b.yaslar, b.stok !== undefined ? `stok ${fmtInt(b.stok)}` : null].filter(Boolean).join(' · ')}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {b.temalar.map((t) => (
                <span key={t.tema} className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] font-bold ${t.durum === 'onayli' ? 'bg-emerald-50 text-emerald-800' : t.durum === 'reddedildi' ? 'bg-slate-100 text-canvas-muted line-through' : 'bg-amber-50 text-amber-900'}`}>
                  {t.tema}
                  <span className="text-[10.5px] font-semibold opacity-70">{t.kaynak === 'crm' ? 'CRM' : t.kaynak === 'oneri' ? 'öneri' : 'elle'}</span>
                  {meta.me.canTheme && t.kaynak !== 'crm' && t.durum === 'onerildi' && (
                    <>
                      <button type="button" aria-label={`${t.tema} temasını onayla`} className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-white/80 active:scale-[0.95]"
                        onClick={() => decide.mutate({ stok: b.stokKodu, tema: t.tema, karar: 'onayla' })}><Check aria-hidden className="h-3.5 w-3.5" /></button>
                      <button type="button" aria-label={`${t.tema} temasını reddet`} className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-white/80 active:scale-[0.95]"
                        onClick={() => decide.mutate({ stok: b.stokKodu, tema: t.tema, karar: 'reddet' })}><X aria-hidden className="h-3.5 w-3.5" /></button>
                    </>
                  )}
                  {meta.me.canTheme && t.kaynak !== 'crm' && t.durum !== 'onerildi' && (
                    <button type="button" aria-label={`${t.tema} temasını kaldır`} className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-white/80 active:scale-[0.95]"
                      onClick={() => decide.mutate({ stok: b.stokKodu, tema: t.tema, karar: 'kaldir' })}><X aria-hidden className="h-3.5 w-3.5" /></button>
                  )}
                </span>
              ))}
              {meta.me.canTheme && (addFor?.stok === b.stokKodu ? (
                <span className="inline-flex items-center gap-1">
                  <label className="sr-only" htmlFor={`add-${b.stokKodu}`}>Tema</label>
                  <select id={`add-${b.stokKodu}`} className={`${field} !w-auto !py-1`} value={addFor.tema} onChange={(e) => setAddFor({ stok: b.stokKodu, tema: e.target.value })}>
                    <option value="">Tema seçin</option>
                    {meta.vocabulary.filter((v) => !b.temalar.some((t) => t.tema === v)).map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                  <button type="button" className={btnPrimary} disabled={!addFor.tema || decide.isPending} onClick={() => decide.mutate({ stok: b.stokKodu, tema: addFor.tema, karar: 'ekle' })}>Ekle</button>
                </span>
              ) : (
                <button type="button" className={`${btnGhost} !min-h-9`} onClick={() => setAddFor({ stok: b.stokKodu, tema: '' })}>
                  <Plus aria-hidden className="h-3.5 w-3.5" /> Tema
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {d && <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />}
    </Panel>
  );
}
