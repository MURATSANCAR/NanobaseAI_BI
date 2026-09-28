import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileText, Loader2, Pencil, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { ReadingBadge, ReadingNote } from '../components/ReadingBadge';
import Sheet from '../editorial/studio/reader/Sheet';
import {
  STATUS_TONE, fmtDay, fmtMoney, fmtPct, parseNum, tendersApi,
  type Job, type Quote, type Summary, type TenderDetail as Detail, type TenderInput, type TenderMeta,
} from './api';
import { AskSheet, Fact, LeftPill, ScoreBadge, Tabs, TenderFrame } from './parts';
import { FileDrop } from '../components/FileDrop';
import { MB } from '../components/fileDropRules';
import TenderItems from './TenderItems';
import TenderChecklist from './TenderChecklist';
import TenderDecision from './TenderDecision';
import TenderRisks from './TenderRisks';
import SqlInfo from '../components/SqlInfo';

/** Tek ihale: Özet · Kalemler · Belgeler · Karar · Sonuç. Sekme adres çubuğunda (?sekme=). Uzun işler (şartname özeti,
 *  kalem eşleştirme) arka planda koşar; ekran iki saniyede bir ilerlemeyi okur. */

const TABS = [
  { key: 'ozet', label: 'Özet' },
  { key: 'kalemler', label: 'Kalemler' },
  { key: 'belgeler', label: 'Belgeler' },
  { key: 'karar', label: 'Karar' },
  { key: 'sonuc', label: 'Sonuç' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function TenderDetailPage() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['tenders', 'meta'], queryFn: tendersApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const detail = useQuery({ queryKey: ['tenders', 'detail', id], queryFn: () => tendersApi.detail(id), enabled: ENGINE_ENABLED && !!id });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'ozet') as Tab;
  const setTab = (t: Tab) => {
    const p = new URLSearchParams(params);
    if (t === 'ozet') p.delete('sekme');
    else p.set('sekme', t);
    setParams(p, { replace: true });
  };

  const running = detail.data?.isler.find((j) => j.durum === 'calisiyor' || j.durum === 'sirada') ?? null;
  const job = useJobWatch(id, running, () => qc.invalidateQueries({ queryKey: ['tenders'] }));

  const d = detail.data;
  const m = meta.data;
  if (!ENGINE_ENABLED) return <TenderFrame back title="İhale" lead=""><Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note></TenderFrame>;
  if (detail.error) return <TenderFrame back title="İhale" lead=""><Note tone="err">{errText(detail.error, 'İhale okunamadı.')}</Note></TenderFrame>;
  if (!d || !m) return <TenderFrame back title="İhale" lead="Yükleniyor…"><div className="py-10 text-center text-[12px] text-canvas-muted">Yükleniyor…</div></TenderFrame>;

  const badge = {
    kalemler: (d.toplamlar.durumlar.oneri ?? 0) + (d.toplamlar.durumlar.belirsiz ?? 0) || null,
    belgeler: d.kontrolListesi.filter((c) => c.zorunlu && c.durum !== 'var').length || null,
    karar: d.kararlar.some((k) => k.durum === 'onayda') ? 1 : null,
  } as Record<string, number | null>;

  return (
    <TenderFrame
      back
      title={d.kurum}
      detail={d.kurum}
      lead={d.konu}
      aside={
        <div className="grid grid-cols-2 gap-2">
          <Fact label="Durum" value={<Pill tone={STATUS_TONE[d.durum]}>{d.durumAdi}</Pill>} help={d.sorumlu ? `Sorumlu: ${d.sorumlu}` : undefined} />
          <Fact label="Uygunluk" value={<ScoreBadge value={d.uygunlukPuani} />} help="Eşleşme, stok, belge, süre" info={<SqlInfo k={d.kaynaklar} alan="uygunlukPuani" label="Uygunluk puanı" />} />
          <Fact label="Son teklif" value={fmtDay(d.sonTeklifTarihi)} help={d.sonTeklifTarihi ? <LeftPill days={d.kalanGun} /> : 'Girilmedi'} info={<SqlInfo k={d.kaynaklar} alan="kalanGun" label="Son teklif kalan gün" />} />
          <Fact label="Teklif ara toplamı" value={fmtMoney(d.toplamlar.araToplam)} help={`${d.toplamlar.fiyatli} kalem, KDV hariç`} info={<SqlInfo k={d.kaynaklar} alan="toplamlar" label="Teklif ara toplamı" />} />
        </div>
      }
    >
      {job && <JobBar job={job} />}
      <Tabs tabs={TABS.map((t) => ({ ...t, badge: badge[t.key] ?? null }))} value={tab} onChange={setTab} />
      {tab === 'ozet' && <Overview d={d} meta={m} busy={!!running} />}
      {tab === 'kalemler' && <TenderItems d={d} meta={m} busy={!!running} />}
      {tab === 'belgeler' && <TenderChecklist d={d} meta={m} />}
      {(tab === 'karar' || tab === 'sonuc') && <TenderDecision d={d} meta={m} view={tab} />}
    </TenderFrame>
  );
}

