import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, Plus, RefreshCw, Search, Trash2, UserRound, X } from 'lucide-react';
import {
  accessApi,
  type AccessBinding,
  type AccessCatalog,
  type AccessRole,
  type AccessRoleInput,
  type AccessSubjectType,
} from '../engine';
import { trFold } from '../nav/navModel';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Card, Loading, Note, Pill, Section, btnGhost, btnPrimary, errText, field, fmtDate, label, nf } from './ui';

/**
 * Yetkiler: rol = görünen sayfalar; rol bir AD grubuna, AD birimine (OU), CRM rolüne ya da tek kişiye
 * bağlanır. Kişi bağlı olduğu rollerin birleşimini görür, yönetici her şeyi. Karar köprüde verilir; bu ekran
 * yalnız tanımı düzenler. Analiz: docs/analiz/yetki-mekanizmasi-2026-09-27.md
 */

const TYPES: Array<{ id: AccessSubjectType; label: string; hint: string }> = [
  { id: 'ad_group', label: 'AD grubu', hint: 'Gruba eklenen kişi rolü en geç 15 dakikada alır' },
  { id: 'ou', label: 'AD birimi', hint: 'Birimdeki (OU) herkes; kişi birim değiştirince rolü de değişir' },
  { id: 'crm_role', label: 'CRM rolü', hint: 'CRM güvenlik rolünü taşıyan etkin kullanıcılar' },
  { id: 'user', label: 'Kişi', hint: 'Tek bir AD hesabı; grup açmadan istisna vermek için' },
];

const invalidateAccess = (qc: ReturnType<typeof useQueryClient>) => qc.invalidateQueries({ queryKey: ['access'] });

