import { type ReactNode } from 'react';
import { ChevronDown, Layers } from 'lucide-react';
import { Note, TableWrap, errText, td, th } from '../admin/ui';
import SqlInfo, { type FieldHelp } from '../components/SqlInfo';
import { day, num, pct, tl0, tl2, type ExtraKey, type FormInputs, type FormPart, type FormResult, type FormSetup } from './api';
import { Group, NumField, Select, TextField, Toggle } from './parts';
import { FORM_HELP as H, FORM_RESULT_HELP as R } from './help';
import { DigitalGroups, digitalOf } from './DigitalForm';

/**
 * Kitap hesabının maliyet alanları: TİMAŞ basım Excel'indeki «Kitap Maliyet Formu»yla aynı alanlar ve aynı hesap
 * (köprü `pricing/form.py`). Kâğıt fiyatı Logo alışından; matbaa kalemleri fiyat listesinden. Sonuç (baskı ve kâğıt
 * bedeli, adet, kapak fiyatı, telif, dolaylı gider) Kitap hesabının fiyat analizine kendiliğinden gider.
 */

export const i = (help: FieldHelp, label: string) => <SqlInfo k={null} alan="" label={label} help={help} />;

export type Setters = {
  set: (p: Partial<FormInputs>) => void;
  setIn: SetIn;
  setKapak: (p: Partial<FormInputs['kapak']>) => void;
  setEk: (p: Partial<FormInputs['ekler']>) => void;
  setPart: (key: ExtraKey, p: Partial<FormPart>) => void;
};

export function setters(setForm: (fn: (f: FormInputs | null) => FormInputs | null) => void): Setters {
  return {
    set: (patch) => setForm((f) => (f ? { ...f, ...patch } : f)),
    setIn: (key, patch) => setForm((f) => (f ? { ...f, [key]: { ...f[key], ...patch } } : f)),
    setKapak: (patch) => setForm((f) => (f ? { ...f, kapak: { ...f.kapak, ...patch } } : f)),
    setEk: (patch) => setForm((f) => (f ? { ...f, ekler: { ...f.ekler, ...patch } } : f)),
    setPart: (key, patch) => setForm((f) => (f ? { ...f, ekler: { ...f.ekler, [key]: { ...f.ekler[key], ...patch } } } : f)),
  };
}

/** Maliyet alanlarının altı adımı (Excel'in sol tarafı). */
export function CostGroups({ form, s, st, r }: { form: FormInputs; s: FormSetup; st: Setters; r?: FormResult }) {
  if (form.baski === 'dijital') {
    return (
      <>
        <BookGroup form={form} s={s} set={st.set} />
        <DigitalGroups form={form} s={s} st={st} r={r} />
      </>
    );
  }
  return (
    <>
      <BookGroup form={form} s={s} set={st.set} />
      <InnerGroup form={form} s={s} setIn={st.setIn} r={r} />
      <CoverGroup form={form} s={s} setKapak={st.setKapak} r={r} />
      <BindingGroup form={form} s={s} setIn={st.setIn} />
      <ExtrasGroup form={form} s={s} setEk={st.setEk} setPart={st.setPart} r={r} />
      <OtherGroup form={form} setIn={st.setIn} set={st.set} />
    </>
  );
}

// ------------------------------------------------------------------ gruplar

export type SetIn = <K extends 'ic' | 'renkli' | 'cilt' | 'diger'>(key: K, patch: Partial<FormInputs[K]>) => void;

function More({ children, label = 'Ayrıntılar' }: { children: ReactNode; label?: string }) {
  return (
    <details className="group col-span-full">
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 text-[12px] font-bold text-canvas-violet sm:min-h-0">
        <ChevronDown aria-hidden className="h-4 w-4 transition-transform duration-200 ease-out group-open:rotate-180 motion-reduce:transition-none" />
        {label}
      </summary>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
    </details>
  );
}

