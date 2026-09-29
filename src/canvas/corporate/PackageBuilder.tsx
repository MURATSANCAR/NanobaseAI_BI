import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileText, Loader2, Sparkles } from 'lucide-react';
import { Note, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { ENGINE_ENABLED } from '../engine';
import { NewOpportunitySheet } from './OppForm';
import { Empty } from './parts';
import { corporateApi, fmtInt, fmtMoney, fmtPct, marginText, parseNum, toItems, type Meta, type OppInput, type PackageAlt, type PackageRequest } from './api';

function AltCard({ alt, kisi, canQuote, busy, onQuote, k }: { alt: PackageAlt; kisi: number; canQuote: boolean; busy: boolean; onQuote: (a: PackageAlt) => void; k?: Kaynaklar }) {
  const info = (label: string) => <SqlInfo k={k} alan="alternatifler[]" row={alt.no} label={`Alternatif ${alt.no}: ${label}`} className="ml-0.5" />;
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-100 bg-white/90 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[14px] font-extrabold">Alternatif {alt.no}</h3>
        <span className="inline-flex items-center font-mono text-[13px] font-bold tabular-nums">{fmtMoney(alt.paketNet, true)} / paket{info('paket net ve kalemler')}</span>
      </div>
      <ol className="flex flex-col gap-1.5">
        {alt.kalemler.map((l) => (
          <li key={l.stok} className="rounded-xl bg-slate-50 px-2.5 py-2">
            <div className="flex items-start justify-between gap-2">
              <span className="min-w-0 break-words text-[12.5px] font-bold leading-snug">{l.ad ?? l.stok}</span>
              <span className="shrink-0 font-mono text-[12px] tabular-nums">{fmtMoney(l.netBirim, true)}</span>
            </div>
            <div className="text-[11px] leading-snug text-canvas-muted">
              {[l.yazar, `liste ${fmtMoney(l.listeFiyati, true)}`, l.fiyatListe ? `fiyat listesi ${l.fiyatListe}` : null].filter(Boolean).join(' · ')}
            </div>
            {l.gerekce && <div className="text-[11px] leading-snug text-canvas-muted">{l.gerekce}</div>}
          </li>
        ))}
      </ol>
      {alt.eksik > 0 && <Note tone="warn">Bütçeye {alt.eksik} kitap daha sığmadı.</Note>}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
        <dt className="text-canvas-muted">{fmtInt(kisi)} paket toplamı</dt>
        <dd className="inline-flex items-center justify-end font-mono font-bold tabular-nums">{fmtMoney(alt.toplamNet)}{info('paket toplamı')}</dd>
        <dt className="text-canvas-muted">Liste fiyatıyla</dt>
        <dd className="inline-flex items-center justify-end font-mono tabular-nums">{fmtMoney(alt.toplamListe)}{info('liste fiyatıyla toplam')}</dd>
        <dt className="text-canvas-muted">Marj</dt>
        <dd className="inline-flex items-center justify-end text-right">{marginText(alt)}{info('marj')}</dd>
      </dl>
      {alt.onayNedenleri.length > 0 && <Note tone="warn">Onay gerekecek: {alt.onayNedenleri.map((r) => r.metin).join(' · ')}</Note>}
      {!alt.butceyeUygun && <Note tone="warn">Paket başı bütçeyi aşıyor.</Note>}
      {canQuote && (
        <button type="button" className={`${btnPrimary} mt-auto`} disabled={busy} onClick={() => onQuote(alt)}>
          <FileText aria-hidden className="h-4 w-4" /> Teklife dönüştür
        </button>
      )}
    </li>
  );
}

