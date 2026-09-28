import { useCallback, useMemo, useState, type InputHTMLAttributes } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { STATUS_TONE, fmtDay, fmtMoney, parseNum, tendersApi, type TenderInput, type TenderMeta, type TenderRow } from './api';
import { LeftPill, ScoreBadge, Tabs, TenderFrame } from './parts';
import TenderCalendar from './TenderCalendar';
import DocumentsVault from './DocumentsVault';
import ResultsTab from './ResultsTab';
import PublicSalesTab from './PublicSalesTab';
import SqlInfo from '../components/SqlInfo';

/** M33 İhale takibi: açık ilanlar, takvim, şirket belge arşivi, sonuçlar ve kamu kurumlarına satış.
 *  Sekme ve süzgeçler adres çubuğunda (?sekme=, ?durum=, ?il=, ?tur=, ?q=); bağlantı paylaşılabilir. */

const TABS = [
  { key: 'ilanlar', label: 'İlanlar' },
  { key: 'takvim', label: 'Takvim' },
  { key: 'belgeler', label: 'Belge arşivi' },
  { key: 'sonuclar', label: 'Sonuçlar' },
  { key: 'kamu', label: 'Kamu satışları' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function TenderList() {
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const meta = useQuery({ queryKey: ['tenders', 'meta'], queryFn: tendersApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'ilanlar') as Tab;

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const me = meta.data?.me;
  return (
    <TenderFrame
      title="Okul, kütüphane ve kamu ihaleleri"
      lead="Kamu kurumlarının kitap alımları: ilan kaydı, şartname kalemlerinin katalogla eşleştirilmesi (stok, fiyat), teklif fiyat tablosu, belge kontrol listesi, karar ve sonuç. Portal kuruma teklif göndermez; hazırlık ve kayıt içindir."
      aside={
        me?.canEdit ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnPrimary} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni ihale
            </button>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'ilanlar' ? null : t })} />
      {tab === 'ilanlar' && meta.data && <Listing meta={meta.data} params={params} update={update} />}
      {tab === 'takvim' && <TenderCalendar />}
      {tab === 'belgeler' && meta.data && <DocumentsVault meta={meta.data} />}
      {tab === 'sonuclar' && <ResultsTab />}
      {tab === 'kamu' && <PublicSalesTab />}
      {meta.data && <NewTenderSheet open={creating} meta={meta.data} onClose={() => setCreating(false)} />}
    </TenderFrame>
  );
}