function BookGroup({ form, s, set }: { form: FormInputs; s: FormSetup; set: (p: Partial<FormInputs>) => void }) {
  const dig = form.baski === 'dijital';
  const dt = s.tariff.dijital;
  // Dijital Excel'in kendi iskonto listesi ofsetinkinin üstüne (ör. Mavi Kirpi ofsette %60, dijitalde %45).
  const rates: Record<string, number> = dig ? { ...s.tariff.publishers, ...(dt?.publishers ?? {}) } : s.tariff.publishers;
  const pubs = Object.keys(rates);
  // Baskı türü değişince dolaylı gider, elle değiştirilmediyse o türün varsayılanına geçer (ofset %90, dijital %40).
  const switchTo = (b: 'ofset' | 'dijital') => {
    const from = dig ? (dt?.dolayli ?? 40) : s.tariff.dolayli;
    const to = b === 'dijital' ? (dt?.dolayli ?? 40) : s.tariff.dolayli;
    set({ baski: b, dijital: digitalOf(form, dt), ...(form.dolayli == null || form.dolayli === from ? { dolayli: to } : {}) });
  };
  const o = s.origin;
  const logoKur = s.logoKur;
  const kf = (v: number) => v.toLocaleString('tr-TR', { maximumFractionDigits: 4 });
  // Boş kutuda hesabın kullandığı kur: fiyat listesinde «elle» seçildiyse listedeki, değilse Logo'nun son döviz faturası.
  const kurHint = (c: 'USD' | 'EUR') => {
    const lg = logoKur[c];
    if (s.tariff.kurKaynak === 'elle') return `Boşsa fiyat listesindeki elle girilen kur: ${kf(s.tariff.kur[c])} ₺${lg ? ` (Logo ${day(lg.date)}: ${kf(lg.rate)} ₺)` : ''}`;
    return lg ? `Logo faturaları ${day(lg.date)}: ${kf(lg.rate)} ₺` : `Logo'da fatura yok; fiyat listesi: ${kf(s.tariff.kur[c])} ₺`;
  };
  return (
    <Group step={1} title="Kitap ve baskı">
      <Select<'ofset' | 'dijital'>
        label="Baskı türü"
        info={i(H.baski, 'Baskı türü')}
        value={dig ? 'dijital' : 'ofset'}
        onChange={switchTo}
        options={[{ value: 'ofset', label: 'Ofset' }, ...(dt ? [{ value: 'dijital' as const, label: 'Dijital (küçük baskı)' }] : [])]}
      />
      <Select<string>
        label="Yayınevi"
        info={i(H.yayinevi, 'Yayınevi')}
        value={form.yayinevi ?? ''}
        onChange={(v) => set({ yayinevi: v || null })}
        options={[{ value: '', label: 'Seçin' }, ...pubs.map((p) => ({ value: p, label: `${p} · vadeli iskonto %${num(rates[p])}` }))]}
        hint={o.yayinevi}
      />
      <NumField label="Sayfa sayısı" info={i(H.sayfa, 'Sayfa sayısı')} digits={0} value={form.sayfa} onChange={(v) => set({ sayfa: v })} hint={o.sayfa} />
      <NumField label="Baskı adedi" info={i(H.adet, 'Baskı adedi')} digits={0} value={form.adet} onChange={(v) => set({ adet: v })} hint={o.adet} />
      <TextField label="Ebat (cm)" info={i(H.ebat, 'Ebat')} value={form.ebat} onChange={(v) => set({ ebat: v || null })} list={dig && dt ? dt.tablo.map((t) => t.ebat) : s.tariff.trims.map((t) => t.ebat)} placeholder="13,5x21" hint={o.ebat} />
      <NumField label="Kapak fiyatı (KDV dahil)" info={i(H.fiyat, 'Kapak fiyatı')} suffix="₺" value={form.fiyat} onChange={(v) => set({ fiyat: v })} hint={o.fiyat} />
      <NumField label="Telif oranı" info={i(H.telif, 'Telif oranı')} suffix="%" value={form.telif} onChange={(v) => set({ telif: v })} hint={o.telif} />
      <More label={dig ? 'Özel iskonto, matbaa ayarı' : 'Özel iskonto, matbaa ayarı, kur'}>
        <NumField label="Özel iskonto" info={i(H.ozelIskonto, 'Özel iskonto')} suffix="%" value={form.ozelIskonto} onChange={(v) => set({ ozelIskonto: v })} placeholder="Yayınevi iskontosu" />
        <NumField label="Matbaa fiyat ayarı" info={i(H.matbaaAyar, 'Matbaa fiyat ayarı')} suffix="%" value={form.matbaaAyar} onChange={(v) => set({ matbaaAyar: v })} placeholder="Ör. -15" />
        {!dig && (
          <>
            <NumField
              label="1 dolar"
              info={i(H.kur, 'Kur')}
              suffix="₺"
              value={form.kur?.USD ?? null}
              onChange={(v) => set({ kur: { ...(form.kur ?? {}), USD: v } })}
              placeholder={kf(s.tariff.kur.USD)}
              hint={kurHint('USD')}
            />
            <NumField
              label="1 euro"
              info={i(H.kur, 'Kur')}
              suffix="₺"
              value={form.kur?.EUR ?? null}
              onChange={(v) => set({ kur: { ...(form.kur ?? {}), EUR: v } })}
              placeholder={kf(s.tariff.kur.EUR)}
              hint={kurHint('EUR')}
            />
          </>
        )}
      </More>
    </Group>
  );
}