export default function PackageBuilder({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const oppId = params.get('firsat');
  const [themes, setThemes] = useState<string[]>(() => (params.get('tema') ? [params.get('tema')!] : []));
  const [kisi, setKisi] = useState('100');
  const [per, setPer] = useState('3');
  const [budget, setBudget] = useState('');
  const [budgetKind, setBudgetKind] = useState<'toplam' | 'kisi'>('kisi');
  const [ageMin, setAgeMin] = useState('');
  const [ageMax, setAgeMax] = useState('');
  const [disc, setDisc] = useState('');
  const [pending, setPending] = useState<PackageAlt | null>(null);
  const opp = useQuery({ queryKey: ['corporate', 'opp', oppId], queryFn: () => corporateApi.opportunity(oppId!), enabled: ENGINE_ENABLED && !!oppId });

  const req: PackageRequest = {
    temalar: themes,
    kisi: Math.max(1, Math.round(parseNum(kisi) ?? 1)),
    kitapSayisi: Math.max(1, Math.round(parseNum(per) ?? 1)),
    butce: parseNum(budget),
    butceTuru: budgetKind,
    yasMin: parseNum(ageMin),
    yasMax: parseNum(ageMax),
    indirim: parseNum(disc),
  };
  const run = useMutation({ mutationFn: () => corporateApi.suggest(req), onError: (e) => toast.error(errText(e, 'Paket önerisi alınamadı.') ?? '') });
  const toQuote = useMutation({
    mutationFn: async ({ alt, newOpp }: { alt: PackageAlt; newOpp?: OppInput }) => {
      const target = newOpp ? await corporateApi.createOpportunity(newOpp) : { id: oppId! };
      const q = await corporateApi.createQuote(target.id, { kalemler: toItems(alt.kalemler), paketAdet: run.data?.kisi ?? null });
      return { oppId: target.id, quoteId: q.id };
    },
    onSuccess: ({ oppId: o, quoteId }) => {
      setPending(null);
      qc.invalidateQueries({ queryKey: ['corporate'] });
      toast.success('Teklif taslağı açıldı.');
      nav(`/kurumsal-satis/firsat/${o}?teklif=${quoteId}`);
    },
    onError: (e) => toast.error(errText(e, 'Teklif açılamadı.') ?? ''),
  });
  const onQuote = (alt: PackageAlt) => {
    if (oppId) toQuote.mutate({ alt });
    else setPending(alt);
  };
  const r = run.data;
  const toggle = (t: string) => setThemes((ts) => (ts.includes(t) ? ts.filter((x) => x !== t) : [...ts, t]));

  return (
    <div className="grid gap-3 xl:grid-cols-[380px_minmax(0,1fr)] xl:gap-4">
      <Panel>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            run.mutate();
          }}
        >
          <p className="text-[12px] leading-snug text-canvas-muted">Kurum için tema, paket sayısı ve bütçe girin; birkaç kitap paketi alternatifi hazırlanır, beğendiğinizi teklife dönüştürürsünüz.</p>
          {opp.data && <Note tone="info">Teklif «{opp.data.kurum} · {opp.data.ad}» fırsatına eklenecek.</Note>}
          <fieldset className="flex flex-col gap-1.5">
            <legend className={labelCls}>Tema (bir ya da daha çok)</legend>
            <div className="flex flex-wrap gap-1.5">
              {meta.vocabulary.map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={themes.includes(t)}
                  onClick={() => toggle(t)}
                  className={`min-h-9 rounded-xl px-2.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${themes.includes(t) ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink'}`}
                >
                  {t}
                </button>
              ))}
            </div>
            {meta.vocabulary.length === 0 && <span className="text-[11.5px] text-canvas-muted">Tema listesi henüz okunmadı (verileri yenileyin).</span>}
          </fieldset>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Paket (kişi) sayısı</span>
              <input className={`${field} font-mono tabular-nums`} inputMode="numeric" value={kisi} onChange={(e) => setKisi(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Paketteki kitap</span>
              <input className={`${field} font-mono tabular-nums`} inputMode="numeric" value={per} onChange={(e) => setPer(e.target.value)} />
            </label>
          </div>
          <div className="flex flex-col gap-1">
            <span className={labelCls}>Bütçe (₺, isteğe bağlı)</span>
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <input className={`${field} font-mono tabular-nums`} inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} aria-label="Bütçe" placeholder="Örn. 250" />
              <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Bütçe türü">
                {(['kisi', 'toplam'] as const).map((k) => (
                  <button key={k} type="button" role="radio" aria-checked={budgetKind === k} onClick={() => setBudgetKind(k)}
                    className={`min-h-9 rounded-lg px-2.5 text-[12px] font-bold ${budgetKind === k ? 'bg-white shadow-sm' : ''}`}>
                    {k === 'kisi' ? 'Paket başı' : 'Toplam'}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Yaş (en az)</span>
              <input className={`${field} font-mono tabular-nums`} inputMode="numeric" value={ageMin} onChange={(e) => setAgeMin(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Yaş (en çok)</span>
              <input className={`${field} font-mono tabular-nums`} inputMode="numeric" value={ageMax} onChange={(e) => setAgeMax(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>İndirim %</span>
              <input className={`${field} font-mono tabular-nums`} inputMode="decimal" value={disc} placeholder="Boş: kural" onChange={(e) => setDisc(e.target.value)} />
            </label>
          </div>
          <p className="text-[11px] leading-snug text-canvas-muted">
            Aday: seçilen temada onaylı etiketi olan, stoğu paket sayısına yeten ve bugün geçerli Logo satış fiyatı olan kitaplar; bu yılın satışına göre sıralanır.
            İndirim boş bırakılırsa adede göre önerilir: benzer büyüklükteki geçmiş kurum faturalarındaki indirim ya da tanımlı indirim basamakları.
          </p>
          <button type="submit" className={btnPrimary} disabled={!themes.length || run.isPending}>
            {run.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            Paket öner
          </button>
        </form>
      </Panel>

      <div className="flex min-w-0 flex-col gap-3">
        {!r && !run.isPending && (
          <Empty title="Tema, paket sayısı ve bütçeyle başlayın">Örnek: «Kişisel gelişim + İş hayatı», 300 paket, paketteki kitap 3, paket başı 250 ₺.</Empty>
        )}
        {r && (
          <>
            <Panel>
              <div className="flex flex-col gap-1 text-[12.5px]">
                <div>
                  <b>{fmtInt(r.adaySayisi)}</b> aday kitap
                  <SqlInfo k={r.kaynaklar} alan="adaySayisi" label="Aday kitap sayısı" className="ml-0.5" /> · indirim <b>{fmtPct(r.indirim)}</b>
                  <SqlInfo k={r.kaynaklar} alan="indirim" label="Önerilen indirim ve dayanağı" className="ml-0.5" />
                  {r.paketBasiButce ? (
                    <>
                      {' '}· paket başı bütçe <b>{fmtMoney(r.paketBasiButce, true)}</b>
                      <SqlInfo k={r.kaynaklar} alan="paketBasiButce" label="Paket başı bütçe" className="ml-0.5" />
                    </>
                  ) : null}
                </div>
                <div className="text-[11.5px] text-canvas-muted">İndirimin dayanağı: {r.indirimDayanak.aciklama}.</div>
                {(r.elenen.stokYetersiz > 0 || r.elenen.fiyatYok > 0 || r.elenen.yasUymuyor > 0) && (
                  <div className="text-[11.5px] text-canvas-muted">
                    Temaya uyup elenen: stoğu yetmeyen {fmtInt(r.elenen.stokYetersiz)}, geçerli fiyatı olmayan {fmtInt(r.elenen.fiyatYok)}, yaşı uymayan ya da yaş bilgisi olmayan {fmtInt(r.elenen.yasUymuyor)}.
                    <SqlInfo k={r.kaynaklar} alan="elenen" label="Temaya uyup elenen kitaplar" className="ml-0.5" />
                  </div>
                )}
              </div>
            </Panel>
            {r.not && <Note tone="warn">{r.not}</Note>}
            <ul className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
              {r.alternatifler.map((a) => (
                <AltCard key={a.no} alt={a} kisi={r.kisi} canQuote={meta.me.canQuote} busy={toQuote.isPending} onQuote={onQuote} k={r.kaynaklar} />
              ))}
            </ul>
          </>
        )}
      </div>

      <NewOpportunitySheet
        open={!!pending}
        onClose={() => setPending(null)}
        vocabulary={meta.vocabulary}
        busy={toQuote.isPending}
        initial={{ tema: themes[0], deger: pending?.toplamNet }}
        onCreate={(b) => pending && toQuote.mutate({ alt: pending, newOpp: b })}
      />
    </div>
  );
}
