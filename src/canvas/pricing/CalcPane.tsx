import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, FilePlus2, Search, Send, Save } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import {
  STATUS_TONE,
  day,
  num,
  pct,
  pricingApi,
  tl0,
  tl2,
  type Analysis,
  type BookDetail,
  type CalcResult,
  type FixedKey,
  type Inputs,
  type Overview,
  type PrinterQuote,
  type Spec,
  type Stage,
  type Suggested,
  type FormInputs,
  overviewKey,
} from './api';
import { Group, NumField, Select, Stat, parseQtys } from './parts';
import SqlInfo, { InfoLabel, type FieldHelp } from '../components/SqlInfo';
import { CALC_HELP as CH, FORM_HELP } from './help';
import { CostGroups, Lines, MobileBar, ResultCard, setters } from './CostForm';
import type { Kaynaklar } from '../components/sqlInfo';
import MarketPrices from './MarketPrices';
import DistributorPrices from './DistributorPrices';
import { Explain } from '../components/Explain';

/** Ekrandaki girdiler: baskı hizmeti ve kâğıt ayrı kutularda, hesaba toplamları gider. */
type Form = Inputs & { printService?: number | null; paperPerCopy?: number | null };

const FIXED_ORDER: FixedKey[] = ['avans', 'ceviri', 'grafik', 'redaksiyon', 'pazarlama', 'diger'];

function fromSuggested(s: Suggested, ov: Overview, fl: Partial<Record<FixedKey, number>> = {}): Form {
  const d = ov.defaults;
  return {
    printService: s.printService,
    paperPerCopy: s.paper?.perCopy ?? null,
    printSetup: s.printSetup ?? 0,
    overheadRate: d.overheadRate,
    fixed: { avans: s.advance ?? 0, ceviri: fl.ceviri ?? 0, grafik: fl.grafik ?? 0, redaksiyon: fl.redaksiyon ?? 0, pazarlama: 0, diger: fl.diger ?? 0 },
    royaltyRate: s.royaltyRate ?? 0,
    // TİMAŞ fiyat çalışmasında telif kapak fiyatı × basılan adetle hesaplanır (sözleşme ayrıntısına bakılmaz; kullanıcı
    // 2026-09-29). Sözleşme türü «Telif» bölümünün açıklamasında yazar, seçimle değiştirilebilir.
    royaltyBase: 'kapak',
    royaltyOn: 'baski',
    vat: s.vat,
    discount: s.discount ?? 0,
    variableRate: s.variableRate ?? d.variableRate,
    sellThrough: d.sellThrough,
    targetMargin: d.targetMargin,
    qtys: d.qtys,
    chosenQty: d.qtys[Math.floor(d.qtys.length / 2)] ?? null,
    price: null,
  };
}

/** Girdi kutusu → önerinin kaynak alanı (köprü `pricing/kaynak.py` `suggested_fields`). */
const INPUT_SOURCE: Record<string, string> = {
  printService: 'printService', paperPerCopy: 'paper', printSetup: 'printSetup', royaltyRate: 'royaltyRate', vat: 'vat',
  discount: 'discount', variableRate: 'variableRate', sellThrough: 'sellThrough', targetMargin: 'targetMargin', avans: 'advance',
};

/** Formsuz başlangıç (yeni kitap, formdan aktarım): portal varsayılanları. */
function fromDefaults(ov: Overview): Form {
  const d = ov.defaults;
  return {
    printService: null, paperPerCopy: null, printSetup: 0, overheadRate: d.overheadRate,
    fixed: { avans: 0, ceviri: 0, grafik: 0, redaksiyon: 0, pazarlama: 0, diger: 0 },
    royaltyRate: 0, royaltyBase: 'kapak', royaltyOn: 'baski', vat: 0, discount: ov.measured?.discount ?? 0,
    variableRate: ov.measured?.distribution.rate ?? d.variableRate, sellThrough: d.sellThrough, targetMargin: d.targetMargin,
    qtys: d.qtys, chosenQty: d.qtys[Math.floor(d.qtys.length / 2)] ?? null, price: null,
  };
}

/** Maliyet formunun cilt adı → fiyat analizindeki (CRM) cilt şekli; emsal süzgeci için. */
function bindingOf(tur: string | null | undefined): string | null {
  const t = (tur ?? '').toLocaleUpperCase('tr-TR');
  if (t.includes('SERT')) return 'Sert Kapak';
  if (t.includes('FLEKS')) return 'Flexi Kapak Cilt';
  if (t.includes('TEL')) return 'Tel Dikiş';
  if (t.includes('AMER')) return 'Amerikan Cilt';
  return null;
}

const toInputs = (f: Form): Inputs => ({
  ...f,
  printPerCopy: (f.printService ?? 0) + (f.paperPerCopy ?? 0) || null,
});