/** Kâğıt satırının elle fiyat kutusu: boşken hesaptaki fiyat ve kaynağı altında yazar. */
function PriceField({ part, onChange, r, unit }: { part: FormPart; onChange: (p: Partial<FormPart>) => void; r?: FormResult; unit: 'kg' | 'adet' }) {
  const used = r?.prices.find((p) => p.name === part.kagit && (unit === 'adet' || (p.gsm ?? null) === (part.gr ?? null)));
  const src = used ? (used.source === 'logo' ? 'Logo alışı' : used.source === 'elle' ? 'elle' : "fiyat listesi (Logo'da alış yok)") : null;
  return (
    <NumField
      label={unit === 'kg' ? 'Kâğıt fiyatı (elle)' : 'Birim fiyat (elle)'}
      info={i(H.kgFiyat, 'Kâğıt fiyatı (elle)')}
      suffix={unit === 'kg' ? '₺/kg' : '₺'}
      value={part.kgFiyat ?? null}
      onChange={(v) => onChange({ kgFiyat: v })}
      placeholder={used && used.source !== 'elle' ? used.used.toLocaleString('tr-TR', { maximumFractionDigits: 2 }) : 'Logo alışı'}
      hint={used && !part.kgFiyat ? `Hesapta ${used.used.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} ₺/${used.unit} · ${src}` : part.kgFiyat ? 'Elle girilen fiyat kullanılıyor; silince Logo alışına döner.' : undefined}
    />
  );
}

function paperOptions(s: FormSetup, unit?: 'ton' | 'adet', empty = 'Yok') {
  return [{ value: '', label: empty }, ...s.tariff.papers.filter((p) => !unit || p.unit === unit).map((p) => ({ value: p.name, label: p.name }))];
}

function SheetFields({ part, onChange, withGsm = true, withVerim = true, what }: { part: FormPart; onChange: (p: Partial<FormPart>) => void; withGsm?: boolean; withVerim?: boolean; what: string }) {
  return (
    <>
      <NumField label={`${what} tabaka eni`} info={i(H.tabaka, 'Tabaka ölçüsü')} suffix="cm" value={part.en} onChange={(v) => onChange({ en: v })} />
      <NumField label={`${what} tabaka boyu`} info={i(H.tabaka, 'Tabaka ölçüsü')} suffix="cm" value={part.boy} onChange={(v) => onChange({ boy: v })} />
      {withGsm && <NumField label={`${what} gramajı`} info={i(H.gramaj, 'Gramaj')} suffix="gr" digits={0} value={part.gr} onChange={(v) => onChange({ gr: v })} />}
      {withVerim && <NumField label="Bir tabakadan çıkan" info={i(H.verim, 'Verim')} digits={0} value={part.verim} onChange={(v) => onChange({ verim: v })} />}
      <NumField label="Fire (adet)" info={i(H.fire, 'Fire')} digits={0} value={part.fire} onChange={(v) => onChange({ fire: v })} />
    </>
  );
}

function InnerGroup({ form, s, setIn, r }: { form: FormInputs; s: FormSetup; setIn: SetIn; r?: FormResult }) {
  const o = s.origin;
  const hasColor = !!form.renkli.sayfa;
  return (
    <Group step={2} title="İç sayfalar">
      <Select<string> label="İç kâğıt" info={i(H.icKagit, 'İç kâğıt')} value={form.ic.kagit ?? ''} onChange={(v) => setIn('ic', { kagit: v || null })} options={paperOptions(s, 'ton', 'Seçin')} />
      <NumField label="Gramaj" info={i(H.gramaj, 'Gramaj')} suffix="gr" digits={0} value={form.ic.gr} onChange={(v) => setIn('ic', { gr: v })} hint={o.icGr} />
      <NumField label="Renk sayısı" info={i(H.renk, 'Renk sayısı')} digits={0} value={form.ic.renk} onChange={(v) => setIn('ic', { renk: v })} hint={o.icRenk} />
      {form.ic.kagit && <PriceField part={form.ic} onChange={(p) => setIn('ic', p)} r={r} unit="kg" />}
      <More label="Tabaka, verim ve fire">
        <SheetFields part={form.ic} onChange={(p) => setIn('ic', p)} withGsm={false} what="İç" />
      </More>
      <div className="col-span-full">
        <Toggle
          label="Kitapta ayrı basılan renkli sayfalar var"
          info={i(H.renkliSayfa, 'Renkli sayfalar')}
          checked={hasColor}
          onChange={(on) => setIn('renkli', { sayfa: on ? 16 : null })}
        />
      </div>
      {hasColor && (
        <>
          <NumField label="Renkli sayfa sayısı" info={i(H.renkliSayfa, 'Renkli sayfa sayısı')} digits={0} value={form.renkli.sayfa} onChange={(v) => setIn('renkli', { sayfa: v })} />
          <Select<string> label="Renkli sayfa kâğıdı" info={i(H.icKagit, 'Kâğıt')} value={form.renkli.kagit ?? ''} onChange={(v) => setIn('renkli', { kagit: v || null })} options={paperOptions(s, 'ton', 'Seçin')} />
          <NumField label="Renkli sayfa rengi" info={i(H.renk, 'Renk sayısı')} digits={0} value={form.renkli.renk} onChange={(v) => setIn('renkli', { renk: v })} />
          {form.renkli.kagit && <PriceField part={form.renkli} onChange={(p) => setIn('renkli', p)} r={r} unit="kg" />}
          <More label="Renkli sayfa tabakası ve fire">
            <SheetFields part={form.renkli} onChange={(p) => setIn('renkli', p)} what="Renkli sayfa" />
          </More>
        </>
      )}
    </Group>
  );
}

