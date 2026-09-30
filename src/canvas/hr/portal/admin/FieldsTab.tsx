import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Lock, Pencil, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../../admin/ui';
import Sheet from '../../../editorial/studio/reader/Sheet';
import { AskSheet, Block } from '../../parts';
import { portalApi, type FieldType, type PersonField, type PortalMeta, type PortalSettings } from '../portalApi';

export default function FieldsTab({ tab, meta }: { tab: 'alanlar' | 'ayarlar'; meta: PortalMeta }) {
  return tab === 'alanlar' ? <Fields meta={meta} /> : <Lists meta={meta} />;
}

/* ------------------------------------------------------------------ alanlar */

const Check = ({ on }: { on: boolean }) => (on ? <span className="font-bold text-emerald-700">✓</span> : <span className="text-slate-300">—</span>);

function Fields({ meta }: { meta: PortalMeta }) {
  const q = useQuery({ queryKey: ['hr', 'portal', 'fields'], queryFn: portalApi.fields, enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<PersonField | 'new' | null>(null);
  const [group, setGroup] = useState('');
  const items = (q.data?.items ?? []).filter((f) => !group || f.group === group);
  const can = meta.rights.fields;
  return (
    <Block title="Personel alanları"
      help="Eski personel portalının Excel listesi. «Yönetici paneli» İK yönetimindeki kartta, «Profilim» çalışanın kendi sayfasında, «Rehber» herkesin gördüğü personel rehberinde görünür. Hassas işaretli alan yalnız «Hassas özlük verisi» yetkisiyle görünür ve rehberde hiç çıkmaz."
      action={
        <div className="flex flex-wrap gap-2">
          <select className={field} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Grup">
            <option value="">Bütün gruplar</option>
            {Object.entries(meta.groups).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {can && <button type="button" className={btnPrimary} onClick={() => setEditing('new')}><Plus aria-hidden className="h-4 w-4" />Alan ekle</button>}
        </div>
      }>
      {!can && <Note tone="info">Alanları görebilirsiniz; değiştirmek için «Personel alanları ve listeler» yetkisi gerekir.</Note>}
      {q.error && <Note tone="err">{errText(q.error, 'Alanlar okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {!!items.length && (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Alan</th><th className={th}>Tür</th><th className={th}>Seçenekler</th><th className={th}>Zorunlu</th>
              <th className={th}>Yönetici paneli</th><th className={th}>Profilim</th><th className={th}>Rehber</th><th className={th}>Hassas</th><th className={th} />
            </tr>
          </thead>
          <tbody>
            {items.map((f) => (
              <tr key={f.key} className={`border-t border-slate-100 ${f.active ? '' : 'opacity-50'}`}>
                <td className={td}>
                  <span className="font-bold">{f.label}</span>
                  <span className="block font-mono text-[11px] text-canvas-muted">{f.key}{!f.active && ' · kapalı'}{!f.builtin && ' · sonradan eklendi'}</span>
                </td>
                <td className={`${td} whitespace-nowrap`}>{meta.fieldTypes[f.type]}</td>
                <td className={`${td} max-w-[240px] text-[12px]`}>{f.options.join(', ') || '—'}</td>
                <td className={td}><Check on={f.required} /></td>
                <td className={td}><Check on={f.showAdmin} /></td>
                <td className={td}><Check on={f.showProfile} /></td>
                <td className={td}><Check on={f.showDirectory} /></td>
                <td className={td}>{f.sensitive ? <Lock aria-label="Hassas" className="h-3.5 w-3.5 text-amber-700" /> : <Check on={false} />}</td>
                <td className={td}>
                  {can && (
                    <button type="button" aria-label={`${f.label} alanını düzenle`} className="inline-flex h-11 w-11 items-center justify-center rounded-lg hover:bg-slate-100 sm:h-8 sm:w-8" onClick={() => setEditing(f)}>
                      <Pencil aria-hidden className="h-4 w-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      <FieldSheet f={editing} meta={meta} onClose={() => setEditing(null)} />
    </Block>
  );
}

const CORE = new Set(['id_no', 'ad_soyad', 'durum']);

function FieldSheet({ f, meta, onClose }: { f: PersonField | 'new' | null; meta: PortalMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const isNew = f === 'new';
  const cur = f && f !== 'new' ? f : null;
  const blank = { key: '', label: '', type: 'text' as FieldType, options: '', required: false, showAdmin: true, showProfile: false, showDirectory: false, sensitive: false, active: true, group: 'diger', sort: 10000 };
  const [form, setForm] = useState(blank);
  const [err, setErr] = useState<string | null>(null);
  const [ask, setAsk] = useState(false);
  useEffect(() => {
    setErr(null);
    setForm(cur ? { key: cur.key, label: cur.label, type: cur.type, options: cur.options.join('\n'), required: cur.required, showAdmin: cur.showAdmin,
      showProfile: cur.showProfile, showDirectory: cur.showDirectory, sensitive: cur.sensitive, active: cur.active, group: cur.group, sort: cur.sort } : blank);
  }, [f]); // eslint-disable-line react-hooks/exhaustive-deps
  const done = () => { void qc.invalidateQueries({ queryKey: ['hr', 'portal'] }); onClose(); };
  const save = useMutation({
    mutationFn: () => {
      const body: Partial<PersonField> = {
        label: form.label, required: form.required, showAdmin: form.showAdmin, showProfile: form.showProfile, showDirectory: form.showDirectory,
        sensitive: form.sensitive, active: form.active, group: form.group, sort: form.sort,
        options: form.options.split('\n').map((x) => x.trim()).filter(Boolean),
      };
      return isNew ? portalApi.createField({ ...body, key: form.key.trim(), type: form.type }) : portalApi.updateField((cur as PersonField).key, body);
    },
    onSuccess: () => { toast.success('Alan kaydedildi.'); done(); },
    onError: (e) => setErr(errText(e, 'Kaydedilemedi.')),
  });
  const del = useMutation({
    mutationFn: () => portalApi.deleteField((cur as PersonField).key),
    onSuccess: (out) => { setAsk(false); toast.success(`Alan silindi; ${out.cleared} kayıttaki değeri temizlendi.`); done(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
    onSettled: () => setAsk(false),
  });
  const core = !!cur && CORE.has(cur.key);
  const box = (k: 'required' | 'showAdmin' | 'showProfile' | 'showDirectory' | 'sensitive' | 'active', text: string, hint?: string, disabled?: boolean) => (
    <label className={`flex items-start gap-2 text-[12.5px] ${disabled ? 'opacity-60' : ''}`}>
      <input type="checkbox" className="mt-0.5 h-4 w-4" checked={form[k]} disabled={disabled} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} />
      <span><span className="font-bold">{text}</span>{hint && <span className="block text-[11.5px] text-canvas-muted">{hint}</span>}</span>
    </label>
  );
  return (
    <Sheet open={!!f} modal onClose={onClose} title={isNew ? 'Yeni alan' : cur?.label ?? ''} subtitle={cur ? `${cur.key} · ${meta.fieldTypes[cur.type]}${cur.builtin ? ' · Excel listesinden' : ''}` : undefined}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {isNew && (
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Anahtar</span>
              <input className={`${field} font-mono`} value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase() })} placeholder="ornek_alan" required pattern="[a-z][a-z0-9_]{1,59}" />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Tür</span>
              <select className={field} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as FieldType })}>
                {Object.entries(meta.fieldTypes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
          </div>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Görünen ad</span>
          <input className={field} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required maxLength={120} />
        </label>
        {form.type === 'enum' && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Seçenekler (her satıra bir)</span>
            <textarea className={`${field} min-h-[110px]`} value={form.options} onChange={(e) => setForm({ ...form, options: e.target.value })} required />
            <span className="text-[11px] text-canvas-muted">Kaldırılan seçeneği taşıyan kayıtlar değerini korur; kart açılınca eski değer ayrıca görünür.</span>
          </label>
        )}
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Grup</span>
            <select className={field} value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })}>
              {Object.entries(meta.groups).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sıra</span>
            <input type="number" className={field} value={form.sort} onChange={(e) => setForm({ ...form, sort: Number(e.target.value) || 0 })} />
          </label>
        </div>
        <fieldset className="flex flex-col gap-2 rounded-xl bg-slate-50 p-3">
          <legend className="sr-only">Kurallar</legend>
          {box('required', 'Zorunlu', 'Boşken kart kaydedilmez; belge alanında ana sayfadaki «eksik belge» sayısına girer.', core)}
          {box('showAdmin', 'Yönetici panelinde', 'İK yönetimindeki kartta.')}
          {box('showProfile', 'Profilim sayfasında', 'Çalışan kendi değerini görür.')}
          {box('showDirectory', 'Personel rehberinde', 'Bütün çalışanlar görür. Hassas alan rehberde işaretli olsa da çıkmaz.')}
          {box('sensitive', 'Hassas', 'T.C. kimlik, IBAN, sağlık gibi; yalnız «Hassas özlük verisi» yetkisiyle görünür.')}
          {box('active', 'Açık', 'Kapalı alan hiçbir ekranda görünmez, değerleri silinmez.', core)}
        </fieldset>
        {err && <Note tone="err">{err}</Note>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          {cur && !cur.builtin ? <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setAsk(true)}><Trash2 aria-hidden className="h-4 w-4" />Alanı sil</button> : <span />}
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button>
          </div>
        </div>
      </form>
      <AskSheet open={ask} title="Alanı sil" danger confirm="Sil" busy={del.isPending}
        message={<>«{cur?.label}» alanı ve bütün personel kayıtlarındaki değeri (belge alanıysa yüklü dosyaları) silinecek. Yalnız gizlemek için «Açık» işaretini kaldırın. Bu işlem geri alınamaz.</>}
        onClose={() => setAsk(false)} onConfirm={() => del.mutate()} />
    </Sheet>
  );
}

/* ------------------------------------------------------------------ listeler ve ayarlar */

const LISTS: { key: keyof Omit<PortalSettings, 'expiryDays'>; title: string; help: string }[] = [
  { key: 'docTypes', title: 'Evrak tipleri', help: 'Çalışanın Evrak talebi ekranında seçtiği belgeler.' },
  { key: 'postCategories', title: 'Duyuru kategorileri', help: 'Şirket içi duyuruların kategorisi.' },
  { key: 'docCategories', title: 'Evrak deposu kategorileri', help: 'Formlar, rehberler gibi.' },
  { key: 'faqCategories', title: 'Sık sorulan soru kategorileri', help: 'Bu sırayla gösterilir.' },
];

function Lists({ meta }: { meta: PortalMeta }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(() => ({
    ...Object.fromEntries(LISTS.map((l) => [l.key, meta.settings[l.key].join('\n')])),
    expiryDays: String(meta.settings.expiryDays),
  }) as Record<string, string>);
  const save = useMutation({
    mutationFn: () => {
      const body: Partial<PortalSettings> = { expiryDays: Number(form.expiryDays) };
      LISTS.forEach((l) => { body[l.key] = (form[l.key] ?? '').split('\n').map((x) => x.trim()).filter(Boolean); });
      return portalApi.saveSettings(body);
    },
    onSuccess: () => { toast.success('Listeler kaydedildi.'); void qc.invalidateQueries({ queryKey: ['hr', 'portal'] }); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Block title="Listeler ve ayarlar" help="Her satıra bir değer. Listeden çıkan değer eski kayıtlarda kalır; yeni kayıtta seçilemez.">
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {LISTS.map((l) => (
            <label key={l.key} className="flex flex-col gap-1">
              <span className={labelCls}>{l.title}</span>
              <textarea className={`${field} min-h-[150px]`} value={form[l.key]} onChange={(e) => setForm({ ...form, [l.key]: e.target.value })} />
              <span className="text-[11px] text-canvas-muted">{l.help}</span>
            </label>
          ))}
        </div>
        <label className="flex max-w-[320px] flex-col gap-1">
          <span className={labelCls}>Yaklaşan tarih uyarısı (gün)</span>
          <input type="number" min={1} max={365} className={field} value={form.expiryDays} onChange={(e) => setForm({ ...form, expiryDays: e.target.value })} />
          <span className="text-[11px] text-canvas-muted">Çalışma izni ve askerlik tecili bitişi İK ana sayfasında bu kadar gün önce görünür.</span>
        </label>
        <div className="flex items-center justify-between gap-2">
          <Pill tone="muted">Alan seçenekleri (firma, şube…) Alanlar sekmesinde</Pill>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button>
        </div>
      </form>
    </Block>
  );
}
