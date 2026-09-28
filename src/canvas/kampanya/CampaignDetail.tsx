import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Loader2, Search, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../editorial/kit';
import { Tabs } from '../budget/parts';
import { fmtDay, fmtInt, fmtMoney, fmtPct } from '../budget/api';
import { kampanyaApi, parseMoney, pctToRatio, worst, type Campaign, type Item, type Overview } from './api';
import { Checks, KampanyaFrame, Margin, StatusPill } from './parts';
import CandidatesPanel from './CandidatesPanel';
import ResultsScreen from './ResultsScreen';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** Kampanya ayrıntısı: kitaplar ve simülasyon, adaylar, Zeki AI metni, sonuç; onay akışı ve «elle kurdum» işareti. */

const TABS = [
  { key: 'kitaplar', label: 'Kitaplar' },
  { key: 'adaylar', label: 'Aday iste' },
  { key: 'metin', label: 'Kampanya metni' },
  { key: 'sonuc', label: 'Sonuç' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function CampaignDetail() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'kitaplar') as Tab;
  const ov = useQuery({ queryKey: ['kampanya', 'overview'], queryFn: kampanyaApi.overview, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const camp = useQuery({ queryKey: ['kampanya', 'campaign', id], queryFn: () => kampanyaApi.get(id), enabled: ENGINE_ENABLED && !!id });
  const c = camp.data;
  const setTab = (t: Tab) => {
    const p = new URLSearchParams(params);
    if (t === 'kitaplar') p.delete('sekme');
    else p.set('sekme', t);
    setParams(p, { replace: true });
  };
  const put = (next: Campaign) => {
    // Değişiklik cevabı hemen görünür; sorgu bilgisi (kaynaklar) okuma ucundan gelir, bu yüzden kayıt yeniden okunur.
    qc.setQueryData(['kampanya', 'campaign', id], (prev: Campaign | undefined) => ({ ...next, kaynaklar: next.kaynaklar ?? prev?.kaynaklar }));
    if (!next.kaynaklar) qc.invalidateQueries({ queryKey: ['kampanya', 'campaign', id] });
    qc.invalidateQueries({ queryKey: ['kampanya', 'list'] });
    qc.invalidateQueries({ queryKey: ['kampanya', 'overview'] });
  };

  return (
    <KampanyaFrame
      title={c?.ad ?? 'Kampanya'}
      lead={c ? `${c.kanalAdi}${c.platform ? ` · ${c.platform}` : ''} · ${fmtDay(c.baslangic)} – ${fmtDay(c.bitis)} · hazırlayan ${c.hazirlayan ?? '—'}` : 'Yükleniyor…'}
      back={{ to: '/kampanyalar', label: 'Kampanyalar' }}
      source={ov.data?.status.dataEnd ? `Logo + CRM · ${fmtDay(ov.data.status.dataEnd)}` : 'Logo + CRM'}
      presence={ov.data?.me.display ?? ''}
      aside={c && ov.data ? <Actions c={c} ov={ov.data} onChange={put} /> : undefined}
    >
      {camp.error && <Note tone="err">{errText(camp.error, 'Kampanya açılamadı.')}</Note>}
      {c && ov.data && (
        <>
          <KpiRow>
            <Kpi label="Kitap" value={fmtInt(c.ozet.kitap)} help={`Ortalama indirim ${fmtPct(c.ozet.ortalamaIndirim, 0)}`}
              info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Kitap ve ortalama indirim" />} />
            <Kpi label="Marj (önce → kampanya)" value={c.ozet.marjOraniSonra === null ? '—' : fmtPct(c.ozet.marjOraniSonra)}
              help={`Kampanyasız ${fmtPct(c.ozet.marjOraniOnce)} · ${fmtInt(c.ozet.marjBilinen)} kitapta hesaplandı`}
              info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Marj (önce → kampanya)" />} />
            <Kpi label="Kırmızı kontrol" value={fmtInt(c.ozet.kirmizi)} help={`${fmtInt(c.ozet.kirmiziKitap)} kitapta · sarı ${fmtInt(c.ozet.sari)}`}
              info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Kırmızı kontrol" />} />
            <Kpi label="Maliyeti eksik / stok riski" value={`${fmtInt(c.ozet.maliyetEksik)} / ${fmtInt(c.ozet.stokRiski)}`} help="Maliyetsiz kitapta marj hesaplanmaz"
              info={<SqlInfo k={c.kaynaklar} alan="ozet" label="Maliyeti eksik / stok riski" />} />
          </KpiRow>
          {c.onayNotu && <Note tone={c.durum === 'taslak' ? 'warn' : 'info'}>{c.durum === 'taslak' ? 'Geri gönderildi' : 'Onay notu'} ({c.onaylayan}): {c.onayNotu}</Note>}
          {c.crmIslenecek && <Note tone="warn">Bayi kampanyası CRM’e işlenecek: CRM’de tanımlayıp kimliğini aşağıya girin. Portal CRM’e yazmaz.</Note>}
          {c.uyarilar.length > 0 && (
            <Note tone="warn">
              <SqlInfo k={c.kaynaklar} alan="kitaplar" label="Stok uyarısı (tükenme tahmini)" className="mr-1" />
              Stok kampanya bitmeden tükenebilir: {c.uyarilar.map((u) => `${u.ad ?? u.stok} (${fmtDay(u.tukenme)})`).join(', ')}.
            </Note>
          )}
          <div className="flex items-center gap-1">
            <div className="min-w-0 flex-1">
              <Tabs tabs={TABS.map((t) => (t.key === 'kitaplar' ? { ...t, badge: c.ozet.kirmiziKitap || null } : t))} value={tab} onChange={setTab} />
            </div>
            {!!c.ozet.kirmiziKitap && <SqlInfo k={c.kaynaklar} alan="ozet" label="Sekme rozeti: kırmızı kontrollü kitap" />}
          </div>
          {tab === 'kitaplar' && <BooksTab c={c} ov={ov.data} onChange={put} />}
          {tab === 'adaylar' && (c.yetki.duzenle ? <CandidatesPanel ov={ov.data} campaignId={c.id} onAdded={() => { camp.refetch(); setTab('kitaplar'); }} />
            : <Note tone="info">Aday eklemek için kampanya taslak olmalı ve hazırlama yetkiniz olmalı.</Note>)}
          {tab === 'metin' && <CopyTab c={c} ov={ov.data} onChange={put} />}
          {tab === 'sonuc' && <ResultsScreen c={c} ov={ov.data} />}
        </>
      )}
    </KampanyaFrame>
  );
}

function Actions({ c, ov, onChange }: { c: Campaign; ov: Overview; onChange: (c: Campaign) => void }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [kurulum, setKurulum] = useState(c.kurulumNotu ?? '');
  const [crmId, setCrmId] = useState(c.crmKampanyaId ?? '');
  useEffect(() => { setKurulum(c.kurulumNotu ?? ''); setCrmId(c.crmKampanyaId ?? ''); }, [c.kurulumNotu, c.crmKampanyaId]);
  const run = useMutation({
    mutationFn: (fn: () => Promise<Campaign>) => fn(),
    onSuccess: (x) => {
      onChange(x);
      setNote('');
      if (x.bildirim === 'no_recipient') toast.info('Kaydedildi. Bildirim alıcısı tanımlı değil; e-posta gitmedi.');
      else toast.success('Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => kampanyaApi.remove(c.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kampanya'] }); nav('/kampanyalar'); toast.success('Taslak silindi.'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const busy = run.isPending || del.isPending;
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 px-3 py-3 text-[12px] font-semibold text-canvas-muted">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill durum={c.durum} label={c.durumAdi} />
        <span className="font-mono text-[11px]">{c.id}</span>
        {c.gonderen && <span>gönderen {c.gonderen}</span>}
        {c.onaylayan && c.durum !== 'taslak' && <span>onaylayan {c.onaylayan}</span>}
      </div>
      {c.durum === 'taslak' && ov.me.canEdit && (
        <div className="flex flex-wrap gap-1.5">
          <button type="button" className={btnPrimary} disabled={busy || !c.ozet.kitap} onClick={() => run.mutate(() => kampanyaApi.submit(c.id))}>Onaya gönder</button>
          {!c.submittedAt && (
            <button type="button" className={btnGhost} disabled={busy} onClick={() => { if (window.confirm('Taslak silinsin mi?')) del.mutate(); }}>
              <Trash2 aria-hidden className="h-4 w-4" />Sil
            </button>
          )}
        </div>
      )}
      {c.durum === 'onay_bekliyor' && c.yetki.kendisi && ov.me.canEdit && (
        <button type="button" className={btnGhost} disabled={busy} onClick={() => run.mutate(() => kampanyaApi.withdraw(c.id))}>Onaydan geri çek</button>
      )}
      {c.durum === 'onay_bekliyor' && c.yetki.karar && (
        <div className="flex flex-col gap-1.5">
          <textarea className={field} rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (geri göndermede zorunlu)" />
          <div className="flex flex-wrap gap-1.5">
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => run.mutate(() => kampanyaApi.decide(c.id, 'onay', note || undefined))}>Onayla</button>
            <button type="button" className={btnGhost} disabled={busy || !note.trim()} onClick={() => run.mutate(() => kampanyaApi.decide(c.id, 'geri', note))}>Geri gönder</button>
          </div>
        </div>
      )}
      {c.durum === 'onay_bekliyor' && c.yetki.kendisi && ov.me.canApprove && (
        <span>Kampanyayı hazırlayan ya da onaya gönderen onaylayamaz.</span>
      )}
      {['onaylandi', 'yurutuluyor', 'bitti'].includes(c.durum) && ov.me.canEdit && (
        <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); run.mutate(() => kampanyaApi.update(c.id, { kurulumNotu: kurulum })); }}>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Elle kurulum</span>
            <input className={field} value={kurulum} onChange={(e) => setKurulum(e.target.value)} placeholder="Nerede, nasıl kuruldu (panel, T-soft, CRM)" />
          </label>
          <button type="submit" className={btnGhost} disabled={busy || kurulum === (c.kurulumNotu ?? '')}>Elle kurdum</button>
          {c.kurulduBy && <span>İşaretleyen {c.kurulduBy} · {fmtDay(c.kurulduAt)}</span>}
        </form>
      )}
      {c.kanal === 'bayi' && ov.me.canEdit && c.durum !== 'iptal' && (
        <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); run.mutate(() => kampanyaApi.update(c.id, { crmKampanyaId: crmId.trim() })); }}>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>CRM kampanya kimliği</span>
            <input className={field} value={crmId} onChange={(e) => setCrmId(e.target.value)} placeholder="CRM’de açılan bayi kampanyası" />
          </label>
          <button type="submit" className={btnGhost} disabled={busy || crmId.trim() === (c.crmKampanyaId ?? '')}>Bağla</button>
        </form>
      )}
      {ov.me.canExport && (
        <div className="flex flex-wrap gap-1.5">
          <a className={btnGhost} href={kampanyaApi.exportUrl(c.id)}><Download aria-hidden className="h-4 w-4" />Brif (Excel)</a>
          <a className={btnGhost} href={kampanyaApi.exportUrl(c.id, true)}><Download aria-hidden className="h-4 w-4" />İç değerlendirme</a>
        </div>
      )}
      {!['bitti', 'iptal'].includes(c.durum) && ov.me.canEdit && (
        <button type="button" className="self-start text-[11.5px] font-bold text-red-700 underline-offset-2 hover:underline" disabled={busy}
          onClick={() => {
            const why = window.prompt('İptal gerekçesi');
            if (why && why.trim()) run.mutate(() => kampanyaApi.cancel(c.id, why.trim()));
          }}>
          Kampanyayı iptal et
        </button>
      )}
    </div>
  );
}

