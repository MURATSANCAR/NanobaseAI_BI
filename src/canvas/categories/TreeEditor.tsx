import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, ChevronRight, GitCompare, ListTree, Loader2, Plus, Save, Send, Trash2, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import Sheet from '../editorial/studio/reader/Sheet';
import { categoriesApi, fmtInt, TREE_TONE, type Impact, type Level, type Options, type TreeNode } from './api';
import { ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Kategori ağacı: yürürlükteki sürüm (salt okunur, düğüm başına kitap/satış) ve taslak (düzenlenir, eşlenir,
 *  onaya gönderilir). Onay açıkça verilen yetkiyle ve gönderenden başka biri tarafından verilir. */

const LEVELS: Level[] = ['yayinevi', 'ana', 'alt', 'altalt'];
type Editable = Pick<TreeNode, 'id' | 'parentId' | 'level' | 'name' | 'code' | 'sort' | 'status'>;
const newId = () => Math.random().toString(16).slice(2, 14);

export default function TreeEditor() {
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const tree = useQuery({ queryKey: ['categories', 'tree'], queryFn: categoriesApi.tree, enabled: ENGINE_ENABLED });
  const options = useQuery({ queryKey: ['categories', 'options'], queryFn: categoriesApi.options, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
  const draft = tree.data?.draft ?? null;
  const live = tree.data?.inForce ?? null;
  const [view, setView] = useState<'draft' | 'live'>('draft');
  const shown = view === 'draft' && draft ? draft : live;
  const editable = view === 'draft' && draft?.status === 'taslak' && !!me?.canEditTree;

  const [nodes, setNodes] = useState<Editable[]>([]);
  const [dirty, setDirty] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [ask, setAsk] = useState<null | 'approve' | 'reject' | 'discard' | 'suggest'>(null);
  const [impactOpen, setImpactOpen] = useState(false);

  useEffect(() => {
    if (!dirty) setNodes((shown?.nodes ?? []).map(({ id, parentId, level, name, code, sort, status }) => ({ id, parentId, level, name, code, sort, status })));
  }, [shown, dirty]);
  useEffect(() => { if (!draft) setView('live'); }, [draft]);

  const after = (msg: string) => () => {
    setDirty(false);
    qc.invalidateQueries({ queryKey: ['categories'] });
    toast.success(msg);
  };
  const onErr = (e: unknown) => toast.error(errText(e, 'İşlem yapılamadı.') ?? '');
  const save = useMutation({ mutationFn: () => categoriesApi.saveTree({ nodes, version: draft?.version }), onSuccess: after('Taslak kaydedildi.'), onError: onErr });
  const open = useMutation({ mutationFn: categoriesApi.openDraft, onSuccess: () => { setView('draft'); after('Taslak yürürlükteki ağaçtan açıldı.')(); }, onError: onErr });
  const suggest = useMutation({
    mutationFn: (replace: boolean) => categoriesApi.suggest(replace),
    onSuccess: (r) => {
      setView('draft');
      setDirty(false);
      qc.invalidateQueries({ queryKey: ['categories'] });
      const s = r.suggestion;
      toast.success(s ? `Taslak ağaç: ${s.nodes} düğüm, ${fmtInt(s.placed)}/${fmtInt(s.books)} kitap yerleşti.` : 'Taslak hazır.');
    },
    onError: onErr,
  });
  const submit = useMutation({ mutationFn: categoriesApi.submit, onSuccess: after('Taslak onaya gönderildi.'), onError: onErr });
  const withdraw = useMutation({ mutationFn: categoriesApi.withdraw, onSuccess: after('Taslak onaydan geri alındı.'), onError: onErr });
  const discard = useMutation({ mutationFn: categoriesApi.discardDraft, onSuccess: () => { setAsk(null); setView('live'); after('Taslak silindi.')(); }, onError: onErr });
  const decide = useMutation({
    mutationFn: ({ ok, note }: { ok: boolean; note: string }) => (ok ? categoriesApi.approve(draft!.version, note || undefined) : categoriesApi.reject(draft!.version, note)),
    onSuccess: (_r, v) => { setAsk(null); setView(v.ok ? 'live' : 'draft'); after(v.ok ? 'Ağaç yürürlüğe girdi; kitaplar yeniden yerleşti.' : 'Taslak gerekçesiyle geri gönderildi.')(); },
    onError: onErr,
  });
  const busy = [save, open, suggest, submit, withdraw, discard, decide].some((m) => m.isPending);

  const byParent = useMemo(() => {
    const m = new Map<string | null, Editable[]>();
    for (const n of nodes) {
      const k = n.parentId ?? null;
      m.set(k, [...(m.get(k) ?? []), n]);
    }
    for (const list of m.values()) list.sort((a, b) => a.sort - b.sort || a.name.localeCompare(b.name, 'tr'));
    return m;
  }, [nodes]);
  const info = useMemo(() => new Map((shown?.nodes ?? []).map((n) => [n.id, n])), [shown]);

  const edit = (fn: (list: Editable[]) => Editable[]) => { setNodes((l) => fn(l)); setDirty(true); };
  const addChild = (parent: Editable | null) => {
    const level = parent ? LEVELS[Math.min(LEVELS.indexOf(parent.level) + 1, LEVELS.length - 1)] : 'yayinevi';
    if (parent && parent.level === 'altalt') return toast.error('Alt alt kategorinin altına düğüm açılmaz.');
    const siblings = byParent.get(parent?.id ?? null) ?? [];
    const id = newId();
    edit((l) => [...l, { id, parentId: parent?.id ?? null, level, name: 'Yeni kategori', code: null, sort: (siblings.at(-1)?.sort ?? 0) + 1, status: 'aktif' }]);
    setSelected(id);
  };
  const remove = (id: string) => {
    const drop = new Set([id]);
    let grew = true;
    while (grew) {
      grew = false;
      for (const n of nodes) if (n.parentId && drop.has(n.parentId) && !drop.has(n.id)) { drop.add(n.id); grew = true; }
    }
    edit((l) => l.filter((n) => !drop.has(n.id)));
    if (selected && drop.has(selected)) setSelected(null);
  };
  const move = (n: Editable, dir: -1 | 1) => {
    const sib = byParent.get(n.parentId ?? null) ?? [];
    const i = sib.findIndex((x) => x.id === n.id);
    const j = i + dir;
    if (j < 0 || j >= sib.length) return;
    const order = [...sib];
    [order[i], order[j]] = [order[j], order[i]];
    const pos = new Map(order.map((x, k) => [x.id, k]));
    edit((l) => l.map((x) => (pos.has(x.id) ? { ...x, sort: pos.get(x.id)! } : x)));
  };

  const mine = draft?.submittedBy && me && draft.submittedBy.toLowerCase() === me.username.toLowerCase();
  const sel = nodes.find((n) => n.id === selected) ?? null;

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            {live && (
              <button type="button" onClick={() => { setView('live'); setDirty(false); }} aria-pressed={view === 'live'}
                className={`inline-flex min-h-9 items-center gap-1.5 rounded-xl px-2.5 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${view === 'live' ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
                Yürürlükte v{live.version}
              </button>
            )}
            {draft && (
              <button type="button" onClick={() => { setView('draft'); setDirty(false); }} aria-pressed={view === 'draft'}
                className={`inline-flex min-h-9 items-center gap-1.5 rounded-xl px-2.5 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${view === 'draft' ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
                {draft.statusLabel} v{draft.version}
              </button>
            )}
            {shown && <Pill tone={TREE_TONE[shown.status]}>{shown.statusLabel}</Pill>}
            {!live && !draft && <span className="text-[12.5px] font-semibold text-canvas-muted">Henüz ağaç yok.{me?.canEditTree ? ' «Veriden taslak oluştur» ile mevcut sınıflamalardan bir başlangıç taslağı hazırlanır.' : ''}</span>}
          </div>
          <div className="flex flex-wrap gap-2">
            {me?.canEditTree && !draft && live && (
              <button type="button" className={btnGhost} disabled={busy} onClick={() => open.mutate()}><Plus aria-hidden className="h-4 w-4" /> Taslak aç</button>
            )}
            {me?.canEditTree && (!draft || draft.status === 'taslak') && (
              <button type="button" className={btnGhost} disabled={busy} onClick={() => (draft?.nodes.length ? setAsk('suggest') : suggest.mutate(false))}>
                {suggest.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <ListTree aria-hidden className="h-4 w-4" />}
                Veriden taslak oluştur
              </button>
            )}
            {draft && (
              <button type="button" className={btnGhost} disabled={busy || dirty} onClick={() => setImpactOpen(true)} title={dirty ? 'Önce kaydedin' : undefined}>
                <GitCompare aria-hidden className="h-4 w-4" /> Etki önizlemesi
              </button>
            )}
            {editable && (
              <>
                <button type="button" className={btnPrimary} disabled={busy || !dirty} onClick={() => save.mutate()}><Save aria-hidden className="h-4 w-4" /> Kaydet</button>
                <button type="button" className={btnGhost} disabled={busy || dirty || !nodes.length} onClick={() => submit.mutate()}><Send aria-hidden className="h-4 w-4" /> Onaya gönder</button>
                <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('discard')}><Trash2 aria-hidden className="h-4 w-4" /> Taslağı sil</button>
              </>
            )}
            {draft?.status === 'onay-bekliyor' && view === 'draft' && (
              <>
                {me?.canEditTree && <button type="button" className={btnGhost} disabled={busy} onClick={() => withdraw.mutate()}><Undo2 aria-hidden className="h-4 w-4" /> Geri al</button>}
                {me?.canApproveTree && !mine && (
                  <>
                    <button type="button" className={btnPrimary} disabled={busy} onClick={() => setAsk('approve')}>Yürürlüğe al</button>
                    <button type="button" className={btnGhost} disabled={busy} onClick={() => setAsk('reject')}>Geri gönder</button>
                  </>
                )}
              </>
            )}
          </div>
        </div>
        {shown && (
          <p className="mt-2 text-[12px] leading-snug text-canvas-muted">
            {shown.status === 'yururlukte' && <>{shown.approvedBy} onayladı, {fmtDate(shown.approvedAt)}. </>}
            {shown.status === 'onay-bekliyor' && <>{shown.submittedBy} onaya gönderdi, {fmtDate(shown.submittedAt)}. {mine ? 'Gönderen onaylayamaz; başka bir yetkili onaylar.' : ''} </>}
            {shown.decisionNote && <>Karar notu: {shown.decisionNote}. </>}
            {shown.note}
          </p>
        )}
        {dirty && <div className="mt-2"><Note tone="warn">Kaydedilmemiş değişiklik var.</Note></div>}
      </Panel>

      {tree.isLoading && <Loading />}
      {tree.error && <Note tone="err">{errText(tree.error, 'Ağaç açılamadı.')}</Note>}

      {shown && (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:gap-4">
          <Panel>
            <div className="flex items-center justify-between gap-2">
              <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
                Düğümler ({fmtInt(nodes.length)})
                <SqlInfo k={kaynakOf(tree.data)} alan="_hepsi" label="Düğüm ve kitap sayıları" />
              </h2>
              {editable && <button type="button" className={`${btnGhost} !min-h-9`} onClick={() => addChild(null)}><Plus aria-hidden className="h-4 w-4" /> Yayınevi düğümü ekle</button>}
            </div>
            <ul className="mt-2 flex flex-col">
              {(byParent.get(null) ?? []).map((n) => (
                <NodeRow key={n.id} n={n} depth={0} byParent={byParent} info={info} editable={editable} selected={selected}
                  onSelect={setSelected} onAdd={addChild} onMove={move} />
              ))}
            </ul>
          </Panel>
          <div className="flex flex-col gap-3 lg:gap-4">
            {sel ? (
              <NodePanel key={sel.id} n={sel} path={info.get(sel.id)?.path ?? sel.name} counts={info.get(sel.id)} mappings={info.get(sel.id)?.mappings ?? {}}
                editable={editable} dirty={dirty} systems={tree.data?.systems ?? {}} levels={tree.data?.levels} options={options.data}
                onRename={(name) => edit((l) => l.map((x) => (x.id === sel.id ? { ...x, name } : x)))}
                onToggle={() => edit((l) => l.map((x) => (x.id === sel.id ? { ...x, status: x.status === 'aktif' ? 'pasif' : 'aktif' } : x)))}
                onRemove={() => remove(sel.id)}
                onSaved={() => qc.invalidateQueries({ queryKey: ['categories', 'tree'] })} />
            ) : (
              <Panel>
                <p className="text-[12.5px] leading-snug text-canvas-muted">
                  Bir düğüm seçin: kitap sayısı, satış, CRM Kitaplık / ürün kategorisi / raf / web kategorisi, site (T-soft) ve konu kodu eşlemeleri.
                  Kitaplar ağaca bu eşlemelerle yerleşir; Zeki AI yalnız yerleşemeyen kitapta ağaçtan seçer.
                </p>
              </Panel>
            )}
          </div>
        </div>
      )}

      <AskSheet open={ask === 'approve'} title="Ağacı yürürlüğe al" confirm="Yürürlüğe al" input="Not (isteğe bağlı)" busy={decide.isPending}
        message="Önceki yürürlükteki sürüm arşive geçer; bütün kitaplar yeni ağaca yeniden yerleşir. Önce etki önizlemesine bakın."
        onClose={() => setAsk(null)} onConfirm={(note) => decide.mutate({ ok: true, note })} />
      <AskSheet open={ask === 'reject'} title="Taslağı geri gönder" confirm="Geri gönder" input="Gerekçe" required busy={decide.isPending}
        message="Taslak düzenlenmek üzere hazırlayana döner." onClose={() => setAsk(null)} onConfirm={(note) => decide.mutate({ ok: false, note })} />
      <AskSheet open={ask === 'discard'} title="Taslağı sil" confirm="Sil" danger busy={discard.isPending}
        message="Taslak ve eşlemeleri silinir; yürürlükteki ağaç değişmez." onClose={() => setAsk(null)} onConfirm={() => discard.mutate()} />
      <AskSheet open={ask === 'suggest'} title="Taslağın üzerine yaz" confirm="Üzerine yaz" danger busy={suggest.isPending}
        message="CRM kitap kartlarından kurala göre (marka → hedef kitle → kitaplık) yeni bir taslak ağaç kurulur; bu taslaktaki düğümler ve eşlemeler silinir." onClose={() => setAsk(null)}
        onConfirm={() => { setAsk(null); suggest.mutate(true); }} />
      {impactOpen && <ImpactSheet onClose={() => setImpactOpen(false)} />}
    </div>
  );
}

function NodeRow({ n, depth, byParent, info, editable, selected, onSelect, onAdd, onMove }: {
  n: Editable;
  depth: number;
  byParent: Map<string | null, Editable[]>;
  info: Map<string, TreeNode>;
  editable: boolean;
  selected: string | null;
  onSelect: (id: string) => void;
  onAdd: (p: Editable) => void;
  onMove: (n: Editable, dir: -1 | 1) => void;
}) {
  const kids = byParent.get(n.id) ?? [];
  const [open, setOpen] = useState(depth < 1);
  const i = info.get(n.id);
  return (
    <li>
      <div className={`flex min-h-11 items-center gap-1 rounded-xl pr-1 ${selected === n.id ? 'bg-canvas-violet/10' : 'hover:bg-slate-50'}`} style={{ paddingLeft: `${depth * 14}px` }}>
        <button type="button" aria-label={open ? 'Daralt' : 'Aç'} aria-expanded={open} disabled={!kids.length} onClick={() => setOpen((v) => !v)}
          className="inline-flex h-9 w-8 shrink-0 items-center justify-center text-canvas-muted disabled:opacity-0">
          <ChevronRight aria-hidden className={`h-4 w-4 transition-transform duration-150 ease-out motion-reduce:transition-none ${open ? 'rotate-90' : ''}`} />
        </button>
        <button type="button" onClick={() => onSelect(n.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <span className={`min-w-0 truncate text-[12.5px] font-bold ${n.status === 'pasif' ? 'text-canvas-muted line-through' : ''}`}>{n.name}</span>
          {i?.books != null && <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">{fmtInt(i.books)}</span>}
        </button>
        {editable && (
          <span className="flex shrink-0 items-center">
            <button type="button" aria-label="Yukarı" onClick={() => onMove(n, -1)} className="inline-flex h-9 w-8 items-center justify-center text-canvas-muted hover:text-canvas-ink"><ArrowUp aria-hidden className="h-3.5 w-3.5" /></button>
            <button type="button" aria-label="Aşağı" onClick={() => onMove(n, 1)} className="inline-flex h-9 w-8 items-center justify-center text-canvas-muted hover:text-canvas-ink"><ArrowDown aria-hidden className="h-3.5 w-3.5" /></button>
            {n.level !== 'altalt' && (
              <button type="button" aria-label="Alt düğüm ekle" onClick={() => { setOpen(true); onAdd(n); }} className="inline-flex h-9 w-8 items-center justify-center text-canvas-violet"><Plus aria-hidden className="h-4 w-4" /></button>
            )}
          </span>
        )}
      </div>
      {open && kids.length > 0 && (
        <ul>
          {kids.map((k) => (
            <NodeRow key={k.id} n={k} depth={depth + 1} byParent={byParent} info={info} editable={editable} selected={selected}
              onSelect={onSelect} onAdd={onAdd} onMove={onMove} />
          ))}
        </ul>
      )}
    </li>
  );
}

const PICK: Record<string, keyof Options | null> = {
  crm_kitaplik: 'kitaplik', crm_urunkategorisi: 'urunkategorisi', crm_raf: 'raf', crm_sergilenecek: 'sergilenecek',
  marka: 'marka', hedef_kitle: 'hedefKitle', tsoft: 'tsoft', crm_webkategori: null, konu_standardi: null,
};

function NodePanel({ n, path, counts, mappings, editable, dirty, systems, levels, options, onRename, onToggle, onRemove, onSaved }: {
  n: Editable;
  path: string;
  counts?: TreeNode;
  mappings: Record<string, Array<{ id: string; name: string | null }>>;
  editable: boolean;
  dirty: boolean;
  systems: Record<string, string>;
  levels?: Record<Level, string>;
  options?: Options;
  onRename: (name: string) => void;
  onToggle: () => void;
  onRemove: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(n.name);
  return (
    <Panel>
      <div className={labelCls}>{levels?.[n.level] ?? n.level}</div>
      <h3 className="mt-0.5 break-words text-[15px] font-extrabold">{path}</h3>
      {counts?.books != null && (
        <p className="mt-1 text-[12px] font-semibold text-canvas-muted">
          {fmtInt(counts.books)} kitap · {fmtInt(counts.approved ?? 0)} onaylı · son dönem net satış {fmtInt(counts.sales ?? 0)} adet ·{' '}
          <Link to={`${ROOT}/kuyruk?dugum=${n.id}`} className="font-extrabold text-canvas-violet hover:underline">Kitapları aç</Link>
        </p>
      )}
      {editable && (
        <div className="mt-3 flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ad</span>
            <input className={field} value={name} onChange={(e) => { setName(e.target.value); onRename(e.target.value); }} />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnGhost} onClick={onToggle}>{n.status === 'aktif' ? 'Pasife al' : 'Etkinleştir'}</button>
            <button type="button" className={`${btnGhost} !text-red-700`} onClick={onRemove}><Trash2 aria-hidden className="h-4 w-4" /> Sil (alt düğümlerle)</button>
          </div>
        </div>
      )}
      <h4 className="mt-4 text-[13px] font-extrabold">Eşlemeler</h4>
      {editable && dirty && <p className="mt-1 text-[11.5px] font-semibold text-amber-800">Eşleme düzenlemek için önce ağacı kaydedin.</p>}
      <div className="mt-2 flex flex-col gap-2">
        {Object.entries(systems).map(([sys, lab]) => (
          <MappingRow key={sys} nodeId={n.id} system={sys} label={lab} items={mappings[sys] ?? []} editable={editable && !dirty}
            choices={PICK[sys] ? ((options?.[PICK[sys] as string] as Array<{ id: string; name: string; active?: boolean }>) ?? []) : null}
            onSaved={onSaved} />
        ))}
      </div>
    </Panel>
  );
}

function MappingRow({ nodeId, system, label, items, editable, choices, onSaved }: {
  nodeId: string;
  system: string;
  label: string;
  items: Array<{ id: string; name: string | null }>;
  editable: boolean;
  choices: Array<{ id: string; name: string; active?: boolean }> | null;
  onSaved: () => void;
}) {
  const [add, setAdd] = useState('');
  const save = useMutation({
    mutationFn: (list: Array<{ externalId: string; externalName?: string | null }>) => categoriesApi.setMappings(nodeId, system, list),
    onSuccess: () => { setAdd(''); onSaved(); },
    onError: (e) => toast.error(errText(e, 'Eşleme kaydedilemedi.') ?? ''),
  });
  const cur = items.map((x) => ({ externalId: x.id, externalName: x.name }));
  const addOne = () => {
    const v = add.trim();
    if (!v) return;
    const c = choices?.find((x) => x.id === v);
    save.mutate([...cur, { externalId: v, externalName: c?.name ?? v }]);
  };
  if (!editable && !items.length) return null;
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2">
      <div className="text-[11.5px] font-bold text-canvas-muted">{label}</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {items.map((x) => (
          <span key={x.id} className="inline-flex min-h-8 items-center gap-1 rounded-lg bg-white px-2 text-[12px] font-semibold">
            {x.name ?? x.id}
            {editable && (
              <button type="button" aria-label={`${x.name ?? x.id} eşlemesini kaldır`} disabled={save.isPending}
                onClick={() => save.mutate(cur.filter((c) => c.externalId !== x.id))} className="text-canvas-muted hover:text-red-700">×</button>
            )}
          </span>
        ))}
      </div>
      {editable && (
        <div className="mt-1.5 flex gap-1.5">
          {choices ? (
            <select className={field} value={add} onChange={(e) => setAdd(e.target.value)} aria-label={`${label} ekle`}>
              <option value="">Ekle…</option>
              {choices.filter((c) => !items.some((i) => i.id === c.id)).map((c) => (
                <option key={c.id} value={c.id}>{c.name}{c.active === false ? ' (pasif)' : ''}</option>
              ))}
            </select>
          ) : (
            <input className={field} value={add} onChange={(e) => setAdd(e.target.value)} placeholder={system === 'crm_webkategori' ? 'Web alt kategorisi metni' : 'Kod'} aria-label={`${label} ekle`} />
          )}
          <button type="button" className={`${btnGhost} !min-h-9 shrink-0`} disabled={!add.trim() || save.isPending} onClick={addOne}>Ekle</button>
        </div>
      )}
    </div>
  );
}

function ImpactSheet({ onClose }: { onClose: () => void }) {
  const q = useQuery({ queryKey: ['categories', 'impact'], queryFn: categoriesApi.impact, enabled: ENGINE_ENABLED, gcTime: 0 });
  const d: Impact | undefined = q.data;
  return (
    <Sheet open modal wide onClose={onClose} title="Etki önizlemesi" subtitle="Taslak yürürlüğe girerse ne değişir">
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Etki hesaplanamadı.')}</Note>}
      {d && (
        <div className="flex flex-col gap-3 text-[12.5px]">
          <div className="flex justify-end"><SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Etki önizlemesi" /></div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat k="Yeri değişen kitap" v={d.books.moved} />
            <Stat k="Yeni yerleşen" v={d.books.newlyPlaced} />
            <Stat k="Yeri kalmayan" v={d.books.lost} warn />
            <Stat k="Onayı düşecek profil" v={d.orphanedApproved.length} warn />
          </div>
          <Block title="Düğüm değişiklikleri" empty={!d.added.length && !d.removed.length && !d.renamed.length && !d.moved.length}>
            {d.added.map((x) => <li key={`a${x.nodeId}`}><Pill tone="ok">Yeni</Pill> {x.path}</li>)}
            {d.removed.map((x) => <li key={`r${x.nodeId}`}><Pill tone="err">Kalkıyor</Pill> {x.path}</li>)}
            {d.renamed.map((x) => <li key={`n${x.nodeId}`}><Pill tone="violet">Ad</Pill> {x.from} → {x.to}</li>)}
            {d.moved.map((x) => <li key={`m${x.nodeId}`}><Pill tone="warn">Taşınıyor</Pill> {x.fromPath} → {x.toPath}</li>)}
          </Block>
          <Block title="Kitapların yer değişimi" empty={!d.bookMoves.length}>
            {d.bookMoves.map((m, i) => <li key={i}>{fmtInt(m.books)} kitap: {m.fromPath ?? 'yeri yok'} → {m.toPath ?? 'yeri yok'}</li>)}
          </Block>
          <Block title="Onaylı kategorisi kalkan kitaplar (yeniden onay gerekir)" empty={!d.orphanedApproved.length}>
            {d.orphanedApproved.map((o) => <li key={o.bookId}><Link to={`${ROOT}/kitap/${o.bookId}`} className="font-bold text-canvas-violet hover:underline">{o.name}</Link> — {o.path}</li>)}
          </Block>
          <Block title="Editör atama kuralı etkilenen kategoriler" empty={!d.m2.length}>
            {d.m2.map((m) => <li key={m.id}>{m.name} ({m.kind === 'kitaplik' ? 'Kitaplık' : 'marka'}): {m.before.join(', ') || 'ağaçta yok'} → {m.after.join(', ') || 'ağaçta yok'}</li>)}
          </Block>
          <Block title="Site (T-soft) karşılığı olmayan alt düğümler" empty={!d.withoutTsoft.length}>
            {d.withoutTsoft.map((x) => <li key={x.nodeId}>{x.path}</li>)}
          </Block>
          <Block title="Eşleme değişiklikleri" empty={!d.mappingChanges.length}>
            {d.mappingChanges.map((m) => <li key={m.nodeId}>{m.path}: +{m.added.length} / −{m.removed.length}</li>)}
          </Block>
        </div>
      )}
    </Sheet>
  );
}

function Stat({ k, v, warn }: { k: string; v: number; warn?: boolean }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2">
      <div className="text-[11px] font-bold text-canvas-muted">{k}</div>
      <div className={`font-mono text-[20px] font-bold tabular-nums ${warn && v ? 'text-red-700' : ''}`}>{fmtInt(v)}</div>
    </div>
  );
}

function Block({ title, empty, children }: { title: string; empty: boolean; children: ReactNode }) {
  return (
    <section>
      <h4 className="text-[13px] font-extrabold">{title}</h4>
      {empty ? <p className="mt-0.5 text-canvas-muted">Yok.</p> : <ul className="mt-1 flex flex-col gap-1 leading-snug">{children}</ul>}
    </section>
  );
}
