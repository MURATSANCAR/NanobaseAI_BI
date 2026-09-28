import { useEffect, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronRight, Search, UserPlus } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi, type AuthorCardSummary } from '../../engine';
import { Note, Pill, btnGhost, errText, field, nf } from '../../admin/ui';
import { crmLabel } from '../../format';
import { useCan } from '../../useAdmin';
import { Pager, Panel, useDebounced } from '../kit';
import { HeatPill, fmtDay, invalidateAuthors, useAuthorsMeta } from './shared';
import SqlInfo from '../../components/SqlInfo';
import type { PanelTarget } from './CardPanel';

/** Potansiyel yazar havuzu: portalda açılan aday kartları aşama aşama, altında CRM'de bir projenin olası yazarı
 *  olup henüz yazar rolüyle eseri olmayan kişiler («Havuza al» ile kart açılır). */

function CardRow({ c, onOpen }: { c: AuthorCardSummary; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-start justify-between gap-3 rounded-2xl border border-slate-100 bg-white/85 px-3 py-2.5 text-left text-[12.5px] transition-colors duration-150 hover:bg-white"
      >
        <span className="min-w-0">
          <span className="block break-words font-extrabold leading-snug">{c.name}</span>
          <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">
            {[c.genre, c.sourceLabel, c.ownerDisplay || c.owner].filter(Boolean).join(' · ') || 'Ayrıntı girilmedi'}
          </span>
          <span className="mt-1 flex flex-wrap gap-1">
            {c.heat.next && <Pill tone="violet">Randevu {fmtDay(c.heat.next)}</Pill>}
            {c.openSteps > 0 && <Pill tone="warn">{c.openSteps} açık adım</Pill>}
            {c.tags.slice(0, 3).map((t) => (
              <Pill key={t} tone="muted">
                {t}
              </Pill>
            ))}
          </span>
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <HeatPill heat={c.heat} compact />
          <span className="text-[11px] text-canvas-muted">{c.meetings ? `${c.meetings} görüşme` : 'görüşme yok'}</span>
        </span>
      </button>
    </li>
  );
}

