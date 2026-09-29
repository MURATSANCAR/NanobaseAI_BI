import { lazy, Suspense, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, Download, FileSpreadsheet, Plus, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, nf, td, th } from '../../../admin/ui';
import Sheet from '../../../editorial/studio/reader/Sheet';
import { EmptyHint } from '../../../components/Explain';
import { FilePick } from '../../../components/FileDrop';
import { useDebounced } from '../../../editorial/kit';
import { Block, HrFrame, Tabs } from '../../parts';
import { Avatar } from '../parts';
import { longDay, portalApi, type ImportResult, type PersonField, type PortalMeta } from '../portalApi';
import PersonSheet from './PersonSheet';

const ContentTabs = lazy(() => import('./ContentTabs'));
const FieldsTab = lazy(() => import('./FieldsTab'));
const LeaveAdmin = lazy(() => import('../../leave/admin/LeaveAdmin'));

/** İK yönetimi (/ik/yonetim): personel özlük kaydı (liste, kart, belge, Excel), portal içeriği (duyuru, evrak deposu,
 *  evrak talepleri, yemek listesi, SSS), alan tanımları ve listeler. Sekmeler yetkiye göre görünür. */

type Tab = 'personel' | 'izinler' | 'izin-ayarlari' | 'talepler' | 'duyurular' | 'evrak' | 'yemek' | 'sss' | 'alanlar' | 'ayarlar' | 'bildirimler';

export default function HrAdmin() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['hr', 'portal', 'meta'], queryFn: portalApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const r = meta.data?.rights;
  const pending = useQuery({ queryKey: ['hr', 'portal', 'admin-requests', 'acik'], queryFn: () => portalApi.adminRequests('acik'), enabled: !!r?.portal });
  const tabs: { key: Tab; label: string; badge?: number | null }[] = [];
  if (r?.view || r?.edit) tabs.push({ key: 'personel', label: 'Personel' });
  if (r?.leave) tabs.push({ key: 'izinler', label: 'İzinler' });
  if (r?.leave || r?.leaveSettings) tabs.push({ key: 'izin-ayarlari', label: 'İzin ayarları' });
  if (r?.portal) {
    tabs.push({ key: 'talepler', label: 'Evrak talepleri', badge: pending.data?.total || null }, { key: 'duyurular', label: 'Duyurular' },
      { key: 'evrak', label: 'Evrak deposu' }, { key: 'yemek', label: 'Yemek listesi' }, { key: 'sss', label: 'Sık sorulan sorular' });
  }
  if (r?.fields || r?.view || r?.edit) tabs.push({ key: 'alanlar', label: 'Alanlar' });
  if (r?.fields || r?.portal) tabs.push({ key: 'ayarlar', label: 'Listeler ve ayarlar' });
  if (r?.portal || r?.leave || r?.leaveSettings) tabs.push({ key: 'bildirimler', label: 'E-posta bildirimleri' });
  const want = params.get('sekme') as Tab | null;
  const tab: Tab | undefined = tabs.find((t) => t.key === want)?.key ?? tabs[0]?.key;
  const setTab = (t: Tab) => {
    const p = new URLSearchParams();
    if (t !== tabs[0]?.key) p.set('sekme', t);
    setParams(p, { replace: true });
  };
  return (
    <HrFrame crumb="İK yönetimi" title="İK yönetimi" back={{ to: '/ik', label: 'İK ana sayfası' }}
      lead="Personel özlük kayıtlarını girin ya da Excel'den yükleyin; izin taleplerini ve bakiyeleri yönetin; duyuru, evrak, yemek listesi ve sık sorulan soruları yönetin; alanları, seçenek listelerini ve hangi alanın hangi sayfada görüneceğini ayarlayın.">
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {meta.isLoading && <Loading />}
      {meta.data && !tabs.length && (
        <Note tone="info">Bu ekranda yetkiniz olan bir bölüm yok. Personel kaydı, portal içeriği ya da alan ayarı için Yönetim → Yetkiler’den rol isteyin.</Note>
      )}
      {meta.data?.me.isAdmin && !r?.sensitive && (
        <Note tone="info">Portal yöneticisisiniz, ama hassas özlük verisi (T.C. kimlik, IBAN, sağlık, belgeler) yöneticiye kendiliğinden verilmez; gerekiyorsa Yönetim → Yetkiler’den kendinize «Hassas özlük verisi» bağlayın (bu değişiklik kayda geçer).</Note>
      )}
      {meta.data && tab && (
        <>
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
          <Suspense fallback={<Loading />}>
            {tab === 'personel' && <People meta={meta.data} />}
            {(tab === 'talepler' || tab === 'duyurular' || tab === 'evrak' || tab === 'yemek' || tab === 'sss') && <ContentTabs tab={tab} meta={meta.data} />}
            {(tab === 'alanlar' || tab === 'ayarlar') && <FieldsTab tab={tab} meta={meta.data} />}
            {(tab === 'izinler' || tab === 'izin-ayarlari' || tab === 'bildirimler') && <LeaveAdmin tab={tab} meta={meta.data} />}
          </Suspense>
        </>
      )}
    </HrFrame>
  );
}