function CoverGroup({ form, s, setKapak, r }: { form: FormInputs; s: FormSetup; setKapak: (p: Partial<FormInputs['kapak']>) => void; r?: FormResult }) {
  const k = form.kapak;
  return (
    <Group step={3} title="Kapak">
      <Select<string> label="Kapak kartonu" info={i(H.kapakKagit, 'Kapak kartonu')} value={k.kagit ?? ''} onChange={(v) => setKapak({ kagit: v || null })} options={paperOptions(s, 'ton', 'Kapak yok')} />
      <NumField label="Gramaj" info={i(H.gramaj, 'Gramaj')} suffix="gr" digits={0} value={k.gr} onChange={(v) => setKapak({ gr: v })} />
      <NumField label="Kapak renk sayısı" info={i(H.kapakRenk, 'Kapak renk sayısı')} digits={0} value={k.renk} onChange={(v) => setKapak({ renk: v })} />
      {k.kagit && <PriceField part={k} onChange={(p) => setKapak(p)} r={r} unit="kg" />}
      <Toggle label="Selofan" info={i(H.selofan, 'Selofan')} checked={k.selofan.var} onChange={(v) => setKapak({ selofan: { ...k.selofan, var: v } })} />
      <Toggle label="Lak" info={i(H.lak, 'Lak')} checked={k.lak.var} onChange={(v) => setKapak({ lak: { ...k.lak, var: v, tur: k.lak.tur ?? 'Lokal Lak-50x70' } })} />
      <Toggle label="Yaldız" info={i(H.yaldiz, 'Yaldız')} checked={k.yaldiz} onChange={(v) => setKapak({ yaldiz: v })} />
      {k.selofan.var && (
        <Select<string> label="Kaplama türü" info={i(H.selofan, 'Kaplama türü')} value={k.selofan.tur} onChange={(v) => setKapak({ selofan: { ...k.selofan, tur: v } })} options={s.laminates.map((x) => ({ value: x, label: x === 'SELOFAN' ? 'Selofan' : 'Dispersiyon lak' }))} />
      )}
      {k.lak.var && (
        <Select<string> label="Lak türü" info={i(H.lak, 'Lak türü')} value={k.lak.tur ?? 'Lokal Lak-50x70'} onChange={(v) => setKapak({ lak: { ...k.lak, tur: v } })} options={s.varnishes.map((x) => ({ value: x, label: x.replace('-50x70', '') }))} />
      )}
      <More label="Gofre, gren, klişe, tabaka ve fire">
        <Toggle label="Gofre (kabartma)" info={i(H.yaldiz, 'Gofre')} checked={k.gofre} onChange={(v) => setKapak({ gofre: v })} />
        <Toggle label="İki yüz selofan" info={i(H.ciftYuz, 'İki yüz selofan')} checked={!!k.selofan.ciftYuz} onChange={(v) => setKapak({ selofan: { ...k.selofan, ciftYuz: v } })} />
        <NumField label="Gren uygulama sayısı" info={i(H.gren, 'Gren')} digits={0} value={k.gren} onChange={(v) => setKapak({ gren: v ?? 0 })} />
        <NumField label="Klişe adedi" info={i(H.klise, 'Klişe')} digits={0} value={k.klise.adet} onChange={(v) => setKapak({ klise: { ...k.klise, adet: v } })} />
        <Select<string> label="Klişe ebadı" info={i(H.klise, 'Klişe ebadı')} value={k.klise.ebat ?? '35x50'} onChange={(v) => setKapak({ klise: { ...k.klise, ebat: v } })}
          options={Object.entries(s.tariff.cliche).map(([e, c]) => ({ value: e, label: `${e} · ${tl0(c.price)}` }))} />
        <NumField label="Bir tabakadan çıkan kapak" info={i(H.kapakVerim, 'Kapak verimi')} digits={0} value={k.verim} onChange={(v) => setKapak({ verim: v })} />
        <SheetFields part={k} onChange={(p) => setKapak(p)} withGsm={false} withVerim={false} what="Kapak" />
      </More>
    </Group>
  );
}

function BindingGroup({ form, s, setIn }: { form: FormInputs; s: FormSetup; setIn: SetIn }) {
  return (
    <Group step={4} title="Cilt">
      <Select<string> label="Cilt şekli" info={i(H.cilt, 'Cilt şekli')} value={form.cilt.tur} onChange={(v) => setIn('cilt', { tur: v })} options={s.bindings.map((b) => ({ value: b, label: b.charAt(0) + b.slice(1).toLocaleLowerCase('tr-TR') }))} hint={s.origin.cilt} />
      <NumField label="Cilt birim fiyatı (elle)" info={i(H.ciltBirim, 'Cilt birim fiyatı')} suffix="₺" value={form.cilt.birim} onChange={(v) => setIn('cilt', { birim: v })} placeholder="Fiyat listesinden hesaplanır" />
    </Group>
  );
}