/** Koşan işi iki saniyede bir okur; bitince detay tazelenir ve sonuç bildirilir. */
function useJobWatch(tid: string, running: Job | null, onDone: () => void): Job | null {
  const jid = running?.id ?? null;
  const q = useQuery({
    queryKey: ['tenders', 'job', tid, jid],
    queryFn: () => tendersApi.job(tid, jid as string),
    enabled: !!jid,
    refetchInterval: (s) => (s.state.data && !['calisiyor', 'sirada'].includes(s.state.data.durum) ? false : 2000),
  });
  const seen = useRef<string | null>(null);
  useEffect(() => {
    const j = q.data;
    if (!j || ['calisiyor', 'sirada'].includes(j.durum) || seen.current === j.id) return;
    seen.current = j.id;
    onDone();
    if (j.durum === 'bitti') toast.success(j.tur === 'ozet' ? 'Şartname özeti hazır.' : j.tur === 'risk' ? 'Riskli koşullar işaretlendi.' : 'Eşleştirme bitti.');
    else toast.error(j.hata || 'İş tamamlanamadı.');
  }, [q.data, onDone]);
  return jid ? q.data ?? running : null;
}

function JobBar({ job }: { job: Job }) {
  const pct = job.toplam ? Math.round((100 * job.ilerleme) / job.toplam) : 0;
  const label = job.tur === 'ozet' ? 'Zeki AI şartnameyi okuyor' : job.tur === 'risk' ? 'Şartnamedeki riskli koşullar işaretleniyor' : 'Kalemler katalogla eşleştiriliyor';
  return (
    <div className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl px-3 py-2 shadow-glass-float" role="status" aria-live="polite">
      <Loader2 aria-hidden className="h-4 w-4 animate-spin text-canvas-violet" />
      <span className="text-[12.5px] font-bold">{label}</span>
      <div className="relative h-1.5 min-w-[120px] flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className="absolute inset-y-0 left-0 rounded-full bg-canvas-violet" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">{job.toplam ? `${job.ilerleme}/${job.toplam}` : 'başlıyor'}</span>
    </div>
  );
}

