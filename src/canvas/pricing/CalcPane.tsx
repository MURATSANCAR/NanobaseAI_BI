import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, Calculator, Search, Send, Save, X } from 'lucide-react';
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
  type Spec,
  type Stage,
  type Suggested,
  overviewKey,
} from './api';
import { Group, NumField, Select, Stat, parseQtys } from './parts';
import MarketPrices from './MarketPrices';

/** Ekrandaki girdiler: baskı hizmeti ve kâğıt ayrı kutularda, hesaba toplamları gider. */
type Form = Inputs & { printService?: number | null; paperPerCopy?: number | null };

const FIXED_ORDER: FixedKey[] = ['avans', 'ceviri', 'grafik', 'redaksiyon', 'pazarlama', 'diger'];
const BINDINGS = ['Amerikan Cilt', 'Tel Dikiş', 'Sert Kapak', 'Sert Kapak (Cilt Bezi Sıvamalı)', 'Spiral Cilt', 'Flexi Kapak Cilt', 'Plastik Kapak Cilt', 'Biala Kapak Cilt', 'Omega Tel Dikiş'];

function fromSuggested(s: Suggested, ov: Overview, fl: Partial<Record<FixedKey, number>> = {}): Form {
  const d = ov.defaults;
  return {
    printService: s.printService,
    paperPerCopy: s.paper?.perCopy ?? null,
    printSetup: s.printSetup ?? 0,
    overheadRate: d.overheadRate,
    fixed: { avans: s.advance ?? 0, ceviri: fl.ceviri ?? 0, grafik: fl.grafik ?? 0, redaksiyon: fl.redaksiyon ?? 0, pazarlama: 0, diger: fl.diger ?? 0 },
    royaltyRate: s.royaltyRate ?? 0,
    royaltyBase: s.royaltyBase,
    royaltyOn: s.royaltyOn,
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

  const analysis = useQuery({ queryKey: ['pricing', 'analysis', aid], queryFn: () => pricingApi.analysis(aid!), enabled: ENGINE_ENABLED && !!aid });
  const book = useQuery({
    queryKey: ['pricing', 'book', code],
    queryFn: () => pricingApi.book(code!),
    enabled: ENGINE_ENABLED && !!code && ready,
    retry: false,
  });

  // Kayıtlı analiz açıldıysa girdiler ondan, yoksa kitaptan (veriden öneri) dolar. Kullanıcının yazdığı ezilmez.
  useEffect(() => {
    const a = analysis.data;
    if (aid && a && loadedKey !== `a:${a.id}:${a.version}`) {
      setTitle(a.title);
      setStage(a.stage);
      setSpec(a.specs ?? {});
      const f = (a.inputs ?? {}) as Form;
      setForm({ ...f, price: a.chosenPrice ?? f.price ?? null, chosenQty: a.chosenQty ?? f.chosenQty ?? null });
      setQtyText((f.qtys ?? ov.defaults.qtys).join(', '));
      setLoadedKey(`a:${a.id}:${a.version}`);
      return;
    }
    const b = book.data;
    if (!aid && b && loadedKey !== `b:${b.book.code}`) {
      setTitle(b.book.name ?? b.book.code);
      setSpec(b.spec);
      setForm(fromSuggested(b.suggested, ov, b.freelance.byKey));
      setOrigin(b.suggested.origin);
      setQtyText(ov.defaults.qtys.join(', '));
      setLoadedKey(`b:${b.book.code}`);
    }
  }, [aid, analysis.data, book.data, loadedKey, ov]);

  const suggest = useMutation({
    mutationFn: () => pricingApi.suggest(spec),
    onSuccess: (s) => {
      setForm((f) => ({ ...fromSuggested(s, ov), ...(f ? { fixed: f.fixed, price: f.price } : {}) }));
      setOrigin(s.origin);
    },
  });

  const readOnly = !!analysis.data && ['onayda', 'onaylandi', 'arsiv'].includes(analysis.data.status);
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
  const setFixed = (k: FixedKey, v: number | null) => setForm((f) => ({ ...(f ?? {}), fixed: { ...(f?.fixed ?? {}), [k]: v ?? 0 } }));

  const save = useMutation({
    mutationFn: async (then: 'save' | 'submit') => {
      if (!form) throw new Error('Önce girdileri doldurun.');
      const payload = {
        title: title.trim() || spec.code || 'Yeni kitap',
        stage,
        specs: { ...spec },
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
            onPick={(c) => {
              setLoadedKey(null);
              setParams({ bolum: 'hesap', kitap: c });
            }}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={btnGhost}
              onClick={() => {
                clear();
                setForm(null);
              }}
            >
              <X aria-hidden className="h-4 w-4" />
              Temizle
            </button>
          </div>
        </div>
        {!ready && <p className="mt-2 text-[12px] text-canvas-muted">Kitap araması veri görüntüsü hazır olunca açılır.</p>}
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

      {(book.error || analysis.error) && <Note tone="err">{errText(book.error ?? analysis.error, 'Kayıt okunamadı.')}</Note>}
      {book.data && !aid && <BookFacts b={book.data} />}

      <Panel>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="block min-w-0 sm:col-span-2">
            <span className={labelCls}>Kitap / analiz adı</span>
            <input className={`${field} mt-1`} value={title} disabled={readOnly} onChange={(e) => setTitle(e.target.value)} placeholder="Ör. yeni roman — ilk baskı" />
          </label>
          <Select<Stage>
            label="Aşama"
            value={stage}
            onChange={setStage}
            options={[
              { value: 'tahmini', label: ov.stages.tahmini },
              { value: 'kesin', label: ov.stages.kesin },
            ]}
            hint={stage === 'tahmini' ? 'Kabul kararından sonra, emsal kitaplarla. Onay: Mali İşler + Satış.' : 'Kesin sayfa sayısı ve matbaa teklifiyle. Onay: Mali İşler + Satış + Pazarlama + Üst Yönetim.'}
          />
          <label className="block min-w-0">
            <span className={labelCls}>Stok kodu</span>
            <input className={`${field} mt-1 font-mono`} value={spec.code ?? ''} disabled={readOnly || !!code} onChange={(e) => setSpec({ ...spec, code: e.target.value || null })} placeholder="Yeni kitapta boş" />
          </label>
        </div>
      </Panel>

      <Group title="Teknik özellikler" help="Sayfa, ebat ve kâğıt gramajı kâğıt maliyetini; sayfa ve cilt şekli emsal kitapları belirler.">
        <NumField label="Sayfa sayısı" value={spec.pages} digits={0} disabled={readOnly} onChange={(v) => setSpec({ ...spec, pages: v })} />
        <label className="block min-w-0">
          <span className={labelCls}>Ebat (cm)</span>
          <input className={`${field} mt-1`} value={spec.trim ?? ''} disabled={readOnly} placeholder="13,5x21" onChange={(e) => setSpec({ ...spec, trim: e.target.value || null })} />
        </label>
        <NumField label="İç kâğıt gramajı" suffix="gr" value={spec.gsm} digits={0} disabled={readOnly} onChange={(v) => setSpec({ ...spec, gsm: v })} />
        <Select<string>
          label="Cilt şekli"
          value={spec.binding ?? ''}
          onChange={(v) => setSpec({ ...spec, binding: v || null })}
          options={[{ value: '', label: 'Hepsi (emsalde ayırma)' }, ...BINDINGS.map((b) => ({ value: b, label: b }))]}
        />
        <div className="flex items-end">
          <button type="button" className={btnGhost} disabled={!ready || !spec.pages || suggest.isPending || readOnly} onClick={() => suggest.mutate()}>
            <Calculator aria-hidden className="h-4 w-4" />
            {suggest.isPending ? 'Hesaplanıyor…' : form ? 'Maliyeti veriden yeniden öner' : 'Veriden öner'}
          </button>
        </div>
        {suggest.error && <Note tone="err">{errText(suggest.error, 'Öneri alınamadı.')}</Note>}
      </Group>

      {!form ? (
        <Note tone="info">
          Bir kitap seçin ya da yeni kitabın sayfa sayısını yazıp «Veriden öner»e basın: baskı bedeli emsal kitapların matbaa faturalarından, kâğıt Logo'daki
          son alış fiyatından, telif CRM sözleşmesinden, iskonto son 12 ayın satışından gelir. Her kutu elle değiştirilebilir.
        </Note>
      ) : (
        <>
          <Group title="Baskı ve kâğıt (adet başına)" help={origin.printService || origin.paper ? `${origin.printService ?? ''}. ${origin.paper ?? ''}` : undefined}>
            <NumField label="Baskı hizmeti" suffix="₺" value={form.printService} disabled={readOnly} onChange={(v) => set({ printService: v })} hint="Matbaa «komple baskı» bedeli, KDV hariç" />
            <NumField label="Kâğıt, kapak kartonu, bandrol" suffix="₺" value={form.paperPerCopy} disabled={readOnly} onChange={(v) => set({ paperPerCopy: v })} hint="Kâğıdı Timaş alır; matbaa faturası kâğıtsızdır" />
            <NumField label="Baskı başına hazırlık" suffix="₺" value={form.printSetup} disabled={readOnly} onChange={(v) => set({ printSetup: v })} hint="Kalıp ve ayar gibi adetten bağımsız bedel (eğriden)" />
            <NumField label="Genel gider payı" suffix="%" percent value={form.overheadRate} disabled={readOnly} onChange={(v) => set({ overheadRate: v })} hint="Baskı ve kâğıda eklenir (varsayım)" />
          </Group>

          <Group title="Sabit giderler (kitap başına)" help="Serbest çalışanlar ekranında bu kitaba açılmış iş paketleri çeviri/grafik/redaksiyon kutularına gelir.">
            {FIXED_ORDER.map((k) => (
              <NumField key={k} label={ov.fixedLabels[k]} suffix="₺" digits={0} value={form.fixed?.[k] ?? 0} disabled={readOnly} onChange={(v) => setFixed(k, v)} />
            ))}
          </Group>

          <Group title="Telif" help={origin.royalty}>
            <NumField label="Telif oranı" suffix="%" percent value={form.royaltyRate} disabled={readOnly} onChange={(v) => set({ royaltyRate: v })} />
            <Select<'kapak' | 'net'>
              label="Telif tabanı"
              value={form.royaltyBase ?? 'kapak'}
              onChange={(v) => set({ royaltyBase: v })}
              options={[
                { value: 'kapak', label: 'Brüt — KDV hariç kapak fiyatı' },
                { value: 'net', label: 'Net — iskonto sonrası satış' },
              ]}
            />
            <Select<'satis' | 'baski'>
              label="Telif doğuşu"
              value={form.royaltyOn ?? 'satis'}
              onChange={(v) => set({ royaltyOn: v })}
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
            <NumField label="KDV oranı" suffix="%" percent value={form.vat} disabled={readOnly} onChange={(v) => set({ vat: v })} />
            <NumField label="Ortalama kanal iskontosu" suffix="%" percent value={form.discount} disabled={readOnly} onChange={(v) => set({ discount: v })} />
            <NumField label="Dağıtım gideri" suffix="%" percent value={form.variableRate} disabled={readOnly} onChange={(v) => set({ variableRate: v })} hint="Net satışın oranı" />
            <NumField label="Satış oranı" suffix="%" percent value={form.sellThrough} disabled={readOnly} onChange={(v) => set({ sellThrough: v })} hint="Basılanın hesap döneminde satılan kısmı" />
            <NumField label="Hedef kâr marjı" suffix="%" percent value={form.targetMargin} disabled={readOnly} onChange={(v) => set({ targetMargin: v })} hint="Net satış gelirine oranla" />
            <label className="block min-w-0">
              <span className={labelCls}>Baskı adedi senaryoları</span>
              <input
                className={`${field} mt-1 tabular-nums`}
                value={qtyText}
                disabled={readOnly}
                onChange={(e) => {
                  setQtyText(e.target.value);
                  const q = parseQtys(e.target.value);
                  if (q.length) set({ qtys: q, chosenQty: q.includes(form.chosenQty ?? -1) ? form.chosenQty : q[Math.floor(q.length / 2)] });
                }}
              />
              <span className="mt-1 block text-[11px] text-canvas-muted">Virgülle: 1000, 2000, 3000, 5000</span>
            </label>
            <Select<string>
              label="Seçilen adet"
              value={String(form.chosenQty ?? '')}
              onChange={(v) => set({ chosenQty: Number(v) })}
              options={(form.qtys ?? []).map((q) => ({ value: String(q), label: num(q) }))}
            />
            <NumField
              label="Kapak fiyatı (KDV dahil)"
              suffix="₺"
              value={form.price}
              disabled={readOnly}
              onChange={(v) => set({ price: v })}
              placeholder={calc.data?.recommendation.price ? `Öneri ${num(calc.data.recommendation.price)}` : 'Boşsa öneri kullanılır'}
            />
          </Group>

          {calc.error && <Note tone="err">{errText(calc.error, 'Hesap yapılamadı.')}</Note>}
          {calc.data && <Results r={calc.data} chosenQty={form.chosenQty ?? null} onPickPrice={(p) => !readOnly && set({ price: p })} />}

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
                  Onaya giden rakamlar sunucuda yeniden hesaplanıp dondurulur; seçilen adet {num(form.chosenQty)} ve kapak fiyatı{' '}
                  {tl0(form.price ?? calc.data?.summary.price)}.
                </span>
              </div>
              {save.error && <div className="mt-2"><Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note></div>}
            </Panel>
          )}
          {!ov.me.canWrite && <Note tone="info">Hesap sizde görünür; analizi kaydetmek ve onaya göndermek «Fiyat analizi hazırlama» yetkisi ister.</Note>}

          {aid && analysis.data && <MarketPrices analysis={analysis.data} canWrite={ov.me.canWrite} />}
        </>
      )}
    </div>
  );
}

function BookPicker({ onPick, disabled }: { onPick: (code: string) => void; disabled?: boolean }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const dq = useDebounced(q.trim(), 250);
  const hits = useQuery({ queryKey: ['pricing', 'books', dq], queryFn: () => pricingApi.books(dq), enabled: ENGINE_ENABLED && dq.length >= 2 && !disabled });
  return (
    <div className="relative min-w-0 flex-1">
      <span className={labelCls}>Kitap ara (ad, yazar ya da stok kodu)</span>
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
          {hits.data.items.length === 0 && <div className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok.</div>}
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
        <Stat label="Güncel kapak fiyatı" value={tl0(b.book.price)} note="CRM kitap kartı" />
        <Stat label="Son baskı (Logo)" value={last ? tl2(last.unit) : '—'} note={last ? `${num(last.qty)} adet · ${day(last.date)} · ${last.printer ?? ''}` : 'Matbaa faturası yok'} />
        <Stat label="Logo birim maliyeti" value={tl2(b.total.unitCost)} note={b.total.costCoverage != null ? `Satışların ${pct(b.total.costCoverage)}'i maliyetli` : 'Satış yok'} />
        <Stat label="Satılan (2021'den)" value={num(b.total.qty)} note={`Net ${tl0(b.total.net)} · ort. ${tl2(b.total.avgNet)}`} />
        <Stat label="Telif" value={roy ? pct(roy.rate) : '—'} note={roy ? `${roy.kindLabel ?? ''} · ${roy.basisLabel ?? ''}${roy.advance ? ` · avans ${num(roy.advance)} ${roy.currency}` : ''}` : 'Yürürlükte sözleşme yok'} />
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
                  <th className={`${th} text-right`}>Adet</th>
                  <th className={`${th} text-right`}>Tutar</th>
                  <th className={`${th} text-right`}>Birim</th>
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
                  <th className={`${th} text-right`}>Adet</th>
                  <th className={`${th} text-right`}>Kapak fiyatı</th>
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
            label="Önerilen kapak fiyatı"
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
          <Stat label="Maliyet alt sınırı" value={tl0(rec.floor)} note={`${num(s.qty)} adette hedef marj ${pct(s.targetMargin)}`} />
          <Stat
            label="Emsal bandı"
            value={rec.band[0] != null ? `${num(rec.band[0])}–${num(rec.band[1])} ₺` : '—'}
            note={comp ? `${num(comp.price.n)} emsal kitap${r.marketCount ? ` + ${num(r.marketCount)} pazar fiyatı` : ''}, ortanca ${tl0(rec.median)}` : 'Emsal yok'}
          />
          <Stat label="Birim maliyet" value={tl2(s.unitCost)} note={`${num(s.qty)} adet, toplam ${tl0(s.totalCost)}`} />
          <Stat
            label="Başabaş"
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
              <th className={`${th} text-right`}>Baskı + kâğıt / adet</th>
              <th className={`${th} text-right`}>Birim maliyet</th>
              <th className={`${th} text-right`}>Toplam maliyet</th>
              <th className={`${th} text-right`}>Net gelir / adet</th>
              <th className={`${th} text-right`}>Başabaş</th>
              <th className={`${th} text-right`}>Kâr</th>
              <th className={`${th} text-right`}>Marj</th>
              <th className={`${th} text-right`}>Hedef marja fiyat</th>
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
                <th className={`${th} text-right`}>Satış payı</th>
                <th className={`${th} text-right`}>İskonto</th>
                <th className={`${th} text-right`}>Net gelir / adet</th>
                <th className={`${th} text-right`}>Telif</th>
                <th className={`${th} text-right`}>Dağıtım</th>
                <th className={`${th} text-right`}>Birim maliyet</th>
                <th className={`${th} text-right`}>Adet başı katkı</th>
                <th className={`${th} text-right`}>Marj</th>
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
          <p className="px-1 text-[11px] text-canvas-muted">İskonto ve satış payı son 12 ayın Logo kitap satışından, müşteri grubu (cari kartın grup kodu) başına.</p>
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
                    <th className={`${th} text-right`}>Sayfa</th>
                    <th className={th}>Son baskı</th>
                    <th className={`${th} text-right`}>Adet</th>
                    <th className={`${th} text-right`}>Baskı / adet</th>
                    <th className={`${th} text-right`}>Logo birim maliyet</th>
                    <th className={`${th} text-right`}>Kapak fiyatı</th>
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
                  Baskı bedeli eğrisi (sayfa başına): adet başına {tl2(comp.printCurvePerPage.a)} + baskı başına {tl0(comp.printCurvePerPage.b)} ÷ adet ·{' '}
                  {num(comp.printCurvePerPage.n)} fatura{comp.printCurvePerPage.r2 != null ? ` · uyum ${pct(comp.printCurvePerPage.r2)}` : ''}
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