function ExtrasGroup({ form, s, setEk, setPart, r }: { form: FormInputs; s: FormSetup; setEk: (p: Partial<FormInputs['ekler']>) => void; setPart: (k: ExtraKey, p: Partial<FormPart>) => void; r?: FormResult }) {
  const keys = Object.keys(s.extras) as ExtraKey[];
  const on = keys.filter((k) => form.ekler[k]?.kagit);
  return (
    <Group step={5} title="Ek parçalar ve işlemler" info={i(H.ekParca, 'Ek parçalar')}>
      {keys.map((k) => {
        const e = s.extras[k];
        const p = form.ekler[k];
        const active = !!p?.kagit;
        return (
          <div key={k} className={`min-w-0 ${active ? 'col-span-full' : ''}`}>
            <Toggle
              label={e.label}
              info={i(H.ekParca, e.label)}
              checked={active}
              onChange={(v) => setPart(k, { kagit: v ? (s.tariff.papers.find((x) => (e.kind === 'tabaka' ? x.unit === 'adet' && (k !== 'mukavva' || /MUKAVVA/i.test(x.name)) && (k !== 'ciltBezi' || /CİLT BEZİ/i.test(x.name)) : x.unit === 'ton')) ?? s.tariff.papers[0]).name : null })}
            />
            {active && (
              <div className="mt-2 grid grid-cols-1 gap-3 rounded-2xl bg-slate-50/70 p-3 sm:grid-cols-2 xl:grid-cols-3">
                <Select<string> label="Malzeme" info={i(H.ekParca, 'Malzeme')} value={p.kagit ?? ''} onChange={(v) => setPart(k, { kagit: v || null })} options={paperOptions(s, e.kind === 'tabaka' ? 'adet' : 'ton')} />
                {(k === 'yanKagit' || k === 'somiz' || k === 'ayrac') && (
                  <NumField label="Baskı renk sayısı" info={i(H.renk, 'Renk sayısı')} digits={0} value={p.renk} onChange={(v) => setPart(k, { renk: v })} placeholder="Baskısız" />
                )}
                {(k === 'somiz' || k === 'ayrac') && (
                  <Toggle label={k === 'somiz' ? 'Şömiz işçiliği' : 'Ayraç / afiş işçiliği'} info={i(H.ekParca, 'İşçilik')} checked={!!p.iscilik} onChange={(v) => setPart(k, { iscilik: v })} />
                )}
                <PriceField part={p} onChange={(x) => setPart(k, x)} r={r} unit={e.kind === 'kg' ? 'kg' : 'adet'} />
                <SheetFields part={p} onChange={(x) => setPart(k, x)} withGsm={e.kind === 'kg'} what={e.label.split(' ')[0]} />
              </div>
            )}
          </div>
        );
      })}
      <NumField label="Kenar boyama birim fiyatı" info={i(H.kenarBoyama, 'Kenar boyama')} suffix="₺" value={form.ekler.kenarBoyama} onChange={(v) => setEk({ kenarBoyama: v })} placeholder="Yok" />
      <Toggle label="Tekli vakumlu paket" info={i(H.vakum, 'Tekli vakumlu paket')} checked={form.ekler.vakum} onChange={(v) => setEk({ vakum: v })} />
      {on.length === 0 && <p className="col-span-full text-[11.5px] text-canvas-muted">Çoğu kitapta ek parça yoktur; sert kapak, şömiz ya da ayraç varsa işaretleyin.</p>}
    </Group>
  );
}

function OtherGroup({ form, setIn, set }: { form: FormInputs; setIn: SetIn; set: (p: Partial<FormInputs>) => void }) {
  const d = form.diger;
  return (
    <Group step={6} title="Diğer giderler ve genel gider">
      <NumField label="Kapak / çizim ücreti (toplam)" info={i(H.kapakUcreti, 'Kapak / çizim ücreti')} suffix="₺" digits={0} value={d.kapakUcreti} onChange={(v) => setIn('diger', { kapakUcreti: v })} />
      <NumField label="Kaç baskıya bölünsün" info={i(H.kapakBolen, 'Kaç baskıya bölünsün')} digits={0} value={d.kapakBolen} onChange={(v) => setIn('diger', { kapakBolen: v })} />
      <NumField label="Dolaylı gider" info={i(H.dolayli, 'Dolaylı gider')} suffix="%" value={form.dolayli} onChange={(v) => set({ dolayli: v })} />
      <More label="Nakliye, mizanpaj, diğer">
        <TextField label="Kapak ücretinin adı" info={i(H.kapakUcreti, 'Kapak ücretinin adı')} value={d.kapakEtiket} onChange={(v) => setIn('diger', { kapakEtiket: v || null })} placeholder="Kapak, çizim, mizanpaj…" />
        <NumField label="Nakliye" info={i(H.nakliye, 'Nakliye')} suffix="₺" digits={0} value={d.nakliye} onChange={(v) => setIn('diger', { nakliye: v })} />
        <NumField label="İç mizanpaj" info={i(H.nakliye, 'İç mizanpaj')} suffix="₺" digits={0} value={d.mizanpaj} onChange={(v) => setIn('diger', { mizanpaj: v })} />
        <NumField label="Diğer gider" info={i(H.nakliye, 'Diğer gider')} suffix="₺" digits={0} value={d.diger} onChange={(v) => setIn('diger', { diger: v })} />
      </More>
    </Group>
  );
}