function Overview({ d, meta, busy }: { d: Detail; meta: TenderMeta; busy: boolean }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [fileTur, setFileTur] = useState<'sartname' | 'ek' | 'belge'>('sartname');
  const can = meta.me.canEdit;
  const invalidate = () => qc.invalidateQueries({ queryKey: ['tenders'] });

  const upload = useMutation({
    mutationFn: (f: File) => tendersApi.addFile(d.id, f, fileTur),
    onSuccess: (f) => { invalidate(); toast.success(`${f.ad} yüklendi.`); },
    onError: (e) => toast.error(errText(e, 'Yüklenemedi.') ?? ''),
  });
  const delFile = useMutation({
    mutationFn: (fid: string) => tendersApi.deleteFile(d.id, fid),
    onSuccess: () => { invalidate(); toast.success('Dosya silindi.'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const summarize = useMutation({
    mutationFn: (fid: string) => tendersApi.summarize(d.id, fid),
    onSuccess: () => { invalidate(); toast.success('Şartname özeti başladı.'); },
    onError: (e) => toast.error(errText(e, 'Başlatılamadı.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: () => tendersApi.remove(d.id),
    onSuccess: () => { invalidate(); toast.success('İhale silindi.'); nav('/ihale'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });

  const u = d.uygunluk?.parcalar;
  const w: Record<string, number> = d.uygunluk?.agirliklar ?? {};
  const s: Summary = d.ozet ?? {};
  const cls = d.kitapIlani?.sonuc;
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-[16px] font-extrabold tracking-tight">İlan bilgileri</h2>
          {can && (
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} onClick={() => setEditing(true)}>
                <Pencil aria-hidden className="h-4 w-4" />
                Düzenle
              </button>
              {!d.kararlar.length && !d.sonuc && (
                <button type="button" className={btnGhost} aria-label="İhaleyi sil" onClick={() => setRemoving(true)}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </div>
          )}
        </div>
        {cls && (
          <div className="mt-2">
            <Note tone={cls === 'evet' ? 'ok' : cls === 'hayir' ? 'err' : 'warn'}>
              Zeki AI: ilan konusu {cls === 'evet' ? 'kitap/yayın alımı' : cls === 'hayir' ? 'kitap alımı gibi görünmüyor' : 'kitap alımı olup olmadığı belirsiz'}
              {d.kitapIlani.olasilik != null ? <> (olasılık {fmtPct(d.kitapIlani.olasilik)}<SqlInfo k={d.kaynaklar} alan="kitapIlani" label="Kitap ilanı olasılığı" className="ml-0.5" />)</> : ''}.
            </Note>
          </div>
        )}
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Fact label="Kurum türü" value={d.kurumTuruAdi} help={d.il ?? undefined} />
          <Fact label="Usul" value={d.usulAdi ?? '—'} help={d.kaynakNo ? `İhale no ${d.kaynakNo}` : d.kaynakAdi} />
          <Fact label="Yaklaşık tutar" value={fmtMoney(d.yaklasikTutar)} info={<SqlInfo k={d.kaynaklar} alan="yaklasikTutar" label="Yaklaşık tutar" />} />
          <Fact label="İlan tarihi" value={fmtDay(d.ilanTarihi)} />
          <Fact label="Teslim süresi" value={d.teslimSuresi ?? '—'} />
          <Fact label="Teminat" value={fmtMoney(d.teminatTutari)} info={<SqlInfo k={d.kaynaklar} alan="teminatTutari" label="Teminat tutarı" />} help={d.teminatIadeTarihi ? `İade ${fmtDay(d.teminatIadeTarihi)}` : undefined} />
          <Fact label="Fiyat oranı" value={fmtPct(d.fiyatOrani)} help={d.fiyatOraniKaynak ?? undefined} info={<SqlInfo k={d.kaynaklar} alan="fiyatOrani" label="Fiyat oranı" />} />
          <Fact label="Kurum yetkilisi" value={d.yetkili ?? '—'} help="Yalnız bu kayıtta tutulur" />
        </div>
        {d.notlar && <p className="mt-3 whitespace-pre-wrap break-words text-[12.5px]">{d.notlar}</p>}
      </Panel>

      <Panel>
        <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">Uygunluk puanı<SqlInfo k={d.kaynaklar} alan="uygunluk" label="Uygunluk puanı parçaları" /></h2>
        <p className="text-[12px] text-canvas-muted">Ölçülemeyen parça puana girmez; ağırlıklar kalanlara göre yeniden dağılır. Karar insanındır.</p>
        <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-4">
          <Fact label={`Eşleşen kalem (ağırlık ${w.eslesme ?? '—'})`} value={fmtPct(u?.eslesme)} />
          <Fact label={`Stoğu yeten (ağırlık ${w.stok ?? '—'})`} value={fmtPct(u?.stok)} />
          <Fact label={`Hazır zorunlu belge (ağırlık ${w.belge ?? '—'})`} value={fmtPct(u?.belge)} />
          <Fact label={`Süre (ağırlık ${w.sure ?? '—'})`} value={fmtPct(u?.sure)} help={d.kalanGun != null ? `${d.kalanGun} gün` : 'Son tarih yok'} />
        </div>
      </Panel>

      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[16px] font-extrabold tracking-tight">Şartname ve ekler</h2>
            <p className="text-[12px] text-canvas-muted">Şartnameden Zeki AI özeti çıkarılır; kalem listesi «Kalemler» sekmesinden bu dosyadan alınır.</p>
          </div>
        </div>
        {/* Birincil eylem: şartname/ek yükleme. Yetkisi olmayan kişi de görür (kilitli, gereken yetki yazılı). */}
        <div className="mt-2.5 grid gap-2 sm:grid-cols-[minmax(0,200px)_minmax(0,1fr)] sm:items-start">
          <label className="block min-w-0">
            <span className={labelCls}>Dosya türü</span>
            <select className={`${field} mt-1`} value={fileTur} onChange={(e) => setFileTur(e.target.value as typeof fileTur)}>
              <option value="sartname">Şartname</option>
              <option value="ek">Ek / kalem listesi</option>
              <option value="belge">İhaleye özel belge</option>
            </select>
          </label>
          <FileDrop
            title={fileTur === 'sartname' ? 'Şartname yükle' : fileTur === 'ek' ? 'Ek / kalem listesi yükle' : 'İhaleye özel belge yükle'}
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.jpg,.jpeg,.png"
            maxBytes={meta.ayarlar.fileMaxMb ? meta.ayarlar.fileMaxMb * MB : undefined}
            feature="ihale.duzenle"
            allowed={can}
            busy={upload.isPending}
            onPick={(f) => upload.mutate(f)}
          />
        </div>
        <ul className="mt-3 flex flex-col gap-1.5">
          {!d.dosyalar.length && <li className="text-[12.5px] text-canvas-muted">Dosya yok. Şartnameyi yukarıdaki alana bırakın.</li>}
          {d.dosyalar.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-100 bg-white/80 px-3 py-2">
              <FileText aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted" />
              <span className="min-w-0 flex-1 break-all text-[12.5px] font-semibold">{f.ad}</span>
              <Pill tone="muted">{f.tur === 'sartname' ? 'Şartname' : f.tur === 'ek' ? 'Ek' : 'Belge'}</Pill>
              <span className="text-[11px] text-canvas-muted">{Math.max(1, Math.round(f.boyut / 1024))} KB · {f.yukleyen}</span>
              <div className="flex gap-1.5">
                <a className={btnGhost} href={tendersApi.fileUrl(d.id, f.id)} target="_blank" rel="noreferrer" aria-label={`${f.ad} indir`}>
                  <Download aria-hidden className="h-4 w-4" />
                </a>
                {can && meta.modelVar && /\.(pdf|docx|txt|csv|xlsx)$/i.test(f.ad) && (
                  <button type="button" className={btnGhost} disabled={busy || summarize.isPending} onClick={() => summarize.mutate(f.id)}>
                    <Sparkles aria-hidden className="h-4 w-4" />
                    Zeki AI özeti
                  </button>
                )}
                {can && (
                  <button type="button" className={btnGhost} aria-label={`${f.ad} sil`} disabled={delFile.isPending} onClick={() => delFile.mutate(f.id)}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Panel>

      {(s.konu || s.belgeler?.length || s.kosullar?.length) ? (
        <Panel>
          <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">Şartname özeti (Zeki AI)<SqlInfo k={d.kaynaklar} alan="ozet" label="Şartname özeti" /></h2>
          <Note tone="warn">Taslaktır: her madde şartnameden alıntılanan cümleyle gösterilir; hukuk ve ihale sorumlusu onaylamadan beyan olarak kullanılmaz.</Note>
          <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-3">
            {([['Konu', s.konu], ['Teslim süresi', s.teslimSuresi], ['Teminat', s.teminat]] as Array<[string, Quote | null | undefined]>).map(([lbl, x]) => (
              <Fact key={lbl} label={lbl} value={x?.deger ?? '—'} help={x?.kaynak ? <><q className="italic">{x.kaynak}</q> <ReadingBadge okuma={x.okuma} guven={x.guven} sayfa={x.sayfa} esik={s.okuma?.esik} /></> : undefined} />
            ))}
          </div>
          {([['İstenen belgeler', s.belgeler ?? []], ['Kritik koşullar', s.kosullar ?? []]] as Array<[string, Quote[]]>).map(([lbl, list]) =>
            list.length ? (
              <div key={lbl} className="mt-3">
                <h3 className="text-[12px] font-bold uppercase tracking-wide text-canvas-muted">{lbl}</h3>
                <ul className="mt-1 flex flex-col gap-1">
                  {list.map((x, i) => (
                    <li key={i} className="rounded-lg bg-white/80 px-3 py-1.5 text-[12.5px]">
                      <div className="font-semibold">{x.deger}</div>
                      <q className="text-[11.5px] italic text-canvas-muted">{x.kaynak}</q>{' '}
                      <ReadingBadge okuma={x.okuma} guven={x.guven} sayfa={x.sayfa} esik={s.okuma?.esik} />
                    </li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
          <div className="mt-2 text-[11.5px] text-canvas-muted">
            {s.dosya ? `Kaynak: ${s.dosya}. ` : ''}{s.parca ? `${s.parca} bölümde okundu. ` : ''}
            {s.atilan ? `${s.atilan} madde şartnamede alıntısı bulunamadığı için atıldı.` : ''}
          </div>
          <ReadingNote reading={s.okuma} />
        </Panel>
      ) : null}

      <TenderRisks d={d} canEdit={can} modelVar={meta.modelVar} busy={busy} />

      <EditSheet open={editing} d={d} meta={meta} onClose={() => setEditing(false)} />
      <AskSheet
        open={removing}
        title="İhaleyi sil"
        message="Yanlış girilmiş kayıt içindir: ihale, kalemleri, kontrol listesi ve dosyaları silinir. Kararı ya da sonucu olan ihale silinmez."
        confirm="Sil"
        danger
        busy={remove.isPending}
        onClose={() => setRemoving(false)}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}

function EditSheet({ open, d, meta, onClose }: { open: boolean; d: Detail; meta: TenderMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const init = () => ({
    kurum: d.kurum, kurumTuru: d.kurumTuru, il: d.il ?? '', konu: d.konu, usul: d.usul ?? '', kaynakNo: d.kaynakNo ?? '',
    yaklasikTutar: d.yaklasikTutar?.toString().replace('.', ',') ?? '', ilanTarihi: d.ilanTarihi ?? '',
    sonTarih: d.sonTeklifTarihi?.slice(0, 10) ?? '', sonSaat: d.sonTeklifTarihi?.slice(11, 16) ?? '',
    teslimSuresi: d.teslimSuresi ?? '', teminatTutari: d.teminatTutari?.toString().replace('.', ',') ?? '',
    teminatIadeTarihi: d.teminatIadeTarihi ?? '', yetkili: d.yetkili ?? '', sorumlu: d.sorumlu ?? '', notlar: d.notlar ?? '',
    durum: d.durum as string, fiyatOrani: d.fiyatOrani != null ? String(Math.round(d.fiyatOrani * 10000) / 100).replace('.', ',') : '',
  });
  const [f, setF] = useState(init);
  const [seen, setSeen] = useState(false);
  if (open !== seen) {
    setSeen(open);
    if (open) setF(init());
  }
  const set = (k: keyof ReturnType<typeof init>) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      const ratio = parseNum(f.fiyatOrani);
      const b: TenderInput = {
        kurum: f.kurum.trim(), kurumTuru: f.kurumTuru, il: f.il.trim(), konu: f.konu.trim(), kaynakNo: f.kaynakNo.trim(),
        yaklasikTutar: parseNum(f.yaklasikTutar), ilanTarihi: f.ilanTarihi || null,
        sonTeklifTarihi: f.sonTarih ? (f.sonSaat ? `${f.sonTarih}T${f.sonSaat}` : f.sonTarih) : null,
        teslimSuresi: f.teslimSuresi.trim(), teminatTutari: parseNum(f.teminatTutari), teminatIadeTarihi: f.teminatIadeTarihi || null,
        yetkili: f.yetkili.trim(), sorumlu: f.sorumlu.trim(), notlar: f.notlar.trim(),
      };
      if (f.usul) b.usul = f.usul;
      if (f.durum !== d.durum) b.durum = f.durum as TenderInput['durum'];
      const oldPct = d.fiyatOrani != null ? Math.round(d.fiyatOrani * 10000) / 100 : null;
      if (ratio !== null && ratio !== oldPct) b.fiyatOrani = ratio / 100;
      return tendersApi.update(d.id, b);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenders'] }); toast.success('Kaydedildi.'); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const statusChoices = Array.from(new Set([d.durum, ...meta.elleDurumlar]));
  const inp = (k: keyof ReturnType<typeof init>, lbl: string, type = 'text') => (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{lbl}</span>
      <input className={field} type={type} inputMode={type === 'text' && /Tutar|Oran/.test(lbl) ? 'decimal' : undefined} value={f[k]} onChange={(e) => set(k)(e.target.value)} />
    </label>
  );
  return (
    <Sheet open={open} modal wide onClose={onClose} title="İhaleyi düzenle">
      <div className="flex flex-col gap-3 text-[13px]">
        {inp('kurum', 'Kurum')}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Konu</span>
          <textarea className={`${field} min-h-[64px]`} value={f.konu} onChange={(e) => set('konu')(e.target.value)} />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kurum türü</span>
            <select className={field} value={f.kurumTuru} onChange={(e) => set('kurumTuru')(e.target.value)}>
              {Object.entries(meta.kurumTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          {inp('il', 'İl')}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Usul</span>
            <select className={field} value={f.usul} onChange={(e) => set('usul')(e.target.value)}>
              <option value="">Belirtilmedi</option>
              {Object.entries(meta.usuller).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          {inp('kaynakNo', 'İhale kayıt no')}
          {inp('yaklasikTutar', 'Yaklaşık tutar (₺)')}
          {inp('ilanTarihi', 'İlan tarihi', 'date')}
          {inp('sonTarih', 'Son teklif tarihi', 'date')}
          {inp('sonSaat', 'Son teklif saati', 'time')}
          {inp('teslimSuresi', 'Teslim süresi')}
          {inp('teminatTutari', 'Teminat tutarı (₺)')}
          {inp('teminatIadeTarihi', 'Teminat iade tarihi', 'date')}
          {inp('fiyatOrani', 'Fiyat oranı (% liste fiyatı)')}
          {inp('yetkili', 'Kurum yetkilisi')}
          {inp('sorumlu', 'Sorumlu (portal kullanıcısı)')}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={f.durum} onChange={(e) => set('durum')(e.target.value)}>
              {statusChoices.map((k) => <option key={k} value={k}>{meta.durumlar[k]}</option>)}
            </select>
          </label>
        </div>
        <p className="text-[11.5px] text-canvas-muted">
          Başvuru kararı «Karar» sekmesinden onayla, kazanıldı/kaybedildi «Sonuç» sekmesinden girilir. Fiyat oranı değişince elle girilmemiş birim fiyatlar yeniden hesaplanır.
        </p>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[56px]`} value={f.notlar} onChange={(e) => set('notlar')(e.target.value)} />
        </label>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} disabled={!f.kurum.trim() || !f.konu.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}
