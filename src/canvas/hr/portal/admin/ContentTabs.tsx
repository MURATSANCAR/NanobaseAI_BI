import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, ChevronRight, Download, ImagePlus, Pencil, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../../../admin/ui';
import Sheet from '../../../editorial/studio/reader/Sheet';
import { EmptyHint } from '../../../components/Explain';
import { FileDrop, FilePick } from '../../../components/FileDrop';
import { AskSheet, Block } from '../../parts';
import { fileSize, localIso, longDay, portalApi, portalSrc, weekday, type DocRequest, type Faq, type Post, type PortalMeta } from '../portalApi';

type Tab = 'talepler' | 'duyurular' | 'evrak' | 'yemek' | 'sss';

export default function ContentTabs({ tab, meta }: { tab: Tab; meta: PortalMeta }) {
  if (tab === 'talepler') return <Requests meta={meta} />;
  if (tab === 'duyurular') return <Posts meta={meta} />;
  if (tab === 'evrak') return <Docs meta={meta} />;
  if (tab === 'yemek') return <MenuEditor />;
  return <FaqEditor meta={meta} />;
}

const useRefresh = () => {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: ['hr', 'portal'] });
};

/* ------------------------------------------------------------------ evrak talepleri */

const TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = { bekliyor: 'warn', hazirlaniyor: 'violet', hazir: 'ok', red: 'err' };

