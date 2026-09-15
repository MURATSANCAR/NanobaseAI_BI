import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pause, Play, Search, Trash2 } from 'lucide-react';
import { adminApi, alertsApi, type AlertRule } from '../engine';
import { Loading, Note, Pill, Section, TableWrap, errText, field, fmtDate, nf, td, th } from './ui';

const norm = (s: string) => s.toLocaleLowerCase('tr');

function useFilter<T>(items: T[], text: (x: T) => string) {
  const [q, setQ] = useState('');
  const filtered = useMemo(() => {
    const n = norm(q.trim());
    return n ? items.filter((x) => norm(text(x)).includes(n)) : items;
  }, [items, q, text]);
  const box = (
    <div className="relative w-full sm:w-72">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-canvas-muted" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ara…" className={`${field} pl-8`} />
    </div>
  );
  return { filtered, box };
}

function IconBtn({ title, onClick, disabled, danger, children }: { title: string; onClick: () => void; disabled?: boolean; danger?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
      className={[
        'inline-flex h-11 min-w-11 items-center justify-center gap-1 rounded-lg px-2 text-[11.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.95] disabled:opacity-40 sm:h-8 sm:min-w-8',
        danger ? 'bg-red-600 text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200',
      ].join(' ')}
    >
      {children}
    </button>
  );
}

/** İki adımlı silme: ilk dokunuş sorar, ikinci siler. */
function DeleteBtn({ onDelete, pending }: { onDelete: () => void; pending: boolean }) {
  const [ask, setAsk] = useState(false);
  return ask ? (
    <span className="inline-flex gap-1">
      <IconBtn title="Evet, sil" danger onClick={onDelete} disabled={pending}>
        Sil
      </IconBtn>
      <IconBtn title="Vazgeç" onClick={() => setAsk(false)}>
        Vazgeç
      </IconBtn>
    </span>
  ) : (
    <IconBtn title="Sil" onClick={() => setAsk(true)}>
      <Trash2 className="h-3.5 w-3.5" />
    </IconBtn>
  );
}

const LAST_REPORT: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' }> = {
  sent: { label: 'Gönderildi', tone: 'ok' },
  no_smtp: { label: 'E-posta ayarı yok', tone: 'warn' },
  no_recipient: { label: 'Alıcı yok', tone: 'muted' },
  failed: { label: 'Hata', tone: 'err' },
};