/* ------------------------------------------------------------------ personel listesi */

function People({ meta }: { meta: PortalMeta }) {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState('');
  const [durum, setDurum] = useState('Aktif');
  const [firma, setFirma] = useState('');
  const [departman, setDepartman] = useState('');
  const dq = useDebounced(q, 250);
  const fields = useQuery({ queryKey: ['hr', 'portal', 'fields'], queryFn: portalApi.fields, enabled: ENGINE_ENABLED });
  const list = useQuery({ queryKey: ['hr', 'portal', 'people', dq, durum, firma, departman], queryFn: () => portalApi.people({ q: dq, durum, firma, departman }), enabled: ENGINE_ENABLED });
  const all = useQuery({ queryKey: ['hr', 'portal', 'people', 'hepsi'], queryFn: () => portalApi.people({ durum: 'hepsi' }), enabled: ENGINE_ENABLED });
  const open = params.get('kisi');
  const setOpen = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set('kisi', id); else p.delete('kisi');
    setParams(p, { replace: true });
  };
  const [importing, setImporting] = useState<File | null>(null);
  const fs: PersonField[] = fields.data?.items ?? [];
  const firmaField = fs.find((f) => f.key === 'firma');
  const departmanlar = [...new Set((all.data?.items ?? []).map((x) => String(x.data.departman ?? '')).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'tr'));
  const labelOf = (k: string) => fs.find((f) => f.key === k)?.label ?? k;
  const canEdit = meta.rights.edit;
  return (
    <Block
      title="Personel"
      help="Özlük kaydı İK'nın elle tuttuğu dosyadır; eski personel portalının alanlarıyla birebir. Ayrılan çalışanın kaydı silinmez, durumu «Pasif» yapılır."
      action={canEdit ? (
        <>
          <FilePick label="Excel'den yükle" accept=".xlsx" maxBytes={meta.fileMaxMb * 1024 * 1024} onPick={setImporting}
            hint="Başlık satırı alan adları (boş şablondaki gibi); personel no ile eşleşir." />
          <button type="button" className={btnGhost} onClick={() => void portalApi.exportXlsx(durum === 'hepsi' ? 'hepsi' : durum).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
            <FileSpreadsheet aria-hidden className="h-4 w-4" />Excel'e aktar
          </button>
          <button type="button" className={btnGhost} onClick={() => void portalApi.templateXlsx().catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
            <Download aria-hidden className="h-4 w-4" />Boş şablon
          </button>
          <button type="button" className={btnPrimary} onClick={() => setOpen('new')}><Plus aria-hidden className="h-4 w-4" />Personel ekle</button>
        </>
      ) : undefined}
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ara</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ad, personel no, unvan, ekip, e-posta" />
          </span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Durum</span>
          <select className={field} value={durum} onChange={(e) => setDurum(e.target.value)}>
            {meta.peopleStatus.map((s) => <option key={s} value={s}>{s}</option>)}
            <option value="hepsi">Hepsi</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Firma</span>
          <select className={field} value={firma} onChange={(e) => setFirma(e.target.value)}>
            <option value="">Bütün firmalar</option>
            {(firmaField?.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Departman</span>
          <select className={field} value={departman} onChange={(e) => setDepartman(e.target.value)}>
            <option value="">Bütün departmanlar</option>
            {departmanlar.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
      </div>
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && (
        <div className="mt-3">
          <p className="mb-2 text-[12px] text-canvas-muted">{nf.format(list.data.total)} kayıt</p>
          {list.data.items.length ? (
            <TableWrap>
              <thead>
                <tr><th className={th}>Ad soyad</th><th className={th}>Personel no</th><th className={th}>Departman / ekip</th><th className={th}>Unvan</th><th className={th}>Firma</th><th className={th}>Son işe giriş</th><th className={th}>Eksik</th><th className={th}>Durum</th></tr>
              </thead>
              <tbody>
                {list.data.items.map((x) => (
                  <tr key={x.id} className="border-t border-slate-100">
                    <td className={td}>
                      <button type="button" className="flex min-h-11 items-center gap-2 text-left font-bold text-canvas-violet hover:underline sm:min-h-0" onClick={() => setOpen(x.id)}>
                        <Avatar name={x.adSoyad} src={x.hasPhoto ? `/portal/photo/${x.id}` : null} size={28} />
                        {x.adSoyad}
                      </button>
                    </td>
                    <td className={`${td} font-mono text-[11.5px]`}>{x.idNo}</td>
                    <td className={td}>{[x.data.departman, x.data.ekip].filter(Boolean).join(' / ') || '—'}</td>
                    <td className={td}>{String(x.data.unvan ?? '') || '—'}</td>
                    <td className={td}>{String(x.data.firma ?? '') || '—'}</td>
                    <td className={`${td} whitespace-nowrap`}>{x.data.s_ise_giris_tarihi ? longDay(String(x.data.s_ise_giris_tarihi)) : '—'}</td>
                    <td className={td}>
                      {x.missing.length ? (
                        <span title={x.missing.map(labelOf).join(', ')} className="inline-flex items-center gap-1 text-[12px] font-bold text-amber-700">
                          <AlertTriangle aria-hidden className="h-3.5 w-3.5" />{x.missing.length}
                        </span>
                      ) : <span className="text-[12px] text-canvas-muted">—</span>}
                    </td>
                    <td className={td}><Pill tone={x.durum === 'Aktif' ? 'ok' : 'muted'}>{x.durum}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          ) : (
            <EmptyHint
              title={q || firma || departman || durum !== 'Aktif' ? 'Süzgece uyan kayıt yok' : 'Henüz personel kaydı yok'}
              why={q || firma || departman || durum !== 'Aktif' ? 'Aramayı temizleyin ya da süzgeçleri gevşetin.' : canEdit ? '«Personel ekle» ile tek tek girin ya da «Boş şablon»u indirip doldurun ve «Excel’den yükle» ile aktarın.' : 'İK kayıtları girince liste dolar.'}
            />
          )}
        </div>
      )}
      {fields.data && (
        <PersonSheet id={open} meta={meta} fields={fs} people={all.data?.items ?? []} onClose={() => setOpen(null)} onSaved={(id) => setOpen(id)} />
      )}
      <ImportSheet file={importing} onClose={() => setImporting(null)} labelOf={labelOf} />
    </Block>
  );
}

/* ------------------------------------------------------------------ Excel'den aktarma */

const KIND: Record<ImportResult['rows'][number]['kind'], { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  new: { label: 'Yeni', tone: 'ok' }, update: { label: 'Güncellenecek', tone: 'violet' }, same: { label: 'Değişiklik yok', tone: 'muted' }, error: { label: 'Hata', tone: 'err' },
};

function ImportSheet({ file, onClose, labelOf }: { file: File | null; onClose: () => void; labelOf: (k: string) => string }) {
  const qc = useQueryClient();
  const preview = useQuery({ queryKey: ['hr', 'portal', 'import', file?.name, file?.size, file?.lastModified], queryFn: () => portalApi.importXlsx(file as File, false), enabled: !!file, retry: false, gcTime: 0 });
  const [onlyProblems, setOnlyProblems] = useState(false);
  const apply = useMutation({
    mutationFn: () => portalApi.importXlsx(file as File, true),
    onSuccess: (out) => { toast.success(`${nf.format(out.applied)} kayıt yazıldı.`); void qc.invalidateQueries({ queryKey: ['hr', 'portal'] }); onClose(); },
    onError: (e) => toast.error(errText(e, 'Aktarılamadı.')),
  });
  const d = preview.data;
  const rows = (d?.rows ?? []).filter((r) => !onlyProblems || r.kind === 'error');
  const writes = d ? d.counts.new + d.counts.update : 0;
  return (
    <Sheet open={!!file} modal wide onClose={onClose} title="Excel'den personel aktarma" subtitle={file?.name}>
      {preview.isLoading && <Loading />}
      {preview.error && <Note tone="err">{errText(preview.error, 'Dosya okunamadı.')}</Note>}
      {d && (
        <div className="flex flex-col gap-3">
          <p className="text-[12.5px] leading-snug">
            «{d.sheet}» sayfasında {d.columns.length} kolon tanındı. Personel no ile eşleşir: yoksa yeni kayıt açılır, varsa yalnız dolu hücreler güncellenir (boş hücre var olan bilgiyi silmez). Önce aşağıdaki önizlemeye bakın; hiçbir şey henüz yazılmadı.
          </p>
          {d.ignoredColumns.length > 0 && (
            <Note tone="warn">Tanınmayan ya da yetkiniz dışındaki kolonlar alınmayacak: {d.ignoredColumns.join(', ')}</Note>
          )}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(Object.keys(KIND) as (keyof typeof KIND)[]).map((k) => (
              <div key={k} className="rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{KIND[k].label}</div>
                <div className={`text-[20px] font-extrabold tabular-nums ${k === 'error' && d.counts.error ? 'text-red-700' : ''}`}>{nf.format(d.counts[k])}</div>
              </div>
            ))}
          </div>
          {d.counts.error > 0 && (
            <label className="flex items-center gap-2 text-[12.5px] font-bold">
              <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} className="h-4 w-4" />Yalnız hatalı satırlar
            </label>
          )}
          <TableWrap>
            <thead><tr><th className={th}>Satır</th><th className={th}>Personel no</th><th className={th}>Ad soyad</th><th className={th}>Sonuç</th><th className={th}>Ayrıntı</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.row} className="border-t border-slate-100">
                  <td className={`${td} tabular-nums`}>{r.row}</td>
                  <td className={`${td} font-mono text-[11.5px]`}>{r.idNo || '—'}</td>
                  <td className={td}>{r.adSoyad || '—'}</td>
                  <td className={td}><Pill tone={KIND[r.kind].tone}>{KIND[r.kind].label}</Pill></td>
                  <td className={`${td} text-[12px]`}>
                    {r.errors.length ? <span className="text-red-700">{r.errors.join(' ')}</span> : r.changed.length ? r.changed.map(labelOf).join(', ') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <div className="sticky bottom-0 -mx-4 flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-white/95 px-4 py-3 backdrop-blur">
            {d.counts.error > 0 && <span className="mr-auto text-[12px] font-bold text-red-700">Hatalı satırları Excel’de düzeltip dosyayı yeniden yükleyin.</span>}
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="button" className={btnPrimary} disabled={!!d.counts.error || !writes || apply.isPending} onClick={() => apply.mutate()}>
              {apply.isPending ? 'Yazılıyor…' : `${nf.format(writes)} kaydı yaz`}
            </button>
          </div>
        </div>
      )}
    </Sheet>
  );
}