function CrmCandidates({ onOpen }: { onOpen: (t: PanelTarget) => void }) {
  const qc = useQueryClient();
  const meta = useAuthorsMeta();
  const canWrite = useCan('yazar-iliski.yaz');
  const [text, setText] = useState('');
  const [closed, setClosed] = useState(false);
  const [page, setPage] = useState(0);
  const q = useDebounced(text.trim(), 350);
  useEffect(() => setPage(0), [q, closed]);
  const list = useQuery({
    queryKey: ['authors', 'pool-crm', q, closed, page],
    queryFn: () => authorsApi.poolCrm({ q, page, closed }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const take = useMutation({
    mutationFn: (p: { id: string; name: string }) => authorsApi.crmCard(p.id, p.name, 'aday'),
    onSuccess: async (c) => {
      await invalidateAuthors(qc);
      toast.success('Havuza alındı', { description: c.name });
      onOpen({ cardId: c.id });
    },
    onError: (e) => toast.error('Havuza alınamadı', { description: e instanceof Error ? e.message : undefined }),
  });
  const data = list.data;
  const err = errText(list.error, "CRM'deki olası yazarlar okunamadı.");
  return (
    <Panel>
      <h2 className="flex items-center gap-1.5 text-[15px] font-extrabold tracking-tight">
        CRM'de olası yazar
        {data && <SqlInfo k={data.kaynaklar} alan="items[]" label="CRM'de olası yazar: proje sayısı ve toplam" />}
      </h2>
      <p className="mt-0.5 text-[12px] leading-snug text-canvas-muted">
        {fmtDay(data?.since ?? meta.data?.poolSince)} sonrası açılan projelerde «olası yazar» olarak girilmiş, henüz yazar rolüyle eser kaydı olmayan kişiler. Başlangıç tarihi Yönetim → Ayarlar'dan
        değişir.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
        <label className="relative block">
          <span className="sr-only">Olası yazar ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad soyad" className={`${field} pl-9`} />
        </label>
        <label className="flex min-h-11 items-center gap-2 text-[12px] font-semibold">
          <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} className="h-4 w-4 accent-[#6D4AFF]" />
          Reddedilen ve iptal projeler de
        </label>
      </div>
      {err && (
        <div className="mt-3">
          <Note tone="err">{err}</Note>
        </div>
      )}
      <Pager page={page} pageSize={data?.pageSize ?? 50} total={data?.total ?? 0} shown={data?.items.length ?? 0} loading={list.isLoading} fetching={list.isFetching} db={data?.db} onPage={setPage} />
      {data && !data.items.length && !list.isLoading && <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan olası yazar yok.</p>}
      <ul className="mt-3 grid gap-2 xl:grid-cols-2">
        {(data?.items ?? []).map((p) => (
          <li key={p.crmContactId} className="flex items-start justify-between gap-3 rounded-2xl border border-slate-100 bg-white/85 px-3 py-2.5 text-[12.5px]">
            <span className="min-w-0">
              <span className="block break-words font-extrabold leading-snug">{p.name || 'Adı kayıtlı değil'}</span>
              {p.latest && (
                <span className="mt-0.5 block break-words text-[11px] leading-snug text-canvas-muted">
                  {crmLabel(p.latest.name) || 'Adsız proje'}
                  {p.latest.status ? ` · ${crmLabel(p.latest.status)}` : ''}
                  {p.latest.editor ? ` · Editör: ${p.latest.editor}` : ''}
                </span>
              )}
              <span className="mt-0.5 block text-[11px] text-canvas-muted">
                {nf.format(p.projects)} proje · son {fmtDay(p.last)}
              </span>
            </span>
            {p.cardId ? (
              <button type="button" className={`${btnGhost} shrink-0 !min-h-9 !py-1`} onClick={() => onOpen({ cardId: p.cardId })}>
                Kartı aç
                <ChevronRight aria-hidden className="h-3.5 w-3.5" />
              </button>
            ) : canWrite ? (
              <button
                type="button"
                className={`${btnGhost} shrink-0 !min-h-9 !py-1`}
                disabled={take.isPending}
                onClick={() => take.mutate({ id: p.crmContactId, name: p.name || '' })}
              >
                <UserPlus aria-hidden className="h-3.5 w-3.5" />
                Havuza al
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function PoolTab({ onOpen }: { onOpen: (t: PanelTarget) => void }) {
  const meta = useAuthorsMeta();
  const [stage, setStage] = useState('');
  const [text, setText] = useState('');
  const [mine, setMine] = useState(false);
  const [archived, setArchived] = useState(false);
  const q = useDebounced(text.trim(), 300);
  const cards = useQuery({
    queryKey: ['authors', 'cards', stage, q, mine, archived],
    queryFn: () => authorsApi.cards({ stage, q, scope: mine ? 'benim' : '', archived }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const stages = (meta.data?.stages ?? []).filter((s) => (meta.data?.poolStages ?? []).includes(s.key));
  const items = cards.data?.items ?? [];
  const err = errText(cards.error, 'Aday kartları okunamadı.');
  const groups = stage ? [{ key: stage, label: stages.find((s) => s.key === stage)?.label ?? stage }] : stages;

  return (
    <div className="grid gap-3 lg:gap-4">
      <Panel>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Aşama süzgeci">
          <button
            type="button"
            aria-pressed={!stage}
            onClick={() => setStage('')}
            className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${!stage ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}
          >
            Tümü
          </button>
          {stages.map((s) => (
            <button
              key={s.key}
              type="button"
              aria-pressed={stage === s.key}
              onClick={() => setStage(s.key)}
              className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${stage === s.key ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}
            >
              {s.label} <span className="font-mono tabular-nums opacity-80">{nf.format(cards.data?.stages[s.key] ?? 0)}</span>
            </button>
          ))}
          {cards.data && (
            <span className="inline-flex items-center">
              <SqlInfo k={cards.data.kaynaklar} alan="stages" label="Aşama başına aday kartı" />
            </span>
          )}
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
          <label className="relative block">
            <span className="sr-only">Aday ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad soyad" className={`${field} pl-9`} />
          </label>
          <label className="flex min-h-11 items-center gap-2 text-[12px] font-semibold">
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} className="h-4 w-4 accent-[#6D4AFF]" />
            Yalnız benim
          </label>
          <label className="flex min-h-11 items-center gap-2 text-[12px] font-semibold">
            <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} className="h-4 w-4 accent-[#6D4AFF]" />
            Arşiv
          </label>
        </div>
        {err && (
          <div className="mt-3">
            <Note tone="err">{err}</Note>
          </div>
        )}
        {cards.data && !items.length && (
          <p className="py-8 text-center text-[12.5px] text-canvas-muted">
            {q || stage || mine || archived ? 'Bu süzgece uyan aday kartı yok.' : 'Havuzda henüz aday yok. «Yeni yazar kartı» ya da aşağıdaki CRM listesinden «Havuza al» ile ekleyin.'}
          </p>
        )}
        <div className="mt-3 space-y-4">
          {groups.map((g) => {
            const list = items.filter((c) => c.stage === g.key);
            if (!list.length) return null;
            return (
              <section key={g.key}>
                <h3 className="flex items-center gap-2 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">
                  {g.label}
                  <span className="font-mono tabular-nums">{list.length}</span>
                  <SqlInfo k={cards.data?.kaynaklar} alan="items[]" label={`${g.label}: görüşme, açık adım, ısı`} />
                </h3>
                <ul className="mt-1.5 grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                  {list.map((c) => (
                    <CardRow key={c.id} c={c} onOpen={() => onOpen({ cardId: c.id })} />
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      </Panel>
      <CrmCandidates onOpen={onOpen} />
    </div>
  );
}