function BooksTab({ c, ov, onChange }: { c: Campaign; ov: Overview; onChange: (c: Campaign) => void }) {
  const edit = c.yetki.duzenle;
  const items = c.kitaplar ?? [];
  const mutate = useMutation({
    mutationFn: (fn: () => Promise<Campaign>) => fn(),
    onSuccess: (x) => {
      onChange(x);
      if (x.bulunamayan?.length) toast.warning(`Bulunamayan stok kodu: ${x.bulunamayan.join(', ')}`);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <>
      {edit && <Settings c={c} run={(fn) => mutate.mutate(fn)} busy={mutate.isPending} />}
      {edit && <BookSearch have={new Set(items.map((i) => i.stok))} onAdd={(stok) => mutate.mutate(() => kampanyaApi.addItems(c.id, [{ stok }]))} />}
      <Panel>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            Kitaplar ve kontroller <SqlInfo k={c.kaynaklar} alan="kitaplar" label="Kitap hesabı" />
          </h2>
          {mutate.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin text-canvas-muted" />}
        </div>
        {!items.length ? (
          <Note tone="info">Kampanyada kitap yok. «Aday iste» sekmesinden ya da yukarıdaki aramadan ekleyin.</Note>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kitap</th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">Liste</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">İndirim</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">Kampanya fiyatı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">Stok / tükenme</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">Birim maliyet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">Telif (önce → kamp.)</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="kitaplar">Marj (önce → kamp.)</InfoLabel></th>
                <th className={th}>Kontroller</th>
                {edit && <th className={th}><span className="sr-only">Çıkar</span></th>}
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <ItemRow key={i.stok} i={i} edit={edit} bitis={c.bitis}
                  onPatch={(b) => mutate.mutate(() => kampanyaApi.updateItem(c.id, i.stok, b))}
                  onRemove={() => mutate.mutate(() => kampanyaApi.removeItem(c.id, i.stok))} />
              ))}
            </tbody>
          </TableWrap>
        )}
        <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
          Birim net gelir = fiyat ÷ (1 + KDV) × (1 − kanal kesintisi). Marj = net gelir − birim maliyet − birim telif; maliyet yoksa «hesaplanamaz».
          Telif esası CRM sözleşmesinden (perakende fiyatından ödenen telifi indirim düşürmez). Son {ov.ayarlar.fiyatGun} gün en düşük fiyat kuralı
          yalnız site için ve kendi günlük fiyat kaydımızdan denetlenir; hukuk birimi teyit etmeli.
        </p>
      </Panel>
    </>
  );
}

