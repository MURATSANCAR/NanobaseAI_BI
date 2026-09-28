import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Paperclip, Search, UserCheck } from 'lucide-react';
import { Loading, Note, btnGhost, errText, field } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { Kpi, KpiRow, useDebounced } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { CategoryPill, Empty, MailFrame, PriorityPill, StatusPill } from './parts';
import { VIEW_ORDER, crmBadges, fmtInt, fmtWhen, mailApi, remainingText, senderText, type Message, type Meta, type View } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** H4 Kurumsal e-posta — gelen kutusu. Sekme ve arama adres çubuğunda (?sekme=, ?q=, ?tur=). */
export default function MailboxHome() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['mailbox', 'meta'], queryFn: mailApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const ov = useQuery({ queryKey: ['mailbox', 'overview'], queryFn: mailApi.overview, enabled: ENGINE_ENABLED, refetchInterval: 120_000 });
  const m = meta.data;
  const visible = VIEW_ORDER.filter((v) => m?.me.seeAll || v === 'mine' || v === 'unit' || v === 'overdue' || v === 'archive');
  const view = (visible.find((v) => v === params.get('sekme')) ?? 'mine') as View;
  const [qInput, setQInput] = useState(params.get('q') ?? '');
  const q = useDebounced(qInput, 300);
  const category = params.get('tur') ?? '';
  const [page, setPage] = useState(0);

  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
    setPage(0);
  };

  const list = useQuery({
    queryKey: ['mailbox', 'messages', view, q, category, page],
    queryFn: () => mailApi.messages({ view, q, category, page }),
    enabled: ENGINE_ENABLED && !!m,
    placeholderData: keepPreviousData,
  });
  const counts = list.data?.counts ?? ov.data?.counts;
  const tabs = visible.map((v) => ({ key: v, label: m?.views[v] ?? v, badge: counts ? counts[v] || null : null }));
  const err = errText(meta.error, 'Ekran bilgisi okunamadı.') ?? errText(list.error, 'İletiler okunamadı.');
  const last = m?.lastRun;

  return (
    <MailFrame
      title="Kurumsal e-posta"
      lead="timas@ genel kutusuna gelen iletiler: Zeki AI türünü ve önceliğini önerir, sorumlu kişi yönlendirme tablosundan gelir, siz atarsınız. Yanıt kutudan gönderilir; portal yalnız okur, iletinin gövdesini saklamaz."
      connection={m?.connection}
      lastRun={last}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {last?.llmError && <Note tone="warn">Zeki AI son turda cevap vermedi; iletiler sonraki turda sınıflanacak.</Note>}

      <KpiRow>
        <Kpi info={<SqlInfo k={kaynakOf(ov.data)} alan="_hepsi" label="Bana atanan" />} label="Bana atanan" value={fmtInt(counts?.mine)} help="Açık ve yanıtlanmamış" active={view === 'mine'} onClick={() => set('sekme', null)} />
        <Kpi info={<SqlInfo k={kaynakOf(ov.data)} alan="_hepsi" label="Süresi aşan" />} label="Süresi aşan" value={fmtInt(counts?.overdue)} help="İlk yanıt süresi geçmiş (iş saatiyle)" active={view === 'overdue'} onClick={() => set('sekme', 'overdue')} />
        {m?.me.seeAll ? (
          <Kpi info={<SqlInfo k={kaynakOf(ov.data)} alan="_hepsi" label="Atanmamış" />} label="Atanmamış" value={fmtInt(counts?.unassigned)} help="Zeki AI'ın önerisi hazır" active={view === 'unassigned'} onClick={() => set('sekme', 'unassigned')} />
        ) : (
          <Kpi info={<SqlInfo k={kaynakOf(ov.data)} alan="_hepsi" label="Birimim" />} label="Birimim" value={fmtInt(counts?.unit)} help="Birimime atanan açık iletiler" active={view === 'unit'} onClick={() => set('sekme', 'unit')} />
        )}
        <Kpi
          info={<SqlInfo k={kaynakOf(ov.data)} alan="_hepsi" label="Bugün gelen" />}
          label="Bugün gelen"
          value={fmtInt(ov.data?.counts.today)}
          help={ov.data?.counts.pending ? `${fmtInt(ov.data.counts.pending)} ileti sınıflanmayı bekliyor` : 'Görebildiğiniz iletiler'}
        />
      </KpiRow>

      <Tabs tabs={tabs} value={view} onChange={(v) => set('sekme', v === 'mine' ? null : v)} />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">İletilerde ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input
            className={`${field} pl-9`}
            value={qInput}
            onChange={(e) => {
              setQInput(e.target.value);
              set('q', e.target.value || null);
            }}
            placeholder="Konu, gönderen ya da özette ara"
            type="search"
          />
        </label>
        <label className="sm:w-64">
          <span className="sr-only">Tür</span>
          <select className={field} value={category} onChange={(e) => set('tur', e.target.value || null)}>
            <option value="">Bütün türler</option>
            {(ov.data?.categories ?? []).map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {(meta.isLoading || list.isLoading) && <Loading />}
      {list.data && list.data.items.length === 0 && (
        <Empty title={q || category ? 'Aramaya uyan ileti yok' : 'Bu sekmede ileti yok'}>
          {m && !m.connection.connected ? 'Kutu bağlanınca iletiler burada görünür.' : view === 'mine' ? 'Size atanmış açık ileti yok.' : null}
        </Empty>
      )}
      {list.data && list.data.items.length > 0 && m && (
        <ul className="flex flex-col gap-2">
          {list.data.items.map((x) => (
            <Row key={x.id} m={x} meta={m} showAssign={view === 'unassigned' && m.me.canAssign} />
          ))}
        </ul>
      )}
      {list.data && list.data.total > list.data.pageSize && (
        <div className="flex items-center justify-between gap-2 text-[12px] font-semibold text-canvas-muted">
          <span className="tabular-nums">
            {fmtInt(page * list.data.pageSize + 1)}–{fmtInt(page * list.data.pageSize + list.data.items.length)} / {fmtInt(list.data.total)}
            <SqlInfo k={kaynakOf(list.data)} alan="_hepsi" label="İleti listesi: sayfa, ek ve SLA" className="ml-1" />
          </span>
          <div className="flex gap-1.5">
            <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Önceki
            </button>
            <button type="button" className={btnGhost} disabled={(page + 1) * list.data.pageSize >= list.data.total} onClick={() => setPage((p) => p + 1)}>
              Sonraki
            </button>
          </div>
        </div>
      )}
    </MailFrame>
  );
}