export function ReportsAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'reports'], queryFn: adminApi.reports, retry: false });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['admin'] });
    void qc.invalidateQueries({ queryKey: ['planli-raporlar'] });
  };
  const status = useMutation({ mutationFn: ({ id, s }: { id: string; s: 'active' | 'paused' }) => adminApi.updateReport(id, { status: s }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: string) => adminApi.deleteReport(id), onSuccess: refresh });
  const items = q.data?.items ?? [];
  const { filtered, box } = useFilter(items, (r) => `${r.title} ${r.owner} ${r.question} ${r.recipients.join(' ')}`);
  const err = errText(status.error, 'Değiştirilemedi.') ?? errText(del.error, 'Silinemedi.');

  return (
    <Section title="Planlı raporlar" help="Herkesin planladığı raporlar. Sahibinin ekranında da aynı anda değişir." action={box}>
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Raporlar okunamadı.')}</Note>
      ) : !filtered.length ? (
        <Note tone="info">{items.length ? 'Aramaya uyan rapor yok.' : 'Henüz planlı rapor yok.'}</Note>
      ) : (
        <TableWrap>
          <thead className="bg-slate-50/80">
            <tr>
              <th className={th}>Rapor</th>
              <th className={th}>Sahibi</th>
              <th className={th}>Plan</th>
              <th className={th}>Alıcılar</th>
              <th className={th}>Son çalışma</th>
              <th className={`${th} text-right`}>İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((r) => (
              <tr key={r.id}>
                <td className={td}>
                  <div className="font-semibold">{r.title}</div>
                  <div className="line-clamp-1 text-[11px] text-canvas-muted">{r.question}</div>
                </td>
                <td className={`${td} font-semibold`}>{r.owner}</td>
                <td className={td}>
                  <div className="whitespace-nowrap">{r.when}</div>
                  <div className="text-[11px] text-canvas-muted">
                    {r.status === 'active' ? `sıradaki ${fmtDate(r.nextRunAt)}` : r.status === 'paused' ? 'duraklatıldı' : 'bitti'}
                  </div>
                </td>
                <td className={`${td} text-[11.5px]`}>{r.recipients.length ? r.recipients.join(', ') : '—'}</td>
                <td className={td}>
                  <div className="tabular-nums">{fmtDate(r.lastRunAt)}</div>
                  {r.lastStatus && (
                    <Pill tone={LAST_REPORT[r.lastStatus].tone}>
                      {LAST_REPORT[r.lastStatus].label}
                      {r.lastRows != null && r.lastStatus !== 'failed' ? ` · ${nf.format(r.lastRows)} satır` : ''}
                    </Pill>
                  )}
                </td>
                <td className={`${td} text-right`}>
                  <span className="inline-flex gap-1">
                    {r.status !== 'done' && (
                      <IconBtn
                        title={r.status === 'active' ? 'Duraklat' : 'Sürdür'}
                        disabled={status.isPending}
                        onClick={() => status.mutate({ id: r.id, s: r.status === 'active' ? 'paused' : 'active' })}
                      >
                        {r.status === 'active' ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                      </IconBtn>
                    )}
                    <DeleteBtn onDelete={() => del.mutate(r.id)} pending={del.isPending} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Section>
  );
}

const COND: Record<AlertRule['condition'], string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' };
const STATE: Record<AlertRule['state'], { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' }> = {
  ok: { label: 'Normal', tone: 'ok' },
  triggered: { label: 'Tetiklendi', tone: 'warn' },
  error: { label: 'Hata', tone: 'err' },
  unknown: { label: 'Ölçülmedi', tone: 'muted' },
};

export function AlertsAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'alerts'], queryFn: adminApi.alerts, retry: false });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['admin'] });
  const status = useMutation({ mutationFn: ({ id, s }: { id: string; s: 'active' | 'paused' }) => alertsApi.update(id, { status: s }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: string) => alertsApi.remove(id), onSuccess: refresh });
  const items = q.data?.items ?? [];
  const { filtered, box } = useFilter(items, (r) => `${r.title} ${r.created_by ?? ''} ${r.question} ${r.recipients.join(' ')}`);
  const err = errText(status.error, 'Değiştirilemedi.') ?? errText(del.error, 'Silinemedi.');

  return (
    <Section title="Uyarılar" help="Eşik kuralları. Kontrol 15 dakikada bir sunucuda yapılır." action={box}>
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Uyarılar okunamadı.')}</Note>
      ) : !filtered.length ? (
        <Note tone="info">{items.length ? 'Aramaya uyan uyarı yok.' : 'Henüz uyarı kuralı yok.'}</Note>
      ) : (
        <TableWrap>
          <thead className="bg-slate-50/80">
            <tr>
              <th className={th}>Kural</th>
              <th className={th}>Oluşturan</th>
              <th className={th}>Koşul</th>
              <th className={th}>Son değer</th>
              <th className={th}>Durum</th>
              <th className={`${th} text-right`}>İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((r) => (
              <tr key={r.id}>
                <td className={td}>
                  <div className="font-semibold">{r.title}</div>
                  <div className="line-clamp-1 text-[11px] text-canvas-muted">{r.question}</div>
                </td>
                <td className={`${td} font-semibold`}>{r.created_by || '—'}</td>
                <td className={`${td} whitespace-nowrap font-mono tabular-nums`}>
                  {COND[r.condition]} {nf.format(r.threshold)}
                </td>
                <td className={td}>
                  <div className="font-mono tabular-nums">{r.last_value != null ? nf.format(r.last_value) : '—'}</div>
                  <div className="text-[11px] text-canvas-muted">{fmtDate(r.last_checked_at)}</div>
                </td>
                <td className={td}>
                  <span className="flex flex-wrap gap-1">
                    <Pill tone={STATE[r.state].tone}>{STATE[r.state].label}</Pill>
                    {r.status === 'paused' && <Pill tone="muted">Duraklatıldı</Pill>}
                  </span>
                </td>
                <td className={`${td} text-right`}>
                  <span className="inline-flex gap-1">
                    <IconBtn
                      title={r.status === 'active' ? 'Duraklat' : 'Sürdür'}
                      disabled={status.isPending}
                      onClick={() => status.mutate({ id: r.id, s: r.status === 'active' ? 'paused' : 'active' })}
                    >
                      {r.status === 'active' ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    </IconBtn>
                    <DeleteBtn onDelete={() => del.mutate(r.id)} pending={del.isPending} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Section>
  );
}

const CHART: Record<string, string> = {
  column: 'Sütun', bar: 'Çubuk', line: 'Çizgi', area: 'Alan', pie: 'Pasta', donut: 'Halka',
  scatter: 'Dağılım', treemap: 'Ağaç harita', kpi: 'Gösterge', table: 'Tablo',
};
const REFRESH: Record<string, string> = { manual: 'Elle', hourly: 'Saatte bir', daily: 'Her gün' };

export function CardsAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['admin', 'cards'], queryFn: adminApi.cards, retry: false });
  const del = useMutation({ mutationFn: (id: string) => adminApi.deleteCard(id), onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin'] }) });
  const items = q.data?.items ?? [];
  const { filtered, box } = useFilter(items, (c) => `${c.title} ${c.owner} ${c.question}`);

  return (
    <Section title="Pano kartları" help="Kişilerin panolarındaki kartlar. Silinen kart sahibinin panosundan da kalkar." action={box}>
      {del.error && <Note tone="err">{errText(del.error, 'Silinemedi.')}</Note>}
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <Note tone="err">{errText(q.error, 'Kartlar okunamadı.')}</Note>
      ) : !filtered.length ? (
        <Note tone="info">{items.length ? 'Aramaya uyan kart yok.' : 'Henüz pano kartı yok.'}</Note>
      ) : (
        <TableWrap>
          <thead className="bg-slate-50/80">
            <tr>
              <th className={th}>Kart</th>
              <th className={th}>Sahibi</th>
              <th className={th}>Grafik</th>
              <th className={th}>Tazeleme</th>
              <th className={th}>Son sonuç</th>
              <th className={`${th} text-right`}>İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((c) => (
              <tr key={c.id}>
                <td className={td}>
                  <div className="font-semibold">{c.title}</div>
                  <div className="line-clamp-1 text-[11px] text-canvas-muted">{c.question || '—'}</div>
                </td>
                <td className={`${td} font-semibold`}>{c.owner}</td>
                <td className={td}>{CHART[c.chart] ?? c.chart}</td>
                <td className={`${td} whitespace-nowrap`}>
                  {REFRESH[c.refresh] ?? c.refresh}
                  {c.refresh === 'daily' && c.refreshAt ? ` ${c.refreshAt}` : ''}
                </td>
                <td className={td}>
                  <div className="tabular-nums">{fmtDate(c.resultAt)}</div>
                  {c.lastError && <Pill tone="err">Hata</Pill>}
                </td>
                <td className={`${td} text-right`}>
                  <DeleteBtn onDelete={() => del.mutate(c.id)} pending={del.isPending} />
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Section>
  );
}