function Requests({ meta }: { meta: PortalMeta }) {
  const [status, setStatus] = useState('acik');
  const list = useQuery({ queryKey: ['hr', 'portal', 'admin-requests', status], queryFn: () => portalApi.adminRequests(status), enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<DocRequest | null>(null);
  return (
    <Block title="Evrak talepleri" help="Çalışanların Evrak talebi ekranından gönderdiği istekler. Durumu siz işaretlersiniz; portal kimseye e-posta göndermez, belgeyi siz iletirsiniz."
      action={
        <select className={field} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Durum">
          <option value="acik">Açık talepler</option>
          {Object.entries(meta.requestStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          <option value="hepsi">Hepsi</option>
        </select>
      }>
      {list.error && <Note tone="err">{errText(list.error, 'Talepler okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && !list.data.items.length && <EmptyHint title={status === 'acik' ? 'Açık talep yok' : 'Bu durumda talep yok'} />}
      {!!list.data?.items.length && (
        <TableWrap>
          <thead><tr><th className={th}>Tarih</th><th className={th}>Çalışan</th><th className={th}>Evrak</th><th className={th}>Teslim</th><th className={th}>Not</th><th className={th}>Durum</th><th className={th} /></tr></thead>
          <tbody>
            {list.data.items.map((r) => (
              <tr key={r.id} className="border-t border-slate-100">
                <td className={`${td} whitespace-nowrap`}>{longDay(r.createdAt)}</td>
                <td className={td}><span className="font-bold">{r.display || r.username}</span><span className="block font-mono text-[11px] text-canvas-muted">{r.username}</span></td>
                <td className={td}>{r.docType}</td>
                <td className={td}>{r.deliveryLabel}{r.mail && <span className="block text-[11.5px] text-canvas-muted">{r.mail}</span>}</td>
                <td className={`${td} max-w-[280px] whitespace-pre-line text-[12px]`}>{r.note || '—'}</td>
                <td className={td}><Pill tone={TONE[r.status] ?? 'muted'}>{r.statusLabel}</Pill>{r.handledBy && <span className="block text-[11px] text-canvas-muted">{r.handledBy}</span>}</td>
                <td className={td}><button type="button" className={btnGhost} onClick={() => setEditing(r)}>İşle</button></td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      <RequestSheet req={editing} meta={meta} onClose={() => setEditing(null)} />
    </Block>
  );
}

function RequestSheet({ req, meta, onClose }: { req: DocRequest | null; meta: PortalMeta; onClose: () => void }) {
  const refresh = useRefresh();
  const [status, setStatus] = useState('hazirlaniyor');
  const [answer, setAnswer] = useState('');
  useEffect(() => { if (req) { setStatus(req.status === 'bekliyor' ? 'hazirlaniyor' : req.status); setAnswer(req.answer ?? ''); } }, [req]);
  const save = useMutation({
    mutationFn: () => portalApi.handleRequest((req as DocRequest).id, { status, answer }),
    onSuccess: () => { toast.success('Talep güncellendi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Sheet open={!!req} modal onClose={onClose} title="Evrak talebi" subtitle={req ? `${req.display || req.username} · ${req.docType}` : undefined}>
      {req && (
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <p className="text-[12.5px]">{longDay(req.createdAt)} · {req.deliveryLabel}{req.mail ? ` · ${req.mail}` : ''}</p>
          {req.note && <p className="whitespace-pre-line rounded-lg bg-slate-50 px-3 py-2 text-[12.5px]">{req.note}</p>}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Durum</span>
            <select className={field} value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(meta.requestStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Çalışana not {status === 'red' ? '(zorunlu)' : '(isteğe bağlı)'}</span>
            <textarea className={`${field} min-h-[80px]`} value={answer} onChange={(e) => setAnswer(e.target.value)} required={status === 'red'} placeholder="Ör. belge e-postanıza gönderildi / İK'dan teslim alabilirsiniz" />
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button>
          </div>
        </form>
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------------ duyurular */

function Posts({ meta }: { meta: PortalMeta }) {
  const list = useQuery({ queryKey: ['hr', 'portal', 'admin-posts'], queryFn: portalApi.adminPosts, enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<Post | 'new' | null>(null);
  const today = localIso(new Date());
  return (
    <Block title="Şirket içi duyurular" help="Yayın tarihi gelen ve açık duyuru çalışanlara görünür. İleri tarihli duyuru o gün kendiliğinden yayına girer."
      action={<button type="button" className={btnPrimary} onClick={() => setEditing('new')}><Plus aria-hidden className="h-4 w-4" />Duyuru ekle</button>}>
      {list.error && <Note tone="err">{errText(list.error, 'Duyurular okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && !list.data.items.length && <EmptyHint title="Henüz duyuru yok" why="«Duyuru ekle» ile ilk duyuruyu yayımlayın." />}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {(list.data?.items ?? []).map((p) => (
          <li key={p.id} className="flex gap-3 rounded-xl bg-white/85 p-3 shadow-sm">
            {p.hasImage && <img src={portalSrc(`/portal/posts/${p.id}/image`)} alt="" className="h-16 w-16 shrink-0 rounded-lg bg-slate-100 object-cover" loading="lazy" />}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wide text-canvas-violet">
                {p.category} · {longDay(p.publishDate)}
                {!p.active ? <Pill tone="muted">Kapalı</Pill> : p.publishDate > today ? <Pill tone="warn">İleri tarihli</Pill> : null}
              </div>
              <div className="truncate text-[13px] font-bold">{p.title}</div>
              <div className="line-clamp-2 text-[12px] text-canvas-muted">{p.body}</div>
              <button type="button" className="mt-1 inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0" onClick={() => setEditing(p)}>
                <Pencil aria-hidden className="h-3.5 w-3.5" />Düzenle
              </button>
            </div>
          </li>
        ))}
      </ul>
      <PostSheet post={editing} meta={meta} onClose={() => setEditing(null)} onCreated={(p) => setEditing(p)} />
    </Block>
  );
}

function PostSheet({ post, meta, onClose, onCreated }: { post: Post | 'new' | null; meta: PortalMeta; onClose: () => void; onCreated: (p: Post) => void }) {
  const refresh = useRefresh();
  const isNew = post === 'new';
  const cur = post && post !== 'new' ? post : null;
  const cats = meta.settings.postCategories;
  const [form, setForm] = useState({ title: '', body: '', category: cats[0] ?? '', publishDate: localIso(new Date()), active: true });
  const [ask, setAsk] = useState(false);
  const [imgBusy, setImgBusy] = useState(false);
  const [imgVer, setImgVer] = useState(0);
  useEffect(() => {
    if (cur) setForm({ title: cur.title, body: cur.body, category: cur.category, publishDate: cur.publishDate.slice(0, 10), active: cur.active });
    else if (isNew) setForm({ title: '', body: '', category: cats[0] ?? '', publishDate: localIso(new Date()), active: true });
  }, [post]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => (isNew ? portalApi.createPost(form) : portalApi.updatePost((cur as Post).id, form)),
    onSuccess: (p) => { toast.success(isNew ? 'Duyuru kaydedildi; görsel ekleyebilirsiniz.' : 'Kaydedildi.'); refresh(); if (isNew) onCreated(p); else onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const del = useMutation({
    mutationFn: () => portalApi.deletePost((cur as Post).id),
    onSuccess: () => { setAsk(false); toast.success('Duyuru silindi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
    onSettled: () => setAsk(false),
  });
  const image = async (file: File | null) => {
    if (!cur) return;
    setImgBusy(true);
    try {
      const p = file ? await portalApi.uploadPostImage(cur.id, file) : await portalApi.deletePostImage(cur.id);
      onCreated(p);
      setImgVer((v) => v + 1);
      refresh();
    } catch (e) {
      toast.error(errText(e, 'Görsel kaydedilemedi.'));
    } finally {
      setImgBusy(false);
    }
  };
  return (
    <Sheet open={!!post} modal wide onClose={onClose} title={isNew ? 'Yeni duyuru' : 'Duyuruyu düzenle'}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kategori</span>
            <select className={field} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {cats.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yayın tarihi</span>
            <input type="date" className={field} value={form.publishDate} onChange={(e) => setForm({ ...form, publishDate: e.target.value })} required />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Başlık</span>
          <input className={field} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required maxLength={200} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Metin</span>
          <textarea className={`${field} min-h-[160px]`} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} required />
        </label>
        <label className="flex items-center gap-2 text-[12.5px] font-bold">
          <input type="checkbox" className="h-4 w-4" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />Yayında (kapalı duyuru çalışanlara görünmez)
        </label>
        {cur && (
          <div className="flex flex-col gap-2 rounded-xl bg-slate-50 p-3">
            <span className={labelCls}>Görsel</span>
            {cur.hasImage && <img key={imgVer} src={`${portalSrc(`/portal/posts/${cur.id}/image`)}?v=${imgVer}`} alt="" className="max-h-48 w-full rounded-lg bg-white object-contain" />}
            <div className="flex flex-wrap gap-2">
              <FilePick label={cur.hasImage ? 'Görseli değiştir' : 'Görsel ekle'} accept={meta.imageAccept} maxBytes={meta.fileMaxMb * 1024 * 1024} busy={imgBusy} onPick={(f) => void image(f)} />
              {cur.hasImage && <button type="button" className={btnGhost} disabled={imgBusy} onClick={() => void image(null)}>Görseli kaldır</button>}
            </div>
          </div>
        )}
        {isNew && <p className="flex items-center gap-1.5 text-[12px] text-canvas-muted"><ImagePlus aria-hidden className="h-4 w-4" />Görsel, duyuru kaydedildikten sonra eklenir.</p>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          {cur ? <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setAsk(true)}><Trash2 aria-hidden className="h-4 w-4" />Sil</button> : <span />}
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending ? 'Kaydediliyor…' : 'Kaydet'}</button>
          </div>
        </div>
      </form>
      <AskSheet open={ask} title="Duyuruyu sil" danger confirm="Sil" busy={del.isPending}
        message={<>«{cur?.title}» duyurusu silinecek; yayından kaldırmak için «Yayında» işaretini de kaldırabilirsiniz. Bu işlem geri alınamaz.</>}
        onClose={() => setAsk(false)} onConfirm={() => del.mutate()} />
    </Sheet>
  );
}

/* ------------------------------------------------------------------ evrak deposu */

function Docs({ meta }: { meta: PortalMeta }) {
  const refresh = useRefresh();
  const list = useQuery({ queryKey: ['hr', 'portal', 'docs'], queryFn: portalApi.docs, enabled: ENGINE_ENABLED });
  const cats = meta.settings.docCategories;
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState(cats[0] ?? '');
  const [code, setCode] = useState('');
  const [ask, setAsk] = useState<{ id: string; title: string } | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => portalApi.deleteDoc(id),
    onSuccess: () => { setAsk(null); toast.success('Evrak silindi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
    onSettled: () => setAsk(null),
  });
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,420px)_1fr] lg:gap-4">
      <Block title="Evrak ekle" help="İzin talep formu, avans formu, işe giriş rehberi gibi herkesin indireceği dosyalar.">
        <div className="flex flex-col gap-2.5">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Evrakın adı</span>
            <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ör. İzin Talep Formu" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kategori</span>
              <select className={field} value={category} onChange={(e) => setCategory(e.target.value)}>
                {cats.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kod (isteğe bağlı)</span>
              <input className={field} value={code} onChange={(e) => setCode(e.target.value)} placeholder="FRM-001" />
            </label>
          </div>
          <FileDrop size="sm" title="Dosyayı bırakın ya da seçin" accept={meta.fileAccept} maxBytes={meta.fileMaxMb * 1024 * 1024}
            disabled={!title.trim()} disabledReason="Önce evrakın adını yazın."
            run={(f) => portalApi.addDoc(f, { title: title.trim(), category, code: code.trim() || undefined })}
            onDone={() => { toast.success('Evrak eklendi.'); setTitle(''); setCode(''); refresh(); }}
            errorFallback="Evrak yüklenemedi." />
        </div>
      </Block>
      <Block title="Depodaki evraklar">
        {list.error && <Note tone="err">{errText(list.error, 'Evraklar okunamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {list.data && !list.data.items.length && <EmptyHint title="Depo boş" />}
        {!!list.data?.items.length && (
          <TableWrap>
            <thead><tr><th className={th}>Evrak</th><th className={th}>Kategori</th><th className={th}>Kod</th><th className={th}>Dosya</th><th className={th} /></tr></thead>
            <tbody>
              {list.data.items.map((d) => (
                <tr key={d.id} className="border-t border-slate-100">
                  <td className={`${td} font-bold`}>{d.title}</td>
                  <td className={td}>{d.category}</td>
                  <td className={`${td} font-mono text-[11.5px]`}>{d.code || '—'}</td>
                  <td className={td}>
                    <button type="button" className="inline-flex min-h-11 items-center gap-1 text-[12px] text-canvas-violet hover:underline sm:min-h-0" onClick={() => void portalApi.docFile(d).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                      <Download aria-hidden className="h-3.5 w-3.5" />{fileSize(d.size)}
                    </button>
                  </td>
                  <td className={td}>
                    <button type="button" aria-label={`${d.title} evrakını sil`} className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-red-700 hover:bg-red-50 sm:h-8 sm:w-8" onClick={() => setAsk({ id: d.id, title: d.title })}>
                      <Trash2 aria-hidden className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Block>
      <AskSheet open={!!ask} title="Evrakı sil" danger confirm="Sil" busy={del.isPending}
        message={<>«{ask?.title}» depodan silinecek. Bu işlem geri alınamaz.</>}
        onClose={() => setAsk(null)} onConfirm={() => ask && del.mutate(ask.id)} />
    </div>
  );
}

/* ------------------------------------------------------------------ yemek listesi */

const mondayOf = (d: Date) => {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
};

function MenuEditor() {
  const refresh = useRefresh();
  const [start, setStart] = useState(() => mondayOf(new Date()));
  const days = Array.from({ length: 5 }, (_, i) => { const x = new Date(start); x.setDate(x.getDate() + i); return localIso(x); });
  const q = useQuery({ queryKey: ['hr', 'portal', 'menu', 'edit', days[0]], queryFn: () => portalApi.menu(days[0], days[4]), enabled: ENGINE_ENABLED });
  const [text, setText] = useState<Record<string, string>>({});
  useEffect(() => {
    const md = q.data;
    if (md) setText(Object.fromEntries(days.map((d) => [d, (md.days.find((x) => x.day === d)?.items ?? []).join('\n')])));
  }, [q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => portalApi.saveMenu(days.map((d) => ({ day: d, items: (text[d] ?? '').split('\n').map((x) => x.trim()).filter(Boolean) }))),
    onSuccess: () => { toast.success('Haftanın menüsü kaydedildi.'); refresh(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const shift = (w: number) => setStart((s) => { const x = new Date(s); x.setDate(x.getDate() + w * 7); return x; });
  return (
    <Block title="Yemek listesi" help="Hafta içi beş gün; her satıra bir yemek. Boş bırakılan gün menüsüz görünür."
      action={
        <div className="flex items-center gap-1.5">
          <button type="button" className={btnGhost} aria-label="Önceki hafta" onClick={() => shift(-1)}><ChevronLeft aria-hidden className="h-4 w-4" /></button>
          <span className="text-[12.5px] font-extrabold">{longDay(days[0])} haftası</span>
          <button type="button" className={btnGhost} aria-label="Sonraki hafta" onClick={() => shift(1)}><ChevronRight aria-hidden className="h-4 w-4" /></button>
        </div>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Menü okunamadı.')}</Note>}
      {q.isLoading ? <Loading /> : (
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
            {days.map((d) => (
              <label key={d} className="flex flex-col gap-1">
                <span className={`${labelCls} capitalize`}>{weekday(d)}</span>
                <textarea className={`${field} min-h-[120px]`} value={text[d] ?? ''} onChange={(e) => setText({ ...text, [d]: e.target.value })} placeholder={'Mercimek çorbası\nIzgara köfte\nPilav\nAyran'} />
              </label>
            ))}
          </div>
          <div className="flex justify-end"><button type="submit" className={btnPrimary} disabled={save.isPending}>{save.isPending ? 'Kaydediliyor…' : 'Haftayı kaydet'}</button></div>
        </form>
      )}
    </Block>
  );
}

/* ------------------------------------------------------------------ sık sorulan sorular */

function FaqEditor({ meta }: { meta: PortalMeta }) {
  const list = useQuery({ queryKey: ['hr', 'portal', 'faq'], queryFn: portalApi.faq, enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<Faq | 'new' | null>(null);
  const items = list.data?.items ?? [];
  const cats = [...new Set(items.map((f) => f.category))];
  return (
    <Block title="Sık sorulan sorular" help="Kategoriler Listeler ve ayarlar sekmesindeki sırayla görünür."
      action={<button type="button" className={btnPrimary} onClick={() => setEditing('new')}><Plus aria-hidden className="h-4 w-4" />Soru ekle</button>}>
      {list.error && <Note tone="err">{errText(list.error, 'Sorular okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data && !items.length && <EmptyHint title="Henüz soru yok" why="«Soru ekle» ile izin, ücret, çalışma düzeni gibi sık sorulanları ekleyin." />}
      {cats.map((c) => (
        <div key={c} className="mb-3">
          <h3 className="mb-1 text-[13px] font-extrabold">{c}</h3>
          <ul className="flex flex-col divide-y divide-slate-100 rounded-xl bg-white/85">
            {items.filter((f) => f.category === c).map((f) => (
              <li key={f.id}>
                <button type="button" className="flex min-h-11 w-full items-center justify-between gap-2 px-3 py-2 text-left text-[13px] hover:bg-slate-50" onClick={() => setEditing(f)}>
                  <span className="min-w-0 font-bold">{f.question}</span>
                  <Pencil aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <FaqSheet faq={editing} meta={meta} onClose={() => setEditing(null)} />
    </Block>
  );
}

function FaqSheet({ faq, meta, onClose }: { faq: Faq | 'new' | null; meta: PortalMeta; onClose: () => void }) {
  const refresh = useRefresh();
  const cur = faq && faq !== 'new' ? faq : null;
  const cats = meta.settings.faqCategories;
  const [form, setForm] = useState({ category: cats[0] ?? '', question: '', answer: '', sort: 0 });
  const [ask, setAsk] = useState(false);
  useEffect(() => {
    setForm(cur ? { category: cur.category, question: cur.question, answer: cur.answer, sort: cur.sort } : { category: cats[0] ?? '', question: '', answer: '', sort: 0 });
  }, [faq]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => (cur ? portalApi.updateFaq(cur.id, form) : portalApi.createFaq(form)),
    onSuccess: () => { toast.success('Kaydedildi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const del = useMutation({
    mutationFn: () => portalApi.deleteFaq((cur as Faq).id),
    onSuccess: () => { setAsk(false); toast.success('Soru silindi.'); refresh(); onClose(); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.')),
    onSettled: () => setAsk(false),
  });
  return (
    <Sheet open={!!faq} modal onClose={onClose} title={cur ? 'Soruyu düzenle' : 'Yeni soru'}>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid grid-cols-[1fr_90px] gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kategori</span>
            <select className={field} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {cats.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sıra</span>
            <input type="number" className={field} value={form.sort} onChange={(e) => setForm({ ...form, sort: Number(e.target.value) || 0 })} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Soru</span>
          <input className={field} value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} required maxLength={300} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Cevap</span>
          <textarea className={`${field} min-h-[140px]`} value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} required />
        </label>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {cur ? <button type="button" className={`${btnGhost} !text-red-700`} onClick={() => setAsk(true)}><Trash2 aria-hidden className="h-4 w-4" />Sil</button> : <span />}
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
            <button type="submit" className={btnPrimary} disabled={save.isPending}>Kaydet</button>
          </div>
        </div>
      </form>
      <AskSheet open={ask} title="Soruyu sil" danger confirm="Sil" busy={del.isPending}
        message={<>«{cur?.question}» sorusu silinecek. Bu işlem geri alınamaz.</>}
        onClose={() => setAsk(false)} onConfirm={() => del.mutate()} />
    </Sheet>
  );
}