export default function CalcPane({ ov }: { ov: Overview }) {
  const [params, setParams] = useSearchParams();
  const code = params.get('kitap');
  const aid = params.get('analiz');
  const qc = useQueryClient();
  const ready = !!ov.measured;

  const [title, setTitle] = useState('');
  const [stage, setStage] = useState<Stage>('tahmini');
  const [spec, setSpec] = useState<Spec>({});
  const [form, setForm] = useState<Form | null>(null);
  const [qtyText, setQtyText] = useState(ov.defaults.qtys.join(', '));
  const [origin, setOrigin] = useState<Record<string, string>>({});
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  /** Girdi kutularının dolduğu cevap: analizden (`inputs`) ya da kitaptan (`suggested.*`). */
  const [fill, setFill] = useState<{ k?: Kaynaklar; prefix: 'inputs' | 'suggested.' | '' } | null>(null);
  /** Maliyet alanları (basım Excel'iyle aynı). `sync`: sonuçları fiyat hesabına kendiliğinden yazılsın mı. */
  const [cost, setCost] = useState<FormInputs | null>(null);
  const [sync, setSync] = useState(true);
  /** Baskı/kâğıt bedeli elle (matbaa teklifi) girildiyse maliyet alanları onları ezmez. */
  const [manualPrint, setManualPrint] = useState(false);

  const analysis = useQuery({ queryKey: ['pricing', 'analysis', aid], queryFn: () => pricingApi.analysis(aid!), enabled: ENGINE_ENABLED && !!aid });
  const book = useQuery({
    queryKey: ['pricing', 'book', code],
    queryFn: () => pricingApi.book(code!),
    enabled: ENGINE_ENABLED && !!code && ready,
    retry: false,
  });
  const setup = useQuery({
    queryKey: ['pricing', 'form', 'setup', code ?? ''],
    queryFn: () => pricingApi.formSetup(code),
    enabled: ENGINE_ENABLED && (!code || ready),
    retry: false,
  });
  const st = useMemo(() => setters((fn) => {
    setSync(true);
    setCost(fn);
  }), []);

  // Kayıtlı analiz açıldıysa girdiler ondan; kitap seçildiyse kitaptan (CRM + Logo); yoksa yeni kitap. Kullanıcının yazdığı ezilmez.
  useEffect(() => {
    const a = analysis.data;
    if (aid && a && setup.data && loadedKey !== `a:${a.id}:${a.version}`) {
      setTitle(a.title);
      setStage(a.stage);
      setSpec(a.specs ?? {});
      const f = (a.inputs ?? {}) as Form;
      setForm({ ...f, price: a.chosenPrice ?? f.price ?? null, chosenQty: a.chosenQty ?? f.chosenQty ?? null });
      setQtyText((f.qtys ?? ov.defaults.qtys).join(', '));
      // Maliyet alanları analizle saklanır; eski analizde yoksa kitabın/yeni formun alanları gösterilir ama kayıtlı
      // bedeller ezilmez (kullanıcı bir alanı değiştirene kadar).
      setCost(a.specs?.form ?? { ...setup.data.inputs, sayfa: a.specs?.pages ?? setup.data.inputs.sayfa, ebat: a.specs?.trim ?? setup.data.inputs.ebat });
      setSync(false);
      setLoadedKey(`a:${a.id}:${a.version}`);
      setFill({ k: a.kaynaklar, prefix: 'inputs' });
      return;
    }
    const b = book.data;
    if (!aid && code && b && setup.data && loadedKey !== `b:${b.book.code}`) {
      setTitle(b.book.name ?? b.book.code);
      setSpec(b.spec);
      setForm(fromSuggested(b.suggested, ov, b.freelance.byKey));
      setOrigin(b.suggested.origin);
      setQtyText(ov.defaults.qtys.join(', '));
      setCost(setup.data.inputs);
      setSync(true);
      setManualPrint(false);
      setLoadedKey(`b:${b.book.code}`);
      setFill({ k: b.kaynaklar, prefix: 'suggested.' });
      return;
    }
    if (!aid && !code && setup.data && loadedKey !== 'yeni') {
      setForm(fromDefaults(ov));
      setCost(setup.data.inputs);
      setSync(true);
      setManualPrint(false);
      setLoadedKey('yeni');
    }
  }, [aid, code, analysis.data, book.data, setup.data, loadedKey, ov]);

  const readOnly = !!analysis.data && ['onayda', 'onaylandi', 'arsiv'].includes(analysis.data.status);

  const costBody = useMemo(() => (cost ? { inputs: cost } : null), [cost]);
  const costDebounced = useDebounced(costBody, 300);
  const costCalc = useQuery({
    queryKey: ['pricing', 'form', 'calc', costDebounced],
    queryFn: () => pricingApi.formCalc(costDebounced!),
    enabled: ENGINE_ENABLED && !!costDebounced && !!costDebounced.inputs.sayfa && !!costDebounced.inputs.adet,
    placeholderData: (prev) => prev,
    retry: false,
  });

  // Maliyet alanlarının sonucu fiyat hesabına: baskı ve kâğıt bedeli (adet başı + baskı başı), genel gider, kapak ücreti,
  // telif oranı, baskı adedi ve kapak fiyatı. Telifin tabanı ve doğuşu CRM sözleşmesinde kalır.
  const mapped = costCalc.data?.analysis;
  useEffect(() => {
    if (!mapped || !sync || readOnly || !cost) return;
    const q = mapped.chosenQty;
    setForm((f) => {
      const base = f ?? fromDefaults(ov);
      const qtys = [...new Set([...(base.qtys ?? ov.defaults.qtys), q])].sort((a, b) => a - b);
      return {
        ...base,
        ...(manualPrint ? {} : { printService: mapped.printService, paperPerCopy: mapped.paperPerCopy, printSetup: mapped.printSetup }),
        overheadRate: mapped.overheadRate, royaltyRate: mapped.royaltyRate, qtys, chosenQty: q, price: mapped.price ?? base.price ?? null,
        fixed: { ...(base.fixed ?? {}), grafik: mapped.fixed.grafik, diger: mapped.fixed.diger },
      };
    });
    setQtyText((t) => {
      const cur = parseQtys(t);
      return cur.includes(q) ? t : [...cur, q].sort((a, b) => a - b).join(', ');
    });
    setSpec((sp) => ({ ...sp, pages: cost.sayfa ?? sp.pages ?? null, trim: cost.ebat ?? sp.trim ?? null, gsm: cost.ic.gr ?? sp.gsm ?? null,
      binding: bindingOf(cost.cilt.tur) ?? sp.binding ?? null, form: cost }));
  }, [mapped, sync, readOnly, manualPrint]); // eslint-disable-line react-hooks/exhaustive-deps

  const market = (analysis.data?.market ?? book.data?.market ?? []).map((m) => m.price);
  const body = useMemo(() => (form ? { inputs: toInputs(form), spec, marketPrices: market } : null), [form, spec, market.join('|')]); // eslint-disable-line react-hooks/exhaustive-deps
  const debounced = useDebounced(body, 350);
  const calc = useQuery({
    queryKey: ['pricing', 'calc', debounced],
    queryFn: () => pricingApi.calc(debounced!),
    enabled: ENGINE_ENABLED && debounced != null && (debounced.inputs.printPerCopy ?? 0) > 0,
    placeholderData: (prev) => prev,
    retry: false,
  });

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...(f ?? {}), ...patch }));
  const setPrint = (patch: Partial<Form>) => {
    setManualPrint(true);
    set(patch);
  };
  /** Girdi kutusunun «i»'si: ne işe yarar ve (varsa) kutuya gelen değerin sorgusu. */
  const inputInfo = (key: string, label: string) => {
    const help: FieldHelp | undefined = CH[key] ?? (['avans', 'ceviri', 'grafik', 'redaksiyon', 'pazarlama', 'diger'].includes(key) ? (key === 'avans' ? CH.avans : CH.fixed) : undefined);
    const only = help ? <SqlInfo k={null} alan="" label={label} help={help} /> : undefined;
    if (!fill || ['printService', 'paperPerCopy', 'printSetup', 'overheadRate'].includes(key)) {
      return ['printService', 'paperPerCopy', 'printSetup', 'overheadRate'].includes(key) && costCalc.data
        ? <SqlInfo k={costCalc.data.kaynaklar} alan="summary" label={label} help={help} />
        : only;
    }
    if (fill.prefix === 'inputs') return <SqlInfo k={fill.k} alan="inputs" label={`${label} (kayıtlı analiz)`} help={help} />;
    if (key === 'qtys') return <SqlInfo k={ov.kaynaklar} alan="defaults" label={label} help={help} />;
    if (key === 'ceviri' || key === 'grafik' || key === 'redaksiyon' || key === 'diger') {
      return book.data ? <SqlInfo k={book.data.kaynaklar} alan="freelance" label={label} help={help} /> : only;
    }
    const f = INPUT_SOURCE[key];
    return f ? <SqlInfo k={fill.k} alan={`${fill.prefix}${f}`} label={label} help={help} /> : only;
  };
  const hi = (key: string, label: string) => <SqlInfo k={null} alan="" label={label} help={CH[key]} />;
  const setFixed = (k: FixedKey, v: number | null) => setForm((f) => ({ ...(f ?? {}), fixed: { ...(f?.fixed ?? {}), [k]: v ?? 0 } }));

  const save = useMutation({
    mutationFn: async (then: 'save' | 'submit') => {
      if (!form) throw new Error('Önce girdileri doldurun.');
      const payload = {
        title: title.trim() || spec.code || cost?.kitap || 'Yeni kitap',
        stage,
        specs: { ...spec, ...(cost ? { form: cost } : {}) },
        inputs: toInputs(form),
        chosenPrice: form.price ?? calc.data?.summary.price ?? null,
        chosenQty: form.chosenQty ?? null,
        stockCode: spec.code ?? null,
        crmBookId: book.data?.book.id ?? analysis.data?.crmBookId ?? null,
      };
      let a: Analysis = aid ? await pricingApi.update(aid, payload) : await pricingApi.create(payload);
      if (then === 'submit') a = await pricingApi.submit(a.id);
      return a;
    },
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ['pricing'] });
      qc.invalidateQueries({ queryKey: overviewKey });
      setLoadedKey(`a:${a.id}:${a.version}`);
      if (!aid) setParams({ bolum: 'hesap', analiz: a.id, ...(code ? { kitap: code } : {}) });
    },
  });

  const clear = () => {
    setParams({ bolum: 'hesap' });
    setForm(null);
    setCost(null);
    setSpec({});
    setTitle('');
    setStage('tahmini');
    setOrigin({});
    setLoadedKey(null);
  };

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <BookPicker
            disabled={!ready}
            info={<SqlInfo k={null} alan="" label="Kitap ara" help={FORM_HELP.kitapAra} />}
            onPick={(c) => {
              setLoadedKey(null);
              setParams({ bolum: 'hesap', kitap: c });
            }}
          />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnGhost} onClick={clear}>
              <FilePlus2 aria-hidden className="h-4 w-4" />
              Yeni kitap
            </button>
          </div>
        </div>
        {!ready && <p className="mt-2 text-[12px] text-canvas-muted">Kitap araması veri görüntüsü hazır olunca açılır.</p>}
        <p className="mt-2 text-[12px] leading-snug text-canvas-muted">
          Alanlar basım Excel'indeki «Kitap Maliyet Formu»yla aynı ve aynı hesabı yapar. Kitap seçince CRM ve Logo'dan dolar; her alanın yanındaki
          <span className="font-bold"> i </span>işaretine basınca o alanın ne işe yaradığı ve verinin nereden geldiği açılır.
        </p>
        {analysis.data && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
            <Pill tone={STATUS_TONE[analysis.data.status]}>{analysis.data.statusLabel}</Pill>
            <span className="font-bold">{analysis.data.title}</span>
            <span className="text-canvas-muted">
              {analysis.data.stageLabel} · sürüm {analysis.data.version} · {analysis.data.createdBy}
            </span>
            {readOnly && <span className="text-canvas-muted">Onaya gönderilmiş analiz değiştirilemez; «Analizler ve onay»dan taslağa alınabilir.</span>}
          </div>
        )}
      </Panel>

      {(book.error || analysis.error || setup.error) && <Note tone="err">{errText(book.error ?? analysis.error ?? setup.error, 'Kitap ya da hesap okunamadı; bağlantıyı yeniden açmayı deneyin.')}</Note>}
      {book.data && !aid && <BookFacts b={book.data} />}

      <Panel>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="block min-w-0 sm:col-span-2">
            <span className={`${labelCls} flex items-center gap-1`}>Kitap / analiz adı{hi('title', 'Kitap / analiz adı')}</span>
            <input className={`${field} mt-1`} value={title} disabled={readOnly} onChange={(e) => setTitle(e.target.value)} placeholder="Ör. yeni roman — ilk baskı" />
          </label>
          <Select<Stage>
            label="Aşama"
            info={hi('stage', 'Aşama')}
            value={stage}
            onChange={setStage}
            disabled={readOnly}
            options={[
              { value: 'tahmini', label: ov.stages.tahmini },
              { value: 'kesin', label: ov.stages.kesin },
            ]}
            hint={stage === 'tahmini' ? 'Kabul kararından sonra. Onay: Mali İşler + Satış.' : 'Kesin sayfa sayısı ve matbaa teklifiyle. Onay: Mali İşler + Satış + Pazarlama + Üst Yönetim.'}
          />
          <label className="block min-w-0">
            <span className={`${labelCls} flex items-center gap-1`}>Stok kodu{hi('code', 'Stok kodu')}</span>
            <input className={`${field} mt-1 font-mono`} value={spec.code ?? ''} disabled={readOnly || !!code} onChange={(e) => setSpec({ ...spec, code: e.target.value || null })} placeholder="Yeni kitapta boş" />
          </label>
        </div>
      </Panel>

      {!cost || !setup.data ? (
        !setup.error && <Note tone="info">Kitap hesabı hazırlanıyor…</Note>
      ) : (
        <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-4">
          <fieldset disabled={readOnly} className="flex min-w-0 flex-col gap-3 lg:gap-4">
            <CostGroups form={cost} s={setup.data} st={st} r={costCalc.data} />
          </fieldset>
          <div className="lg:sticky lg:top-2">
            <ResultCard r={costCalc.data} loading={costCalc.isFetching} err={costCalc.error} />
          </div>
        </div>
      )}
      {!sync && !readOnly && cost && (
        <Note tone="info">
          Bu analiz maliyet alanları eklenmeden önce kaydedilmiş; fiyat hesabındaki bedeller kayıttaki gibi duruyor. Yukarıdaki alanlardan birini
          değiştirince bedeller alanlardan yeniden hesaplanır.
        </Note>
      )}

      {form && (
        <>
          <Group
            step={7}
            title="Fiyat hesabına giden bedeller (adet başına)"
            help={manualPrint ? 'Baskı ve kâğıt bedeli elle girildi; maliyet alanları bu kutuları değiştirmez.' : 'Yukarıdaki alanlardan hesaplanır: baskı ve kâğıt bedeli iki adette hesaplanıp adet başı ve baskı başı diye ayrılır.'}
          >
            <NumField label="Baskı hizmeti" info={inputInfo('printService', 'Baskı hizmeti')} suffix="₺" value={form.printService} disabled={readOnly} onChange={(v) => setPrint({ printService: v })} hint="Matbaa bedeli, KDV hariç, kâğıtsız" />
            <NumField label="Kâğıt, kapak kartonu" info={inputInfo('paperPerCopy', 'Kâğıt, kapak kartonu')} suffix="₺" value={form.paperPerCopy} disabled={readOnly} onChange={(v) => setPrint({ paperPerCopy: v })} hint="Logo kâğıt alış fiyatıyla" />
            <NumField label="Baskı başına hazırlık" info={inputInfo('printSetup', 'Baskı başına hazırlık')} suffix="₺" value={form.printSetup} disabled={readOnly} onChange={(v) => setPrint({ printSetup: v })} hint="Kalıp, fire gibi adetten bağımsız kısım" />
            <NumField label="Genel gider payı" info={inputInfo('overheadRate', 'Genel gider payı')} suffix="%" percent value={form.overheadRate} disabled={readOnly} onChange={(v) => set({ overheadRate: v })} hint="Dolaylı gider (yukarıda)" />
            {manualPrint && !readOnly && (
              <div className="flex items-end">
                <button type="button" className={btnGhost} onClick={() => { setManualPrint(false); setSync(true); }}>
                  Alanlardan yeniden hesapla
                </button>
              </div>
            )}
          </Group>

          {!readOnly && (book.data?.quotes.length ?? 0) > 0 && (
            <QuoteHint
              quotes={book.data!.quotes}
              k={book.data!.kaynaklar}
              onUse={(unit) => {
                setPrint({ printService: unit });
                setStage('kesin');
              }}
            />
          )}

          <Group title="Sabit giderler (kitap başına)" help="Kapak ücreti yukarıdaki alandan; serbest çalışanlar ekranında bu kitaba açılmış iş paketleri çeviri/grafik/redaksiyon kutularına gelir.">
            {FIXED_ORDER.map((k) => (
              <NumField key={k} label={ov.fixedLabels[k]} info={inputInfo(k, ov.fixedLabels[k])} suffix="₺" digits={0} value={form.fixed?.[k] ?? 0} disabled={readOnly} onChange={(v) => setFixed(k, v)} />
            ))}
          </Group>

          <Group title="Telif" help={`Varsayılan: kapak fiyatı × basılan adet (fiyat çalışmasındaki uygulama). Oran yukarıda (Kitap ve baskı).${origin.royalty ? ` ${origin.royalty}.` : ''}`}>
            <Select<'kapak' | 'net'>
              label="Telif tabanı"
              info={hi('royaltyBase', 'Telif tabanı')}
              value={form.royaltyBase ?? 'kapak'}
              onChange={(v) => set({ royaltyBase: v })}
              disabled={readOnly}
              options={[
                { value: 'kapak', label: 'Brüt — KDV hariç kapak fiyatı' },
                { value: 'net', label: 'Net — iskonto sonrası satış' },
              ]}
            />
            <Select<'satis' | 'baski'>
              label="Telif doğuşu"
              info={hi('royaltyOn', 'Telif doğuşu')}
              value={form.royaltyOn ?? 'satis'}
              onChange={(v) => set({ royaltyOn: v })}
              disabled={readOnly}
              options={[
                { value: 'satis', label: 'Satıştan ödeme — satılan adet' },
                { value: 'baski', label: 'Baskıdan ödeme — basılan adet' },
              ]}
              hint="Avans telife mahsup edilir (sabit giderlerde)."
            />
            {book.data?.suggested.advanceForeign && (
              <Note tone="warn">
                Sözleşme avansı {num(book.data.suggested.advanceForeign.amount)} {book.data.suggested.advanceForeign.currency}; kur bilinmediği için TL avans kutusuna
                eklenmedi, elle yazın.
              </Note>
            )}
          </Group>

          <Group title="Satış" help={[origin.discount, origin.variableRate].filter(Boolean).join('. ')}>
            <NumField label="KDV oranı" info={inputInfo('vat', 'KDV oranı')} suffix="%" percent value={form.vat} disabled={readOnly} onChange={(v) => set({ vat: v })} />
            <NumField label="Ortalama kanal iskontosu" info={inputInfo('discount', 'Ortalama kanal iskontosu')} suffix="%" percent value={form.discount} disabled={readOnly} onChange={(v) => set({ discount: v })} />
            <NumField label="Dağıtım gideri" info={inputInfo('variableRate', 'Dağıtım gideri')} suffix="%" percent value={form.variableRate} disabled={readOnly} onChange={(v) => set({ variableRate: v })} hint="Net satışın oranı" />
            <NumField label="Satış oranı" info={inputInfo('sellThrough', 'Satış oranı')} suffix="%" percent value={form.sellThrough} disabled={readOnly} onChange={(v) => set({ sellThrough: v })} hint="Basılanın hesap döneminde satılması beklenen kısmı; satılmayan kitap depoda maliyet olarak kalır" />
            <NumField label="Hedef kâr marjı" info={inputInfo('targetMargin', 'Hedef kâr marjı')} suffix="%" percent value={form.targetMargin} disabled={readOnly} onChange={(v) => set({ targetMargin: v })} hint="Kârın net satış gelirine oranı; fiyat önerisi bu hedefe göre hesaplanır" />
            <label className="block min-w-0">
              <span className={`${labelCls} flex items-center gap-1`}>Baskı adedi senaryoları{inputInfo('qtys', 'Baskı adedi senaryoları')}</span>
              <input
                className={`${field} mt-1 tabular-nums`}
                value={qtyText}
                disabled={readOnly}
                onChange={(e) => {
                  setQtyText(e.target.value);
                  const q = parseQtys(e.target.value);
                  if (q.length) set({ qtys: q.includes(form.chosenQty ?? -1) ? q : [...q, form.chosenQty!].filter(Boolean).sort((a, b) => a - b) });
                }}
              />
              <span className="mt-1 block text-[11px] text-canvas-muted">Virgülle: 1000, 2000, 3000, 5000. Baskı adedi (yukarıda) her zaman eklenir.</span>
            </label>
          </Group>

          {calc.error && <Note tone="err">{errText(calc.error, 'Hesap yapılamadı; girdileri kontrol edin (baskı bedeli ve sayfa sayısı dolu olmalı).')}</Note>}
          {calc.data && (
            <Results
              r={calc.data}
              chosenQty={form.chosenQty ?? null}
              onPickPrice={(p) => {
                if (readOnly) return;
                st.set({ fiyat: p });
                set({ price: p });
              }}
            />
          )}

          {!readOnly && ov.me.canWrite && (
            <Panel>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate('save')}>
                  <Save aria-hidden className="h-4 w-4" />
                  {aid ? 'Değişiklikleri kaydet' : 'Analiz olarak kaydet'}
                </button>
                <button type="button" className={btnPrimary} disabled={save.isPending || !calc.data?.summary.price} onClick={() => save.mutate('submit')}>
                  <Send aria-hidden className="h-4 w-4" />
                  Kaydet ve onaya gönder
                </button>
                <span className="text-[11.5px] text-canvas-muted">
                  Onaya giden rakamlar sunucuda yeniden hesaplanıp dondurulur; baskı adedi {num(form.chosenQty)} ve kapak fiyatı{' '}
                  {tl0(form.price ?? calc.data?.summary.price)}.
                  <SqlInfo k={calc.data?.kaynaklar} alan="summary" label="Seçilen adet ve kapak fiyatı" className="ml-0.5" />
                </span>
              </div>
              {save.error && <div className="mt-2"><Note tone="err">{errText(save.error, 'Analiz kaydedilemedi; biraz sonra yeniden deneyin.')}</Note></div>}
            </Panel>
          )}
          {!ov.me.canWrite && <Note tone="info">Hesap sizde görünür; analizi kaydetmek ve onaya göndermek «Fiyat analizi hazırlama» yetkisi ister.</Note>}

          <DistributorPrices
            code={code ?? analysis.data?.stockCode ?? null}
            pages={spec.pages}
            binding={spec.binding}
            analysisId={aid}
            crmBookId={book.data?.book.id ?? analysis.data?.crmBookId ?? null}
            canWrite={ov.me.canWrite}
            readOnly={readOnly}
          />
          {aid && analysis.data && <MarketPrices analysis={analysis.data} canWrite={ov.me.canWrite} />}
        </>
      )}

      {costCalc.data && <Lines r={costCalc.data} />}
      {costCalc.data && <MobileBar r={costCalc.data} />}
    </div>
  );
}

