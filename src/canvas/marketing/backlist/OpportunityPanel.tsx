import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Loader2 } from 'lucide-react';
import Sheet from '../../editorial/studio/reader/Sheet';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnPrimary, errText } from '../../admin/ui';
import { fmtDay, fmtMoney, fmtShortDay } from '../api';
import SqlInfo from '../../components/SqlInfo';
import { M46_TONE, blApi, fmtChange, fmtN, fmtOne, monthName, runout, type BlMeta } from './api';

/** Kitap fırsat kartı (yan panel): bileşenler ve ham değerleri, 36 tam ay satış, önerilen eylemler ve gerekçesi,
 *  eşleşmeler, geçmiş kampanyaların öncesi/sonrası, planlar. */
export default function OpportunityPanel({ stok, meta, agirlik, onClose }: { stok: string | null; meta: BlMeta; agirlik: string; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ['bl', 'detail', stok, agirlik], queryFn: () => blApi.detail(stok as string, agirlik), enabled: ENGINE_ENABLED && !!stok });
  const create = useMutation({
    mutationFn: () => blApi.createPlan([{ stokKodu: stok as string }]),
    onSuccess: (plan) => {
      qc.invalidateQueries({ queryKey: ['bl'] });
      toast.success('Aktivasyon planı taslağı açıldı.');
      nav(`/pazarlama/plan/${encodeURIComponent(plan.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Plan açılamadı.') ?? ''),
  });
  const d = q.data;
  const money = meta.me.canSeeBudget;
  const raw = (k: string, v: number | string | null) => {
    if (v === null) return 'değer yok';
    if (v === 'inf') return 'satış yok, stok var';
    const n = Number(v);
    if (k === 'egilim') return `satış ${fmtChange(-n)}`;
    if (k === 'stok') return n === 0 ? 'stok yok' : `${fmtOne(n)} ay yeter`;
    if (k === 'marj') return money ? `%${Math.round(n * 100)}` : 'yetki gerekli';
    if (k === 'tahmin') return `${fmtN(n)} adet`;
    if (k === 'sapma') return `gerçekleşme %${Math.round((1 - n) * 100)}`;
    return String(v);
  };

  return (
    <Sheet open={!!stok} onClose={onClose} wide title={d?.ad ?? stok ?? ''}
      subtitle={d ? [d.stokKodu, d.yazar, d.yayinevi, d.kitaplik, d.hedefKitle, d.ilkYayin ? `ilk yayın ${fmtDay(d.ilkYayin)}` : null].filter(Boolean).join(' · ') : undefined}>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kart açılamadı.')}</Note>}
      {d && (
        <div className="flex flex-col gap-4 text-[12.5px]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[28px] font-bold tabular-nums leading-none">{d.endeks === null ? '—' : Math.round(d.endeks)}</span>
            <span className="text-canvas-muted">uyku endeksi (sizin ağırlıklarınızla)</span>
            {d.m46.sapmaAcik && <Pill tone="err">Hedefte açık sapma{money && d.m46.acikTutar ? ` · ${fmtMoney(d.m46.acikTutar)}` : ''}</Pill>}
            {d.m46.durum && <Pill tone={M46_TONE[d.m46.durum] ?? 'muted'}>Hedef: {d.m46.durumAdi}</Pill>}
            {meta.me.canWrite && (d.stok ?? 0) > 0 && (
              <button type="button" className={`${btnPrimary} ml-auto`} disabled={create.isPending} onClick={() => create.mutate()}>
                {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}Aktivasyon planı oluştur
              </button>
            )}
          </div>

          <section>
            <h3 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Bileşenler<SqlInfo k={d.kaynaklar} alan="bilesen" label="Bileşenler ve endeks" /></h3>
            <ul className="mt-1 flex flex-col gap-1.5">
              {meta.components.map((c) => {
                const b = d.bilesen[c.key];
                return (
                  <li key={c.key} className="grid grid-cols-[110px_1fr_auto] items-center gap-2">
                    <span className="font-bold">{c.ad}</span>
                    <span className="relative h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden>
                      {b.yuzdelik !== null && <span className="absolute inset-y-0 left-0 rounded-full bg-canvas-violet" style={{ width: `${b.yuzdelik}%` }} />}
                    </span>
                    <span className="whitespace-nowrap text-right text-[11.5px] tabular-nums text-canvas-muted">
                      {b.yuzdelik === null ? '—' : Math.round(b.yuzdelik)} · {raw(c.key, b.ham)}
                    </span>
                  </li>
                );
              })}
            </ul>
            <p className="mt-1.5 text-[11px] leading-snug text-canvas-muted">
              Son 12 ay {fmtN(d.adetSon12)} adet, önceki 12 ay {fmtN(d.adetOnceki12)} ({fmtChange(d.degisim)}); depo stoku {fmtN(d.stok)} ({runout(d)});
              12 aylık Zeki AI tahmini {fmtN(d.tahmin12)} adet{money && d.ciroSon12 !== null ? `; son 12 ay net ciro ${fmtMoney(d.ciroSon12)}` : ''}.
              Veri sonu {fmtDay(d.veriSonu)}.
              <SqlInfo k={d.kaynaklar} alan="adetSon12" label="12 ay satış, stok, tahmin" className="ml-0.5" />
            </p>
          </section>

          <section>
            <h3 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Son 36 tam ay net adet<SqlInfo k={d.kaynaklar} alan="seri[]" label="Aylık seri" /></h3>
            <div className="mt-1 h-44 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.seri.map((m) => ({ ay: monthName(m.ay), adet: m.adet }))} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
                  <CartesianGrid vertical={false} stroke="#eef0f4" />
                  <XAxis dataKey="ay" tick={{ fontSize: 10 }} interval={5} tickLine={false} />
                  <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
                  <Tooltip formatter={(v) => [typeof v === 'number' ? fmtN(v) : '—', 'net adet']} />
                  <Bar dataKey="adet" fill="#6d28d9" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section>
            <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Önerilen eylemler</h3>
            <ul className="mt-1 flex flex-col gap-1">
              {d.eylemler.map((a, i) => (
                <li key={i}><strong>{a.eylem}</strong> — <span className="text-canvas-muted">{a.gerekce}</span></li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-canvas-muted">Kural tabanlı adaylardır; fiyat ve promosyon kararı fiyatlama ve e-ticaret ekibindedir.</p>
          </section>

          {d.eslesmeler.length > 0 && (
            <section>
              <h3 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Gündem eşleşmeleri<SqlInfo k={d.kaynaklar} alan="eslesmeler[]" label="Gündem eşleşmeleri" /></h3>
              <ul className="mt-1 flex flex-col gap-1">
                {d.eslesmeler.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-center gap-1.5">
                    <Pill tone={m.tur === 'konu' ? 'violet' : 'muted'}>{m.turAdi}</Pill>
                    <span>{m.etiket}</span>
                    <span className="text-canvas-muted">{fmtShortDay(m.tarih)}</span>
                    {m.tur === 'konu' && <span className="text-canvas-muted">· {m.onay === 'kabul' ? 'onaylandı' : m.onay === 'red' ? 'reddedildi' : 'onay bekliyor'}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Geçmiş kampanyalar (öncesi / sonrası)<SqlInfo k={d.kaynaklar} alan="kampanyalar[]" label="Kampanya etkisi" /></h3>
            {!d.kampanyalar.length && <p className="mt-1 text-canvas-muted">CRM'de bu kitabın kampanyası yok (B2C ve pazar yeri kampanyaları CRM'de tutulmuyor).</p>}
            <ul className="mt-1 flex flex-col gap-1.5">
              {d.kampanyalar.map((k) => (
                <li key={k.kampanyaId} className="rounded-xl bg-white/80 p-2">
                  <div className="font-bold">{k.ad ?? 'Kampanya'} <span className="font-normal text-canvas-muted">· {k.mecra ?? '—'} · {fmtShortDay(k.baslangic)} – {fmtShortDay(k.bitis)}</span></div>
                  <div className="text-canvas-muted">
                    Önceki 3 ay {fmtN(k.once3)} · kampanya {fmtN(k.kampanya)} ({k.kampanyaAyi ?? '—'} ay) · sonraki 2 ay {fmtN(k.sonra2)} adet
                    {k.aylikDegisim !== null ? ` · aylık ortalama ${fmtChange(k.aylikDegisim)}` : ''}
                    {k.kapsam === 'suruyor' ? ' · sonrası henüz veride yok' : k.kapsam === 'veri-yok' ? ' · satış verisi pencere dışında' : ''}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {d.planlar.length > 0 && (
            <section>
              <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Planlar</h3>
              <ul className="mt-1 flex flex-col gap-1">
                {d.planlar.map((p) => (
                  <li key={p.id}><Link className="font-bold text-canvas-violet hover:underline" to={`/pazarlama/plan/${encodeURIComponent(p.id)}`}>{p.baslik}</Link> · {p.durumAdi}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Sheet>
  );
}
