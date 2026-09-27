import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { budgetApi, parseNum, type BudgetParams, type Plan, type Scenario } from './api';
import { NumField } from './parts';

const SC: Array<[Scenario, string]> = [['muhafazakar', 'Muhafazakâr'], ['temel', 'Temel'], ['iyimser', 'İyimser']];
const pct = (v: number | undefined | null) => (v === null || v === undefined ? '' : (v * 100).toLocaleString('tr-TR', { maximumFractionDigits: 2 }));

export type ParamText = { hacim: Record<Scenario, string>; fiyat: string; gider: string; marjDegisim: string; esik: string; tahmin: boolean };

export function toText(p: BudgetParams): ParamText {
  return {
    hacim: { muhafazakar: pct(p.hacim?.muhafazakar), temel: pct(p.hacim?.temel), iyimser: pct(p.hacim?.iyimser) },
    fiyat: pct(p.fiyat),
    gider: pct(p.gider),
    marjDegisim: pct(p.marjDegisim),
    esik: pct(p.esik),
    tahmin: !!p.tahmin,
  };
}

export function fromText(t: ParamText): Partial<BudgetParams> {
  const n = (s: string, label: string) => {
    const v = parseNum(s);
    if (v === null) throw new Error(`${label} sayı olmalı.`);
    return v / 100;
  };
  return {
    hacim: { muhafazakar: n(t.hacim.muhafazakar, 'Muhafazakâr büyüme'), temel: n(t.hacim.temel, 'Temel büyüme'), iyimser: n(t.hacim.iyimser, 'İyimser büyüme') },
    fiyat: n(t.fiyat, 'Fiyat artışı'),
    gider: n(t.gider, 'Gider artışı'),
    marjDegisim: n(t.marjDegisim, 'Marj değişimi'),
    esik: n(t.esik, 'Uyarı eşiği'),
    tahmin: t.tahmin,
  };
}

/** Senaryo parametreleri: hacim büyümesi senaryoya göre, fiyat/gider/marj/eşik ortak. */
export function ParamsForm({ value, onChange, sources, only, forecast }: {
  value: ParamText; onChange: (v: ParamText) => void; sources?: { fiyat?: string; gider?: string }; only?: Scenario; forecast?: string | null;
}) {
  const set = (k: keyof Omit<ParamText, 'hacim' | 'tahmin'>) => (s: string) => onChange({ ...value, [k]: s });
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {SC.filter(([k]) => !only || k === only).map(([k, l]) => (
          <NumField key={k} id={`h-${k}`} label={`${l}: hacim büyümesi`} value={value.hacim[k]} suffix="%"
            onChange={(s) => onChange({ ...value, hacim: { ...value.hacim, [k]: s } })} help="Net adet, taban döneme göre" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <NumField id="p-fiyat" label="Fiyat artışı (net birim fiyat)" value={value.fiyat} onChange={set('fiyat')} suffix="%" help={sources?.fiyat} />
        <NumField id="p-gider" label="Gider artışı (departman)" value={value.gider} onChange={set('gider')} suffix="%" help={sources?.gider} />
        <NumField id="p-marj" label="Marj değişimi (puan)" value={value.marjDegisim} onChange={set('marjDegisim')} suffix="%" help="Kitabın taban marjına eklenir" />
        <NumField id="p-esik" label="Sapma uyarı eşiği" value={value.esik} onChange={set('esik')} suffix="%" help="Gerçekleşen, beklenenin bu oranının altına düşünce uyarı" />
      </div>
      <label className="flex min-h-11 items-start gap-2 text-[12.5px]">
        <input type="checkbox" className="mt-1 h-4 w-4" checked={value.tahmin} onChange={(e) => onChange({ ...value, tahmin: e.target.checked })} />
        <span>
          <strong>Backlist tabanında ZEKİ AI satış tahminini kullan</strong>
          <span className="block text-canvas-muted">
            {forecast ? `Baskı önerisinin kitap başına 12 aylık tahmini (${forecast} başlangıçlı). ` : 'Tahmin bu kurulumda henüz yok; seçilse de geçmiş satış kullanılır. '}
            Yalnız plan yılı Logo verisinin ötesindeyse uygulanır; tahmini olmayan kitapta taban dönemin satışı kalır.
          </span>
        </span>
      </label>
    </div>
  );
}

export default function GenerateSheet({ open, year, years, onClose, onDone }: {
  open: boolean; year: number; years: number[]; onClose: () => void; onDone: (items: Plan[]) => void;
}) {
  const qc = useQueryClient();
  const [y, setY] = useState(year);
  const [scenarios, setScenarios] = useState<Scenario[]>(['muhafazakar', 'temel', 'iyimser']);
  const [text, setText] = useState<ParamText | null>(null);
  useEffect(() => { if (open) setY(year); }, [open, year]);
  const defaults = useQuery({ queryKey: ['budget', 'defaults', y], queryFn: () => budgetApi.defaults(y), enabled: ENGINE_ENABLED && open });
  useEffect(() => { if (defaults.data) setText(toText(defaults.data)); }, [defaults.data]);
  const run = useMutation({
    mutationFn: () => budgetApi.generate(y, scenarios, fromText(text!)),
    onSuccess: (out) => {
      toast.success(`${out.items.length} taslak plan hazırlandı.`);
      qc.invalidateQueries({ queryKey: ['budget'] });
      onDone(out.items);
    },
    onError: (e) => toast.error(errText(e, 'Öneri hazırlanamadı.') ?? ''),
  });
  const choices = [...new Set([...years, year, year + 1, new Date().getFullYear() + 1])].sort();
  return (
    <Sheet open={open} onClose={onClose} modal wide title="ZEKİ AI bütçe önerisi"
      subtitle="Seçilen her senaryo için ayrı bir taslak plan kurulur. Taslaklar Senaryolar sekmesinde yan yana karşılaştırılır; biri onaya gönderilir.">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[140px_1fr]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Plan yılı</span>
            <select className={field} value={y} onChange={(e) => setY(Number(e.target.value))}>
              {choices.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <fieldset className="flex flex-col gap-1">
            <legend className={labelCls}>Senaryolar</legend>
            <div className="flex flex-wrap gap-2">
              {SC.map(([k, l]) => (
                <label key={k} className="flex min-h-11 items-center gap-2 rounded-xl bg-slate-50 px-3 text-[12.5px] font-semibold">
                  <input type="checkbox" className="h-4 w-4" checked={scenarios.includes(k)}
                    onChange={(e) => setScenarios((s) => (e.target.checked ? [...s, k] : s.filter((x) => x !== k)))} />
                  {l}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        {defaults.isLoading || !text ? (
          defaults.error ? <Note tone="err">{errText(defaults.error, 'Varsayılanlar okunamadı.')}</Note> : <Loading />
        ) : (
          <>
            <Note tone="info">Taban dönem: <strong>{defaults.data?.pencere}</strong>. Fiyat ve gider artışı veriden ölçüldü; değiştirebilirsiniz.</Note>
            <ParamsForm value={text} onChange={setText} sources={{ fiyat: defaults.data?.fiyatKaynak, gider: defaults.data?.giderKaynak }}
              forecast={defaults.data?.tahminVar ? defaults.data?.tahminBaslangic : null} />
          </>
        )}
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} onClick={() => run.mutate()} disabled={run.isPending || !text || !scenarios.length}>
            {run.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            {run.isPending ? 'Hazırlanıyor…' : 'Taslakları hazırla'}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
