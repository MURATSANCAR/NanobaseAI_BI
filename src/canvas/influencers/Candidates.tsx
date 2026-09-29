import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Search, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED, editorialSearchApi } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { PART_LABEL, STAGE_TONE, fmtDay, fmtInt, fmtMoney, inflApi, parseNum, type Candidate, type Candidates as Data, type Meta } from './api';
import NewCollabSheet from './NewCollabSheet';
import { InflFrame, RelationBadge, ScoreBar, TopicPills, useMeta } from './parts';

/** Kitaba gerekçeli aday sırası. Puan kuralla (ağırlıklar Yönetim ayarında); Zeki AI yalnız seçilenlere gerekçe cümlesi
 *  yazar. Liste tavansız; iletişim kurulmayacak ve bu kitabı almış kişiler ayrı listede nedeniyle durur. */
export default function Candidates() {
  const { kitap } = useParams();
  const meta = useMeta();
  return (
    <InflFrame
      title="Kitaba aday içerik üreticileri"
      lead="Bir kitap seçin; kayıtlı içerik üreticileri bu kitaba uygunluklarına göre sıralanır: konu uyumu, kitlenin yaşı, geçmiş sonuçlar, ilişki, son işbirliğinden bu yana geçen süre ve bütçe. Yeni hesap aranmaz, yalnız kayıtlı kişiler sıralanır."
    >
      {!kitap ? <BookSearch /> : meta.data ? <Ranking kitap={kitap} meta={meta.data} /> : null}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
    </InflFrame>
  );
}

function BookSearch() {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const res = useQuery({ queryKey: ['influencers', 'book-search', dq], queryFn: () => editorialSearchApi.search(dq, 'kitap'), enabled: ENGINE_ENABLED && dq.trim().length >= 2 });
  return (
    <Panel>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Kitap</span>
        <span className="relative flex items-center">
          <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
          <input className={`${field} pl-9`} value={q} placeholder="Kitap adı ya da ISBN" onChange={(e) => setQ(e.target.value)} />
        </span>
      </label>
      <div className="mt-2 flex flex-col gap-1">
        {res.isFetching && <span className="text-[12px] text-canvas-muted">Aranıyor…</span>}
        {res.error && <Note tone="err">{errText(res.error, 'Arama yapılamadı.')}</Note>}
        {(res.data?.books ?? []).map((b) => (
          <button key={b.id} type="button" onClick={() => nav(`/isbirlikleri/aday/${b.id}`)}
            className="min-h-11 rounded-xl bg-white/80 px-3 py-2 text-left text-[12.5px] hover:bg-slate-50">
            <span className="font-bold">{b.title}</span>{b.note && <span className="ml-1 text-canvas-muted">· {b.note}</span>}
          </button>
        ))}
        {res.data && res.data.books.length === 0 && <span className="text-[12px] text-canvas-muted">Kitap bulunamadı.</span>}
      </div>
    </Panel>
  );
}

