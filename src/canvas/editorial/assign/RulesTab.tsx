import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Sparkles, Trash2, X } from 'lucide-react';
import { assignApi, type AssignRule, type RuleCategory, type RuleVersion } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { assignKeys, assignRulesOptions } from '../queries';

/** Kategori–editör kural tablosu. Kategori CRM «Kitaplık»; kitaplığı boş projede marka. Taslak yazılır, onay
 *  yetkisi olan kişi yürürlüğe alır; önceki sürüm arşive geçer. Öneri ekranı yalnız yürürlükteki sürümü kullanır. */

type Names = Map<string, string>;
const keyOf = (r: { kind: string; id: string }) => `${r.kind}:${r.id}`;
const kindLabel = (k: string) => (k === 'kitaplik' ? 'Kitaplık' : 'Marka');

function People({ ids, names }: { ids: string[]; names: Names }) {
  if (!ids.length) return <span className="text-canvas-muted">—</span>;
  return <>{ids.map((id) => names.get(id) ?? 'Bilinmeyen kişi').join(', ')}</>;
}

function RuleTable({ rules, names, diff }: { rules: AssignRule[]; names: Names; diff?: Map<string, 'yeni' | 'degisti'> }) {
  if (!rules.length) return <p className="py-4 text-center text-[12px] text-canvas-muted">Kural yok.</p>;
  return (
    <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-100 bg-white">
      {rules.map((r) => (
        <li key={keyOf(r)} className="grid gap-1 px-3 py-2 text-[12.5px] sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)] sm:gap-3">
          <div className="min-w-0">
            <span className="break-words font-extrabold">{r.name || '—'}</span> <span className="text-[11px] text-canvas-muted">{kindLabel(r.kind)}</span>
            {diff?.get(keyOf(r)) && <span className="ml-1.5"><Pill tone="violet">{diff.get(keyOf(r)) === 'yeni' ? 'Yeni' : 'Değişti'}</Pill></span>}
          </div>
          <div className="min-w-0 break-words">
            <span className="text-[11px] font-bold text-canvas-muted sm:hidden">Birincil: </span>
            <People ids={r.primary} names={names} />
          </div>
          <div className="min-w-0 break-words text-canvas-muted">
            <span className="text-[11px] font-bold sm:hidden">Yedek: </span>
            <People ids={r.backup} names={names} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function PersonPicker({ ids, onChange, options, names, placeholder }: { ids: string[]; onChange: (ids: string[]) => void; options: { id: string; name: string | null }[]; names: Names; placeholder: string }) {
  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {ids.map((id) => (
          <span key={id} className="inline-flex items-center gap-1 rounded-lg bg-canvas-violet/10 py-0.5 pl-2 pr-0.5 text-[12px] font-bold text-canvas-violet">
            {names.get(id) ?? 'Bilinmeyen kişi'}
            <button type="button" aria-label={`${names.get(id) ?? 'Kişiyi'} çıkar`} className="flex h-7 w-7 items-center justify-center rounded-md hover:bg-canvas-violet/10" onClick={() => onChange(ids.filter((x) => x !== id))}>
              <X aria-hidden className="h-3.5 w-3.5" />
            </button>
          </span>
        ))}
      </div>
      <select
        aria-label={placeholder}
        value=""
        onChange={(e) => e.target.value && onChange([...ids, e.target.value])}
        className={`${field} mt-1`}
      >
        <option value="">{placeholder}</option>
        {options
          .filter((o) => !ids.includes(o.id))
          .map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
      </select>
    </div>
  );
}

function Editor({
  initial,
  categories,
  editors,
  names,
  onCancel,
}: {
  initial: AssignRule[];
  categories: RuleCategory[];
  editors: { id: string; name: string | null; disabled: boolean }[];
  names: Names;
  onCancel: () => void;
}) {
  const qc = useQueryClient();
  const [rules, setRules] = useState<AssignRule[]>(initial);
  const [note, setNote] = useState('');
  const [addKey, setAddKey] = useState('');
  const used = new Set(rules.map(keyOf));
  const active = editors.filter((e) => !e.disabled);
  const catByKey = useMemo(() => new Map(categories.map((c) => [keyOf(c), c])), [categories]);
  const save = useMutation({
    mutationFn: () => assignApi.saveDraft(rules, note.trim() || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      toast.success('Taslak kaydedildi', { description: 'Onaylanınca yürürlüğe girer.' });
      onCancel();
    },
  });
  const suggest = useMutation({
    mutationFn: assignApi.suggestRules,
    onSuccess: (r) => {
      const have = new Set(rules.map(keyOf));
      const add = r.rules.filter((x) => !have.has(keyOf(x)));
      setRules([...rules, ...add]);
      toast(add.length ? `${add.length} kategori CRM geçmişinden eklendi` : 'Eklenecek yeni kategori çıkmadı', {
        description: 'Her kategoride en çok proje yürütmüş etkin editör birincil, sonraki iki kişi yedek.',
      });
    },
  });
  const set = (i: number, patch: Partial<AssignRule>) => setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const missingPrimary = rules.some((r) => !r.primary.length);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnGhost} onClick={() => suggest.mutate()} disabled={suggest.isPending}>
          <Sparkles aria-hidden className="h-4 w-4" />
          {suggest.isPending ? 'Hesaplanıyor…' : 'CRM geçmişinden öner'}
        </button>
      </div>
      {suggest.error && <Note tone="err">{errText(suggest.error, 'Öneri hesaplanamadı.')}</Note>}
      <ul className="space-y-2">
        {rules.map((r, i) => {
          const cat = catByKey.get(keyOf(r));
          return (
            <li key={keyOf(r)} className="rounded-2xl border border-slate-100 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 text-[12.5px]">
                  <span className="break-words font-extrabold">{r.name}</span> <span className="text-[11px] text-canvas-muted">{kindLabel(r.kind)}</span>
                  {cat && (
                    <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">
                      {nf.format(cat.projects)} proje · CRM geçmişi: {cat.editors.slice(0, 4).map((e) => `${e.name} ${e.count}`).join(', ') || 'editör yok'}
                      {cat.editors.length > 4 ? ` +${cat.editors.length - 4}` : ''}
                    </div>
                  )}
                </div>
                <button type="button" aria-label={`${r.name} kuralını sil`} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:bg-slate-100 sm:h-8 sm:w-8" onClick={() => setRules(rules.filter((_, j) => j !== i))}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <div>
                  <span className={label}>Birincil</span>
                  <PersonPicker ids={r.primary} onChange={(ids) => set(i, { primary: ids, backup: r.backup.filter((x) => !ids.includes(x)) })} options={active} names={names} placeholder="Birincil editör ekle" />
                </div>
                <div>
                  <span className={label}>Yedek</span>
                  <PersonPicker ids={r.backup} onChange={(ids) => set(i, { backup: ids })} options={active.filter((e) => !r.primary.includes(e.id))} names={names} placeholder="Yedek editör ekle" />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-col gap-2 sm:flex-row">
        <select aria-label="Kategori ekle" value={addKey} onChange={(e) => setAddKey(e.target.value)} className={field}>
          <option value="">Kategori seçin…</option>
          {(['kitaplik', 'marka'] as const).map((k) => (
            <optgroup key={k} label={kindLabel(k)}>
              {categories
                .filter((c) => c.kind === k && !used.has(keyOf(c)))
                .map((c) => (
                  <option key={keyOf(c)} value={keyOf(c)}>
                    {c.name} ({nf.format(c.projects)})
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        <button
          type="button"
          className={btnGhost}
          disabled={!addKey}
          onClick={() => {
            const c = catByKey.get(addKey);
            if (c) setRules([...rules, { kind: c.kind, id: c.id, name: c.name, primary: [], backup: [] }]);
            setAddKey('');
          }}
        >
          <Plus aria-hidden className="h-4 w-4" />
          Ekle
        </button>
      </div>
      <label className="block">
        <span className={label}>Değişiklik notu (onaylayan görür)</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} className={`${field} mt-1`} placeholder="Ör. çocuk kitaplığına yeni editör" />
      </label>
      {missingPrimary && <Note tone="warn">Her kategoride en az bir birincil editör olmalı.</Note>}
      {save.error && <Note tone="err">{errText(save.error, 'Taslak kaydedilemedi.')}</Note>}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className={btnGhost} onClick={onCancel}>
          Vazgeç
        </button>
        <button type="button" className={btnPrimary} disabled={save.isPending || missingPrimary} onClick={() => save.mutate()}>
          {save.isPending ? 'Kaydediliyor…' : 'Taslağı kaydet'}
        </button>
      </div>
    </div>
  );
}

function diffOf(draft: RuleVersion, active: RuleVersion | null) {
  const before = new Map((active?.rules ?? []).map((r) => [keyOf(r), r]));
  const marks = new Map<string, 'yeni' | 'degisti'>();
  for (const r of draft.rules) {
    const b = before.get(keyOf(r));
    if (!b) marks.set(keyOf(r), 'yeni');
    else if (b.primary.join() !== r.primary.join() || b.backup.join() !== r.backup.join()) marks.set(keyOf(r), 'degisti');
  }
  const draftKeys = new Set(draft.rules.map(keyOf));
  const removed = (active?.rules ?? []).filter((r) => !draftKeys.has(keyOf(r)));
  return { marks, removed };
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }) : '—');

export default function RulesTab() {
  const qc = useQueryClient();
  const q = useQuery(assignRulesOptions());
  const d = q.data;
  const [editing, setEditing] = useState(false);
  const names = useMemo(() => new Map((d?.editors ?? []).map((e) => [e.id, e.name ?? 'Adı kayıtlı değil'])), [d]);
  const approve = useMutation({
    mutationFn: (v: number) => assignApi.approve(v),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      toast.success('Kural tablosu yürürlükte');
    },
  });
  const discard = useMutation({
    mutationFn: assignApi.discardDraft,
    onSuccess: () => qc.invalidateQueries({ queryKey: assignKeys.all }),
  });
  const err = errText(q.error, 'Kural tablosu okunamadı.');
  const diff = d?.draft ? diffOf(d.draft, d.active) : null;

  return (
    <div className="space-y-3 lg:space-y-4">
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && <Panel><p className="py-10 text-center text-[12.5px] text-canvas-muted">Kural tablosu okunuyor…</p></Panel>}

      {d && editing && (
        <Panel>
          <h2 className="px-1 text-[13px] font-extrabold">Taslak {d.draft ? `sürüm ${d.draft.version}` : '(yeni)'}</h2>
          <p className="mb-3 mt-0.5 px-1 text-[11.5px] text-canvas-muted">Kaydedilen taslak onaylanana kadar öneriyi etkilemez.</p>
          <Editor initial={d.draft?.rules ?? d.active?.rules ?? []} categories={d.categories} editors={d.editors} names={names} onCancel={() => setEditing(false)} />
        </Panel>
      )}

      {d?.draft && !editing && (
        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-2 px-1">
            <div className="min-w-0">
              <h2 className="text-[13px] font-extrabold">
                Onay bekleyen taslak · sürüm {d.draft.version} <Pill tone="warn">Taslak</Pill>
              </h2>
              <p className="mt-0.5 text-[11.5px] text-canvas-muted">
                {d.draft.createdBy} · {when(d.draft.createdAt)}
                {d.draft.note ? ` · «${d.draft.note}»` : ''}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {d.canEdit && (
                <>
                  <button type="button" className={btnGhost} onClick={() => setEditing(true)}>
                    Düzenle
                  </button>
                  <button type="button" className={btnGhost} onClick={() => discard.mutate()} disabled={discard.isPending}>
                    Taslağı sil
                  </button>
                </>
              )}
              {d.canApprove && (
                <button type="button" className={btnPrimary} onClick={() => approve.mutate(d.draft!.version)} disabled={approve.isPending}>
                  {approve.isPending ? 'Onaylanıyor…' : 'Onayla ve yürürlüğe al'}
                </button>
              )}
            </div>
          </div>
          {!d.canApprove && <p className="mt-1 px-1 text-[11.5px] text-canvas-muted">Onay yetkisi olan kişi yürürlüğe alır.</p>}
          {(approve.error || discard.error) && <Note tone="err">{errText(approve.error || discard.error, 'İşlem yapılamadı.')}</Note>}
          {diff && diff.removed.length > 0 && (
            <div className="mt-2">
              <Note tone="warn">Kaldırılan: {diff.removed.map((r) => r.name).join(', ')}</Note>
            </div>
          )}
          <div className="mt-3">
            <RuleTable rules={d.draft.rules} names={names} diff={diff?.marks} />
          </div>
        </Panel>
      )}

      {d && (
        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-2 px-1">
            <div className="min-w-0">
              <h2 className="text-[13px] font-extrabold">
                Yürürlükteki kurallar{d.active ? ` · sürüm ${d.active.version}` : ''}
              </h2>
              <p className="mt-0.5 text-[11.5px] text-canvas-muted">
                {d.active
                  ? `Onaylayan ${d.active.approvedBy} · ${when(d.active.approvedAt)} · ${nf.format(d.active.rules.length)} kategori`
                  : 'Henüz onaylanmış kural yok; öneri yalnız CRM geçmişine ve yüke bakar.'}
              </p>
            </div>
            {d.canEdit && !editing && !d.draft && (
              <button type="button" className={btnPrimary} onClick={() => setEditing(true)}>
                {d.active ? 'Yeni taslak' : 'Kural tablosu yaz'}
              </button>
            )}
          </div>
          {d.active && (
            <div className="mt-3">
              <div className="hidden px-3 pb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted sm:grid sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)] sm:gap-3">
                <span>Kategori</span>
                <span>Birincil</span>
                <span>Yedek</span>
              </div>
              <RuleTable rules={d.active.rules} names={names} />
            </div>
          )}
        </Panel>
      )}

      {d && d.history.length > 0 && (
        <Panel>
          <details>
            <summary className="cursor-pointer px-1 text-[13px] font-extrabold">Önceki sürümler ({nf.format(d.history.length)})</summary>
            <ul className="mt-3 space-y-3">
              {d.history.map((v) => (
                <li key={v.id}>
                  <p className="mb-1 px-1 text-[11.5px] text-canvas-muted">
                    Sürüm {v.version} · onaylayan {v.approvedBy} · {when(v.approvedAt)}
                    {v.note ? ` · «${v.note}»` : ''}
                  </p>
                  <RuleTable rules={v.rules} names={names} />
                </li>
              ))}
            </ul>
          </details>
        </Panel>
      )}
    </div>
  );
}