// ------------------------------------------------------------------ sonuç

export function ResultCard({ r, loading, err }: { r: FormResult | undefined; loading: boolean; err: unknown }) {
  const sm = r?.summary;
  const loss = sm && sm.karAdet < 0;
  return (
    <section className="glass-panel flex flex-col gap-3 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4" aria-live="polite">
      <div className="flex items-center gap-1 text-[12px] font-extrabold uppercase tracking-wide text-canvas-ink">
        Maliyet {i(R.birimMaliyet, 'Maliyet')}
      </div>
      {Boolean(err) && <Note tone="err">{errText(err, 'Hesaplanamadı.')}</Note>}
      {!sm ? (
        !err && <p className="text-[12.5px] text-canvas-muted">Sayfa sayısı ve baskı adedi girilince maliyet burada görünür.</p>
      ) : (
        <div className={`flex flex-col gap-3 transition-opacity duration-150 ${loading ? 'opacity-60' : ''}`}>
          <div className="rounded-2xl bg-white/80 p-3">
            <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Birim maliyet {i(R.birimMaliyet, 'Birim maliyet')}</div>
            <div className="mt-1 font-mono text-[30px] font-bold leading-none tabular-nums">{tl2(sm.birimMaliyet)}</div>
            <div className="mt-1 text-[11.5px] text-canvas-muted">{num(sm.adet)} adet · genel toplam {tl0(sm.genelToplam)}</div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Mini label="Satış fiyatı" help={R.satisFiyati} value={tl2(sm.satisFiyati)} note={`%${num(sm.iskonto)} iskonto`} />
            <Mini label="Kâr / adet" help={R.karAdet} value={tl2(sm.karAdet)} tone={loss ? 'err' : 'ok'} />
            <Mini label="Kâr %" help={R.karYuzde} value={pct(sm.karYuzde)} tone={loss ? 'err' : 'ok'} note="maliyete göre" />
          </div>
          <Breakdown sm={sm} />
          {r.warnings.length > 0 && (
            <ul className="space-y-1 text-[11.5px] leading-snug text-amber-800">
              {r.warnings.map((w) => (
                <li key={w} className="rounded-lg bg-amber-50 px-2.5 py-1.5">{w}</li>
              ))}
            </ul>
          )}
          <a href="#kalemler" className="inline-flex items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline">
            <Layers aria-hidden className="h-4 w-4" /> Kalem kalem döküm
          </a>
        </div>
      )}
    </section>
  );
}

function Mini({ label, value, note, tone, help }: { label: string; value: string; note?: string; tone?: 'ok' | 'err'; help: FieldHelp }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 p-2">
      <div className="flex items-center gap-0.5 text-[10.5px] font-bold uppercase leading-tight tracking-wide text-canvas-muted">
        <span className="truncate">{label}</span>
        {i(help, label)}
      </div>
      <div className={`mt-1 truncate font-mono text-[15px] font-bold tabular-nums ${tone === 'err' ? 'text-red-600' : tone === 'ok' ? 'text-emerald-700' : ''}`}>{value}</div>
      {note && <div className="truncate text-[10.5px] text-canvas-muted">{note}</div>}
    </div>
  );
}

function Breakdown({ sm }: { sm: FormResult['summary'] }) {
  const other = sm.birimMaliyet - sm.kagitAdet - sm.matbaaAdet - sm.telifAdet - sm.dolayli / sm.adet;
  const dig = sm.baski === 'dijital';
  const parts = [
    ...(dig ? [] : [{ label: 'Kâğıt', v: sm.kagitAdet, c: 'bg-sky-500' }]),
    { label: dig ? 'Baskı, kapak ve cilt (kâğıt dahil)' : 'Matbaa', v: sm.matbaaAdet, c: 'bg-violet-500' },
    { label: 'Telif', v: sm.telifAdet, c: 'bg-amber-500' },
    { label: dig ? 'Diğer giderler' : 'Kapak ücreti ve diğer', v: Math.max(0, other), c: 'bg-slate-400' },
    { label: `Dolaylı gider %${num(sm.dolayliOran)}`, v: sm.dolayli / sm.adet, c: 'bg-rose-400' },
  ];
  const total = parts.reduce((a, p) => a + Math.max(0, p.v), 0) || 1;
  return (
    <div>
      <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
        Birim maliyetin kırılımı {i(R.kitapMaliyeti, 'Kırılım')}
      </div>
      <div className="mt-1.5 flex h-2.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        {parts.map((p) => (
          <span key={p.label} className={p.c} style={{ width: `${(Math.max(0, p.v) / total) * 100}%` }} />
        ))}
      </div>
      <dl className="mt-2 space-y-1 text-[12px]">
        {parts.map((p) => (
          <div key={p.label} className="flex items-center justify-between gap-2">
            <dt className="flex min-w-0 items-center gap-1.5">
              <span className={`h-2 w-2 shrink-0 rounded-full ${p.c}`} aria-hidden />
              <span className="truncate">{p.label}</span>
            </dt>
            <dd className="font-mono tabular-nums">{tl2(p.v)}</dd>
          </div>
        ))}
        <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-1 font-bold">
          <dt>İşletme gideri hariç (kâğıt + matbaa + telif)</dt>
          <dd className="font-mono tabular-nums">{tl2(sm.kitapMaliyeti)}</dd>
        </div>
      </dl>
    </div>
  );
}

