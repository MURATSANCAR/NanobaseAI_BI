import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { useDebounced } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDateTime, fmtDay, hrApi, type Employee, type HrMeta, type SyncPreview, type Unit } from '../hrApi';
import { Block, HrFrame, Tabs } from '../parts';

/** İK-0 ortak kayıtlar: çalışan ve birim (CRM ∩ AD'den öneri, İK onayıyla), aydınlatma metni sürümleri, saklama süreleri,
 *  imha tutanakları ve erişim kaydı. CRM'e hiçbir şey yazılmaz. M56–M58 bu kayıtları kullanır. */

const TABS = [
  { key: 'calisanlar', label: 'Çalışanlar' },
  { key: 'birimler', label: 'Birimler' },
  { key: 'aydinlatma', label: 'Aydınlatma metinleri' },
  { key: 'saklama', label: 'Saklama ve imha' },
  { key: 'erisim', label: 'Erişim kaydı' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function HrRecordsScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'calisanlar') as Tab;
  const meta = useQuery({ queryKey: ['hr', 'meta'], queryFn: hrApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const keys = new Set(meta.data?.me.keys ?? []);
  const can = (k: string) => keys.has(`ozellik:ik.${k}`);
  const setTab = (t: Tab) => {
    const p = new URLSearchParams(params);
    if (t === 'calisanlar') p.delete('sekme');
    else p.set('sekme', t);
    setParams(p, { replace: true });
  };
  return (
    <HrFrame
      crumb="Çalışan ve KVKK kayıtları"
      title="Çalışan ve KVKK kayıtları"
      lead="İnsan kaynakları modüllerinin ortak kaydı. Çalışan ve birim listesi CRM ve Active Directory'den öneri olarak gelir, İK onaylayınca yazılır; CRM'e yazılmaz. T.C. kimlik no, adres, ücret ve sağlık bilgisi tutulmaz."
    >
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {meta.data?.me.isAdmin && !meta.data.settings.adminSeesPersonal && !can('kvkk-yonet') && (
        <Note tone="info">Yöneticisiniz, ama İK kişisel veri yetkileri yöneticiye kendiliğinden verilmez; gerekiyorsa Yetkiler ekranından kendinize rol bağlayın (değişiklik kaydına düşer).</Note>
      )}
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {meta.data && tab === 'calisanlar' && <Employees meta={meta.data} canEdit={can('calisan-yonet')} />}
      {meta.data && tab === 'birimler' && <Units canEdit={can('calisan-yonet')} />}
      {meta.data && tab === 'aydinlatma' && <Notices meta={meta.data} canEdit={can('kvkk-yonet')} />}
      {meta.data && tab === 'saklama' && <Retention canEdit={can('kvkk-yonet')} canRuns={can('kvkk-yonet') || can('erisim-kaydi')} />}
      {meta.data && tab === 'erisim' && (can('erisim-kaydi') ? <AccessLog /> : <Note tone="info">Erişim kaydı rolünüzde yok.</Note>)}
    </HrFrame>
  );
}

/* ------------------------------------------------------------------ çalışanlar */

function Employees({ meta, canEdit }: { meta: HrMeta; canEdit: boolean }) {
  const [status, setStatus] = useState('aktif');
  const [unit, setUnit] = useState('');
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [editing, setEditing] = useState<Employee | 'new' | null>(null);
  const [syncing, setSyncing] = useState(false);
  const units = useQuery({ queryKey: ['hr', 'units'], queryFn: hrApi.units, enabled: ENGINE_ENABLED });
  const list = useQuery({ queryKey: ['hr', 'employees', status, unit, dq], queryFn: () => hrApi.employees({ status, unit, q: dq }), enabled: ENGINE_ENABLED });
  return (
    <Block
      title="Çalışanlar"
      help="Elle düzeltilen alan (kaynağı «İK») eşitlemede ezilmez. Bilgisayar kullanmayan çalışan elle eklenir."
      action={canEdit ? (
        <>
          <button type="button" className={btnGhost} onClick={() => setSyncing(true)}>
            <RefreshCw aria-hidden className="h-4 w-4" />
            CRM ve AD'den eşitle
          </button>
          <button type="button" className={btnPrimary} onClick={() => setEditing('new')}>
            <Plus aria-hidden className="h-4 w-4" />
            Çalışan ekle
          </button>
        </>
      ) : undefined}
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1.4fr_1fr_1fr]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ara</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ad, hesap, unvan, birim" />
          </span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Durum</span>
          <select className={field} value={status} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(meta.employeeStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            <option value="hepsi">Hepsi</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Birim</span>
          <select className={field} value={unit} onChange={(e) => setUnit(e.target.value)}>
            <option value="">Bütün birimler</option>
            {(units.data?.items ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </label>
      </div>
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      {list.data && (
        <div className="mt-3">
          <TableWrap>
            <table className="w-full min-w-[640px] text-[12.5px]">
              <thead>
                <tr><th className={th}>Ad</th><th className={th}>Hesap</th><th className={th}>Birim</th><th className={th}>Unvan</th><th className={th}>İşe giriş</th><th className={th}>Durum</th></tr>
              </thead>
              <tbody>
                {list.data.items.map((e) => (
                  <tr key={e.id} className="border-t border-slate-100">
                    <td className={td}>
                      {canEdit ? (
                        <button type="button" className="text-left font-bold text-canvas-violet hover:underline" onClick={() => setEditing(e)}>{e.displayName}</button>
                      ) : <span className="font-bold">{e.displayName}</span>}
                    </td>
                    <td className={`${td} font-mono text-[11.5px]`}>{e.username ?? '—'}</td>
                    <td className={td}>{e.unitName ?? '—'}</td>
                    <td className={td}>{e.title || '—'}</td>
                    <td className={td}>{fmtDay(e.startDate)}</td>
                    <td className={td}><Pill tone={e.status === 'aktif' ? 'ok' : 'muted'}>{e.statusLabel}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {!list.data.items.length && <div className="py-6 text-center text-[12px] text-canvas-muted">Kayıt yok.{canEdit ? ' «CRM ve AD\'den eşitle» ile başlayın.' : ''}</div>}
          <div className="mt-1 text-right font-mono text-[11.5px] text-canvas-muted">{list.data.total} çalışan</div>
        </div>
      )}
      {editing !== null && (
        <EmployeeSheet key={editing === 'new' ? 'new' : editing.id + (editing.updatedAt ?? '')} e={editing === 'new' ? null : editing}
          units={units.data?.items ?? []} meta={meta} onClose={() => setEditing(null)} />
      )}
      {syncing && <SyncSheet onClose={() => setSyncing(false)} />}
    </Block>
  );
}

function EmployeeSheet({ e, units, meta, onClose }: { e: Employee | null; units: Unit[]; meta: HrMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ displayName: e?.displayName ?? '', username: e?.username ?? '', unitId: e?.unitId ?? '', title: e?.title ?? '',
    startDate: e?.startDate ?? '', endDate: e?.endDate ?? '', status: e?.status ?? 'aktif' });
  const save = useMutation({
    mutationFn: () => {
      const b = { ...f, unitId: f.unitId || null, startDate: f.startDate || null, endDate: f.endDate || null, username: f.username || null } as Partial<Employee>;
      return e ? hrApi.updateEmployee(e.id, b) : hrApi.createEmployee(b);
    },
    onSuccess: () => {
      toast.success('Çalışan kaydı kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['hr', 'employees'] });
      void qc.invalidateQueries({ queryKey: ['hr', 'units'] });
      onClose();
    },
    onError: (err) => toast.error(errText(err, 'Kaydedilemedi.')),
  });
  const src = e?.source ?? {};
  return (
    <Sheet open modal onClose={onClose} title={e ? e.displayName : 'Çalışan ekle'} subtitle={e?.crmSystemUserId ? 'CRM kullanıcısı; elle düzelttiğiniz alan eşitlemede korunur.' : 'Elle eklenen çalışan'}>
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad soyad {src.display_name && <em className="not-italic text-canvas-muted">· kaynak {src.display_name}</em>}</span>
          <input className={field} value={f.displayName} onChange={(x) => setF({ ...f, displayName: x.target.value })} />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>AD hesabı (bilgisayarsızda boş)</span>
            <input className={field} value={f.username} onChange={(x) => setF({ ...f, username: x.target.value })} autoComplete="off" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Birim</span>
            <select className={field} value={f.unitId} onChange={(x) => setF({ ...f, unitId: x.target.value })}>
              <option value="">Seçilmedi</option>
              {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Unvan</span>
            <input className={field} value={f.title} onChange={(x) => setF({ ...f, title: x.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={f.status} onChange={(x) => setF({ ...f, status: x.target.value as Employee['status'] })}>
              {Object.entries(meta.employeeStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İşe giriş</span>
            <input type="date" className={field} value={f.startDate} onChange={(x) => setF({ ...f, startDate: x.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ayrılış</span>
            <input type="date" className={field} value={f.endDate} onChange={(x) => setF({ ...f, endDate: x.target.value })} />
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || !f.displayName.trim()} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

function SyncSheet({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [kinds, setKinds] = useState<Record<string, boolean>>({ units: true, new: true, changed: true, departed: false });
  const pv = useQuery({ queryKey: ['hr', 'sync-preview'], queryFn: hrApi.syncPreview, enabled: ENGINE_ENABLED, retry: false, staleTime: 0, gcTime: 0 });
  const apply = useMutation({
    mutationFn: () => hrApi.syncApply(Object.entries(kinds).filter(([, v]) => v).map(([k]) => k)),
    onSuccess: (r) => {
      const a = r.applied;
      toast.success(`Eşitlendi: ${a.new ?? 0} yeni, ${a.changed ?? 0} değişen, ${a.departed ?? 0} ayrılan, ${a.units ?? 0} birim.`);
      void qc.invalidateQueries({ queryKey: ['hr'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Eşitlenemedi.')),
  });
  const d: SyncPreview | undefined = pv.data;
  const label: Record<string, string> = { units: 'Birimler', new: 'Yeni çalışanlar', changed: 'Değişen çalışanlar', departed: 'Ayrılanlar («ayrıldı» olarak işaretle)' };
  return (
    <Sheet open modal wide onClose={onClose} title="CRM ve AD'den eşitleme" subtitle="Öneri CRM'deki etkin kullanıcılar ile AD'deki etkin kişi hesaplarının kesişimidir. Onaylamadan hiçbir şey yazılmaz.">
      {pv.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">CRM ve AD okunuyor…</div>}
      {pv.error && <Note tone="err">{errText(pv.error, 'CRM okunamadı.')}</Note>}
      {d && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ['CRM etkin kullanıcı', d.stats.crmInteractive], ['AD ile eşleşen', d.stats.adChecked ? d.stats.matched : '—'],
              ['Birim', `${d.stats.units} (${d.stats.unitsWithManager} yöneticili)`], ['Devre dışı olmayan CRM hesabı', d.stats.crmEnabled],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
                <div className="font-mono text-[15px] font-bold tabular-nums">{v}</div>
              </div>
            ))}
          </div>
          {d.notes.map((n) => <Note key={n} tone="warn">{n}</Note>)}
          <div className="flex flex-col gap-1">
            {Object.keys(label).map((k) => {
              const n = k === 'units' ? d.stats.unitsNew + d.units.filter((u) => u.action === 'degisti').length : k === 'new' ? d.stats.new : k === 'changed' ? d.stats.changed : d.stats.departed;
              return (
                <label key={k} className="flex min-h-11 items-center gap-2 sm:min-h-0">
                  <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={!!kinds[k]} onChange={(e) => setKinds({ ...kinds, [k]: e.target.checked })} />
                  <span className="text-[12.5px] font-semibold">{label[k]}</span>
                  <span className="font-mono text-[12px] tabular-nums text-canvas-muted">{n}</span>
                </label>
              );
            })}
          </div>
          <details className="rounded-xl bg-slate-50 p-2.5">
            <summary className="cursor-pointer text-[12.5px] font-bold">Değişiklik listesi</summary>
            <ul className="mt-1 flex flex-col gap-0.5 text-[12px]">
              {d.employees.filter((e) => e.action !== 'ayni').map((e) => (
                <li key={e.crmSystemUserId}>
                  <Pill tone={e.action === 'yeni' ? 'ok' : 'warn'}>{e.action === 'yeni' ? 'yeni' : 'değişti'}</Pill> {e.displayName}
                  <span className="text-canvas-muted"> · {e.username} · {e.unitName || 'birim yok'}{Object.keys(e.changes).length ? ` · ${Object.keys(e.changes).join(', ')}` : ''}</span>
                </li>
              ))}
              {d.departed.map((e) => (
                <li key={e.id}><Pill tone="muted">ayrıldı</Pill> {e.displayName}<span className="text-canvas-muted"> · CRM ∩ AD'de artık yok</span></li>
              ))}
            </ul>
          </details>
          <details className="rounded-xl bg-slate-50 p-2.5">
            <summary className="cursor-pointer text-[12.5px] font-bold">Birim ve ekip dağılımı (CRM)</summary>
            <TableWrap>
              <table className="w-full min-w-[420px] text-[12px]">
                <thead><tr><th className={th}>Birim</th><th className={th}>Devre dışı olmayan hesap</th><th className={th}>Önerilen çalışan</th></tr></thead>
                <tbody>
                  {d.units.map((u) => (
                    <tr key={u.crmBusinessUnitId} className="border-t border-slate-100">
                      <td className={td}>{u.name}</td><td className={`${td} font-mono tabular-nums`}>{u.enabledUsers}</td><td className={`${td} font-mono tabular-nums`}>{u.employees}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <div className="mt-2 text-[12px] font-bold">Ekipler</div>
            <ul className="text-[12px]">{d.teams.map((t) => <li key={t.teamId}>{t.team} · <span className="font-mono">{t.members}</span></li>)}</ul>
          </details>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="button" className={btnPrimary} disabled={apply.isPending || !Object.values(kinds).some(Boolean)} onClick={() => apply.mutate()}>
              {apply.isPending ? 'Yazılıyor…' : 'Seçilenleri uygula'}
            </button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------------ birimler */

function Units({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient();
  const units = useQuery({ queryKey: ['hr', 'units'], queryFn: hrApi.units, enabled: ENGINE_ENABLED });
  const emps = useQuery({ queryKey: ['hr', 'employees', 'aktif', '', ''], queryFn: () => hrApi.employees({ status: 'aktif' }), enabled: ENGINE_ENABLED && canEdit });
  const [name, setName] = useState('');
  const items = units.data?.items ?? [];
  const byId = Object.fromEntries(items.map((u) => [u.id, u.name]));
  const empName = Object.fromEntries((emps.data?.items ?? []).map((e) => [e.id, e.displayName]));
  const save = useMutation({
    mutationFn: (x: { id?: string; body: Partial<Unit> }) => (x.id ? hrApi.updateUnit(x.id, x.body) : hrApi.createUnit(x.body)),
    onSuccess: () => {
      toast.success('Birim kaydedildi.');
      setName('');
      void qc.invalidateQueries({ queryKey: ['hr', 'units'] });
    },
    onError: (e) => toast.error(errText(e, 'Birim kaydedilemedi.')),
  });
  return (
    <Block title="Birimler" help="CRM iş birimlerinden eşitlenir; üst birim ve birim yöneticisi burada düzeltilir.">
      {canEdit && (
        <form className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); save.mutate({ body: { name } }); }}>
          <label className="flex flex-1 flex-col gap-1">
            <span className={labelCls}>Yeni birim</span>
            <input className={field} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <button type="submit" className={btnPrimary} disabled={!name.trim() || save.isPending}>Ekle</button>
        </form>
      )}
      <TableWrap>
        <table className="w-full min-w-[640px] text-[12.5px]">
          <thead><tr><th className={th}>Birim</th><th className={th}>Üst birim</th><th className={th}>Yönetici</th><th className={th}>Çalışan</th><th className={th}>Kaynak</th></tr></thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id} className="border-t border-slate-100">
                <td className={`${td} font-bold`}>{u.name}{!u.active && <span className="ml-1 text-canvas-muted">(pasif)</span>}</td>
                <td className={td}>
                  {canEdit ? (
                    <select className={`${field} !min-h-9 !py-1`} value={u.parentId ?? ''} onChange={(e) => save.mutate({ id: u.id, body: { parentId: e.target.value || null } })} aria-label={`${u.name} üst birimi`}>
                      <option value="">—</option>
                      {items.filter((x) => x.id !== u.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                    </select>
                  ) : (byId[u.parentId ?? ''] ?? '—')}
                </td>
                <td className={td}>
                  {canEdit ? (
                    <select className={`${field} !min-h-9 !py-1`} value={u.managerEmployeeId ?? ''} onChange={(e) => save.mutate({ id: u.id, body: { managerEmployeeId: e.target.value || null } })} aria-label={`${u.name} yöneticisi`}>
                      <option value="">—</option>
                      {(emps.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.displayName}</option>)}
                    </select>
                  ) : (empName[u.managerEmployeeId ?? ''] ?? (u.managerEmployeeId ? 'kayıtlı' : '—'))}
                </td>
                <td className={`${td} font-mono tabular-nums`}>{u.employees}</td>
                <td className={td}>{u.crmBusinessUnitId ? 'CRM' : 'İK'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      {units.data && !items.length && <div className="py-6 text-center text-[12px] text-canvas-muted">Birim yok; Çalışanlar sekmesinden eşitleyin.</div>}
    </Block>
  );
}

/* ------------------------------------------------------------------ aydınlatma metinleri */

function Notices({ meta, canEdit }: { meta: HrMeta; canEdit: boolean }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['hr', 'notices'], queryFn: () => hrApi.notices(), enabled: ENGINE_ENABLED });
  const [f, setF] = useState({ audience: 'aday', title: '', body: '' });
  const publish = useMutation({
    mutationFn: () => hrApi.publishNotice(f),
    onSuccess: (n) => {
      toast.success(`Sürüm ${n.version} yayımlandı.`);
      setF({ ...f, title: '', body: '' });
      void qc.invalidateQueries({ queryKey: ['hr', 'notices'] });
    },
    onError: (e) => toast.error(errText(e, 'Yayımlanamadı.')),
  });
  const items = list.data?.items ?? [];
  return (
    <Block title="Aydınlatma metinleri" help="Her yayım yeni sürümdür; eski sürüm silinmez. Rıza kaydı hangi sürüme dayandığını taşır. Metni TİMAŞ'ın hukukçusu ya da KVKK danışmanı onaylamalıdır.">
      {canEdit && (
        <div className="mb-3 flex flex-col gap-2 rounded-xl bg-slate-50 p-2.5">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[200px_1fr]">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kitle</span>
              <select className={field} value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })}>
                {Object.entries(meta.audiences).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Başlık</span>
              <input className={field} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Metin</span>
            <textarea className={`${field} min-h-[180px]`} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
          </label>
          <div className="flex justify-end">
            <button type="button" className={btnPrimary} disabled={!f.title.trim() || !f.body.trim() || publish.isPending} onClick={() => publish.mutate()}>Yeni sürüm yayımla</button>
          </div>
        </div>
      )}
      {list.data && !items.length && <Note tone="warn">Yayımlanmış aydınlatma metni yok; rıza kaydı ve «başvurunuz alındı» mektubu buna dayanır.</Note>}
      <ul className="flex flex-col gap-2">
        {items.map((n) => (
          <li key={n.id} className="rounded-xl border border-slate-100 bg-white/80 p-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[13px] font-extrabold">{n.title}</span>
              <Pill tone="violet">{meta.audiences[n.audience] ?? n.audience}</Pill>
              <span className="font-mono text-[11px] text-canvas-muted">sürüm {n.version} · {fmtDateTime(n.publishedAt)} · {n.publishedBy ?? '—'}</span>
            </div>
            <details className="mt-1">
              <summary className="cursor-pointer text-[12px] font-bold text-canvas-violet">Metni göster</summary>
              <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 font-sans text-[12.5px] leading-snug">{n.body}</pre>
            </details>
          </li>
        ))}
      </ul>
    </Block>
  );
}

/* ------------------------------------------------------------------ saklama ve imha */

function Retention({ canEdit, canRuns }: { canEdit: boolean; canRuns: boolean }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['hr', 'retention'], queryFn: hrApi.retention, enabled: ENGINE_ENABLED });
  const preview = useQuery({ queryKey: ['hr', 'purge-preview'], queryFn: hrApi.purgePreview, enabled: ENGINE_ENABLED && canEdit });
  const runs = useInfiniteQuery({
    queryKey: ['hr', 'purge-runs'],
    queryFn: ({ pageParam }) => hrApi.purgeRuns(pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => (last.hasMore ? (last.next ?? undefined) : undefined),
    enabled: ENGINE_ENABLED && canRuns,
  });
  const [draft, setDraft] = useState<Record<string, { keepDays: string; legalBasis: string }>>({});
  const rows = list.data?.items ?? [];
  const val = (k: string, prop: 'keepDays' | 'legalBasis', fallback: string) => draft[k]?.[prop] ?? fallback;
  const save = useMutation({
    mutationFn: () => hrApi.putRetention(rows.map((r) => ({
      dataClass: r.dataClass,
      keepDays: val(r.dataClass, 'keepDays', r.keepDays === null ? '' : String(r.keepDays)).trim() ? Number(val(r.dataClass, 'keepDays', '')) : null,
      legalBasis: val(r.dataClass, 'legalBasis', r.legalBasis),
    }))),
    onSuccess: () => {
      toast.success('Saklama süreleri kaydedildi.');
      setDraft({});
      void qc.invalidateQueries({ queryKey: ['hr', 'retention'] });
      void qc.invalidateQueries({ queryKey: ['hr', 'purge-preview'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Block title="Saklama süreleri" help="Süre TİMAŞ'ın saklama-imha politikasından girilir; boş bırakılan sınıfta imha yapılmaz. Gece imha işi (03:40) süresi dolanı siler ve tutanak yazar.">
        <div className="flex flex-col gap-2">
          {rows.map((r) => (
            <div key={r.dataClass} className="grid grid-cols-1 gap-2 rounded-xl border border-slate-100 bg-white/80 p-2.5 sm:grid-cols-[1fr_120px_1.4fr]">
              <div className="min-w-0">
                <div className="text-[13px] font-extrabold">{r.label}</div>
                <div className="text-[11.5px] leading-snug text-canvas-muted">{r.hint}</div>
                {r.approvedBy && <div className="mt-0.5 text-[11px] text-canvas-muted">{r.approvedBy} · {fmtDay(r.approvedAt)}</div>}
                {r.keepDays === null && <Pill tone="warn">Süre girilmedi</Pill>}
              </div>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Gün</span>
                <input className={`${field} font-mono tabular-nums`} inputMode="numeric" disabled={!canEdit}
                  value={val(r.dataClass, 'keepDays', r.keepDays === null ? '' : String(r.keepDays))}
                  onChange={(e) => setDraft({ ...draft, [r.dataClass]: { keepDays: e.target.value, legalBasis: val(r.dataClass, 'legalBasis', r.legalBasis) } })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Hukuki dayanak</span>
                <input className={field} disabled={!canEdit}
                  value={val(r.dataClass, 'legalBasis', r.legalBasis)}
                  onChange={(e) => setDraft({ ...draft, [r.dataClass]: { keepDays: val(r.dataClass, 'keepDays', r.keepDays === null ? '' : String(r.keepDays)), legalBasis: e.target.value } })} />
              </label>
            </div>
          ))}
        </div>
        {canEdit && (
          <div className="mt-2 flex justify-end">
            <button type="button" className={btnPrimary} disabled={!Object.keys(draft).length || save.isPending} onClick={() => save.mutate()}>Kaydet</button>
          </div>
        )}
      </Block>
      {canEdit && (
        <Block title="Bu gece silinecek" help="Kayıt sayısı; ad ve kimlik gösterilmez.">
          <ul className="flex flex-col gap-1 text-[12.5px]">
            {(preview.data?.items ?? []).map((p) => (
              <li key={p.key} className="flex items-center justify-between rounded-lg bg-white/80 px-2 py-1.5">
                <span>{p.label}</span>
                <span className="font-mono font-bold tabular-nums">{p.error ? 'okunamadı' : p.due}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}
      {canRuns && (
        <Block title="İmha tutanakları" help="Her gece her veri sınıfı için bir satır (sıfır da olsa); talep üzerine silmeler «talep» sınıfıyla.">
          <TableWrap>
            <table className="w-full min-w-[560px] text-[12.5px]">
              <thead><tr><th className={th}>Zaman</th><th className={th}>Sınıf</th><th className={th}>Silinen</th><th className={th}>Kim</th><th className={th}>Hata</th></tr></thead>
              <tbody>
                {(runs.data?.pages ?? []).flatMap((pg) => pg.items).map((r) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className={td}>{fmtDateTime(r.at)}</td><td className={td}>{r.label}</td>
                    <td className={`${td} font-mono tabular-nums`}>{r.purged}</td><td className={td}>{r.actor ?? '—'}</td>
                    <td className={`${td} text-red-700`}>{r.error ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {runs.hasNextPage && (
            <div className="mt-2 flex justify-center">
              <button type="button" className={btnGhost} disabled={runs.isFetchingNextPage} onClick={() => void runs.fetchNextPage()}>Daha eski</button>
            </div>
          )}
        </Block>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ erişim kaydı */

const ACTION: Record<string, string> = { goruntule: 'Görüntüledi', indir: 'İndirdi', disa_aktar: 'Dışa aktardı', sil: 'Sildi' };

function AccessLog() {
  const [user, setUser] = useState('');
  const [subject, setSubject] = useState('');
  const du = useDebounced(user, 400);
  const ds = useDebounced(subject, 400);
  const log = useInfiniteQuery({
    queryKey: ['hr', 'access-log', du, ds],
    queryFn: ({ pageParam }) => hrApi.accessLog({ user: du, subjectId: ds, before: pageParam }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => (last.hasMore ? (last.next ?? undefined) : undefined),
    enabled: ENGINE_ENABLED,
  });
  return (
    <Block title="Erişim kaydı" help="Aday ve çalışan kayıtlarının her görüntülenmesi, indirilmesi, dışa aktarılması ve silinmesi.">
      <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kişi (hesap adı)</span>
          <input className={field} value={user} onChange={(e) => setUser(e.target.value)} autoComplete="off" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kayıt kimliği</span>
          <input className={field} value={subject} onChange={(e) => setSubject(e.target.value)} autoComplete="off" />
        </label>
      </div>
      {log.error && <Note tone="err">{errText(log.error, 'Erişim kaydı okunamadı.')}</Note>}
      <TableWrap>
        <table className="w-full min-w-[560px] text-[12.5px]">
          <thead><tr><th className={th}>Zaman</th><th className={th}>Kişi</th><th className={th}>İşlem</th><th className={th}>Kayıt</th><th className={th}>Amaç</th></tr></thead>
          <tbody>
            {(log.data?.pages ?? []).flatMap((pg) => pg.items).map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className={td}>{fmtDateTime(r.at)}</td><td className={`${td} font-mono text-[11.5px]`}>{r.username}</td>
                <td className={td}>{ACTION[r.action] ?? r.action}</td><td className={`${td} font-mono text-[11.5px]`}>{r.subjectType}:{r.subjectId}</td>
                <td className={td}>{r.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      {log.hasNextPage && (
        <div className="mt-2 flex justify-center">
          <button type="button" className={btnGhost} disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>Daha eski</button>
        </div>
      )}
    </Block>
  );
}