function Listing({ meta, params, update }: { meta: TenderMeta; params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const durum = params.get('durum') ?? 'acik';
  const il = params.get('il') ?? '';
  const tur = params.get('tur') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const list = useQuery({
    queryKey: ['tenders', 'list', durum, il, tur, dq],
    queryFn: () => tendersApi.list({ durum, il, kurumTuru: tur, q: dq }),
    enabled: ENGINE_ENABLED,
  });
  const items = list.data?.items ?? [];
  const soon = items.filter((t) => t.kalanGun !== null && t.kalanGun >= 0 && t.kalanGun <= 7 && ['yeni', 'inceleniyor', 'basvurulacak'].includes(t.durum)).length;
  const pending = items.filter((t) => t.onayBekliyor).length;
  const counts = list.data?.durumSayilari ?? {};
  const open = meta.acikDurumlar.reduce((s, k) => s + (counts[k] ?? 0), 0);

  return (
    <>
      <KpiRow>
        <Kpi label="Açık ihale" value={String(open)} help="Yeni, inceleniyor, başvurulacak, teklif verildi" active={durum === 'acik'} onClick={() => update({ durum: null })} info={<SqlInfo k={list.data?.kaynaklar} alan="sayac.acik" label="Açık ihale" />} />
        <Kpi label="7 gün içinde son tarih" value={String(soon)} help="Listede, başvuru öncesi aşamada" info={<SqlInfo k={list.data?.kaynaklar} alan="sayac.yediGun" label="7 gün içinde son tarih" />} />
        <Kpi label="Onay bekleyen karar" value={String(pending)} help="Başvuru kararı ve teklif fiyatı" info={<SqlInfo k={list.data?.kaynaklar} alan="sayac.onayBekleyen" label="Onay bekleyen karar" />} />
        <Kpi label="Kazanılan" value={String(counts.kazanildi ?? 0)} help={`Kaybedilen ${counts.kaybedildi ?? 0}`} active={durum === 'kazanildi'} onClick={() => update({ durum: 'kazanildi' })} info={<SqlInfo k={list.data?.kaynaklar} alan="durumSayilari" label="Kazanılan ve kaybedilen" />} />
      </KpiRow>
      <Note tone="info">
        Liste yalnız portala girilen ilanları içerir. Resmî kaynaktan otomatik ilan içe alma {meta.ayarlar.watchEnabled ? 'ikinci sürümde gelecek' : 'bu ortamda kapalı'};
        ilanlar elle ya da şartname dosyasıyla girilir.
      </Note>
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Kurum, konu, ihale no, il" onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null }); }} />
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={durum} onChange={(e) => update({ durum: e.target.value === 'acik' ? null : e.target.value })}>
              <option value="acik">Açık olanlar</option>
              <option value="kapali">Kapanmış olanlar</option>
              <option value="hepsi">Hepsi</option>
              {Object.entries(meta.durumlar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kurum türü</span>
            <select className={field} value={tur} onChange={(e) => update({ tur: e.target.value || null })}>
              <option value="">Hepsi</option>
              {Object.entries(meta.kurumTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İl</span>
            <select className={field} value={il} onChange={(e) => update({ il: e.target.value || null })}>
              <option value="">Hepsi</option>
              {(list.data?.iller ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-3 flex flex-col gap-2">
          {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
          {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
          {list.data && !items.length && (
            <div className="py-8 text-center text-[12.5px] text-canvas-muted">
              Bu süzgeçte ihale yok.{meta.me.canEdit ? ' «Yeni ihale» ile ilk kaydı girin.' : ''}
            </div>
          )}
          {items.map((t) => <TenderCard key={t.id} t={t} />)}
        </div>
        {list.data && <div className="mt-2 flex items-center justify-end gap-1 font-mono text-[11.5px] text-canvas-muted">{list.data.total} ihale<SqlInfo k={list.data.kaynaklar} alan="items[]" label="İlanlar: son teklif, kalan gün, yaklaşık tutar" /></div>}
      </Panel>
    </>
  );
}

function TenderCard({ t }: { t: TenderRow }) {
  return (
    <Link
      to={`/ihale/${t.id}`}
      className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1fr)_150px_120px_110px] md:items-center"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={STATUS_TONE[t.durum]}>{t.durumAdi}</Pill>
          {t.onayBekliyor && <Pill tone="warn">Onay bekliyor</Pill>}
          {t.kitapIlani?.sonuc === 'hayir' && <Pill tone="err">Kitap alımı olmayabilir</Pill>}
          <span className="text-[11px] font-semibold text-canvas-muted">{t.kurumTuruAdi}{t.il ? ` · ${t.il}` : ''}</span>
        </div>
        <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{t.kurum}</div>
        <div className="line-clamp-2 break-words text-[12px] leading-snug text-canvas-muted">{t.konu}</div>
      </div>
      <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-1">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Son teklif</span>
        <span className="font-mono text-[12px] font-bold tabular-nums">{fmtDay(t.sonTeklifTarihi)}</span>
        {t.sonTeklifTarihi && ['yeni', 'inceleniyor', 'basvurulacak'].includes(t.durum) && <LeftPill days={t.kalanGun} />}
      </div>
      <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-1">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Kalem</span>
        <span className="font-mono text-[12px] tabular-nums">{t.kalem ? `${t.eslesen}/${t.kalem} eşleşti` : 'kalem yok'}</span>
        {t.yaklasikTutar !== null && <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">{fmtMoney(t.yaklasikTutar)}</span>}
      </div>
      <div className="flex items-center gap-2 md:justify-end">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Uygunluk</span>
        <ScoreBadge value={t.uygunlukPuani} />
      </div>
    </Link>
  );
}

const EMPTY = { kurum: '', kurumTuru: 'okul', il: '', konu: '', usul: '', kaynakNo: '', yaklasikTutar: '', ilanTarihi: '', sonTarih: '', sonSaat: '', yetkili: '', notlar: '' };

function NewTenderSheet({ open, meta, onClose }: { open: boolean; meta: TenderMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [f, setF] = useState(EMPTY);
  const set = (k: keyof typeof EMPTY) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const amount = useMemo(() => (f.yaklasikTutar.trim() ? parseNum(f.yaklasikTutar) : null), [f.yaklasikTutar]);
  const create = useMutation({
    mutationFn: () => {
      const b: TenderInput = {
        kurum: f.kurum.trim(), kurumTuru: f.kurumTuru, il: f.il.trim(), konu: f.konu.trim(), kaynakNo: f.kaynakNo.trim(),
        yetkili: f.yetkili.trim(), notlar: f.notlar.trim(), yaklasikTutar: amount, ilanTarihi: f.ilanTarihi || null,
        sonTeklifTarihi: f.sonTarih ? (f.sonSaat ? `${f.sonTarih}T${f.sonSaat}` : f.sonTarih) : null,
      };
      if (f.usul) b.usul = f.usul;
      return tendersApi.create(b);
    },
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ['tenders'] });
      toast.success('İhale kaydedildi.');
      setF(EMPTY);
      onClose();
      nav(`/ihale/${t.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const bad = !f.kurum.trim() || !f.konu.trim() || (f.yaklasikTutar.trim() !== '' && amount === null);
  const inp = (k: keyof typeof EMPTY, lbl: string, props: InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{lbl}</span>
      <input className={field} value={f[k]} onChange={(e) => set(k)(e.target.value)} {...props} />
    </label>
  );
  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni ihale" subtitle="İlan bilgilerini girin; şartname dosyasını ve kalem listesini kayıttan sonra yüklersiniz.">
      <div className="flex flex-col gap-3 text-[13px]">
        {inp('kurum', 'Kurum *', { placeholder: 'Örn. İstanbul İl Milli Eğitim Müdürlüğü' })}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kurum türü *</span>
            <select className={field} value={f.kurumTuru} onChange={(e) => set('kurumTuru')(e.target.value)}>
              {Object.entries(meta.kurumTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          {inp('il', 'İl')}
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Konu *</span>
          <textarea className={`${field} min-h-[72px]`} value={f.konu} onChange={(e) => set('konu')(e.target.value)} placeholder="İlandaki iş tanımı" />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Usul</span>
            <select className={field} value={f.usul} onChange={(e) => set('usul')(e.target.value)}>
              <option value="">Belirtilmedi</option>
              {Object.entries(meta.usuller).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          {inp('kaynakNo', 'İhale kayıt no')}
          {inp('yaklasikTutar', 'Yaklaşık tutar (₺)', { inputMode: 'decimal' })}
          {inp('ilanTarihi', 'İlan tarihi', { type: 'date' })}
          {inp('sonTarih', 'Son teklif tarihi', { type: 'date' })}
          {inp('sonSaat', 'Son teklif saati', { type: 'time' })}
        </div>
        {inp('yetkili', 'Kurum yetkilisi (yalnız bu kayıtta tutulur)')}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[56px]`} value={f.notlar} onChange={(e) => set('notlar')(e.target.value)} />
        </label>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnPrimary} disabled={bad || create.isPending} onClick={() => create.mutate()}>
            {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}
