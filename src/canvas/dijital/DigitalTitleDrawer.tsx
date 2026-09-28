import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnPrimary, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { LISTING_TONE, dijitalApi, fmtInt, fmtMoney, type Contract, type Format, type ListingState, type Meta, type TitleDetail } from './api';
import { Fact, RightPill } from './parts';

/** Kitap ayrıntısı (yan panel; /dijital-yayin/kitap/:id): kimlik alanları, sözleşmeler ve hak bayrakları, telif kararı,
 *  e-kitap dosyası (CRM + stüdyo), platform durumu ve geçmişi, dijital fiyat kararı, CRM'e işlenecekler, dijital satış. */
export default function DigitalTitleDrawer({ id, meta, onClose }: { id: string | null; meta: Meta; onClose: () => void }) {
  const q = useQuery({ queryKey: ['dijital', 'title', id], queryFn: () => dijitalApi.title(id as string), enabled: ENGINE_ENABLED && !!id });
  const t = q.data;
  return (
    <Sheet open={!!id} onClose={onClose} modal wide title={t?.ad ?? 'Kitap'}
      subtitle={t ? [t.stokKodu, t.yazar, t.tipAdi, t.yayinDurumu].filter(Boolean).join(' · ') : undefined}>
      {q.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {q.error && <Note tone="err">{errText(q.error, 'Kitap okunamadı.')}</Note>}
      {t && <Body t={t} meta={meta} />}
    </Sheet>
  );
}

function Body({ t, meta }: { t: TitleDetail; meta: Meta }) {
  return (
    <div className="flex flex-col gap-4 text-[13px]">
      {t.uyari && <Note tone="warn">{t.uyari}</Note>}
      <section>
        <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Kimlik ve dosya</h3>
        <div className="mt-1.5 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Fact label="ISBN / barkod" value={t.isbn ?? t.ean ?? '—'} />
          <Fact label="e-ISBN" value={t.eIsbn ?? 'yok'} help={t.studioEIsbn && t.studioEIsbn !== t.eIsbn ? `Stüdyodaki e-kitapta: ${t.studioEIsbn}` : undefined} />
          <Fact label="E-kitap stok kodu / barkod" value={t.ekitapStokKodu ?? 'yok'} help={t.ekitapBarkod ?? undefined} />
          <Fact label="CRM E-Pub durumu" value={t.epubCrm ? 'Evet' : 'Hayır'} help={t.uretimDurumu ? `Üretim: ${t.uretimDurumu} (${t.uretimTarih ?? '—'})` : undefined} />
          <Fact label="Stüdyo e-kitabı" value={t.studioDurumuAdi} help={t.studioDenetim ? `Denetim: ${t.studioDenetim === 'OK' ? 'temiz' : t.studioDenetim === 'WARN' ? 'uyarılı' : 'hatalı'}` : undefined} />
          <Fact label="Basılı son 12 ay" value={`${fmtInt(t.basili12Adet)} adet`} help={t.basili12Ciro !== null ? fmtMoney(t.basili12Ciro) : undefined} />
        </div>
        {t.baskiDegisim && <Note tone="warn">{t.baskiDegisim.tarih}: {t.baskiDegisim.tur}. Dijital sürümün güncellenmesi gerekip gerekmediğine bakın.</Note>}
        {(t.firsatGerekcesi || t.sesliFirsatGerekcesi) && (
          <div className="mt-2 flex flex-col gap-1">
            {t.firsatGerekcesi && <Note tone="info">E-kitap fırsatı: {t.firsatGerekcesi}</Note>}
            {t.sesliFirsatGerekcesi && <Note tone="info">Sesli kitap adayı: {t.sesliFirsatGerekcesi}</Note>}
          </div>
        )}
      </section>

      <section>
        <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Haklar ({t.hakKaynak})</h3>
        <div className="mt-1.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded-xl bg-white/80 px-3 py-2"><div className="flex items-center gap-2"><span className="font-bold">E-kitap</span><RightPill value={t.hakEkitap} label={t.hakEkitapAdi} /></div><p className="mt-1 text-[12px] leading-snug text-canvas-muted">{t.hakEkitapGerekce}</p></div>
          <div className="rounded-xl bg-white/80 px-3 py-2"><div className="flex items-center gap-2"><span className="font-bold">Sesli kitap</span><RightPill value={t.hakSesli} label={t.hakSesliAdi} /></div><p className="mt-1 text-[12px] leading-snug text-canvas-muted">{t.hakSesliGerekce}</p></div>
        </div>
        <div className="mt-2 flex flex-col gap-2">
          {!t.sozlesmeler.length && <div className="text-[12px] text-canvas-muted">Kitaba bağlı telif alış sözleşmesi yok.</div>}
          {t.sozlesmeler.map((c) => <ContractRow key={c.id} c={c} t={t} meta={meta} />)}
        </div>
      </section>

      <section>
        <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Platformlar</h3>
        <div className="mt-1.5 flex flex-col gap-2">
          {!t.platformlar.length && <div className="text-[12px] text-canvas-muted">Platform tanımlı değil (Katalog → Platformlar).</div>}
          {t.platformlar.map((c) => <ListingRow key={c.platformId} t={t} chip={c} meta={meta} />)}
        </div>
        {!!t.platformGecmisi.length && (
          <details className="mt-2">
            <summary className="cursor-pointer text-[12px] font-bold text-canvas-violet">Platform geçmişi ({t.platformGecmisi.length})</summary>
            <ul className="mt-1 flex flex-col gap-1 text-[12px]">
              {t.platformGecmisi.map((h, i) => (
                <li key={i} className="break-words">
                  <span className="font-mono text-[11px] text-canvas-muted">{h.tarih}</span> {h.platform}: <b>{h.durumAdi}</b>
                  {h.fiyat !== null ? ` · ${h.fiyat}` : ''}{h.not ? ` · ${h.not}` : ''} <span className="text-canvas-muted">({h.yazan}{h.kaynak === 'rapor' ? ', rapordan' : ''})</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <PriceBox t={t} meta={meta} />

      {!!t.crmIslenecek.length && (
        <section>
          <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">CRM'e işlenecek</h3>
          <ul className="mt-1.5 flex flex-col gap-1 text-[12px]">
            {t.crmIslenecek.map((p) => (
              <li key={p.id} className="break-words"><Pill tone={p.durum === 'acik' ? 'warn' : 'muted'}>{p.durum === 'acik' ? 'açık' : 'kapandı'}</Pill> <b>{p.alanAdi}</b>: <span className="font-mono">{p.deger}</span> <span className="text-canvas-muted">— {p.kaynak}</span></li>
            ))}
          </ul>
        </section>
      )}

      {t.satis && (
        <section>
          <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Dijital satış</h3>
          {!t.satis.platform.length && !t.satis.logo.length && <div className="mt-1 text-[12px] text-canvas-muted">Onaylı raporda ya da Logo'da bu kitabın dijital satışı yok.</div>}
          {!!t.satis.platform.length && (
            <ul className="mt-1.5 flex flex-col gap-0.5 text-[12px]">
              {t.satis.platform.map((s, i) => <li key={i}><span className="font-mono">{s.donem}</span> {s.platform}: {fmtInt(s.adet)} adet · {fmtMoney(s.netTl)}</li>)}
            </ul>
          )}
          {!!t.satis.logo.length && (
            <p className="mt-1 text-[12px] text-canvas-muted">Logo'da e-kitap stok koduyla fatura: {t.satis.logo.map((s) => `${s.donem} ${fmtInt(s.adet)} adet`).join(' · ')}</p>
          )}
        </section>
      )}
      <p className="text-[11px] text-canvas-muted">Okuma: {fmtDate(t.okundu)}</p>
    </div>
  );
}

function ContractRow({ c, t, meta }: { c: Contract; t: TitleDetail; meta: Meta }) {
  const decided = t.kararlar.filter((k) => k.sozlesmeId === c.id);
  const flag = (on: boolean, text: string) => <Pill tone={on ? 'ok' : 'err'}>{text}</Pill>;
  return (
    <div className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="break-words text-[12.5px] font-extrabold">{c.taraflar.join(', ') || c.ad}</span>
        <Pill tone={c.yururlukte ? 'ok' : 'muted'}>{c.yururlukte ? 'yürürlükte' : 'yürürlükte değil'}</Pill>
        <span className="text-[11px] text-canvas-muted">{c.suresiz ? 'süresiz' : c.bitis ? `bitiş ${c.bitis}` : ''}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {flag(c.ekitap, 'e-kitap')}{flag(c.sesli, 'sesli')}{flag(c.iletim, 'internette gösterim')}{flag(c.zkitap, 'Z-kitap')}
        {c.korumaDisi && <Pill tone="muted">koruma dışı</Pill>}
      </div>
      {c.not && (
        <blockquote className="mt-1.5 break-words rounded-lg bg-amber-50 px-2.5 py-1.5 text-[12px] leading-snug">
          <span className="font-bold">Hak notu: </span>{c.not}
          {c.notOkuma && <span className="mt-0.5 block text-[11px] text-canvas-muted">Zeki AI ön okuması: {c.notOkuma.sonucAdi}{c.notOkuma.olasilik !== null ? ` (olasılık %${Math.round((c.notOkuma.olasilik ?? 0) * 100)})` : ''} — karar telif biriminin.</span>}
        </blockquote>
      )}
      {decided.map((d, i) => (
        <div key={i} className="mt-1 text-[12px]"><b>{d.bicimAdi}:</b> {d.kararAdi} — {d.gerekce} <span className="text-canvas-muted">({d.yazan}, {fmtDate(d.tarih)})</span></div>
      ))}
      {c.not && c.yururlukte && meta.me.canRights && <DecisionForm t={t} c={c} meta={meta} />}
    </div>
  );
}

function DecisionForm({ t, c, meta }: { t: TitleDetail; c: Contract; meta: Meta }) {
  const qc = useQueryClient();
  const [bicim, setBicim] = useState<Format>('ekitap');
  const [karar, setKarar] = useState('uygun');
  const [gerekce, setGerekce] = useState('');
  const m = useMutation({
    mutationFn: () => dijitalApi.decide({ kitapId: t.kitapId, sozlesmeId: c.id, bicim, karar, gerekce: gerekce.trim() }),
    onSuccess: () => {
      toast.success('Karar kaydedildi.');
      setGerekce('');
      qc.invalidateQueries({ queryKey: ['dijital'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <div className="mt-2 grid grid-cols-1 gap-2 rounded-lg bg-slate-50 p-2 sm:grid-cols-[120px_160px_minmax(0,1fr)_auto] sm:items-end">
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Biçim</span>
        <select className={field} value={bicim} onChange={(e) => setBicim(e.target.value as Format)}>
          {Object.entries(meta.bicimler).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Karar</span>
        <select className={field} value={karar} onChange={(e) => setKarar(e.target.value)}>
          {Object.entries(meta.kararlar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Gerekçe</span>
        <input className={field} value={gerekce} onChange={(e) => setGerekce(e.target.value)} placeholder="Sözleşmenin ilgili maddesi, bölge/platform kısıtı" />
      </label>
      <button type="button" className={btnPrimary} disabled={!gerekce.trim() || m.isPending} onClick={() => m.mutate()}>
        {m.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
        Kararı yaz
      </button>
    </div>
  );
}

function ListingRow({ t, chip, meta }: { t: TitleDetail; chip: TitleDetail['platformlar'][number]; meta: Meta }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [durum, setDurum] = useState<ListingState>(chip.durum);
  const [tarih, setTarih] = useState(new Date().toISOString().slice(0, 10));
  const [not, setNot] = useState('');
  const [fiyat, setFiyat] = useState('');
  const m = useMutation({
    mutationFn: () => dijitalApi.setListing(t.kitapId, chip.platformId, { durum, tarih, not: not.trim() || undefined, fiyat: fiyat.trim() || undefined }),
    onSuccess: (out) => {
      if (out.uyari) toast.warning(out.uyari);
      else toast.success('Platform durumu kaydedildi.');
      setOpen(false);
      setNot('');
      qc.invalidateQueries({ queryKey: ['dijital'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <div className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12.5px] font-extrabold">{chip.platform}</span>
          <Pill tone={LISTING_TONE[chip.durum]}>{chip.durumAdi}</Pill>
          {chip.tarih && <span className="font-mono text-[11px] text-canvas-muted">{chip.tarih}</span>}
        </div>
        {meta.me.canWrite && !open && (
          <button type="button" className="min-h-11 rounded-xl px-2 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0" onClick={() => setOpen(true)}>Durumu değiştir</button>
        )}
      </div>
      {open && (
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[150px_150px_120px_minmax(0,1fr)_auto] sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={durum} onChange={(e) => setDurum(e.target.value as ListingState)}>
              {Object.entries(meta.platformDurumlari).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tarih</span>
            <input type="date" className={field} value={tarih} onChange={(e) => setTarih(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Platform fiyatı</span>
            <input className={field} inputMode="decimal" value={fiyat} onChange={(e) => setFiyat(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Not</span>
            <input className={field} value={not} onChange={(e) => setNot(e.target.value)} placeholder="Ret nedeni, dağıtıcı, bağlantı…" />
          </label>
          <button type="button" className={btnPrimary} disabled={m.isPending} onClick={() => m.mutate()}>Kaydet</button>
        </div>
      )}
    </div>
  );
}

function PriceBox({ t, meta }: { t: TitleDetail; meta: Meta }) {
  const qc = useQueryClient();
  const [fiyat, setFiyat] = useState(t.dijitalFiyat !== null ? String(t.dijitalFiyat).replace('.', ',') : '');
  const [gerekce, setGerekce] = useState('');
  const m = useMutation({
    mutationFn: () => dijitalApi.setPrice(t.kitapId, { fiyat: fiyat.trim() || null, gerekce: gerekce.trim() }),
    onSuccess: () => {
      toast.success('Dijital fiyat kararı kaydedildi.');
      setGerekce('');
      qc.invalidateQueries({ queryKey: ['dijital'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const ratio = t.dijitalFiyat !== null && t.basiliFiyat ? t.dijitalFiyat / t.basiliFiyat : null;
  return (
    <section>
      <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Fiyat</h3>
      <div className="mt-1.5 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Fact label="Basılı liste fiyatı (CRM, KDV dahil)" value={fmtMoney(t.basiliFiyat)} />
        <Fact label="Dijital fiyat kararı" value={fmtMoney(t.dijitalFiyat)}
          help={t.fiyatOnaylayan ? `${t.fiyatOnaylayan}, ${fmtDate(t.fiyatTarih)}${t.fiyatGerekce ? ` — ${t.fiyatGerekce}` : ''}` : 'Karar yok'} />
        <Fact label="Dijital / basılı" value={ratio !== null ? `%${Math.round(ratio * 100)}` : '—'} />
      </div>
      {meta.me.canPrice && (
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[160px_minmax(0,1fr)_auto] sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Dijital fiyat (₺)</span>
            <input className={field} inputMode="decimal" value={fiyat} onChange={(e) => setFiyat(e.target.value)} placeholder="boş: kararı kaldır" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Gerekçe</span>
            <input className={field} value={gerekce} onChange={(e) => setGerekce(e.target.value)} />
          </label>
          <button type="button" className={btnPrimary} disabled={m.isPending || (!!fiyat.trim() && !gerekce.trim())} onClick={() => m.mutate()}>Kaydet</button>
        </div>
      )}
      <p className="mt-1 text-[11px] text-canvas-muted">Fiyat kararı platformlara gönderilmez; platform girişinin ve CRM kaydının dayanağıdır.</p>
    </section>
  );
}