function Ranking({ kitap, meta }: { kitap: string; meta: Meta }) {
  const [budget, setBudget] = useState('');
  const db = useDebounced(budget, 400);
  const b = db.trim() ? parseNum(db) : null;
  const q = useQuery({ queryKey: ['influencers', 'candidates', kitap, b], queryFn: () => inflApi.candidates(kitap, b), enabled: ENGINE_ENABLED });
  const [picked, setPicked] = useState<string[]>([]);
  const [why, setWhy] = useState<Record<string, { text: string; source: string }>>({});
  const [openFor, setOpenFor] = useState<Candidate | null>(null);
  const explain = useMutation({
    mutationFn: () => inflApi.explain(kitap, picked),
    onSuccess: (r) => setWhy((x) => ({ ...x, ...Object.fromEntries(r.items.map((i) => [i.personId, { text: i.text, source: i.source }])) })),
    onError: (e) => toast.error(errText(e, 'Gerekçe alınamadı.') ?? ''),
  });
  const d = q.data;
  return (
    <>
      <Link to="/isbirlikleri/aday" className="px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline">Başka kitap</Link>
      {q.isLoading && <Panel><div className="py-8 text-center text-[12px] text-canvas-muted">Sıralanıyor…</div></Panel>}
      {q.error && <Note tone="err">{errText(q.error, 'Aday listesi okunamadı.')}</Note>}
      {d && (
        <>
          <BookHead d={d} meta={meta} budget={budget} setBudget={setBudget} />
          <Panel>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="flex items-center gap-1 text-[13px] font-extrabold">{d.total} aday<SqlInfo k={d.kaynaklar} alan="items" label="Aday sırası ve puanlar" /></h2>
              {d.modelVar && meta.me.canEdit && (
                <button type="button" className={btnGhost} disabled={!picked.length || explain.isPending} onClick={() => explain.mutate()}>
                  {explain.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                  Seçilenlere Zeki AI gerekçesi ({picked.length})
                </button>
              )}
            </div>
            {d.items.length === 0 && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Kayıt defterinde aday yok. Önce içerik üreticisi ekleyin.</div>}
            <ol className="flex flex-col gap-2">
              {d.items.map((c, i) => (
                <li key={c.personId} className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 md:grid-cols-[28px_minmax(0,1fr)_minmax(0,1.3fr)_auto] md:items-start">
                  <label className="flex items-center gap-2 md:block">
                    <input type="checkbox" className="h-5 w-5" aria-label={`${c.name} seç`} checked={picked.includes(c.personId)}
                      onChange={(e) => setPicked((x) => (e.target.checked ? [...x, c.personId] : x.filter((y) => y !== c.personId)))} />
                    <span className="font-mono text-[11px] text-canvas-muted md:hidden">#{i + 1}</span>
                  </label>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Link to={`/isbirlikleri/kisi/${c.personId}`} className="break-words text-[13.5px] font-extrabold hover:underline">{c.name}</Link>
                      {c.minor && <Pill tone="warn">Reşit değil</Pill>}
                    </div>
                    <div className="mt-0.5 text-[12px] text-canvas-muted">{c.accounts.map((a) => `@${a.handle}`).join(' · ') || 'hesap yok'}{c.followers ? ` · ${fmtInt(c.followers)} takipçi` : ''}</div>
                    <div className="mt-1"><TopicPills keys={c.topics} meta={meta} /></div>
                    {meta.me.canSeeFee && (c.feeMin !== null || c.feeMax !== null) && <div className="mt-1 font-mono text-[11.5px]">{fmtMoney(c.feeMin)} – {fmtMoney(c.feeMax)}</div>}
                  </div>
                  <div className="min-w-0 text-[12px] leading-snug">
                    <div>{why[c.personId]?.text ?? c.reason}</div>
                    {why[c.personId] && <div className="mt-0.5 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{why[c.personId].source === 'zeki' ? 'Zeki AI' : 'Kural'}</div>}
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-canvas-muted">
                      {Object.entries(c.parts).map(([k, v]) => <span key={k}>{PART_LABEL[k] ?? k} <span className="font-mono">{Math.round(v * 100)}</span></span>)}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-end">
                    <ScoreBar value={c.score} />
                    <RelationBadge rel={c.relation} />
                    {meta.me.canEdit && <button type="button" className={btnPrimary} onClick={() => setOpenFor(c)}>İşbirliği aç</button>}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
          {d.excluded.length > 0 && (
            <Panel>
              <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">Sıraya girmeyenler ({d.excluded.length})<SqlInfo k={d.kaynaklar} alan="excluded" label="Sıraya girmeyenler" /></h2>
              <ul className="flex flex-col gap-1 text-[12.5px]">
                {d.excluded.map((e) => (
                  <li key={e.personId}><Link to={`/isbirlikleri/kisi/${e.personId}`} className="font-bold hover:underline">{e.name}</Link> <span className="text-canvas-muted">— {e.reason}</span></li>
                ))}
              </ul>
            </Panel>
          )}
          <NewCollabSheet open={!!openFor} meta={meta} onClose={() => setOpenFor(null)}
            person={openFor ? { id: openFor.personId, name: openFor.name } : null}
            book={d.book.kitapId ? { id: d.book.kitapId, title: d.book.ad ?? 'Kitap' } : null} />
        </>
      )}
    </>
  );
}

function BookHead({ d, meta, budget, setBudget }: { d: Data; meta: Meta; budget: string; setBudget: (v: string) => void }) {
  return (
    <Panel>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 break-words text-[16px] font-extrabold">{d.book.ad}<SqlInfo k={d.kaynaklar} alan="profile" label="Kitap kartı ve profili" /></h2>
          <div className="text-[12px] text-canvas-muted">{[d.book.yazar, d.book.turler, d.book.raf, d.book.hedefKitle].filter(Boolean).join(' · ')}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <TopicPills keys={d.profile.topics} meta={meta} />
            {d.profile.topicSource === 'zeki' && <Pill tone="violet">Zeki AI %{Math.round((d.profile.topicProbability ?? 0) * 100)}</Pill>}
            {d.profile.ageGroups.map((a) => <Pill key={a} tone="muted">{meta.yasGruplari[a] ?? a}</Pill>)}
          </div>
          {!d.profile.topics.length && <p className="mt-1 text-[11.5px] text-amber-700">Kitabın konusu CRM tür/raf/hedef kitle alanlarından çıkmadı; konu puanı herkese nötr verildi.</p>}
        </div>
        {meta.me.canSeeFee && (
          <label className="flex w-full flex-col gap-1 lg:w-56">
            <span className={labelCls}>Kişi başı bütçe (₺)</span>
            <input className={`${field} font-mono`} inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="Boş bırakırsanız bütçe sırayı etkilemez" />
          </label>
        )}
      </div>
      {d.collabs.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-2">
          <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Bu kitabın işbirlikleri</div>
          <div className="flex flex-wrap gap-1.5">
            {d.collabs.map((c) => (
              <Link key={c.id} to={`/isbirlikleri?is=${c.id}`} className="inline-flex items-center gap-1.5 rounded-xl bg-slate-50 px-2 py-1 text-[12px] hover:bg-slate-100">
                <Pill tone={STAGE_TONE[c.stage]}>{c.stageLabel}</Pill>{c.personName}<span className="text-canvas-muted">{fmtDay(c.duePublish)}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}