function Settings({ c, run, busy }: { c: Campaign; run: (fn: () => Promise<Campaign>) => void; busy: boolean }) {
  const pct = (v: number | null) => (v === null || v === undefined ? '' : String(Math.round(v * 1000) / 10).replace('.', ','));
  const [bulk, setBulk] = useState(pct(c.varsayilanIndirim));
  const [kes, setKes] = useState(pct(c.kanalKesinti));
  const [artis, setArtis] = useState(c.beklenenArtis === null ? '' : String(c.beklenenArtis).replace('.', ','));
  const [bas, setBas] = useState(c.baslangic);
  const [bit, setBit] = useState(c.bitis);
  const [platform, setPlatform] = useState(c.platform ?? '');
  const bulkRatio = pctToRatio(bulk);
  const dirty = kes !== pct(c.kanalKesinti) || artis !== (c.beklenenArtis === null ? '' : String(c.beklenenArtis).replace('.', ','))
    || bas !== c.baslangic || bit !== c.bitis || platform !== (c.platform ?? '');
  return (
    <Panel>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-[150px_150px_1fr_150px_150px_auto]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Başlangıç</span>
          <input type="date" className={field} value={bas} onChange={(e) => setBas(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Bitiş</span>
          <input type="date" className={field} value={bit} min={bas} onChange={(e) => setBit(e.target.value)} />
        </label>
        <label className="col-span-2 flex flex-col gap-1 lg:col-span-1">
          <span className={labelCls}>Platform</span>
          <input className={field} value={platform} onChange={(e) => setPlatform(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kanal kesintisi %</span>
          <input className={field} inputMode="decimal" value={kes} onChange={(e) => setKes(e.target.value)} placeholder="girilmedi" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Beklenen artış (kat)</span>
          <input className={field} inputMode="decimal" value={artis} onChange={(e) => setArtis(e.target.value)} placeholder="öğrenimden" />
        </label>
        <div className="col-span-2 flex items-end lg:col-span-1">
          <button type="button" className={`${btnGhost} w-full`} disabled={!dirty || busy || bit < bas}
            onClick={() => run(() => kampanyaApi.update(c.id, { baslangic: bas, bitis: bit, platform: platform.trim() || null,
              kanalKesinti: kes.trim() ? pctToRatio(kes) : null, beklenenArtis: artis.trim() ? Number(artis.replace(',', '.')) : null }))}>
            Kaydet ve hesapla
          </button>
        </div>
      </div>
      <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (bulkRatio !== null) run(() => kampanyaApi.simulate(c.id, bulkRatio)); }}>
        <label className="flex w-[160px] flex-col gap-1">
          <span className={labelCls}>Toplu indirim %</span>
          <input className={field} inputMode="decimal" value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder="Örn. 30" />
        </label>
        <button type="submit" className={btnPrimary} disabled={bulkRatio === null || busy}>Bütün kitaplara uygula</button>
        <span className="text-[11.5px] text-canvas-muted">Kitap satırındaki fiyat ya da indirim tek tek değiştirilebilir.</span>
      </form>
    </Panel>
  );
}

function BookSearch({ have, onAdd }: { have: Set<string>; onAdd: (stok: string) => void }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q.trim(), 300);
  const hits = useQuery({ queryKey: ['kampanya', 'books', dq], queryFn: () => kampanyaApi.books(dq), enabled: dq.length >= 2 });
  return (
    <Panel>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Kitap ekle</span>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, yazar, stok kodu ya da barkod" />
        </div>
      </label>
      {hits.error && <div className="mt-2"><Note tone="err">{errText(hits.error, 'Arama yapılamadı.')}</Note></div>}
      {dq.length >= 2 && hits.data && (
        <div className="mt-2 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
          <InfoLabel k={hits.data.kaynaklar} alan="items" label="Kitap araması: stok, liste fiyatı">{`${fmtInt(hits.data.total)} kitap`}</InfoLabel>
        </div>
      )}
      {dq.length >= 2 && hits.data && (
        <ul className="mt-2 flex max-h-72 flex-col gap-1 overflow-y-auto">
          {hits.data.items.map((b) => (
            <li key={b.stok} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
              <span className="min-w-0">
                <span className="font-semibold">{b.ad ?? b.stok}</span>
                <span className="block text-[11px] text-canvas-muted">{[b.yazar, b.stok, `stok ${fmtInt(b.stokAdet)}`, fmtMoney(b.liste)].filter(Boolean).join(' · ')}</span>
              </span>
              <button type="button" className={btnGhost} disabled={have.has(b.stok)} onClick={() => onAdd(b.stok)}>
                {have.has(b.stok) ? 'Eklendi' : 'Ekle'}
              </button>
            </li>
          ))}
          {!hits.data.items.length && <li className="text-[12px] text-canvas-muted">Eşleşen kitap yok.</li>}
        </ul>
      )}
    </Panel>
  );
}

const ROW_TONE = { kirmizi: 'bg-red-50/50', sari: 'bg-amber-50/40', bilgi: '' } as const;

function ItemRow({ i, edit, bitis, onPatch, onRemove }: {
  i: Item; edit: boolean; bitis: string; onPatch: (b: { indirim?: number | null; kampanyaFiyati?: number | null }) => void; onRemove: () => void;
}) {
  const pct = i.indirim === null ? '' : String(Math.round(i.indirim * 1000) / 10).replace('.', ',');
  const price = i.kampanyaFiyati === null ? '' : String(i.kampanyaFiyati).replace('.', ',');
  const [ind, setInd] = useState(pct);
  const [kf, setKf] = useState(price);
  useEffect(() => { setInd(pct); setKf(price); }, [pct, price]);
  const w = worst(i.kontroller);
  const late = i.tukenme && i.tukenme <= bitis;
  return (
    <tr className={`border-t border-slate-100 ${w ? ROW_TONE[w] : ''}`}>
      <td className={td}>
        <div className="font-semibold">{i.ad ?? i.stok}</div>
        <div className="text-[11px] text-canvas-muted">{[i.yazar, i.stok].filter(Boolean).join(' · ')}</div>
        {i.adayGerekcesi && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">Aday: {i.adayGerekcesi}</div>}
      </td>
      <td className={`${td} text-right font-mono tabular-nums`}>
        {fmtMoney(i.liste)}
        {i.hesap.listeKaynak && <div className="text-[10.5px] text-canvas-muted">{i.hesap.listeKaynak === 'crm' ? 'CRM' : i.hesap.listeKaynak === 'logo' ? 'Logo' : 'elle'}</div>}
      </td>
      <td className={`${td} text-right`}>
        {edit ? (
          <input className={`${field} w-20 text-right`} inputMode="decimal" aria-label={`${i.ad ?? i.stok} indirim yüzdesi`} value={ind}
            onChange={(e) => setInd(e.target.value)}
            onBlur={() => { if (ind !== pct) { const r = pctToRatio(ind); if (r !== null) onPatch({ indirim: r }); else setInd(pct); } }} />
        ) : <span className="font-mono tabular-nums">{fmtPct(i.indirim, 0)}</span>}
      </td>
      <td className={`${td} text-right`}>
        {edit ? (
          <input className={`${field} w-24 text-right`} inputMode="decimal" aria-label={`${i.ad ?? i.stok} kampanya fiyatı`} value={kf}
            onChange={(e) => setKf(e.target.value)}
            onBlur={() => { if (kf !== price) { const v = parseMoney(kf); if (v !== null) onPatch({ kampanyaFiyati: v }); else setKf(price); } }} />
        ) : <span className="font-mono tabular-nums">{fmtMoney(i.kampanyaFiyati)}</span>}
      </td>
      <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>
        {fmtInt(i.stokAdet)}
        <div className={`text-[11px] ${late ? 'font-bold text-amber-800' : 'text-canvas-muted'}`}>{i.tukenme ? fmtDay(i.tukenme) : 'satış yok'}</div>
      </td>
      <td className={`${td} text-right font-mono tabular-nums`}>
        {i.birimMaliyet === null ? <span className="text-[11.5px] font-semibold text-red-700">yok</span> : fmtMoney(i.birimMaliyet)}
        <div className="max-w-[160px] whitespace-normal text-[10.5px] leading-tight text-canvas-muted">{i.maliyetKaynak}</div>
      </td>
      <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>
        {i.telifOnce === null ? '—' : `${fmtMoney(i.telifOnce)} → ${fmtMoney(i.telifSonra)}`}
      </td>
      <td className={`${td} whitespace-nowrap text-right`}>
        <Margin v={i.marjOnce} pct={i.marjOraniOnce} /> → <Margin v={i.marjSonra} pct={i.marjOraniSonra} />
      </td>
      <td className={`${td} min-w-[220px]`}><Checks items={i.kontroller} /></td>
      {edit && (
        <td className={td}>
          <button type="button" className={btnGhost} aria-label={`${i.ad ?? i.stok} kitabını çıkar`} onClick={onRemove}>
            <Trash2 aria-hidden className="h-4 w-4" />
          </button>
        </td>
      )}
    </tr>
  );
}

const COPY_KINDS = ['baslik', 'aciklama', 'banner'] as const;

function CopyTab({ c, ov, onChange }: { c: Campaign; ov: Overview; onChange: (c: Campaign) => void }) {
  const qc = useQueryClient();
  const [sel, setSel] = useState<Record<string, string>>({});
  useEffect(() => {
    const s = c.metin.secili ?? {};
    setSel({ baslik: s.baslik ?? '', aciklama: s.aciklama ?? '', banner: s.banner ?? '' });
  }, [c.metin.secili]);
  const gen = useMutation({
    mutationFn: (tur: (typeof COPY_KINDS)[number]) => kampanyaApi.copy(c.id, tur),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['kampanya', 'campaign', c.id] });
      toast.success(`${r.secenekler.length} seçenek geldi${r.dusenSayisi ? `; ${r.dusenSayisi} kurala uymadığı için atıldı` : ''}.`);
    },
    onError: (e) => toast.error(errText(e, 'Metin üretilemedi.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => kampanyaApi.update(c.id, { metin: { secili: sel } }),
    onSuccess: (x) => { onChange(x); toast.success('Metin kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const canSave = ov.me.canEdit && c.durum !== 'iptal';
  return (
    <Panel>
      <p className="mb-3 text-[12px] leading-snug text-canvas-muted">
        Zeki AI yalnız kampanya adını, kitapları, özel günü ve indirim oranını kullanır; kaynaksız rakam ya da kanıtsız üstünlük iddiası içeren seçenek atılır.
        Seçtiğiniz metin brife girer; platforma gönderilmez.
      </p>
      <div className="flex flex-col gap-4">
        {COPY_KINDS.map((k) => {
          const meta = ov.metinTurleri[k];
          const opts = c.metin[k] ?? [];
          const v = sel[k] ?? '';
          return (
            <section key={k} className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-[13.5px] font-extrabold">{meta.ad} <span className="font-semibold text-canvas-muted">(en çok {meta.sinir} karakter)</span></h3>
                {ov.me.canCopy && c.ozet.kitap > 0 && (
                  <button type="button" className={btnGhost} disabled={gen.isPending} onClick={() => gen.mutate(k)}>
                    {gen.isPending && gen.variables === k ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                    Zeki AI’dan iste
                  </button>
                )}
              </div>
              {opts.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {opts.map((o) => (
                    <button key={o} type="button" onClick={() => setSel((s) => ({ ...s, [k]: o }))} aria-pressed={v === o}
                      className={`rounded-xl px-3 py-2 text-left text-[12.5px] font-semibold transition-transform duration-150 ease-out active:scale-[0.98] ${
                        v === o ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}>
                      {o}
                    </button>
                  ))}
                </div>
              )}
              <textarea className={field} rows={k === 'aciklama' ? 3 : 1} value={v} maxLength={meta.sinir} disabled={!canSave}
                onChange={(e) => setSel((s) => ({ ...s, [k]: e.target.value }))} />
              <span className={`self-end font-mono text-[11px] tabular-nums ${v.length > meta.sinir ? 'text-red-700' : 'text-canvas-muted'}`}>{v.length}/{meta.sinir}</span>
            </section>
          );
        })}
      </div>
      {canSave && (
        <button type="button" className={`${btnPrimary} mt-3`} disabled={save.isPending} onClick={() => save.mutate()}>Metni kaydet</button>
      )}
    </Panel>
  );
}
