import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, FileSpreadsheet, Loader2, ScanSearch, Search, X } from 'lucide-react';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import {
  MATCH_TONE, fmtInt, fmtMoney, fmtPct, parseNum, tendersApi,
  type Candidate, type Item, type MatchState, type TenderDetail, type TenderMeta,
} from './api';

/** Şartname kalemleri: liste alma (yapıştır ya da yüklenen dosya), katalogla eşleştirme (ISBN → ad → Zeki AI), insan
 *  onayı ve düzeltmesi, adet ve birim teklif fiyatı, teklif tablosu toplamları ve Excel. Geniş tablo kendi içinde kayar. */

export default function TenderItems({ d, meta, busy }: { d: TenderDetail; meta: TenderMeta; busy: boolean }) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<MatchState | 'hepsi' | 'stok'>('hepsi');
  const [picking, setPicking] = useState<Item | null>(null);
  const can = meta.me.canEdit && ['yeni', 'inceleniyor'].includes(d.durum) && !d.kararlar.some((k) => k.durum === 'onayda');
  const invalidate = () => qc.invalidateQueries({ queryKey: ['tenders'] });
  const t = d.toplamlar;

  const match = useMutation({
    mutationFn: (onlyPending: boolean) => tendersApi.match(d.id, { onlyPending }),
    onSuccess: () => { invalidate(); toast.success('Eşleştirme başladı.'); },
    onError: (e) => toast.error(errText(e, 'Başlatılamadı.') ?? ''),
  });
  const patch = useMutation({
    mutationFn: ({ sira, b }: { sira: number; b: Parameters<typeof tendersApi.updateItem>[2] }) => tendersApi.updateItem(d.id, sira, b),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  const rows = useMemo(
    () => d.kalemler.filter((k) => (filter === 'hepsi' ? true : filter === 'stok' ? k.stokYetersiz : k.durum === filter)),
    [d.kalemler, filter],
  );
  const chips: Array<{ key: typeof filter; label: string; n: number }> = [
    { key: 'hepsi', label: 'Hepsi', n: t.kalem },
    { key: 'eslesti', label: 'Eşleşti', n: t.durumlar.eslesti ?? 0 },
    { key: 'oneri', label: 'Onay bekliyor', n: t.durumlar.oneri ?? 0 },
    { key: 'belirsiz', label: 'Emin değil', n: t.durumlar.belirsiz ?? 0 },
    { key: 'yok', label: 'Katalogda yok', n: t.durumlar.yok ?? 0 },
    { key: 'bekliyor', label: 'Eşleştirilmedi', n: t.durumlar.bekliyor ?? 0 },
    { key: 'stok', label: 'Stok yetersiz', n: t.stokYetersiz },
  ];

  return (
    <>
      {can && <ImportPanel d={d} busy={busy} />}
      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[16px] font-extrabold tracking-tight">Kalem–katalog eşleştirme</h2>
            <p className="max-w-[90ch] text-[12px] text-canvas-muted">
              Sıra: ISBN/barkod birebir → ad birebir (yazarla ayıklanır) → benzer adlı {d.ayarlar.candidates} adaya Zeki AI «aynı eser hangisi» sorusu.
              Olasılık %{Math.round(d.ayarlar.autoProb * 100)} ve üstü (marj %{Math.round(d.ayarlar.autoMargin * 100)}) kendiliğinden eşleşir,
              %{Math.round(d.ayarlar.suggestProb * 100)} ve üstü onayınızı bekler, altı «emin değil». Stok ve fiyat Logo/CRM'den okunur.
            </p>
          </div>
          {can && d.kalemler.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnPrimary} disabled={busy || match.isPending} onClick={() => match.mutate(false)}>
                {match.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <ScanSearch aria-hidden className="h-4 w-4" />}
                Katalogla eşleştir
              </button>
              {(t.durumlar.bekliyor || t.durumlar.belirsiz) ? (
                <button type="button" className={btnGhost} disabled={busy || match.isPending} onClick={() => match.mutate(true)}>Yalnız bekleyenler</button>
              ) : null}
            </div>
          )}
        </div>
        {!meta.modelVar && <div className="mt-2"><Note tone="warn">Zeki AI bu kurulumda tanımlı değil: ISBN ve ad birebir eşleşmeyen kalemler aday listesinden elle seçilir.</Note></div>}
        {d.kararlar.some((k) => k.durum === 'onayda') && <div className="mt-2"><Note tone="info">Onay bekleyen karar var; kalemler karar sonuçlanana ya da geri çekilene kadar değişmez.</Note></div>}
        <div className="mt-3 -mx-1 overflow-x-auto px-1">
          <div className="flex w-max gap-1.5">
            {chips.map((c) => (
              <button
                key={c.key}
                type="button"
                aria-pressed={filter === c.key}
                onClick={() => setFilter(c.key)}
                className={`inline-flex min-h-9 items-center gap-1.5 rounded-xl px-3 text-[12px] font-bold transition-colors duration-150 ${filter === c.key ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}
              >
                {c.label}
                <span className="font-mono tabular-nums">{c.n}</span>
              </button>
            ))}
          </div>
        </div>
      </Panel>

      {d.kalemler.length === 0 ? (
        <Panel><div className="py-6 text-center text-[12.5px] text-canvas-muted">Kalem listesi yok. Şartnamedeki kitap listesini yapıştırın ya da yüklenen dosyadan alın.</div></Panel>
      ) : (
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>#</th>
              <th className={th}>Şartname kalemi</th>
              <th className={th}>Eşleşen kitap</th>
              <th className={`${th} text-right`}>Adet</th>
              <th className={`${th} text-right`}>Stok</th>
              <th className={`${th} text-right`}>Liste (KDV dahil)</th>
              <th className={`${th} text-right`}>Birim teklif (KDV hariç)</th>
              <th className={`${th} text-right`}>Tutar</th>
              <th className={th}>İşlem</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((k) => (
              <tr key={k.sira} className="border-b border-slate-50 align-top last:border-0">
                <td className={`${td} font-mono tabular-nums text-canvas-muted`}>{k.sira}</td>
                <td className={`${td} min-w-[220px] max-w-[340px]`}>
                  <div className="break-words font-semibold">{k.ad ?? k.metin}</div>
                  <div className="break-words text-[11px] text-canvas-muted">{[k.yazar, k.yayinevi, k.isbn && `ISBN ${k.isbn}`].filter(Boolean).join(' · ')}</div>
                </td>
                <td className={`${td} min-w-[220px] max-w-[320px]`}>
                  <div className="flex flex-wrap items-center gap-1">
                    <Pill tone={MATCH_TONE[k.durum]}>{k.durumAdi}</Pill>
                    {k.yontemAdi && <span className="text-[10.5px] font-bold text-canvas-muted">{k.yontemAdi}{k.olasilik != null && k.yontem === 'zeki' ? ` · ${fmtPct(k.olasilik)}` : ''}</span>}
                  </div>
                  {k.eslesenAd && <div className="mt-0.5 break-words font-semibold">{k.eslesenAd}</div>}
                  {k.stokKodu && <div className="font-mono text-[10.5px] text-canvas-muted">{k.stokKodu}</div>}
                  {k.not && <div className="mt-0.5 text-[11px] text-canvas-muted">{k.not}</div>}
                </td>
                <td className={`${td} text-right`}>
                  <NumCell value={k.adet} disabled={!can || patch.isPending} label={`${k.sira}. kalem adedi`} onSave={(v) => patch.mutate({ sira: k.sira, b: { adet: v } })} />
                </td>
                <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums ${k.stokYetersiz ? 'font-bold text-red-700' : ''}`}>{fmtInt(k.stok)}</td>
                <td className={`${td} whitespace-nowrap text-right`}>
                  <div className="font-mono tabular-nums">{fmtMoney(k.listeFiyati)}</div>
                  {k.fiyatKaynagi && <div className="text-[10.5px] text-canvas-muted">{k.fiyatKaynagi}</div>}
                  {k.logoFiyati != null && <div className="text-[10.5px] text-canvas-muted" title={k.logoFiyatNotu ?? undefined}>Logo {fmtMoney(k.logoFiyati)}</div>}
                </td>
                <td className={`${td} text-right`}>
                  <NumCell value={k.onerilenFiyat} money disabled={!can || patch.isPending || !k.stokKodu} label={`${k.sira}. kalem birim teklif fiyatı`} onSave={(v) => patch.mutate({ sira: k.sira, b: { onerilenFiyat: v } })} />
                  {k.fiyatElle && <div className="text-[10.5px] text-canvas-muted">elle</div>}
                  {k.marj != null && <div className="text-[10.5px] text-canvas-muted">marj {fmtPct(k.marj)}</div>}
                </td>
                <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>{fmtMoney(k.tutar)}</td>
                <td className={td}>
                  {can && (
                    <div className="flex flex-wrap gap-1">
                      {(k.durum === 'oneri' || k.durum === 'belirsiz') && k.stokKodu && (
                        <button type="button" className={btnGhost} aria-label={`${k.sira}. kalemin eşleşmesini onayla`} disabled={patch.isPending} onClick={() => patch.mutate({ sira: k.sira, b: { onayla: true } })}>
                          <Check aria-hidden className="h-4 w-4" />
                        </button>
                      )}
                      <button type="button" className={btnGhost} onClick={() => setPicking(k)}>Seç</button>
                      {k.durum !== 'yok' && (
                        <button type="button" className={btnGhost} aria-label={`${k.sira}. kalem katalogda yok`} disabled={patch.isPending} onClick={() => patch.mutate({ sira: k.sira, b: { stokKodu: null } })}>
                          <X aria-hidden className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}

      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-[16px] font-extrabold tracking-tight">Teklif tablosu</h2>
          {meta.me.canExport && t.fiyatli > 0 && (
            <a className={btnGhost} href={tendersApi.pricingUrl(d.id)}>
              <FileSpreadsheet aria-hidden className="h-4 w-4" />
              Excel
            </a>
          )}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-5">
          <Box label="Ara toplam (KDV hariç)" value={fmtMoney(t.araToplam)} help={`${t.fiyatli} kalem`} />
          <Box label="KDV" value={fmtMoney(t.kdv)} />
          <Box label="Genel toplam" value={fmtMoney(t.genelToplam)} />
          <Box label="Liste toplamı (KDV hariç)" value={fmtMoney(t.listeToplami)} help={`Fiyat oranı ${fmtPct(d.fiyatOrani)}`} />
          <Box label="Tahmini marj" value={fmtPct(t.marj)} help={t.maliyetNotu ?? `${t.maliyetKapsam} kalemin maliyeti biliniyor`} />
        </div>
        {t.disarida > 0 && <div className="mt-2"><Note tone="warn">{t.disarida} eşleşen kalemin adedi ya da fiyatı yok; toplama girmedi.</Note></div>}
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Birim teklif fiyatı = KDV hariç liste fiyatı × fiyat oranı ({d.fiyatOraniKaynak ?? 'liste fiyatı'}). Teklif fiyatı karar onayıyla kesinleşir; sistem kendi başına fiyat vermez.
        </p>
      </Panel>

      <PickSheet d={d} item={picking} onClose={() => setPicking(null)} onPick={(code) => {
        const k = picking;
        setPicking(null);
        if (k) patch.mutate({ sira: k.sira, b: { stokKodu: code } });
      }} />
    </>
  );
}

function Box({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <div className="rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{value}</div>
      {help && <div className="text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}

/** Tabloda düzenlenen sayı: odaktan çıkınca ya da Enter ile kaydedilir; değişmediyse istek gitmez. */
function NumCell({ value, onSave, disabled, money, label }: { value: number | null; onSave: (v: number | null) => void; disabled: boolean; money?: boolean; label: string }) {
  const show = (v: number | null) => (v == null ? '' : money ? v.toFixed(2).replace('.', ',') : String(v).replace('.', ','));
  const [text, setText] = useState(show(value));
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    setText(show(value));
  }
  if (disabled) return <span className="font-mono tabular-nums">{money ? fmtMoney(value) : fmtInt(value)}</span>;
  const commit = () => {
    const v = text.trim() ? parseNum(text) : null;
    if (text.trim() && v === null) {
      toast.error('Sayı girin.');
      setText(show(value));
      return;
    }
    if (v !== value) onSave(v);
  };
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      className="w-24 rounded-lg border border-slate-200 bg-white px-2 py-1 text-right font-mono text-base tabular-nums outline-none focus:border-canvas-violet sm:text-[12px]"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
    />
  );
}

function ImportPanel({ d, busy }: { d: TenderDetail; busy: boolean }) {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [fileId, setFileId] = useState('');
  const [mode, setMode] = useState<'replace' | 'append'>(d.kalemler.length ? 'append' : 'replace');
  const [skipped, setSkipped] = useState<Array<{ satir: number; metin: string; neden: string }>>([]);
  const files = d.dosyalar.filter((f) => /\.(xlsx|csv|txt|docx|pdf)$/i.test(f.ad));
  const run = useMutation({
    mutationFn: () => tendersApi.importItems(d.id, fileId ? { fileId, mode } : { text, mode }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['tenders'] });
      setSkipped(r.okunamayan);
      setText('');
      toast.success(`${r.eklenen} kalem alındı${r.okunamayan.length ? `, ${r.okunamayan.length} satır okunamadı` : ''}.`);
    },
    onError: (e) => toast.error(errText(e, 'Liste alınamadı.') ?? ''),
  });
  return (
    <Panel>
      <h2 className="text-[16px] font-extrabold tracking-tight">Kalem listesini al</h2>
      <p className="text-[12px] text-canvas-muted">Excel'den kopyalanan tablo (başlık satırıyla daha doğru okunur: kitap adı, yazar, yayınevi, ISBN, adet), satır satır liste ya da yüklenmiş dosya. Hiçbir satır kesilmez; okunamayanlar nedeniyle listelenir.</p>
      <div className="mt-2 grid grid-cols-1 gap-3 lg:grid-cols-[1fr_280px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Yapıştır</span>
          <textarea
            className={`${field} min-h-[120px] font-mono`}
            value={text}
            disabled={!!fileId}
            placeholder={'Kitap adı\tYazar\tISBN\tAdet\nKüçük Prens\tAntoine de Saint-Exupéry\t9789753626123\t25'}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ya da yüklenmiş dosyadan</span>
            <select className={field} value={fileId} onChange={(e) => setFileId(e.target.value)}>
              <option value="">— yapıştırılan metin —</option>
              {files.map((f) => <option key={f.id} value={f.id}>{f.ad}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Mevcut kalemler</span>
            <select className={field} value={mode} onChange={(e) => setMode(e.target.value as 'replace' | 'append')}>
              <option value="replace">Yerine koy</option>
              <option value="append">Sonuna ekle</option>
            </select>
          </label>
          <button type="button" className={btnPrimary} disabled={busy || run.isPending || (!fileId && !text.trim())} onClick={() => run.mutate()}>
            {run.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Listeyi al
          </button>
        </div>
      </div>
      {skipped.length > 0 && (
        <details className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
          <summary className="cursor-pointer font-bold">Okunamayan {skipped.length} satır</summary>
          <ul className="mt-1 flex flex-col gap-0.5">
            {skipped.map((s) => <li key={s.satir} className="break-words"><b>{s.satir}.</b> {s.metin} — {s.neden}</li>)}
          </ul>
        </details>
      )}
    </Panel>
  );
}

function PickSheet({ d, item, onClose, onPick }: { d: TenderDetail; item: Item | null; onClose: () => void; onPick: (code: string) => void }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 350);
  const search = useQuery({
    queryKey: ['tenders', 'catalog', d.id, dq],
    queryFn: () => tendersApi.catalogSearch(d.id, dq),
    enabled: !!item && dq.trim().length >= 2,
  });
  const list: Candidate[] = dq.trim().length >= 2 ? search.data?.items ?? [] : item?.adaylar ?? [];
  return (
    <Sheet open={!!item} modal onClose={() => { setQ(''); onClose(); }} title="Katalogdan seç" subtitle={item ? `${item.sira}. kalem: ${item.ad ?? item.metin}` : undefined}>
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ara (ad, yazar, stok kodu ya da ISBN)</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          </span>
        </label>
        {search.isFetching && <div className="text-[12px] text-canvas-muted">Aranıyor…</div>}
        {search.error && <Note tone="err">{errText(search.error, 'Arama yapılamadı.')}</Note>}
        <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{dq.trim().length >= 2 ? 'Arama sonucu' : 'Eşleştirme adayları'}</div>
        {!list.length && <div className="text-[12.5px] text-canvas-muted">Aday yok; yukarıdan arayın.</div>}
        <ul className="flex flex-col gap-1.5">
          {list.map((c) => (
            <li key={c.stokKodu}>
              <button
                type="button"
                onClick={() => onPick(c.stokKodu)}
                className={`w-full rounded-xl border px-3 py-2 text-left transition-colors duration-150 hover:border-canvas-violet/50 ${item?.stokKodu === c.stokKodu ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-100 bg-white/80'}`}
              >
                <div className="break-words font-semibold">{c.ad ?? '(adsız)'}</div>
                <div className="break-words text-[11px] text-canvas-muted">{[c.yazar, c.yayinevi, c.isbn && `ISBN ${c.isbn}`, c.stokKodu].filter(Boolean).join(' · ')}</div>
                {c.benzerlik != null && <div className="font-mono text-[10.5px] text-canvas-muted">benzerlik {fmtPct(c.benzerlik)}</div>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Sheet>
  );
}