function Row({ m, meta, showAssign }: { m: Message; meta: Meta; showAssign: boolean }) {
  const qc = useQueryClient();
  const assign = useMutation({
    mutationFn: () => mailApi.assign(m.id, m.suggestedAssignee, m.suggestedUnit),
    onSuccess: () => {
      toast.success(`${m.suggestedAssignee} kişisine atandı.`);
      qc.invalidateQueries({ queryKey: ['mailbox'] });
    },
    onError: (e) => toast.error(errText(e, 'Atanamadı.') ?? ''),
  });
  const badges = useMemo(() => crmBadges(m.crm), [m.crm]);
  const rem = remainingText(m.remainingH);
  return (
    <li className="glass-panel rounded-2xl p-3 shadow-glass-float sm:p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
        <Link to={`/kurumsal-eposta/ileti/${m.id}`} className="min-w-0 flex-1 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-canvas-violet">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]">
            <span className="min-w-0 truncate font-extrabold">{senderText(m)}</span>
            {badges.map((b) => (
              <span key={b.key} className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10.5px] font-bold text-emerald-700">
                {b.text}
              </span>
            ))}
            <span className="ml-auto shrink-0 text-[11px] tabular-nums text-canvas-muted">{fmtWhen(m.receivedAt)}</span>
          </div>
          <div className="mt-1 flex min-w-0 items-center gap-1.5">
            {m.attachments.length > 0 && <Paperclip aria-label={`${m.attachments.length} ek`} className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />}
            <span className="min-w-0 truncate text-[13.5px] font-bold">{m.subject || '(konusuz)'}</span>
          </div>
          {m.summary && <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-snug text-canvas-muted">{m.summary}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <CategoryPill m={m} />
            {m.priority && m.priority !== 'normal' && <PriorityPill priority={m.priority} label={meta.priorities[m.priority]} />}
            <StatusPill status={m.status} label={m.statusLabel} />
            {rem && <span className={`text-[11px] font-bold tabular-nums ${m.overdue ? 'text-red-700' : 'text-canvas-muted'}`}>{rem}</span>}
            {m.assignee && <span className="text-[11px] font-semibold text-canvas-muted">· {m.assignee}</span>}
          </div>
        </Link>
        {showAssign && m.suggestedAssignee && (
          <button type="button" className={`${btnGhost} shrink-0`} disabled={assign.isPending} onClick={() => assign.mutate()}>
            <UserCheck aria-hidden className="h-4 w-4" />
            <span className="truncate">Öneriyi ata: {m.suggestedAssignee}</span>
          </button>
        )}
      </div>
    </li>
  );
}
