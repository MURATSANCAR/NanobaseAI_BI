import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, X } from 'lucide-react';
import { ENGINE_ENABLED, contributorsApi, type Contributor, type PersonDetail } from '../engine';
import { contributorsListOptions, roleFacetsOptions } from './queries';
import { Loading, Note, Pill, btnGhost, errText, field, nf } from '../admin/ui';
import { dateTime, pct } from '../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel, useDebounced } from './kit';

/** Esere katkı verenler: yazarlar (M7), çevirmenler (M4), çizer ve serbest çalışanlar (M8). Hepsi CRM'deki
 *  eser katılım kayıtlarından, rol süzgeciyle okunur. Kapasite, puan, hız ve müsaitlik CRM'de tutulmadığı
 *  için gösterilmez. */

export type ContributorModule = {
  route: string;
  crumb: string;
  title: string;
  lead: string;
  /** Bu modülün kapsadığı CRM katılımcı tipleri. */
  roles: string[];
  people: string;
};

const statusTone = (s: string | null): 'ok' | 'warn' | 'err' | 'muted' => {
  const t = (s || '').toLocaleLowerCase('tr');
  if (t.includes('yenileme') || t.includes('bekleme')) return 'warn';
  if (t.startsWith('aktif') || t.includes('onaylı') || t.includes('çalışıyor')) return 'ok';
  if (t.includes('fesih') || t.includes('iptal') || t.includes('red')) return 'err';
  return 'muted';
};

function Block({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="flex items-baseline gap-2 text-[12px] font-extrabold">
        {title}
        <span className="font-mono font-semibold tabular-nums text-canvas-muted">{nf.format(count)}</span>
      </h3>
      {children}
    </section>
  );
}

function Detail({ p, onClose }: { p: PersonDetail; onClose: () => void }) {
  return (
    <div className="text-[12.5px]">
      <div className="flex items-start justify-between gap-2">
        <h2 className="min-w-0 break-words text-[17px] font-extrabold leading-tight tracking-tight">{p.name || 'Adı kayıtlı değil'}</h2>
        <button type="button" onClick={onClose} aria-label="Ayrıntıyı kapat" className={`${btnGhost} shrink-0 px-2.5`}>
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      {p.bio && <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-line leading-snug text-canvas-muted">{p.bio}</p>}

      <Block title="Eserler" count={p.works.length}>
        {p.truncated && <p className="mt-1 text-[11px] text-canvas-muted">Liste sunucunun satır sınırında kesildi.</p>}
        <ul className="mt-1.5 max-h-72 space-y-1 overflow-y-auto pr-1">
          {p.works.map((w, i) => (
            <li key={`${w.bookId}-${w.role}-${i}`} className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 break-words">{w.title || 'Kitap bağlanmamış'}</span>
              <span className="shrink-0 text-[11px] text-canvas-muted">{w.role}</span>
            </li>
          ))}
        </ul>
      </Block>

      {p.contracts.length > 0 && (
        <Block title="Sözleşmeler" count={p.contracts.length}>
          <ul className="mt-1.5 max-h-60 space-y-1.5 overflow-y-auto pr-1">
            {p.contracts.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="font-mono text-[11.5px] tabular-nums">{c.no || '—'}</span>
                {c.status && <Pill tone={statusTone(c.status)}>{c.status}</Pill>}
                <span className="font-mono text-[11px] tabular-nums text-canvas-muted">
                  {dateTime(c.start)} – {dateTime(c.end)}
                </span>
                {c.royalty != null && <span className="text-[11px] text-canvas-muted">telif {pct(c.royalty, 0)}</span>}
              </li>
            ))}
          </ul>
        </Block>
      )}

      {p.projects.length > 0 && (
        <Block title="Projeler" count={p.projects.length}>
          <ul className="mt-1.5 max-h-60 space-y-1.5 overflow-y-auto pr-1">
            {p.projects.map((j) => (
              <li key={j.id}>
                <div className="break-words font-semibold">{j.name || 'Adsız proje'}</div>
                <div className="text-[11px] text-canvas-muted">{[j.status, j.text, j.editor && `Editör: ${j.editor}`].filter(Boolean).join(' · ')}</div>
              </li>
            ))}
          </ul>
        </Block>
      )}
    </div>
  );
}

