import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, Sparkles, Target, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtDays, fmtInt, fmtMoney, fmtNum, fmtPct, shippingApi, type DecisionType, type Group, type Meta, type ScoreRow } from './api';
import { Empty, ExportButton, FreshNote, ShippingFrame } from './parts';

/** M44 Firma karnesi (/kargo/firmalar): kargo firmalarının gönderi, teslim süresi, iade ve (yetkiyle) desi başı maliyeti;
 *  şehir ve çıkış şubesi kırılımı, il hedef süresi (kullanıcı verir; termin olmadığı için «geç» oranı yalnız hedefe göre),
 *  kurye/bölge/sözleşme kararı kaydı (K3). Süzgeç adres çubuğunda (?bas=, ?bit=, ?kirilim=, ?sehir=, ?firma=). */

export default function Carriers() {
  const [params, setParams] = useSearchParams();
  const bas = params.get('bas') ?? '';
  const bit = params.get('bit') ?? '';
  const kirilim = (params.get('kirilim') ?? 'firma') as Group;
  const sehir = params.get('sehir') ?? '';
  const firma = params.get('firma') ?? '';
  const [targetsOpen, setTargetsOpen] = useState(false);
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const card = useQuery({
    queryKey: ['shipping', 'carriers', bas, bit, kirilim, sehir, firma],
    queryFn: () => shippingApi.carriers({ baslangic: bas, bitis: bit, kirilim, sehir, firma }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };
  const d = card.data;
  const cost = !!d?.maliyetGorunur;
  const hasTarget = !!d?.items.some((i) => i.hedefGun);
  const m = meta.data;
  return (
    <ShippingFrame
      crumb="Firma karnesi"
      title="Kargo firma karnesi"
      lead="Kargo firmasının gönderi kaydından: gönderi, teslim süresi (ortanca, ortalama, %90), iade oranı ve teslim bekleyen; yetkiyle desi başı ve sevk başı maliyet. Dönem kargo irsaliye tarihine göredir. Termin tutulmadığı için «geç teslim» oranı yalnız sizin verdiğiniz il hedefine göre hesaplanır."
      meta={m}
      aside={
        m && (
          <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
            {m.me.karar && (
              <button type="button" className={btnGhost} onClick={() => setTargetsOpen(true)}>
                <Target aria-hidden className="h-4 w-4" />
                İl hedefleri
              </button>
            )}
            <ExportButton list="firmalar" params={{ baslangic: bas || undefined, bitis: bit || undefined, kirilim, sehir: sehir || undefined, firma: firma || undefined }} can={m.me.disaAktar} label="Excel'e al" />
          </div>
        )
      }
    >
      {card.error && <Note tone="err">{errText(card.error, 'Karne okunamadı.')}</Note>}
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input className={field} type="date" value={bas || d?.baslangic || ''} onChange={(e) => set('bas', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input className={field} type="date" value={bit || d?.bitis || ''} onChange={(e) => set('bit', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kırılım</span>
            <select className={field} value={kirilim} onChange={(e) => set('kirilim', e.target.value === 'firma' ? '' : e.target.value)}>
              {Object.entries(m?.kirilimlar ?? { firma: 'Kargo firması' }).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Alıcı şehri</span>
            <select className={field} value={sehir} onChange={(e) => set('sehir', e.target.value)}>
              <option value="">Hepsi</option>
              {(d?.sehirler ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kargo firması</span>
            <select className={field} value={firma} onChange={(e) => set('firma', e.target.value)}>
              <option value="">Hepsi</option>
              {(d?.firmalar ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
        </div>
        {!bas && !bit && d && <p className="mt-2 text-[11.5px] text-canvas-muted">Dönem seçilmedi: kargo kaydının veri sonunda biten son 30 gün.</p>}
      </Panel>
      {d && (
        <>
          <KpiRow>
            <Kpi label="Gönderi" value={fmtInt(d.toplam.gonderi)} help={`${fmtDay(d.baslangic)} – ${fmtDay(d.bitis)}`} info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Gönderi" />} />
            <Kpi label="Ortanca teslim" value={fmtDays(d.toplam.ortancaGun)} help={`${fmtInt(d.toplam.teslim)} teslim edilmiş gönderi`} info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Ortanca teslim" />} />
            <Kpi label="İade" value={fmtInt(d.toplam.iade)} help={`Oran ${fmtPct(d.toplam.gonderi ? d.toplam.iade / d.toplam.gonderi : null)}`} info={<SqlInfo k={d.kaynaklar} alan="toplam" label="İade ve iade oranı" />} />
            {cost ? (
              <Kpi label="Desi başı" value={fmtMoney(d.toplam.desiBasi)} help={`Tutar ${fmtMoney(d.toplam.tutar)} · sevk başı ${fmtMoney(d.toplam.sevkBasi)}`} info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Desi başı, tutar ve sevk başı" />} />
            ) : (
              <Kpi label="Maliyet" value="—" help="Kargo maliyetini görme yetkisi gerekir" />
            )}
          </KpiRow>
          <FreshNote f={d.kargoVeri} k={d.kaynaklar} />
          <Panel>
            <h2 className="text-[14px] font-extrabold">{d.kirilimAdi}</h2>
            {d.items.length === 0 ? (
              <Empty>Bu dönemde kargo kaydı yok. Bu «gecikme yok» demek değildir; veri sonuna bakın.</Empty>
            ) : (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      {(kirilim === 'firma' || kirilim === 'firma-sehir') && <th className={th}>Firma</th>}
                      {(kirilim === 'sehir' || kirilim === 'firma-sehir') && <th className={th}>Şehir</th>}
                      {kirilim === 'sube' && <th className={th}>Çıkış şubesi</th>}
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Gönderi</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Ortanca</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">%90</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Bekleyen</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">İade oranı</InfoLabel></th>
                      {hasTarget && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Hedefi aşan</InfoLabel></th>}
                      {cost && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Desi</InfoLabel></th>}
                      {cost && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Tutar</InfoLabel></th>}
                      {cost && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Desi başı</InfoLabel></th>}
                      {cost && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[]">Sevk başı</InfoLabel></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((r, i) => <ScoreLine key={i} r={r} kirilim={kirilim} cost={cost} hasTarget={hasTarget} />)}
                  </tbody>
                </TableWrap>
              </div>
            )}
            <p className="mt-2 text-[11.5px] text-canvas-muted">
              Teslim süresi = teslim tarihi − kargo irsaliye tarihi. Tarihleri tutarsız (teslim irsaliyeden önce) kayıtlar süreye girmez, «tutarsız» diye sayılır.
            </p>
          </Panel>
          {m && <DecisionsPanel meta={m} bas={d.baslangic} bit={d.bitis} sehir={sehir} />}
        </>
      )}
      {card.isLoading && <Empty>Kargo kayıtları okunuyor…</Empty>}
      {m && <TargetsSheet open={targetsOpen} meta={m} cities={d?.sehirler ?? []} onClose={() => setTargetsOpen(false)} />}
    </ShippingFrame>
  );
}

function ScoreLine({ r, kirilim, cost, hasTarget }: { r: ScoreRow; kirilim: Group; cost: boolean; hasTarget: boolean }) {
  return (
    <tr className="border-t border-slate-100">
      {(kirilim === 'firma' || kirilim === 'firma-sehir') && <td className={`${td} font-bold`}>{r.firma}</td>}
      {(kirilim === 'sehir' || kirilim === 'firma-sehir') && <td className={td}>{r.sehir}</td>}
      {kirilim === 'sube' && <td className={td}>{r.sube}</td>}
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.gonderi)}</td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtDays(r.ortancaGun)}</td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtDays(r.p90Gun)}</td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.bekleyen)}</td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.iadeOrani)}</td>
      {hasTarget && (
        <td className={`${td} text-right font-mono tabular-nums`}>
          {r.hedefGun ? `${fmtPct(r.hedefiAsanOrani)} (hedef ${r.hedefGun} gün)` : '—'}
        </td>
      )}
      {cost && <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.desi)}</td>}
      {cost && <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.tutar)}</td>}
      {cost && <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtMoney(r.desiBasi)}</td>}
      {cost && <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.sevkBasi)}</td>}
    </tr>
  );
}

