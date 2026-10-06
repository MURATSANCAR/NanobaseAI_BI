import { day, num, type DigitalInputs, type DigitalTariff, type FormInputs, type FormResult, type FormSetup } from './api';
import { i, type Setters } from './CostForm';
import { Group, NumField, Select, Toggle } from './parts';
import { FORM_HELP as H } from './help';

/**
 * Dijital baskı adımları (TİMAŞ «TBK dijital» Excel'i; köprü `pricing/form_dijital.py`). Ofsetteki iç kâğıt, kapak,
 * cilt ve ek parça adımlarının yerine gelir: iç baskı sayfa başına (kâğıt dahil), kapak baskı + selofan + cilt adet
 * başına tek fiyat; ek işlemler isteğe bağlı.
 */

const BLANK: DigitalInputs = {
  icKagit: '1/1- 60gr KİTAP KAĞIDI', renkliSayfa: null, renkliKagit: '4/4- 115gr KUŞE-KALİTELİ', kapakKagit: 'BRİSTOL', kapakGr: 230,
  pay: 25, ekler: { ayracAtma: false, ayracRenk: null, gofre: false, kulakli: false, kapakRenk: null, selofan: false, lokalLak: false },
};

export function digitalOf(form: FormInputs, t?: DigitalTariff): DigitalInputs {
  return { ...BLANK, pay: t?.pay ?? BLANK.pay, ...(form.dijital ?? {}) };
}

/** Tablodaki birim fiyat (matbaa fiyat ayarı uygulanmış); yoksa null. Yalnız kutunun altındaki ipucu için. */
function tablePrice(t: DigitalTariff | undefined, ebat: string | null | undefined, kagit: string | null, ayar: number | null | undefined) {
  const norm = (x: string | null | undefined) => (x ?? '').trim().toLocaleUpperCase('tr-TR').replace(/\s/g, '');
  const row = t?.tablo.find((r) => norm(r.ebat) === norm(ebat));
  const v = row && kagit ? Object.entries(row.fiyat).find(([k]) => norm(k) === norm(kagit))?.[1] : undefined;
  return v ? v * (1 + (ayar ?? 0) / 100) : null;
}

const fmt = (v: number) => v.toLocaleString('tr-TR', { maximumFractionDigits: 4 });

