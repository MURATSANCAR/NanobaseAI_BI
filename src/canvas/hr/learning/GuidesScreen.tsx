import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { NAV, trFold } from '../../nav/navModel';
import { Block, Tabs } from '../parts';
import { learningApi, type Guide, type Info } from './learningApi';
import { GuideText, LearningFrame, fmtDay, useLearningInfo } from './parts';

/** Modül rehberleri: her menü ekranı için kısa, adım adım kullanım rehberi. Zeki AI ekranın menü tanımından taslak yazar,
 *  portal sorumlusu (`ik.rehber-yaz`) düzeltip yayımlar. Yayımlı rehber ekranın başlığındaki «Nasıl kullanılır»dan açılır;
 *  okuyanın «yaradı / yaramadı» oyu yalnız o sürüme sayılır. */

type Item = { id: string; label: string; group: string; hint: string; keywords: string[] };
const ITEMS: Item[] = NAV.filter((g) => g.id !== 'kampus').flatMap((g) =>
  g.items.map((i) => ({ id: i.id, label: i.label, group: g.label, hint: i.hint, keywords: i.keywords ?? [] })),
);

export default function GuidesScreen() {
  const info = useLearningInfo();
  const q = useQuery({ queryKey: ['hr', 'learning', 'guides'], queryFn: learningApi.guides, enabled: ENGINE_ENABLED });
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<Item | null>(null);
  const byRoute = useMemo(() => new Map((q.data?.items ?? []).map((g) => [g.moduleRoute, g])), [q.data]);
  const needle = trFold(search.trim());
  const shown = ITEMS.filter((i) => !needle || trFold(`${i.label} ${i.group} ${i.hint}`).includes(needle));
  const published = (q.data?.items ?? []).filter((g) => g.published).length;
  return (
    <LearningFrame
      crumb="Eğitim ve gelişim"
      title="Modül rehberleri"
      lead="Her ekran için kısa, göreve dayalı rehber. Yayımlanan rehber o ekranın üst şeridindeki «Nasıl kullanılır» düğmesinden açılır."
    >
      {q.error && <Note tone="err">{errText(q.error, 'Rehberler okunamadı.')}</Note>}
      <Block title="Ekranlar" help={`${ITEMS.length} ekran · ${published} rehber yayında`}
        action={<input className={`${field} sm:w-[260px]`} placeholder="Ekran ara" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Ekran ara" />}>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((i) => {
            const g = byRoute.get(i.id);
            return (
              <li key={i.id}>
                <button type="button" onClick={() => setOpen(i)}
                  className="flex min-h-11 w-full flex-col items-start gap-1 rounded-xl border border-slate-100 bg-white px-3 py-2 text-left transition-transform duration-150 ease-out hover:border-canvas-violet/40 active:scale-[0.99]">
                  <span className="text-[13px] font-extrabold">{i.label}</span>
                  <span className="text-[11px] text-canvas-muted">{i.group}</span>
                  <span className="flex flex-wrap gap-1.5">
                    {!g && <Pill tone="muted">Rehber yok</Pill>}
                    {g && <Pill tone={g.published ? 'ok' : 'warn'}>{g.published ? `Yayında · sürüm ${g.version}` : 'Taslak'}</Pill>}
                    {g?.dirty && <Pill tone="warn">Yayımlanmamış değişiklik</Pill>}
                    {g && g.published && <Pill tone="muted">Yaradı {g.votes.useful} · yaramadı {g.votes.notUseful}</Pill>}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </Block>
      {open && info.data && <GuideEditor item={open} guide={byRoute.get(open.id) ?? null} info={info.data} onClose={() => setOpen(null)} />}
    </LearningFrame>
  );
}

function GuideEditor({ item, guide, info, onClose }: { item: Item; guide: Guide | null; info: Info; onClose: () => void }) {
  const qc = useQueryClient();
  const canWrite = info.can.guides;
  const [title, setTitle] = useState(guide?.title ?? `${item.label} — nasıl kullanılır`);
  const [body, setBody] = useState(guide?.body ?? '');
  const [notes, setNotes] = useState('');
  const [tab, setTab] = useState<'yaz' | 'onizle'>(guide ? 'onizle' : 'yaz');
  const [current, setCurrent] = useState<Guide | null>(guide);
  const refresh = (g: Guide) => {
    setCurrent(g);
    setTitle(g.title);
    setBody(g.body);
    void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'guides'] });
    void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'guide-index'] });
  };
  const save = useMutation({
    mutationFn: () => (current ? learningApi.updateGuide(current.id, { title, body }) : learningApi.createGuide({ moduleRoute: item.id, title, body })),
    onSuccess: (g) => {
      toast.success('Taslak kaydedildi.');
      refresh(g);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const draft = useMutation({
    mutationFn: () => learningApi.draftGuide({ moduleRoute: item.id, label: item.label, group: item.group, hint: item.hint, keywords: item.keywords, notes, guideId: current?.id }),
    onSuccess: (g) => {
      toast.success('Zeki AI taslağı hazır; okuyup düzeltin.');
      refresh(g);
      setTab('yaz');
    },
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.')),
  });
  const publish = useMutation({
    mutationFn: async () => {
      const g = current && (current.title !== title || current.body !== body) ? await learningApi.updateGuide(current.id, { title, body }) : current;
      if (!g) throw new Error('Önce taslağı kaydedin.');
      return learningApi.publishGuide(g.id);
    },
    onSuccess: (g) => {
      toast.success(`Yayımlandı (sürüm ${g.version}).`);
      refresh(g);
    },
    onError: (e) => toast.error(errText(e, 'Yayımlanamadı.')),
  });
  const unpublish = useMutation({
    mutationFn: () => learningApi.unpublishGuide(current?.id ?? ''),
    onSuccess: () => {
      toast.success('Rehber yayından kaldırıldı.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaldırılamadı.')),
  });
  const busy = save.isPending || draft.isPending || publish.isPending || unpublish.isPending;
  return (
    <Sheet open modal wide onClose={onClose} title={item.label} subtitle={`${item.group} · ${item.hint}`}>
      <div className="flex flex-col gap-3 p-4">
        {current && (
          <p className="text-[11.5px] text-canvas-muted">
            {current.published ? `Yayında: sürüm ${current.version}, ${fmtDay(current.approvedAt)} (${current.approvedBy ?? '—'})` : 'Henüz yayımlanmadı'}
            {current.modelDrafted ? ' · Zeki AI taslağından' : ''}
          </p>
        )}
        <Tabs tabs={[{ key: 'yaz', label: 'Metin' }, { key: 'onizle', label: 'Önizleme' }] as const} value={tab} onChange={setTab} />
        {tab === 'onizle' ? (
          body.trim() ? <GuideText body={body} /> : <p className="text-[12px] text-canvas-muted">Metin yok.</p>
        ) : (
          <>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Başlık</span>
              <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} disabled={!canWrite} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Metin</span>
              <textarea className={`${field} min-h-[260px] font-mono text-[12.5px]`} value={body} onChange={(e) => setBody(e.target.value)} disabled={!canWrite}
                placeholder={'## Ne işe yarar\n…\n\n## Adımlar\n1. …\n2. …'} />
              <span className="text-[11px] text-canvas-muted">«## » başlık, «1. » adım, «- » madde. Altyapı ya da model adı yazılmaz; yapay zekâ özelliği «Zeki AI» diye geçer.</span>
            </label>
            {canWrite && info.modelVar && (
              <label className="flex flex-col gap-1">
                <span className={labelCls}>Zeki AI'a notlarınız (isteğe bağlı)</span>
                <textarea className={`${field} min-h-[64px]`} value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="ör. En sık iş: sözleşme özetini onaylamak; kullanıcılar takvim sekmesini bulamıyor" />
              </label>
            )}
          </>
        )}
        {canWrite ? (
          <div className="flex flex-wrap gap-2">
            {info.modelVar && (
              <button type="button" className={btnGhost} disabled={busy} onClick={() => draft.mutate()}>
                {draft.isPending ? 'Zeki AI yazıyor…' : current ? 'Zeki AI ile yeniden yaz' : 'Zeki AI taslağı'}
              </button>
            )}
            <button type="button" className={btnGhost} disabled={busy || !title.trim() || !body.trim()} onClick={() => save.mutate()}>Taslağı kaydet</button>
            <button type="button" className={btnPrimary} disabled={busy || !current || !body.trim()} onClick={() => publish.mutate()}>Yayımla</button>
            {current?.published && <button type="button" className={btnGhost} disabled={busy} onClick={() => unpublish.mutate()}>Yayından kaldır</button>}
          </div>
        ) : (
          <Note tone="info">Rehber yazma yetkiniz yok; yalnız okuyabilirsiniz.</Note>
        )}
      </div>
    </Sheet>
  );
}