export function BookPicker({ onPick, disabled, label = 'Kitap ara (ad, yazar ya da stok kodu)', info }: { onPick: (code: string) => void; disabled?: boolean; label?: string; info?: ReactNode }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const dq = useDebounced(q.trim(), 250);
  const hits = useQuery({ queryKey: ['pricing', 'books', dq], queryFn: () => pricingApi.books(dq), enabled: ENGINE_ENABLED && dq.length >= 2 && !disabled });
  return (
    <div className="relative min-w-0 flex-1">
      <span className={`${labelCls} flex items-center gap-1`}>{label}{info}</span>
      <div className="relative mt-1">
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input
          className={`${field} pl-9`}
          value={q}
          disabled={disabled}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          placeholder="Ör. Kiraz ağacı, 15201.01.4529"
          role="combobox"
          aria-expanded={open && !!hits.data?.items.length}
        />
      </div>
      {open && dq.length >= 2 && hits.data && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-[50vh] overflow-y-auto rounded-2xl border border-slate-100 bg-white p-1 shadow-xl" role="listbox">
          {hits.data.items.length === 0 && <div className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok. Adın bir kısmını ya da stok kodunu deneyin; yeni kitapsa aramadan sayfa sayısını yazıp «Veriden öner»e basın.</div>}
          {hits.data.items.map((b) => (
            <button
              key={b.code}
              type="button"
              role="option"
              aria-selected={false}
              className="flex w-full min-h-11 items-start gap-2 rounded-xl px-3 py-2 text-left hover:bg-slate-50 sm:min-h-0"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onPick(b.code);
                setQ('');
                setOpen(false);
              }}
            >
              <BookOpen aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-canvas-violet" />
              <span className="min-w-0">
                <span className="block truncate text-[12.5px] font-bold">{b.name ?? b.code}</span>
                <span className="block truncate text-[11px] text-canvas-muted">
                  {[b.author, b.publisher, b.code, b.pages ? `${b.pages} sayfa` : null, b.price ? tl0(b.price) : null, b.prints ? `${b.prints} baskı faturası` : 'baskı faturası yok']
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
            </button>
          ))}
          {hits.data.total > hits.data.items.length && (
            <div className="px-3 py-2 text-[11px] text-canvas-muted">
              {num(hits.data.total)} eşleşmenin ilk {num(hits.data.items.length)} tanesi; aramayı daraltın.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BookFacts({ b }: { b: BookDetail }) {
  const last = b.prints[b.prints.length - 1];
  const roy = b.book.royalty;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[17px] font-extrabold tracking-tight">{b.book.name ?? b.book.code}</h2>
        <span className="text-[12px] text-canvas-muted">{[b.book.author, b.book.publisher, b.book.library, b.book.code].filter(Boolean).join(' · ')}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-5">
        <Stat info={<SqlInfo k={b.kaynaklar} alan="book" label="Güncel kapak fiyatı" />} label="Güncel kapak fiyatı" value={tl0(b.book.price)} note="CRM kitap kartı" />
        <Stat info={<SqlInfo k={b.kaynaklar} alan="prints[]" label="Son baskı (Logo)" />} label="Son baskı (Logo)" value={last ? tl2(last.unit) : '—'} note={last ? `${num(last.qty)} adet · ${day(last.date)} · ${last.printer ?? ''}` : 'Matbaa faturası yok'} />
        <Stat info={<SqlInfo k={b.kaynaklar} alan="total" label="Logo birim maliyeti" />} label="Logo birim maliyeti" value={tl2(b.total.unitCost)} note={b.total.costCoverage != null ? `Satışların ${pct(b.total.costCoverage)}'i maliyetli` : 'Satış yok'} />
        <Stat info={<SqlInfo k={b.kaynaklar} alan="total" label="Satılan (2021'den)" />} label="Satılan (2021'den)" value={num(b.total.qty)} note={`Net ${tl0(b.total.net)} · ort. ${tl2(b.total.avgNet)}`} />
        <Stat info={<SqlInfo k={b.kaynaklar} alan="book" label="Telif" />} label="Telif" value={roy ? pct(roy.rate) : '—'} note={roy ? `${roy.kindLabel ?? ''} · ${roy.basisLabel ?? ''}${roy.advance ? ` · avans ${num(roy.advance)} ${roy.currency}` : ''}` : 'Yürürlükte sözleşme yok'} />
      </div>
      {(b.prints.length > 0 || b.crmPrints.length > 0) && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] font-bold text-canvas-violet">Baskı geçmişi ({b.prints.length} matbaa faturası, {b.crmPrints.length} CRM üretim kaydı)</summary>
          <div className="mt-2 grid gap-3 xl:grid-cols-2">
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Fatura tarihi</th>
                  <th className={th}>Matbaa</th>
                  <th className={`${th} text-right`}><InfoLabel k={b.kaynaklar} alan="prints[]">Adet</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={b.kaynaklar} alan="prints[]">Tutar</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={b.kaynaklar} alan="prints[]">Birim</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {[...b.prints].reverse().map((p, i) => (
                  <tr key={`${p.invoice}-${i}`} className="border-t border-slate-100">
                    <td className={td}>{day(p.date)}</td>
                    <td className={td}>{p.printer ?? '—'}</td>
                    <td className={`${td} text-right tabular-nums`}>{num(p.qty)}</td>
                    <td className={`${td} text-right tabular-nums`}>{tl0(p.cost)}</td>
                    <td className={`${td} text-right tabular-nums`}>{tl2(p.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Baskı</th>
                  <th className={th}>Tarih</th>
                  <th className={`${th} text-right`}><InfoLabel k={b.kaynaklar} alan="crmPrints[]">Adet</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={b.kaynaklar} alan="crmPrints[]">Kapak fiyatı</InfoLabel></th>
                  <th className={th}>Sayfa · cilt · matbaa</th>
                </tr>
              </thead>
              <tbody>
                {[...b.crmPrints].reverse().map((p, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className={td}>{p.no ?? '—'}</td>
                    <td className={td}>{day(p.date)}</td>
                    <td className={`${td} text-right tabular-nums`}>{num(p.qty)}</td>
                    <td className={`${td} text-right tabular-nums`}>{tl0(p.price)}</td>
                    <td className={td}>{[p.pages ? `${p.pages} s.` : null, p.binding, p.printer].filter(Boolean).join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </details>
      )}
    </Panel>
  );
}

function Results({ r, chosenQty, onPickPrice }: { r: CalcResult; chosenQty: number | null; onPickPrice: (p: number) => void }) {
  const s = r.summary;
  const rec = r.recommendation;
  const comp = r.comparables;
  return (
    <>
      <Panel>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
          <Stat
            info={<SqlInfo k={r.kaynaklar} alan="recommendation" label="Önerilen kapak fiyatı" />}
            label="Önerilen kapak fiyatı"
            explain="Maliyet alt sınırı ile benzer kitapların ortanca fiyatından büyük olanı; KDV dahil ve 5 ₺'ye yukarı yuvarlanmış."
            value={tl0(rec.price)}
            note={
              rec.price ? (
                <button type="button" className="font-bold text-canvas-violet hover:underline" onClick={() => onPickPrice(rec.price!)}>
                  Bu fiyatı kullan
                </button>
              ) : (
                rec.floorReason
              )
            }
          />
          <Stat info={<SqlInfo k={r.kaynaklar} alan="recommendation" label="Maliyet alt sınırı" />} label="Maliyet alt sınırı" explain="Seçilen baskı adedinde hedef kâr marjını tutturan en düşük kapak fiyatı (KDV dahil). Bunun altındaki fiyat hedef marjı karşılamaz." value={tl0(rec.floor)} note={`${num(s.qty)} adette hedef marj ${pct(s.targetMargin)}`} />
          <Stat
            info={<SqlInfo k={r.kaynaklar} alan="comparables" label="Emsal bandı" />}
            label="Emsal bandı"
            explain="Benzer kitapların kapak fiyatlarının orta yarısı: en ucuz dörtte biri ile en pahalı dörtte biri dışarıda bırakılır."
            value={rec.band[0] != null ? `${num(rec.band[0])}–${num(rec.band[1])} ₺` : '—'}
            note={comp ? `${num(comp.price.n)} emsal kitap${r.marketCount ? ` + ${num(r.marketCount)} pazar fiyatı` : ''}, ortanca ${tl0(rec.median)}` : 'Emsal yok'}
          />
          <Stat info={<SqlInfo k={r.kaynaklar} alan="summary" label="Birim maliyet" />} label="Birim maliyet" explain="Basılan kitap başına maliyet: baskı ve kâğıt bedeli ile sabit giderlerin (avans, çeviri, grafik…) adede düşen payı. Telif ve dağıtım satışa bağlı olduğu için dahil değildir." value={tl2(s.unitCost)} note={`${num(s.qty)} adet, toplam ${tl0(s.totalCost)}`} />
          <Stat
            info={<SqlInfo k={r.kaynaklar} alan="summary" label="Başabaş" />}
            label="Başabaş"
            explain="Bu fiyatla bütün maliyetin karşılanması için satılması gereken adet. Kırmızı: başabaş baskı adedini aşıyor, yani baskının tamamı satılsa da zarar. Turuncu: marj hedefin altında. Yeşil: hedef marj tutuyor."
            value={s.breakeven != null ? `${num(s.breakeven)} adet` : '—'}
            tone={s.breakeven != null && s.breakeven > s.qty ? 'err' : s.margin != null && s.margin >= s.targetMargin ? 'ok' : 'warn'}
            note={`${tl0(s.price)} fiyatla marj ${pct(s.margin)} · kâr ${tl0(s.profit)}`}
          />
        </div>
        {rec.notes.length > 0 && (
          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[11.5px] text-canvas-muted">
            {rec.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
      </Panel>

      <section className="space-y-2">
        <h3 className="px-1 text-[14px] font-extrabold">Baskı adedi senaryoları · {tl0(s.price)} kapak fiyatıyla</h3>
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Adet</th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Baskı + kâğıt / adet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Birim maliyet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Toplam maliyet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Net gelir / adet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Başabaş</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Kâr</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="scenarios[]">Marj</InfoLabel></th>
              <th className={`${th} text-right`}>
                <span className="inline-flex items-center gap-1">
                  <InfoLabel k={r.kaynaklar} alan="floors[]">Hedef marja fiyat</InfoLabel>
                  <Explain label="Hedef marja fiyat">O baskı adedinde hedef kâr marjını tutturan en düşük kapak fiyatı (KDV dahil, 5 ₺'ye yukarı).</Explain>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {r.scenarios.map((sc) => {
              const floor = r.floors.find((f) => f.qty === sc.qty);
              const on = sc.qty === chosenQty;
              return (
                <tr key={sc.qty} className={`border-t border-slate-100 ${on ? 'bg-canvas-violet/5 font-bold' : ''}`}>
                  <td className={`${td} tabular-nums`}>{num(sc.qty)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(sc.printUnit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(sc.unitCost)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl0(sc.totalCost)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(sc.netUnit)}</td>
                  <td className={`${td} text-right tabular-nums`}>
                    {sc.breakeven != null ? `${num(sc.breakeven)} (${pct(sc.breakevenShare)})` : 'yok'}
                  </td>
                  <td className={`${td} text-right tabular-nums ${sc.profit != null && sc.profit < 0 ? 'text-red-600' : ''}`}>{tl0(sc.profit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{pct(sc.margin)}</td>
                  <td className={`${td} text-right tabular-nums`} title={floor?.reason ?? undefined}>
                    {floor?.price ? tl0(floor.price) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
        <p className="px-1 text-[11px] leading-snug text-canvas-muted">
          Başabaş: basılan kitabın baskı bedeli ve sabit giderler satılan adetlerin katkısıyla (net gelir − telif − dağıtım) karşılanır; parantezde baskı adedine
          oranı. %100'ün üstü, bu fiyatla baskının tamamı satılsa bile zarar demektir.
        </p>
      </section>

      {r.channels.length > 0 && (
        <section className="space-y-2">
          <h3 className="px-1 text-[14px] font-extrabold">Kanal fiyat matrisi · {num(s.qty)} adet, {tl0(s.price)}</h3>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Müşteri grubu</th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">Satış payı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">İskonto</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">Net gelir / adet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">Telif</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">Dağıtım</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">Birim maliyet</InfoLabel></th>
                <th className={`${th} text-right`}>
                  <span className="inline-flex items-center gap-1">
                    <InfoLabel k={r.kaynaklar} alan="channels[]">Adet başı katkı</InfoLabel>
                    <Explain label="Adet başı katkı">Bu müşteri grubuna satılan bir kitabın net gelirinden telif, dağıtım ve birim maliyet düşülünce kalan tutar. Eksi ise o grupta her satış zarar ettirir.</Explain>
                  </span>
                </th>
                <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="channels[]">Marj</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {r.channels.map((c) => (
                <tr key={c.channel} className="border-t border-slate-100">
                  <td className={td}>{c.channel}</td>
                  <td className={`${td} text-right tabular-nums`}>{pct(c.share)}</td>
                  <td className={`${td} text-right tabular-nums`}>{pct(c.discount)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(c.netUnit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(c.royaltyUnit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(c.variableUnit)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(c.unitCost)}</td>
                  <td className={`${td} text-right tabular-nums ${c.contribution < 0 ? 'text-red-600' : ''}`}>{tl2(c.contribution)}</td>
                  <td className={`${td} text-right tabular-nums`}>{pct(c.margin)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <p className="px-1 text-[11px] text-canvas-muted">Aynı kapak fiyatının her müşteri grubunda ne kadar kazandırdığını gösterir. İskonto ve satış payı son 12 ayın Logo kitap satışından, müşteri grubu (cari kartın grup kodu) başına.</p>
        </section>
      )}

      {comp && (
        <section className="space-y-2">
          <h3 className="px-1 text-[14px] font-extrabold">
            Emsal kitaplar · {num(comp.count)} kitap{comp.pages ? `, ${num(comp.pages)} sayfa ±%${Math.round(comp.band * 100)}` : ''}
            {comp.binding ? `, ${comp.binding}` : ''} · {day(comp.since)} – {day(comp.until)} arası baskı
          </h3>
          {comp.count === 0 ? (
            <Note tone="info">Bu ölçülerde son 12 ayda basılmış kitap yok; baskı bedelini elle girin ya da cilt süzgecini kaldırın.</Note>
          ) : (
            <>
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Kitap</th>
                    <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="comparables">Sayfa</InfoLabel></th>
                    <th className={th}>Son baskı</th>
                    <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="comparables">Adet</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="comparables">Baskı / adet</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="comparables">Logo birim maliyet</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={r.kaynaklar} alan="comparables">Kapak fiyatı</InfoLabel></th>
                  </tr>
                </thead>
                <tbody>
                  {comp.rows.slice(0, 40).map((c) => (
                    <tr key={c.code} className="border-t border-slate-100">
                      <td className={td}>
                        <div className="font-bold">{c.name}</div>
                        <div className="text-[11px] text-canvas-muted">{[c.publisher, c.binding, c.printer].filter(Boolean).join(' · ')}</div>
                      </td>
                      <td className={`${td} text-right tabular-nums`}>{num(c.pages)}</td>
                      <td className={td}>{day(c.printDate)}</td>
                      <td className={`${td} text-right tabular-nums`}>{num(c.printQty)}</td>
                      <td className={`${td} text-right tabular-nums`}>{tl2(c.printUnit)}</td>
                      <td className={`${td} text-right tabular-nums`}>{tl2(c.unitCost)}</td>
                      <td className={`${td} text-right tabular-nums`}>{tl0(c.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              {comp.rows.length > 40 && <p className="px-1 text-[11px] text-canvas-muted">{num(comp.rows.length)} emsalin son basılan 40 tanesi gösteriliyor; özet sayılar hepsinden.</p>}
              {comp.printCurvePerPage && (
                <p className="px-1 text-[11px] text-canvas-muted">
                  <SqlInfo k={r.kaynaklar} alan="comparables" label="Baskı bedeli eğrisi" className="mr-0.5" />
                  Baskı bedeli eğrisi (sayfa başına): adet başına {tl2(comp.printCurvePerPage.a)} + baskı başına {tl0(comp.printCurvePerPage.b)} ÷ adet ·{' '}
                  {num(comp.printCurvePerPage.n)} fatura{comp.printCurvePerPage.r2 != null ? ` · faturalarla uyum ${pct(comp.printCurvePerPage.r2)}` : ''}
                  {comp.printCurvePerPage.shape === 'ortalama' ? ' · veride adetle düşen bir eğri yok, ortalama kullanıldı' : ''}.
                </p>
              )}
            </>
          )}
        </section>
      )}
    </>
  );
}

/** M12 üretim kartındaki matbaa teklifleri: Aşama 2'de baskı hizmeti bedeli tekliften gelir. */
function QuoteHint({ quotes, onUse, k }: { quotes: PrinterQuote[]; onUse: (unit: number) => void; k?: Kaynaklar }) {
  const unitOf = (q: PrinterQuote) => q.unitPrice ?? (q.totalPrice && q.printQty ? q.totalPrice / q.printQty : null);
  return (
    <Panel>
      <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
        Matbaa teklifleri (Üretim ekranından) · {quotes.length}
        <SqlInfo k={k} alan="quotes[]" label="Matbaa teklifleri: birim, toplam, baskı no" />
      </h3>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">
        Kesin fiyat (Aşama 2) matbaa teklifiyle hesaplanır. Teklifin kâğıt içerip içermediğini kontrol edin: Timaş kâğıdı kendi alıyorsa kâğıt kutusu ayrıca kalır.
      </p>
      <ul className="mt-2 space-y-1.5">
        {quotes.map((q) => {
          const unit = unitOf(q);
          return (
            <li key={q.id} className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <span className="font-bold">{q.printer}</span>
              <span className="text-canvas-muted">
                {[q.printNo ? `${q.printNo}. baskı` : null, unit != null ? `${tl2(unit)} / adet` : null, q.totalPrice != null ? `toplam ${tl0(q.totalPrice)}` : null, q.deliveryDay ? `teslim ${day(q.deliveryDay)}` : null, q.byName]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              {unit != null && (
                <button type="button" className={btnGhost} onClick={() => onUse(unit)}>
                  Baskı hizmetine yaz
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