export function DigitalGroups({ form, s, st, r }: { form: FormInputs; s: FormSetup; st: Setters; r?: FormResult }) {
  const t = s.tariff.dijital;
  const d = digitalOf(form, t);
  const setD = (p: Partial<DigitalInputs>) => st.set({ dijital: { ...d, ...p } });
  const setE = (p: Partial<DigitalInputs['ekler']>) => setD({ ekler: { ...d.ekler, ...p } });
  const opts = (xs: string[] | undefined) => (xs ?? []).map((x) => ({ value: x, label: x }));
  const hint = (kagit: string | null, manual: number | null | undefined, unit: string) => {
    if (manual) return 'Elle girilen fiyat kullanılıyor; silince tablodaki fiyata döner.';
    const p = tablePrice(t, form.ebat, kagit, form.matbaaAyar);
    return p ? `Tabloda ${fmt(p)} ₺/${unit}` : `«${form.ebat ?? '—'}» ebatında tabloda fiyat yok: elle girin.`;
  };
  const used = (key: string) => r?.lines.find((l) => l.key === key);
  const kapakTabaka = r?.summary.kapakTabaka;
  const dg = form.diger;
  return (
    <>
      <Group step={2} title="İç baskı (dijital)" help={t?.guncelleme ? <>Sayfa fiyatları kâğıt dahil; tablo {day(t.guncelleme)} tarihli.</> : undefined}>
        <Select<string> label="Kâğıt ve renk" info={i(H.dijitalKagit, 'Kâğıt ve renk')} value={d.icKagit ?? ''} onChange={(v) => setD({ icKagit: v || null })} options={opts(t?.kagitlar)} />
        <NumField
          label="Sayfa fiyatı (elle)"
          info={i(H.dijitalBirim, 'Sayfa fiyatı (elle)')}
          suffix="₺/sayfa"
          value={d.icBirim ?? null}
          onChange={(v) => setD({ icBirim: v })}
          placeholder={used('icBaski')?.priceSource === 'tarife' ? fmt(used('icBaski')!.unitPrice ?? 0) : 'Tablodan'}
          hint={hint(d.icKagit, d.icBirim, 'sayfa')}
        />
        <NumField label="Matbaa ek payı" info={i(H.dijitalPay, 'Matbaa ek payı')} suffix="%" value={d.pay} onChange={(v) => setD({ pay: v })} placeholder={num(t?.pay ?? 25)} />
        <div className="col-span-full">
          <Toggle label="Renkli basılan sayfalar var" info={i(H.dijitalKagit, 'Renkli sayfalar')} checked={!!d.renkliSayfa} onChange={(on) => setD({ renkliSayfa: on ? 16 : null })} />
        </div>
        {!!d.renkliSayfa && (
          <>
            <NumField label="Renkli sayfa sayısı" info={i(H.renkliSayfa, 'Renkli sayfa sayısı')} digits={0} value={d.renkliSayfa} onChange={(v) => setD({ renkliSayfa: v })} />
            <Select<string> label="Renkli sayfa kâğıdı" info={i(H.dijitalKagit, 'Renkli sayfa kâğıdı')} value={d.renkliKagit ?? ''} onChange={(v) => setD({ renkliKagit: v || null })} options={opts(t?.kagitlar)} />
            <NumField label="Renkli sayfa fiyatı (elle)" info={i(H.dijitalBirim, 'Renkli sayfa fiyatı')} suffix="₺/sayfa" value={d.renkliBirim ?? null} onChange={(v) => setD({ renkliBirim: v })} hint={hint(d.renkliKagit, d.renkliBirim, 'sayfa')} />
          </>
        )}
      </Group>

      <Group step={3} title="Kapak baskı, selofan ve cilt">
        <Select<string> label="Kapak kartonu" info={i(H.dijitalKapak, 'Kapak kartonu')} value={d.kapakKagit ?? 'BRİSTOL'} onChange={(v) => setD({ kapakKagit: v })} options={opts(t?.kapakKagitlari)} />
        <Select<string>
          label="Kapak gramajı"
          info={i(H.dijitalKapak, 'Kapak gramajı')}
          value={d.kapakGr == null ? '' : String(d.kapakGr)}
          onChange={(v) => setD({ kapakGr: v ? Number(v) : null })}
          options={[{ value: '', label: 'Seçilmedi' }, ...(t?.kapakGramajlari ?? []).map((g) => ({ value: String(g), label: `${g} gr` }))]}
        />
        <NumField label="Kapak fiyatı (elle)" info={i(H.dijitalBirim, 'Kapak fiyatı (elle)')} suffix="₺/adet" value={d.kapakBirim ?? null} onChange={(v) => setD({ kapakBirim: v })} hint={hint(d.kapakKagit, d.kapakBirim, 'adet')} />
      </Group>

      <Group step={4} title="Ek işlemler" help={kapakTabaka ? <>Kapak tabakası {num(kapakTabaka)} (eşikler bu sayıdan).</> : undefined}>
        <Toggle label="Ayracı kitabın içine atma" info={i(H.dijitalEk, 'Ek işlemler')} checked={d.ekler.ayracAtma} onChange={(v) => setE({ ayracAtma: v })} />
        <NumField label="Ayraç baskı (renk)" info={i(H.dijitalEk, 'Ayraç baskı')} digits={0} value={d.ekler.ayracRenk} onChange={(v) => setE({ ayracRenk: v })} placeholder="Yok" />
        <NumField label="Ek kapak baskısı (renk)" info={i(H.dijitalEk, 'Kapak baskısı')} digits={0} value={d.ekler.kapakRenk} onChange={(v) => setE({ kapakRenk: v })} placeholder="Yok" />
        <Toggle label="Gofre" info={i(H.dijitalEk, 'Gofre')} checked={d.ekler.gofre} onChange={(v) => setE({ gofre: v })} />
        <Toggle label="Kulaklı kapak" info={i(H.dijitalEk, 'Kulaklı kapak')} checked={d.ekler.kulakli} onChange={(v) => setE({ kulakli: v })} />
        <Toggle label="Ek selofan" info={i(H.dijitalEk, 'Selofan')} checked={d.ekler.selofan} onChange={(v) => setE({ selofan: v })} />
        <Toggle label="Lokal lak" info={i(H.dijitalEk, 'Lokal lak')} checked={d.ekler.lokalLak} onChange={(v) => setE({ lokalLak: v })} />
      </Group>

      <Group step={5} title="Diğer giderler ve genel gider">
        <NumField label="Dolaylı gider" info={i(H.dolayli, 'Dolaylı gider')} suffix="%" value={form.dolayli} onChange={(v) => st.set({ dolayli: v })} />
        <NumField label="Nakliye (adet başına)" info={i(H.dijitalDiger, 'Nakliye')} suffix="₺" value={dg.nakliyeAdet ?? null} onChange={(v) => st.setIn('diger', { nakliyeAdet: v })} />
        <NumField label="Yan kâğıdı" info={i(H.dijitalDiger, 'Yan kâğıdı')} suffix="₺" digits={0} value={dg.yanKagit ?? null} onChange={(v) => st.setIn('diger', { yanKagit: v })} />
        <NumField label="Hediye" info={i(H.dijitalDiger, 'Hediye')} suffix="₺" digits={0} value={dg.hediye ?? null} onChange={(v) => st.setIn('diger', { hediye: v })} />
        <NumField label="Zayiat" info={i(H.dijitalDiger, 'Zayiat')} suffix="₺" digits={0} value={dg.zayiat ?? null} onChange={(v) => st.setIn('diger', { zayiat: v })} />
        <NumField label="Reklam" info={i(H.dijitalDiger, 'Reklam')} suffix="₺" digits={0} value={dg.reklam ?? null} onChange={(v) => st.setIn('diger', { reklam: v })} />
        <NumField label="Diğer gider" info={i(H.dijitalDiger, 'Diğer gider')} suffix="₺" digits={0} value={dg.diger} onChange={(v) => st.setIn('diger', { diger: v })} />
      </Group>
    </>
  );
}