export function Lines({ r }: { r: FormResult }) {
  const dig = r.baski === 'dijital';
  // Toplam satırlarının Excel hücreleri iki şablonda farklı (ofset J40–J46, dijital J32–J38).
  const cell = dig ? { toplam: 'J32', dolayli: 'J33', genel: 'J34 · J38' } : { toplam: 'J40', dolayli: 'J41', genel: 'J42 · J46' };
  const groups: Array<[FormResult['lines'][number]['group'], string]> = [['kagit', 'Kâğıt'], ['matbaa', 'Matbaa ve işçilik'], ['telif', 'Telif'], ['diger', 'Diğer giderler']];
  const sm = r.summary;
  return (
    <section id="kalemler" className="space-y-2 scroll-mt-4">
      <h3 className="flex items-center gap-1 px-1 text-[14px] font-extrabold">
        Kalem kalem döküm {i(R.kalemler, 'Kalem kalem döküm')}
        <SqlInfo k={r.kaynaklar} alan="summary" label="Maliyet formu hesabı" />
      </h3>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Kalem</th>
            <th className={`${th} text-right`}>Miktar</th>
            <th className={`${th} text-right`}>Birim fiyat</th>
            <th className={`${th} text-right`}>Toplam</th>
            <th className={`${th} text-right`}>Adet başı</th>
            <th className={th}>Excel</th>
          </tr>
        </thead>
        <tbody>
          {groups.map(([g, title]) => {
            const rows = r.lines.filter((l) => l.group === g);
            if (!rows.length) return null;
            const sum = rows.reduce((a, l) => a + l.total, 0);
            return [
              <tr key={`${g}-h`} className="border-t border-slate-200 bg-slate-50/80">
                <td className={`${td} font-extrabold`} colSpan={3}>{title}</td>
                <td className={`${td} text-right font-extrabold tabular-nums`}>{tl0(sum)}</td>
                <td className={`${td} text-right font-extrabold tabular-nums`}>{tl2(sum / sm.adet)}</td>
                <td className={td} />
              </tr>,
              ...rows.map((l) => (
                <tr key={l.key} className="border-t border-slate-100">
                  <td className={td}>
                    <span className="inline-flex items-center gap-1 font-bold">
                      {l.name}
                      {i({ ne: l.formula ?? 'Fiyat listesindeki bedel.', nereden: lineSource(l, dig), excel: `${l.excel} hücresi.` }, l.name)}
                    </span>
                    {l.material && <div className="text-[11px] text-canvas-muted">{l.material}</div>}
                  </td>
                  <td className={`${td} text-right tabular-nums`}>
                    {l.kg != null ? `${num(l.kg)} kg` : l.sheets != null ? `${num(l.sheets)} tabaka` : l.plates != null ? `${num(l.plates)} kalıp` : '—'}
                  </td>
                  <td className={`${td} text-right tabular-nums`}>
                    {l.unitPrice != null ? `${l.unitPrice.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} ${l.unit ?? '₺'}` : '—'}
                    {l.priceSource && (
                      <div className="text-[10.5px] text-canvas-muted">
                        {l.priceSource === 'logo' ? 'Logo alışı' : l.priceSource === 'elle' ? 'Elle girildi' : dig ? 'Dijital fiyat tablosu' : 'Fiyat listesi (Logo\'da alış yok)'}
                      </div>
                    )}
                  </td>
                  <td className={`${td} text-right tabular-nums`}>{tl0(l.total)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl2(l.perCopy)}</td>
                  <td className={`${td} font-mono text-[11px] text-canvas-muted`}>{l.excel}</td>
                </tr>
              )),
            ];
          })}
          <tr className="border-t-2 border-slate-200">
            <td className={`${td} font-extrabold`} colSpan={3}>Toplam (matbaa + diğer giderler)</td>
            <td className={`${td} text-right font-extrabold tabular-nums`}>{tl0(sm.toplam)}</td>
            <td className={`${td} text-right font-extrabold tabular-nums`}>{tl2(sm.toplam / sm.adet)}</td>
            <td className={`${td} font-mono text-[11px] text-canvas-muted`}>{cell.toplam}</td>
          </tr>
          <tr className="border-t border-slate-100">
            <td className={td} colSpan={3}>Dolaylı gider %{num(sm.dolayliOran)}</td>
            <td className={`${td} text-right tabular-nums`}>{tl0(sm.dolayli)}</td>
            <td className={`${td} text-right tabular-nums`}>{tl2(sm.dolayli / sm.adet)}</td>
            <td className={`${td} font-mono text-[11px] text-canvas-muted`}>{cell.dolayli}</td>
          </tr>
          <tr className="border-t border-slate-100 bg-violet-50/60">
            <td className={`${td} font-extrabold`} colSpan={3}>
              <span className="inline-flex items-center gap-1">Genel toplam {i(R.genelToplam, 'Genel toplam')}</span>
            </td>
            <td className={`${td} text-right font-extrabold tabular-nums`}>{tl0(sm.genelToplam)}</td>
            <td className={`${td} text-right font-extrabold tabular-nums`}>{tl2(sm.birimMaliyet)}</td>
            <td className={`${td} font-mono text-[11px] text-canvas-muted`}>{cell.genel}</td>
          </tr>
        </tbody>
      </TableWrap>
      {r.prices.length > 0 && <Prices r={r} />}
    </section>
  );
}