function DecisionsPanel({ meta, bas, bit, sehir }: { meta: Meta; bas: string; bit: string; sehir: string }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['shipping', 'decisions'], queryFn: shippingApi.decisions, enabled: ENGINE_ENABLED });
  const [open, setOpen] = useState(false);
  const del = useMutation({
    mutationFn: (id: string) => shippingApi.deleteDecision(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['shipping', 'decisions'] }),
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const items = list.data?.items ?? [];
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[14px] font-extrabold">Karar kaydı</h2>
          <p className="max-w-[80ch] text-[11.5px] text-canvas-muted">Kurye firması değişimi, bölge kuralı ve sözleşme kararları gerekçesiyle burada tutulur. Karar insanındır; portal kargo firmasına ya da CRM'e bir şey yazmaz.</p>
        </div>
        {meta.me.karar && (
          <button type="button" className={btnPrimary} onClick={() => setOpen(true)}>
            <Plus aria-hidden className="h-4 w-4" />
            Karar ekle
          </button>
        )}
      </div>
      {list.error && <div className="mt-2"><Note tone="err">{errText(list.error, 'Kararlar okunamadı.')}</Note></div>}
      {items.length === 0 ? (
        <Empty>Henüz karar kaydı yok.</Empty>
      ) : (
        <div className="mt-2 flex flex-col gap-2">
          {items.map((k) => (
            <div key={k.id} className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
              <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
                <Pill tone="violet">{k.turAdi}</Pill>
                <span className="text-canvas-muted">{k.kararVeren} · {fmtDay(k.tarih)}</span>
                {Object.entries(k.kapsam).map(([a, b]) => <Pill key={a} tone="muted">{a}: {b}</Pill>)}
                {meta.me.karar && (
                  <button type="button" className="ml-auto inline-flex min-h-9 items-center text-canvas-muted hover:text-red-700" aria-label="Kararı sil" onClick={() => del.mutate(k.id)}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </div>
              <p className="mt-1 break-words text-[13px] font-bold">{k.karar}</p>
              {k.gerekce && <p className="mt-1 whitespace-pre-line break-words text-[12px] text-canvas-ink">{k.gerekce}</p>}
              {k.modelOzet && <p className="mt-1 whitespace-pre-line break-words rounded-lg bg-canvas-violet/5 px-2 py-1 text-[12px]">Zeki AI özeti: {k.modelOzet}</p>}
            </div>
          ))}
        </div>
      )}
      <DecisionSheet open={open} meta={meta} bas={bas} bit={bit} sehir={sehir} onClose={() => setOpen(false)} />
    </Panel>
  );
}

function DecisionSheet({ open, meta, bas, bit, sehir, onClose }: { open: boolean; meta: Meta; bas: string; bit: string; sehir: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [tur, setTur] = useState<DecisionType>('kurye');
  const [firma, setFirma] = useState('');
  const [karar, setKarar] = useState('');
  const [gerekce, setGerekce] = useState('');
  const [ozet, setOzet] = useState<string | null>(null);
  const summary = useMutation({
    mutationFn: () => shippingApi.decisionSummary({ baslangic: bas, bitis: bit, sehir }),
    onSuccess: (r) => {
      if (r.metin) setOzet(r.metin);
      else toast.message(r.not ?? 'Zeki AI özeti alınamadı.');
    },
    onError: (e) => toast.error(errText(e, 'Özet alınamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () =>
      shippingApi.createDecision({ tur, karar: karar.trim(), gerekce: gerekce.trim(), modelOzet: ozet, kapsam: { baslangic: bas, bitis: bit, ...(sehir ? { sehir } : {}), ...(firma ? { firma } : {}) } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shipping', 'decisions'] });
      toast.success('Karar kaydedildi.');
      setKarar('');
      setGerekce('');
      setOzet(null);
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="Karar ekle" subtitle={`Kapsam: ${fmtDay(bas)} – ${fmtDay(bit)}${sehir ? ` · ${sehir}` : ''}`}>
      <div className="flex flex-col gap-3 text-[13px]">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={tur} onChange={(e) => setTur(e.target.value as DecisionType)}>
              {Object.entries(meta.kararTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İlgili firma</span>
            <input className={field} value={firma} onChange={(e) => setFirma(e.target.value)} placeholder="İsteğe bağlı" />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Karar *</span>
          <textarea className={`${field} min-h-[64px]`} value={karar} onChange={(e) => setKarar(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Gerekçe</span>
          <textarea className={`${field} min-h-[72px]`} value={gerekce} onChange={(e) => setGerekce(e.target.value)} />
        </label>
        <div className="rounded-xl bg-slate-50 p-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[12px] font-bold">Zeki AI gerekçe özeti</span>
            <button type="button" className={btnGhost} disabled={summary.isPending} onClick={() => summary.mutate()}>
              {summary.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Karneden özet çıkar
            </button>
          </div>
          {ozet ? <p className="mt-1.5 whitespace-pre-line text-[12px]">{ozet}</p> : <p className="mt-1.5 text-[11.5px] text-canvas-muted">Yalnız karnedeki rakamlar verilir; olgu dışı sayı içeren metin atılır.</p>}
        </div>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} disabled={!karar.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}

function TargetsSheet({ open, meta, cities, onClose }: { open: boolean; meta: Meta; cities: string[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [rows, setRows] = useState<Array<{ il: string; gun: string }>>(() => Object.entries(meta.is.bolgeHedef).map(([il, gun]) => ({ il, gun: String(gun) })));
  const save = useMutation({
    mutationFn: () => {
      const h: Record<string, number> = {};
      rows.forEach((r) => {
        if (r.il.trim() && /^\d{1,3}$/.test(r.gun)) h[r.il.trim()] = Number(r.gun);
      });
      return shippingApi.saveSettings({ bolgeHedef: h });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shipping'] });
      toast.success('İl hedefleri kaydedildi.');
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title="İl hedef süreleri" subtitle="Bir ilde teslimin kaç günde olmasını beklediğinizi yazın. Karne «hedefi aşan payı» yalnız hedef verilen illerde hesaplar.">
      <div className="flex flex-col gap-2 text-[13px]">
        <datalist id="kargo-iller">
          {cities.map((c) => <option key={c} value={c} />)}
        </datalist>
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[minmax(0,1fr)_96px_44px] items-end gap-2">
            <input className={field} list="kargo-iller" value={r.il} placeholder="İl" aria-label="İl" onChange={(e) => setRows((x) => x.map((y, j) => (j === i ? { ...y, il: e.target.value } : y)))} />
            <input className={field} inputMode="numeric" value={r.gun} placeholder="Gün" aria-label="Hedef gün" onChange={(e) => setRows((x) => x.map((y, j) => (j === i ? { ...y, gun: e.target.value.replace(/\D/g, '').slice(0, 3) } : y)))} />
            <button type="button" className={btnGhost} aria-label="Satırı sil" onClick={() => setRows((x) => x.filter((_, j) => j !== i))}>
              <Trash2 aria-hidden className="h-4 w-4" />
            </button>
          </div>
        ))}
        <button type="button" className={`${btnGhost} self-start`} onClick={() => setRows((x) => [...x, { il: '', gun: '' }])}>
          <Plus aria-hidden className="h-4 w-4" />
          İl ekle
        </button>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}