function Row({ c, active, onOpen }: { c: Contributor; active: boolean; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-pressed={active}
        className={`flex w-full items-center justify-between gap-3 rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-colors duration-150 ${
          active ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
        }`}
      >
        <span className="min-w-0">
          <span className="block break-words font-extrabold leading-snug">{c.name || 'Adı kayıtlı değil'}</span>
          <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">
            {c.roles.map((r) => `${r.role} ${nf.format(r.works)}`).join(' · ')}
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="block font-mono text-[15px] font-bold tabular-nums leading-none">{nf.format(c.works)}</span>
          <span className="mt-1 block text-[11px] text-canvas-muted">{c.recentWorks ? `son 12 ayda ${nf.format(c.recentWorks)}` : dateTime(c.last)}</span>
        </span>
      </button>
    </li>
  );
}

export default function ContributorsScreen({ module: m }: { module: ContributorModule }) {
  const [text, setText] = useState('');
  const [role, setRole] = useState('');
  const [order, setOrder] = useState('son');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const q = useDebounced(text.trim(), 350);
  const roles = useMemo(() => (role ? [role] : m.roles), [role, m.roles]);

  useEffect(() => setPage(0), [q, role, order]);

  const facets = useQuery({ ...roleFacetsOptions(), enabled: ENGINE_ENABLED && m.roles.length > 1 });
  const list = useQuery(contributorsListOptions(roles, q, order, page));
  const person = useQuery({ queryKey: ['editorial', 'person', open], queryFn: () => contributorsApi.person(open as string), enabled: ENGINE_ENABLED && !!open });

  const data = list.data;
  const items = data?.items ?? [];
  const roleOptions = (facets.data?.items ?? []).filter((f) => m.roles.includes(f.role));
  const err = errText(list.error || person.error, 'Kayıtlar okunamadı.');

  return (
    <ModuleFrame route={m.route} crumb={m.crumb} title={m.title} lead={m.lead} source={data ? `${nf.format(data.total)} ${m.people}` : 'CRM eser katılımları'}>
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {data && (
        <KpiRow>
          <Kpi label={m.people} value={nf.format(data.total)} help={q || role ? 'Süzgece uyan kişi' : 'Eser katılım kaydı olan kişi'} />
          <Kpi label="Son 12 ayda çalışan" value={nf.format(data.activePeople)} help="Bu dönemde yeni eser kaydı olan" />
          <Kpi label="Kişi başına eser" value={data.total ? nf.format(Math.round((data.contributions / data.total) * 10) / 10) : '—'} help={`${nf.format(data.contributions)} eser katkısı`} />
          <Kpi label="Kapsanan rol" value={nf.format(roles.length)} help={roles.join(', ')} />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:items-start lg:gap-4">
        <Panel>
          <div className={`grid gap-2 sm:grid-cols-2 ${m.roles.length > 1 ? 'lg:grid-cols-[minmax(0,1fr)_190px_170px]' : 'lg:grid-cols-[minmax(0,1fr)_170px]'}`}>
            <label className="relative block">
              <span className="sr-only">Kişi ara</span>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad soyad" className={`${field} pl-9`} />
            </label>
            {m.roles.length > 1 && (
              <select aria-label="Rol" value={role} onChange={(e) => setRole(e.target.value)} className={field}>
                <option value="">Tüm roller</option>
                {roleOptions.map((f) => (
                  <option key={f.role} value={f.role}>
                    {f.role} ({nf.format(f.people)})
                  </option>
                ))}
              </select>
            )}
            <select aria-label="Sıralama" value={order} onChange={(e) => setOrder(e.target.value)} className={field}>
              <option value="son">Son çalışan</option>
              <option value="eser">En çok eser</option>
              <option value="ad">Ada göre</option>
            </select>
          </div>
          <Pager page={page} pageSize={data?.pageSize ?? 50} total={data?.total ?? 0} shown={items.length} loading={list.isLoading} fetching={list.isFetching} db={data?.db} onPage={setPage} />
          {!list.isLoading && !items.length && !err && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan kişi yok.</p>}
          <ul className="mt-3 grid gap-2 xl:grid-cols-2">
            {items.map((c) => (
              <Row key={c.id} c={c} active={open === c.id} onOpen={() => setOpen(c.id)} />
            ))}
          </ul>
        </Panel>

        {/* Telefonda ayrıntı listenin üstüne gelir; masaüstünde sağda durur. */}
        {open && (
          <div className="order-first lg:sticky lg:top-0 lg:order-none">
            <Panel>{person.data && person.data.id === open ? <Detail p={person.data} onClose={() => setOpen(null)} /> : <Loading />}</Panel>
          </div>
        )}
      </div>
    </ModuleFrame>
  );
}