export default function AccessAdmin() {
  const qc = useQueryClient();
  const [view, setView] = useState<'roles' | 'data' | 'person'>('roles');
  const refresh = useMutation({ mutationFn: accessApi.refresh, onSuccess: () => void invalidateAccess(qc) });

  return (
    <Section
      title="Yetkiler"
      help="Kim hangi sayfayı görür. Rolü bir AD grubuna, AD birimine, CRM rolüne ya da tek kişiye bağlayın; kişi bağlı olduğu bütün rollerin sayfalarını görür. Yöneticiler her şeyi görür."
      action={
        <button type="button" onClick={() => refresh.mutate()} disabled={refresh.isPending} className={btnGhost}>
          {refresh.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Üyeleri şimdi oku
        </button>
      }
    >
      {refresh.data && (
        <Note tone={refresh.data.ok ? 'ok' : 'warn'}>
          {refresh.data.ok
            ? `${nf.format(refresh.data.refreshed)} bağın üyeleri AD ve CRM'den okundu.`
            : `${nf.format(refresh.data.failed.length)} bağ okunamadı, eski üyeleri geçerli: ${refresh.data.failed.map((f) => f.subject).join(', ')}`}
        </Note>
      )}
      {refresh.error && <Note tone="err">{errText(refresh.error, 'Üyeler okunamadı.')}</Note>}

      <div role="tablist" aria-label="Yetki görünümü" className="inline-flex rounded-xl bg-slate-100 p-1">
        {(
          [
            ['roles', 'Roller'],
            ['data', 'Veri alanları'],
            ['person', 'Kişi gözüyle'],
          ] as const
        ).map(([id, text]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            onClick={() => setView(id)}
            className={`min-h-11 rounded-lg px-3.5 text-[12.5px] font-extrabold transition-colors sm:min-h-9 ${
              view === id ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'
            }`}
          >
            {text}
          </button>
        ))}
      </div>

      {view === 'roles' ? <Roles /> : view === 'data' ? <DataDomains /> : <PersonView />}
    </Section>
  );
}

/* ------------------------------------------------------------------ roller */

function Roles() {
  const roles = useQuery({ queryKey: ['access', 'roles'], queryFn: accessApi.roles, retry: false });
  const catalog = useQuery({ queryKey: ['access', 'catalog'], queryFn: accessApi.catalog, retry: false, staleTime: 10 * 60_000 });
  const [selected, setSelected] = useState<string | 'new' | null>(null);
  const items = roles.data?.items ?? [];
  // Yeni oluşturulan rol liste tazelenene kadar bulunmaz: o arada başka rolü değil yükleniyor göster.
  const current = selected === 'new' ? null : selected ? items.find((r) => r.id === selected) : items[0] ?? null;

  if (roles.isLoading || catalog.isLoading) return <Loading />;
  if (roles.error || catalog.error) return <Note tone="err">{errText(roles.error ?? catalog.error, 'Yetkiler okunamadı.')}</Note>;
  const total = catalog.data?.pages.length ?? 0;

  return (
    <div className="grid gap-3 md:grid-cols-[280px_minmax(0,1fr)] md:gap-4">
      <div className="space-y-2">
        <button type="button" onClick={() => setSelected('new')} className={`${btnPrimary} w-full`}>
          <Plus className="h-4 w-4" />
          Yeni rol
        </button>
        {/* Rol satırı düğme olduğu için «i» listenin başında: sayfa, bağ ve kişi sayıları. */}
        <div className="flex justify-end text-[11px] text-canvas-muted">
          <InfoLabel k={roles.data?.kaynaklar} alan="items" label="Rol sayıları">Sayfa, bağ ve kişi sayıları</InfoLabel>
        </div>
        <ul className="space-y-1.5">
          {items.map((r) => {
            const on = selected !== 'new' && current?.id === r.id;
            const people = r.bindings.reduce((a, b) => a + (b.members ?? 0), 0);
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setSelected(r.id)}
                  aria-current={on ? 'true' : undefined}
                  className={`w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${
                    on ? 'border-canvas-violet/40 bg-white shadow-sm' : 'border-slate-100 bg-white/60 hover:bg-white'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-[13px] font-extrabold">{r.name}</span>
                    <Pill tone={r.allPerms ? 'violet' : 'muted'}>{r.allPerms ? 'Bütün sayfalar' : `${r.perms.filter((k) => k.startsWith('sayfa:')).length}/${total} sayfa`}</Pill>
                  </span>
                  <span className="mt-0.5 block text-[11.5px] text-canvas-muted">
                    {r.system
                      ? 'Giriş yapan herkes'
                      : r.bindings.length
                        ? `${nf.format(r.bindings.length)} bağ · ${nf.format(people)} kişi`
                        : 'Henüz kimseye bağlı değil'}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      {current === undefined ? (
        <Loading />
      ) : catalog.data && (
        <RoleEditor
          key={selected === 'new' ? 'new' : current?.id ?? 'none'}
          role={selected === 'new' ? null : current}
          catalog={catalog.data}
          onSaved={(id) => setSelected(id)}
          onDeleted={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function RoleEditor({
  role,
  catalog,
  onSaved,
  onDeleted,
}: {
  role: AccessRole | null;
  catalog: AccessCatalog;
  onSaved: (id: string) => void;
  onDeleted: () => void;
}) {
  const qc = useQueryClient();
  const initial: AccessRoleInput = useMemo(
    () => ({ name: role?.name ?? '', description: role?.description ?? '', allPerms: role?.allPerms ?? false, perms: role?.perms ?? [] }),
    [role],
  );
  const [draft, setDraft] = useState<AccessRoleInput>(initial);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const perms = useMemo(() => new Set(draft.perms), [draft.perms]);
  const dirty =
    draft.name !== initial.name ||
    draft.description !== initial.description ||
    draft.allPerms !== initial.allPerms ||
    [...perms].sort().join() !== [...initial.perms].sort().join();

  const save = useMutation({
    mutationFn: () => (role ? accessApi.updateRole(role.id, draft) : accessApi.createRole(draft)),
    onSuccess: (r) => {
      void invalidateAccess(qc);
      onSaved(r.id);
    },
  });
  const remove = useMutation({
    mutationFn: () => accessApi.deleteRole(role!.id),
    onSuccess: () => {
      void invalidateAccess(qc);
      onDeleted();
    },
  });

  const toggle = (keys: string[], on: boolean) =>
    setDraft((d) => {
      const next = new Set(d.perms);
      keys.forEach((k) => (on ? next.add(k) : next.delete(k)));
      return { ...d, perms: [...next] };
    });

  return (
    <div className="min-w-0 space-y-3">
      <Card className="space-y-3">
        {role?.system && (
          <Note tone="info">
            «Herkes» giriş yapan herkese uygulanır. Roller atanana kadar bütün sayfalar açık; prod öncesi burada
            daraltılır.
          </Note>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1">
            <span className={label}>Rol adı</span>
            <input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              disabled={role?.system}
              placeholder="örn. Finans okuyucu"
              className={field}
            />
          </label>
          <label className="space-y-1">
            <span className={label}>Açıklama</span>
            <input
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="Bu rol kimin için"
              className={field}
            />
          </label>
        </div>

        <label className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-xl bg-slate-50 px-3 py-2 sm:min-h-0">
          <input
            type="checkbox"
            checked={draft.allPerms}
            onChange={(e) => setDraft({ ...draft, allPerms: e.target.checked })}
            className="h-4 w-4 accent-canvas-violet"
          />
          <span className="text-[12.5px] font-bold">Bütün sayfalar ve işlemler</span>
          <span className="text-[11.5px] text-canvas-muted">sonradan eklenenler dahil; «ayrıca verilir» işaretliler hariç</span>
        </label>

        {/* Sütun sayısı panelin genişliğinden: ekran genişliğine bağlı sütun, dar yönetim panelinde metni komşu kutuya taşırıyordu. */}
        <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr))]">
          {catalog.areas.map((area) => {
            const pages = catalog.pages.filter((p) => p.area === area.id);
            const features = catalog.features.filter((f) => f.area === area.id);
            // Alan başlığı sayfaları ve olağan işlemleri birlikte seçer; açıkça verilen işlemler toplu seçilmez.
            const bulk = [...pages.filter((p) => !p.explicit).map((p) => p.key), ...features.filter((f) => !f.explicit).map((f) => f.key)];
            const n = bulk.filter((k) => perms.has(k)).length;
            const covered = draft.allPerms;
            return (
              <div key={area.id} role="group" aria-label={area.label} className="min-w-0 rounded-xl border border-slate-100 bg-white/70 p-2.5">
                {bulk.length > 0 && (
                  <TriCheck
                    checked={covered || n === bulk.length}
                    mixed={!covered && n > 0 && n < bulk.length}
                    disabled={covered}
                    onChange={(on) => toggle(bulk, on)}
                    className="border-b border-slate-100 pb-1.5"
                  >
                    <span className="flex-1 text-[12.5px] font-extrabold">{area.label}</span>
                    <span className="text-[11px] font-bold tabular-nums text-canvas-muted">{covered ? 'hepsi' : `${n}/${bulk.length}`}</span>
                  </TriCheck>
                )}
                {bulk.length === 0 && <div className="border-b border-slate-100 px-1 pb-1.5 text-[12.5px] font-extrabold">{area.label}</div>}
                <div className="mt-1 space-y-0.5">
                  {pages.map((p) => (
                    <TriCheck
                      key={p.key}
                      checked={p.explicit ? perms.has(p.key) : covered || perms.has(p.key)}
                      disabled={covered && !p.explicit}
                      onChange={(on) => toggle([p.key], on)}
                    >
                      <span className="min-w-0 flex-1 break-words text-[12.5px] font-semibold">{p.label}</span>
                      {p.explicit && <Pill tone="warn">ayrıca verilir</Pill>}
                    </TriCheck>
                  ))}
                </div>
                {features.length > 0 && (
                  <div className="mt-1.5 border-t border-dashed border-slate-200 pt-1.5">
                    <div className="px-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">İşlemler</div>
                    {features.map((f) => {
                      const on = f.explicit ? perms.has(f.key) : covered || perms.has(f.key);
                      return (
                        <TriCheck key={f.key} checked={on} disabled={covered && !f.explicit} onChange={(v) => toggle([f.key], v)}>
                          <span className="min-w-0 flex-1" title={f.hint}>
                            <span className="block break-words text-[12.5px] font-semibold leading-snug">{f.label}</span>
                            <span className="line-clamp-2 break-words text-[11px] leading-snug text-canvas-muted">{f.hint}</span>
                          </span>
                          {f.explicit && <Pill tone="warn">ayrıca verilir</Pill>}
                        </TriCheck>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div role="group" aria-labelledby="zeki-veri" className="min-w-0 rounded-xl border border-slate-100 bg-white/70 p-2.5">
          <div id="zeki-veri" className="px-1 pb-1 text-[12.5px] font-extrabold">ZEKİ AI veri alanları</div>
          <p className="px-1 pb-1.5 text-[11.5px] text-canvas-muted">
            ZEKİ AI'a sorulan soruların, panoların, planlı raporların ve uyarıların hangi verileri okuyabileceği. Kapsam dışı
            soru açık bir retle cevaplanır.
          </p>
          <div className="grid gap-0.5 [grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr))]">
            {catalog.data.map((d) =>
              d.always ? (
                <div key={d.key} className="flex min-h-11 items-center gap-2 px-1 text-[12.5px] font-semibold text-canvas-muted sm:min-h-8" title={d.hint}>
                  <Check className="h-4 w-4 shrink-0 text-emerald-600" />
                  {d.label} <span className="text-[11px] font-normal">(herkese açık)</span>
                </div>
              ) : (
                <TriCheck key={d.key} checked={draft.allPerms || perms.has(d.key)} disabled={draft.allPerms} onChange={(on) => toggle([d.key], on)}>
                  <span className="min-w-0 flex-1" title={d.hint}>
                    <span className="block break-words text-[12.5px] font-semibold leading-snug">{d.label}</span>
                    <span className="line-clamp-2 break-words text-[11px] leading-snug text-canvas-muted">{d.hint}</span>
                  </span>
                </TriCheck>
              ),
            )}
          </div>
        </div>

        {save.error && <Note tone="err">{errText(save.error, 'Rol kaydedilemedi.')}</Note>}
        {remove.error && <Note tone="err">{errText(remove.error, 'Rol silinemedi.')}</Note>}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => save.mutate()} disabled={!dirty || !draft.name.trim() || save.isPending} className={btnPrimary}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            {role ? 'Kaydet' : 'Rolü oluştur'}
          </button>
          {dirty && role && (
            <button type="button" onClick={() => setDraft(initial)} className={btnGhost}>
              Vazgeç
            </button>
          )}
          {role && !role.system && (
            <span className="ml-auto">
              {confirmDelete ? (
                <span className="inline-flex items-center gap-2">
                  <span className="text-[12px] font-semibold text-canvas-muted">Bağlarıyla birlikte silinsin mi?</span>
                  <button type="button" onClick={() => remove.mutate()} disabled={remove.isPending} className={`${btnGhost} text-red-700`}>
                    {remove.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    Sil
                  </button>
                  <button type="button" onClick={() => setConfirmDelete(false)} className={btnGhost}>
                    Vazgeç
                  </button>
                </span>
              ) : (
                <button type="button" onClick={() => setConfirmDelete(true)} className={`${btnGhost} text-red-700`}>
                  <Trash2 className="h-4 w-4" />
                  Rolü sil
                </button>
              )}
            </span>
          )}
        </div>
        {role && (
          <p className="text-[11px] text-canvas-muted">
            Son değişiklik {fmtDate(role.updatedAt)}
            {role.updatedBy ? ` · ${role.updatedBy}` : ''}
          </p>
        )}
      </Card>

      {role && !role.system && <Bindings role={role} />}
      {!role && <Note tone="info">Rol oluşturulunca AD grubu, AD birimi, CRM rolü ya da kişi bağlayabilirsiniz.</Note>}
    </div>
  );
}

/** Onay kutusu; `mixed` alanın bir kısmı seçiliyken gösterilir. */
function TriCheck({
  checked,
  mixed = false,
  disabled = false,
  onChange,
  className = '',
  children,
}: {
  checked: boolean;
  mixed?: boolean;
  disabled?: boolean;
  onChange: (on: boolean) => void;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <label className={`flex min-h-11 min-w-0 items-center gap-2 rounded-lg px-1 sm:min-h-8 ${disabled ? 'opacity-45' : 'cursor-pointer'} ${className}`}>
      <input
        ref={ref}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 shrink-0 accent-canvas-violet"
      />
      {children}
    </label>
  );
}

/* ------------------------------------------------------------------ bağlar */

function Bindings({ role }: { role: AccessRole }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => accessApi.deleteBinding(id),
    onSuccess: () => {
      setConfirm(null);
      void invalidateAccess(qc);
    },
  });

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-[14px] font-extrabold">Bu rolü kimler alır</h3>
          <p className="text-[12px] text-canvas-muted">Bağdaki herkes rolün sayfalarını görür. Kaldırınca en geç bir dakikada düşer.</p>
        </div>
        {!adding && (
          <button type="button" onClick={() => setAdding(true)} className={btnGhost}>
            <Plus className="h-4 w-4" />
            Bağ ekle
          </button>
        )}
      </div>

      {role.bindings.length === 0 && !adding && <Note tone="warn">Bu rol henüz kimseye bağlı değil; kimse bu rolden sayfa almıyor.</Note>}

      {role.bindings.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/80">
          {role.bindings.map((b) => (
            <li key={b.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
              <Pill tone={b.type === 'crm_role' ? 'ok' : b.type === 'user' ? 'muted' : 'violet'}>{b.typeLabel}</Pill>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-bold">{b.label}</span>
                <BindingMeta b={b} />
              </span>
              {confirm === b.id ? (
                <span className="inline-flex items-center gap-1.5">
                  <button type="button" onClick={() => remove.mutate(b.id)} disabled={remove.isPending} className={`${btnGhost} text-red-700`}>
                    {remove.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    Evet, kaldır
                  </button>
                  <button type="button" onClick={() => setConfirm(null)} className={btnGhost} aria-label="Vazgeç">
                    <X className="h-4 w-4" />
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirm(b.id)}
                  className="min-h-11 rounded-lg px-2 text-[12px] font-bold text-canvas-muted hover:text-red-700 sm:min-h-0"
                >
                  Kaldır
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {remove.error && <Note tone="err">{errText(remove.error, 'Bağ kaldırılamadı.')}</Note>}

      {adding && <BindingPicker role={role} onClose={() => setAdding(false)} />}
    </Card>
  );
}

function BindingMeta({ b }: { b: AccessBinding }) {
  // Rol listesinin okuması önbellekte; üye sayısının kaynağı (üye görüntüsü ve onu dolduran okuma) oradan.
  const k = useQuery({ queryKey: ['access', 'roles'], queryFn: accessApi.roles, retry: false }).data?.kaynaklar;
  if (b.type === 'user') return <span className="block text-[11.5px] text-canvas-muted">{b.subject}</span>;
  return (
    <span className="block text-[11.5px] text-canvas-muted">
      {b.members === null ? 'Üyeler henüz okunmadı' : `${nf.format(b.members)} kişi`}
      {b.members !== null && <SqlInfo k={k} alan="items" label={`${b.label}: üye sayısı`} className="ml-0.5" />}
      {b.updatedAt ? ` · ${fmtDate(b.updatedAt)} itibarıyla` : ''}
      {b.error && <span className="ml-1 font-semibold text-amber-700">· son okuma başarısız, eski üyeler geçerli</span>}
    </span>
  );
}

function BindingPicker({ role, onClose }: { role: AccessRole; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<AccessSubjectType>('ad_group');
  const [q, setQ] = useState('');
  const list = useQuery({ queryKey: ['access', 'subjects', type], queryFn: () => accessApi.subjects(type), retry: false, staleTime: 5 * 60_000 });
  const bound = new Set(role.bindings.filter((b) => b.type === type).map((b) => b.subject.toLowerCase()));
  const add = useMutation({
    mutationFn: (c: { subject: string; label: string }) => accessApi.addBinding(role.id, { type, ...c }),
    onSuccess: () => void invalidateAccess(qc),
  });
  const needle = trFold(q.trim());
  const shown = (list.data?.items ?? []).filter(
    (c) => !needle || trFold(`${c.label} ${c.hint ?? ''} ${c.detail ?? ''} ${c.subject}`).includes(needle),
  );
  const meta = TYPES.find((t) => t.id === type)!;

  return (
    <div className="space-y-2.5 rounded-xl border border-canvas-violet/20 bg-canvas-violet/[0.03] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12.5px] font-extrabold">Bağ ekle</span>
        <button type="button" onClick={onClose} className="grid h-11 w-11 place-items-center rounded-lg text-canvas-muted hover:bg-white sm:h-8 sm:w-8" aria-label="Kapat">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex gap-1 overflow-x-auto [scrollbar-width:none]">
        {TYPES.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => {
              setType(t.id);
              setQ('');
            }}
            aria-pressed={type === t.id}
            className={`min-h-11 shrink-0 rounded-lg px-3 text-[12px] font-extrabold transition-colors sm:min-h-8 ${
              type === t.id ? 'bg-white text-canvas-ink shadow-sm ring-1 ring-canvas-violet/30' : 'text-canvas-muted hover:bg-white/70'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="text-[11.5px] text-canvas-muted">{meta.hint}</p>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`${meta.label} ara`} className={`${field} pl-9`} autoFocus />
      </div>
      {add.error && <Note tone="err">{errText(add.error, 'Bağ eklenemedi.')}</Note>}
      {add.data?.refresh && !add.data.refresh.ok && (
        <Note tone="warn">Bağ eklendi ama üyeler okunamadı; zamanlayıcı 15 dakika içinde yeniden dener.</Note>
      )}
      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>
      ) : shown.length === 0 ? (
        <p className="py-4 text-center text-[12px] text-canvas-muted">Eşleşen yok.</p>
      ) : (
        <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto overscroll-contain rounded-xl border border-slate-100 bg-white">
          {shown.map((c) => {
            const already = bound.has(c.subject.toLowerCase());
            const busy = add.isPending && add.variables?.subject === c.subject;
            return (
              <li key={c.subject} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] font-bold">{c.label}</span>
                  {(c.hint || c.detail) && (
                    <span className="block truncate text-[11px] text-canvas-muted">{[c.hint, c.detail].filter(Boolean).join(' · ')}</span>
                  )}
                </span>
                {typeof c.count === 'number' && (
                  <span className="flex shrink-0 items-center gap-0.5 text-[11.5px] font-bold tabular-nums text-canvas-muted">
                    {nf.format(c.count)} kişi
                    <SqlInfo k={list.data?.kaynaklar} alan="items" label={`${c.label}: kişi sayısı`} />
                  </span>
                )}
                {already ? (
                  <Pill tone="ok">Bağlı</Pill>
                ) : (
                  <button
                    type="button"
                    onClick={() => add.mutate({ subject: c.subject, label: c.label })}
                    disabled={add.isPending}
                    className="min-h-11 shrink-0 rounded-lg px-2.5 text-[12px] font-extrabold text-canvas-violet hover:bg-canvas-violet/10 disabled:opacity-50 sm:min-h-8"
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Ekle'}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ kişi gözüyle */

function PersonView() {
  const [q, setQ] = useState('');
  const [who, setWho] = useState<{ subject: string; label: string } | null>(null);
  const people = useQuery({ queryKey: ['access', 'subjects', 'user'], queryFn: () => accessApi.subjects('user'), retry: false, staleTime: 5 * 60_000 });
  const explain = useQuery({
    queryKey: ['access', 'explain', who?.subject],
    queryFn: () => accessApi.explain(who!.subject),
    enabled: !!who,
    retry: false,
  });
  const needle = trFold(q.trim());
  const shown = needle
    ? (people.data?.items ?? []).filter((c) => trFold(`${c.label} ${c.subject} ${c.detail ?? ''}`).includes(needle))
    : [];
  const areas = useQuery({ queryKey: ['access', 'catalog'], queryFn: accessApi.catalog, retry: false, staleTime: 10 * 60_000 }).data?.areas ?? [];
  const e = explain.data;

  return (
    <div className="grid gap-3 md:grid-cols-[280px_minmax(0,1fr)] md:gap-4">
      <div className="space-y-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input value={q} onChange={(ev) => setQ(ev.target.value)} placeholder="Ad ya da AD hesabı" className={`${field} pl-9`} />
        </div>
        {people.isLoading ? (
          <Loading />
        ) : people.error ? (
          <Note tone="err">{errText(people.error, 'Kişiler okunamadı.')}</Note>
        ) : !needle ? (
          <p className="px-1 text-[12px] text-canvas-muted">Kimin neyi neden gördüğüne bakmak için bir kişi arayın.</p>
        ) : shown.length === 0 ? (
          <p className="px-1 text-[12px] text-canvas-muted">Eşleşen kişi yok.</p>
        ) : (
          <ul className="max-h-[420px] space-y-1 overflow-y-auto overscroll-contain">
            {shown.map((c) => (
              <li key={c.subject}>
                <button
                  type="button"
                  onClick={() => setWho({ subject: c.subject, label: c.label })}
                  aria-current={who?.subject === c.subject ? 'true' : undefined}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${
                    who?.subject === c.subject ? 'border-canvas-violet/40 bg-white shadow-sm' : 'border-slate-100 bg-white/60 hover:bg-white'
                  }`}
                >
                  <span className="block truncate text-[12.5px] font-bold">{c.label}</span>
                  <span className="block truncate text-[11px] text-canvas-muted">{[c.subject, c.detail].filter(Boolean).join(' · ')}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="min-w-0">
        {!who ? (
          <Card className="grid min-h-[200px] place-items-center text-center">
            <span className="text-[12.5px] text-canvas-muted">
              <UserRound className="mx-auto mb-2 h-6 w-6" />
              Kişi seçilince rolleri, nereden aldığı ve gördüğü sayfalar burada görünür.
            </span>
          </Card>
        ) : explain.isLoading ? (
          <Loading />
        ) : explain.error ? (
          <Note tone="err">{errText(explain.error, 'Kişinin yetkisi okunamadı.')}</Note>
        ) : e ? (
          <div className="space-y-3">
            <Card className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[15px] font-extrabold">{who.label}</h3>
                <span className="text-[12px] text-canvas-muted">{e.user}</span>
                {e.isAdmin && <Pill tone="violet">Yönetici · her şeyi görür</Pill>}
              </div>
              {e.notes.map((n) => (
                <Note key={n} tone="warn">
                  {n}
                </Note>
              ))}
              <div>
                <div className={label}>Roller ve nereden geldiği</div>
                <ul className="mt-1.5 space-y-1.5">
                  {e.roles.map((r) => (
                    <li key={r.id} className="rounded-xl bg-slate-50 px-3 py-2">
                      <span className="text-[12.5px] font-extrabold">{r.name}</span>
                      <span className="block text-[11.5px] text-canvas-muted">{r.via.join(' · ')}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Chips title="AD grupları" items={e.adGroups} empty="Grubu yok" />
                <Chips title="CRM rolleri" items={e.crmRoles} empty="CRM rolü yok" />
              </div>
            </Card>
            <Card className="space-y-2">
              <div className={label}>Gördüğü sayfalar ve yapabildiği işlemler (italik)</div>
              <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr))]">
                {areas.map((a) => (
                  <div key={a.id} className="rounded-xl border border-slate-100 bg-white/70 p-2.5">
                    <div className="border-b border-slate-100 pb-1 text-[12.5px] font-extrabold">{a.label}</div>
                    <ul className="mt-1 space-y-0.5">
                      {e.pages
                        .filter((p) => p.area === a.id)
                        .map((p) => (
                          <li key={p.key} className={`flex items-center gap-2 text-[12.5px] ${p.allowed ? 'font-semibold' : 'text-canvas-muted/70'}`}>
                            {p.allowed ? <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" /> : <X className="h-3.5 w-3.5 shrink-0" />}
                            {p.label}
                          </li>
                        ))}
                      {e.features
                        .filter((f) => f.area === a.id)
                        .map((f) => (
                          <li key={f.key} className={`flex items-center gap-2 text-[12px] ${f.allowed ? 'font-semibold' : 'text-canvas-muted/70'}`}>
                            {f.allowed ? <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" /> : <X className="h-3.5 w-3.5 shrink-0" />}
                            <span className="italic">{f.label}</span>
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
              </div>
            </Card>
            <Card className="space-y-2">
              <div className={label}>ZEKİ AI'ın bu kişi için okuyabildiği veri</div>
              <ul className="grid gap-1 [grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr))]">
                {e.data.map((d) => (
                  <li key={d.id} className={`flex items-center gap-2 text-[12.5px] ${d.allowed ? 'font-semibold' : 'text-canvas-muted/70'}`} title={d.hint}>
                    {d.allowed ? <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" /> : <X className="h-3.5 w-3.5 shrink-0" />}
                    {d.label}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ veri alanları */

/** Kataloğun her varlığı hangi veri alanında: kural dosyasından ya da yöneticinin atamasıyla. Atanmamış varlıklar
 *  kimseye açılmaz (Herkes daraltılınca); yönetici buradan alanını seçer. */
function DataDomains() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['access', 'data-entities'], queryFn: accessApi.dataEntities, retry: false, staleTime: 60_000 });
  const catalog = useQuery({ queryKey: ['access', 'catalog'], queryFn: accessApi.catalog, retry: false, staleTime: 10 * 60_000 });
  const domains = catalog.data?.data ?? [];
  const counts = list.data?.counts ?? {};
  const [filter, setFilter] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const active = filter ?? ((counts.atanmamis ?? 0) > 0 ? 'atanmamis' : 'all');
  const set = useMutation({
    mutationFn: (v: { entity: string; domain: string | null }) => accessApi.setEntityDomain(v.entity, v.domain),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['access', 'data-entities'] }),
  });
  const needle = trFold(q.trim());
  const rows = (list.data?.items ?? []).filter(
    (r) => (active === 'all' || r.domain === active) && (!needle || trFold(`${r.entity} ${r.description}`).includes(needle)),
  );
  const [shown, setShown] = useState(100);
  useEffect(() => setShown(100), [active, needle]);

  if (list.isLoading || catalog.isLoading) return <Loading />;
  if (list.error || catalog.error) return <Note tone="err">{errText(list.error ?? catalog.error, 'Veri alanları okunamadı.')}</Note>;
  const total = list.data?.items.length ?? 0;

  return (
    <div className="space-y-3">
      <Note tone="info">
        Her tablo bir veri alanına düşer; rol, ZEKİ AI'ın hangi alanları okuyabileceğini taşır. Alan kurallarla atanır; buradan
        seçtiğiniz alan kuralın önüne geçer. «Atanmamış» tablolar, «Herkes» rolü daraltıldığında yalnız yöneticiye açık kalır.
      </Note>
      <div className="flex flex-wrap items-center gap-1.5">
        <SqlInfo k={list.data?.kaynaklar} alan="counts" label="Veri alanı sayaçları ve satır sayıları" />
        {[{ id: 'all', label: 'Hepsi', n: total }, ...domains.map((d) => ({ id: d.id, label: d.label, n: counts[d.id] ?? 0 }))].map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setFilter(c.id)}
            aria-pressed={active === c.id}
            className={`min-h-11 rounded-lg px-2.5 text-[12px] font-extrabold transition-colors sm:min-h-8 ${
              active === c.id ? 'bg-white text-canvas-ink shadow-sm ring-1 ring-canvas-violet/30' : 'bg-slate-100 text-canvas-muted hover:text-canvas-ink'
            } ${c.id === 'atanmamis' && c.n > 0 ? 'text-amber-800' : ''}`}
          >
            {c.label} <span className="tabular-nums opacity-70">{nf.format(c.n)}</span>
          </button>
        ))}
      </div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tablo adı ya da açıklaması" className={`${field} pl-9`} />
      </div>
      {set.error && <Note tone="err">{errText(set.error, 'Alan değiştirilemedi.')}</Note>}
      {rows.length === 0 ? (
        <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte tablo yok.</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/80">
          {rows.slice(0, shown).map((r) => (
            <li key={r.entity} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="truncate font-mono text-[12px] font-bold">{r.entity}</span>
                  <Pill tone={r.source === 'crm' ? 'ok' : 'muted'}>{r.source === 'crm' ? 'CRM' : 'Logo'}</Pill>
                </span>
                <span className="block truncate text-[11.5px] text-canvas-muted">
                  {[r.description, `${nf.format(r.rows)} satır`, r.tables > 1 ? `${nf.format(r.tables)} tablo` : ''].filter(Boolean).join(' · ')}
                </span>
              </span>
              <select
                aria-label={`${r.entity} veri alanı`}
                value={r.domain}
                disabled={set.isPending}
                onChange={(e) => set.mutate({ entity: r.entity, domain: e.target.value })}
                className="min-h-11 rounded-lg border border-slate-200 bg-white px-2 text-[12.5px] font-semibold sm:min-h-8"
              >
                {domains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
              {r.manual && (
                <button
                  type="button"
                  onClick={() => set.mutate({ entity: r.entity, domain: null })}
                  className="min-h-11 rounded-lg px-2 text-[11.5px] font-bold text-canvas-muted hover:text-canvas-ink sm:min-h-0"
                  title="Yöneticinin atamasını kaldır; alan kurala göre belirlensin"
                >
                  Kurala dön
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {rows.length > shown && (
        <button type="button" onClick={() => setShown((n) => n + 200)} className={`${btnGhost} w-full`}>
          Devamını göster ({nf.format(rows.length - shown)} tablo daha)
        </button>
      )}
    </div>
  );
}

function Chips({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <div className={label}>{title}</div>
      {items.length ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {items.map((i) => (
            <Pill key={i} tone="muted">
              {i}
            </Pill>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-[12px] text-canvas-muted">{empty}</p>
      )}
    </div>
  );
}