function lineSource(l: FormResult['lines'][number], dig = false): string {
  if (dig) {
    if (l.priceSource === 'elle') return 'Bu kitap için elle girilen birim fiyat (tablodaki fiyatın yerine).';
    if (l.priceSource === 'tarife') return 'Birim fiyat dijital baskı fiyat tablosundan (ebat × kâğıt; Veri ve varsayımlar → Dijital baskı fiyatları).';
    return 'Dijital baskı fiyat listesinden ya da elle girilen tutar.';
  }
  if (l.priceSource === 'logo') return 'Kâğıt fiyatı Logo\'daki son 6 ayın alış faturalarından (aynı cins ve gramaj, kg ağırlıklı ortalama).';
  if (l.priceSource === 'elle') return 'Bu kitap için elle girilen kâğıt fiyatı (Logo alışının yerine).';
  if (l.priceSource === 'tarife') return 'Bu kâğıdın Logo\'da son 6 ayda alışı yok; fiyat listesindeki ton fiyatı × vade farkı × kur kullanıldı.';
  return 'Birim fiyatlar matbaa ve malzeme fiyat listesinden (Veri ve varsayımlar → Matbaa ve malzeme fiyat listesi).';
}

function Prices({ r }: { r: FormResult }) {
  return (
    <div className="space-y-1.5 pt-2">
      <h4 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
        Kullanılan kâğıt fiyatları
        <SqlInfo k={r.kaynaklar} alan="prices[]" label="Kâğıt fiyatları" help={H.kagitFiyati} />
      </h4>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Kâğıt</th>
            <th className={th}>Kaynak</th>
            <th className={`${th} text-right`}>Hesapta</th>
          </tr>
        </thead>
        <tbody>
          {r.prices.map((p) => (
            <tr key={`${p.name}-${p.gsm}`} className="border-t border-slate-100">
              <td className={td}>
                <div className="font-bold">{p.name}{p.gsm ? ` · ${num(p.gsm)} gr` : ''}</div>
              </td>
              <td className={`${td} text-[12px]`}>
                {p.source === 'elle'
                  ? 'Elle girildi (bu kitap için)'
                  : p.source === 'logo' && p.logo
                  ? `Logo alışı · ${p.logo.cards} kâğıt kartı${p.logo.sameGsm ? ', aynı gramaj' : ', aynı cins (gramaj yok)'} · son alış ${day(p.logo.last)}`
                  : p.unit === 'kg' ? `Fiyat listesi (Logo'da alış yok): ${p.tarifeText}` : `Fiyat listesi: ${p.tarifeText}`}
              </td>
              <td className={`${td} text-right font-bold tabular-nums`}>{p.used.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} ₺/{p.unit}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      <p className="px-1 text-[11px] text-canvas-muted">Kur: 1 $ = {r.kur.USD.toLocaleString('tr-TR')} ₺, 1 € = {r.kur.EUR.toLocaleString('tr-TR')} ₺ · Logo verisi {day(r.dataEnd)} tarihine kadar.</p>
    </div>
  );
}

/** Telefonda formu doldururken sonucun özeti ekranın altında kalır. */
export function MobileBar({ r }: { r: FormResult }) {
  const sm = r.summary;
  return (
    <a
      href="#kalemler"
      className="sticky bottom-2 z-20 flex items-center justify-between gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-white shadow-2xl lg:hidden"
    >
      <span className="text-[11px] font-bold uppercase tracking-wide text-slate-300">Birim maliyet</span>
      <span className="font-mono text-[17px] font-bold tabular-nums">{tl2(sm.birimMaliyet)}</span>
      <span className={`font-mono text-[13px] font-bold tabular-nums ${sm.karAdet < 0 ? 'text-red-300' : 'text-emerald-300'}`}>{pct(sm.karYuzde)}</span>
    </a>
  );
}
