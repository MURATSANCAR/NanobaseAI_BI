import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED, type ContractFacet, type EditorLoad } from '../engine';
import { editorsOverviewOptions, projectsListOptions } from './queries';
import { Note, Pill, errText, field, nf } from '../admin/ui';
import { dateTime } from '../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel, useDebounced } from './kit';

/** M2 Editör Atama. CRM proje kartındaki "Editörü" alanından editör başına proje dağılımı ve proje listesi.
 *  Atama önerisi, redaksiyon takvimi ve iş yükü yüzdesi CRM'de tutulmadığı için burada yok. */

const TONES = ['bg-canvas-violet', 'bg-canvas-coral', 'bg-canvas-mint', 'bg-canvas-amber', 'bg-sky-400', 'bg-slate-400', 'bg-rose-300', 'bg-teal-300'];

function Bar({ parts, order, max }: { parts: ContractFacet[]; order: number[]; max: number }) {
  const total = parts.reduce((a, b) => a + b.count, 0);
  return (
    <div className="flex h-2 overflow-hidden rounded-full bg-slate-100" style={{ width: `${Math.max(4, (total / max) * 100)}%` }}>
      {order.map((code, i) => {
        const part = parts.find((p) => p.code === code);
        return part ? <div key={code} className={TONES[i % TONES.length]} style={{ width: `${(part.count / total) * 100}%` }} title={`${part.label}: ${nf.format(part.count)}`} /> : null;
      })}
    </div>
  );
}

function EditorRow({ e, order, max, active, onOpen }: { e: EditorLoad; order: number[]; max: number; active: boolean; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-pressed={active}
        className={`w-full rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-colors duration-150 ${active ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'}`}
      >
        <span className="flex items-baseline justify-between gap-2">
          <span className="min-w-0 break-words font-extrabold">
            {e.name || 'Adı kayıtlı değil'}
            {e.disabled && <span className="ml-1.5 text-[11px] font-semibold text-canvas-muted">CRM hesabı kapalı</span>}
          </span>
          <span className="shrink-0 font-mono text-[15px] font-bold tabular-nums">{nf.format(e.total)}</span>
        </span>
        <span className="mt-1.5 block">
          <Bar parts={e.byStatus} order={order} max={max} />
        </span>
        <span className="mt-1 block text-[11px] text-canvas-muted">Son değişiklik {dateTime(e.last)}</span>
      </button>
    </li>
  );
}

export default function EditorsScreen() {
  const [editor, setEditor] = useState('');
  const [status, setStatus] = useState('');
  const [text, setText] = useState('');
  const [page, setPage] = useState(0);
  const q = useDebounced(text.trim(), 350);

  const overview = useQuery(editorsOverviewOptions());
  const o = overview.data;
  useEffect(() => setPage(0), [q, editor, status]);

  const list = useQuery(projectsListOptions(q, editor, status, o?.sinceYear, page));

  const editors = o?.items ?? [];
  const order = (o?.statuses ?? []).map((s) => s.code);
  const max = editors[0]?.total ?? 1;
  const assigned = editors.reduce((a, b) => a + b.total, 0);
  const unassigned = (o?.unassigned ?? []).reduce((a, b) => a + b.count, 0);
  const data = list.data;
  const items = data?.items ?? [];
  const current = editors.find((e) => e.id === editor);
  const err = errText(overview.error || list.error, 'Editör kayıtları okunamadı.');

  return (
    <ModuleFrame
      route="/editor-atama"
      code="M2"
      crumb="Editör Atama"
      title="Editörler ve projeleri"
      lead="CRM proje kartındaki “Editörü” alanından editör başına proje dağılımı. Atama önerisi, redaksiyon takvimi ve iş yükü yüzdesi CRM'de tutulmadığı için burada yok."
      source={o ? `${o.sinceYear} ve sonrası projeler` : 'CRM projeleri'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {o && (
        <KpiRow>
          <Kpi label="Editör" value={nf.format(editors.length)} help={`${o.sinceYear} ve sonrası projesi olan`} />
          <Kpi label="Editörlü proje" value={nf.format(assigned)} help="“Editörü” alanı dolu" />
          <Kpi label="Editörsüz proje" value={nf.format(unassigned)} help="“Editörü” alanı boş" />
          <Kpi label="Editör başına" value={editors.length ? nf.format(Math.round(assigned / editors.length)) : '—'} help="Ortalama proje" />
        </KpiRow>
      )}

      {o && (
        <Panel>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px]">
            {o.statuses.map((s, i) => (
              <li key={s.code} className="flex items-center gap-1.5">
                <span aria-hidden className={`h-2 w-2 rounded-full ${TONES[i % TONES.length]}`} />
                <span>{s.label}</span>
                <span className="font-mono font-bold tabular-nums">{nf.format(s.count)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:items-start lg:gap-4">
        <Panel>
          <h2 className="px-1 text-[13px] font-extrabold">Editörler</h2>
          <ul className="mt-2 space-y-1.5">
            {editors.map((e) => (
              <EditorRow key={e.id} e={e} order={order} max={max} active={editor === e.id} onOpen={() => setEditor(editor === e.id ? '' : e.id)} />
            ))}
          </ul>
        </Panel>

        <Panel>
          <h2 className="px-1 text-[13px] font-extrabold">{current ? `${current.name} · projeleri` : 'Tüm projeler'}</h2>
          <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_260px]">
            <label className="relative block">
              <span className="sr-only">Projelerde ara</span>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Proje ya da yazar" className={`${field} pl-9`} />
            </label>
            <select aria-label="Proje durumu" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
              <option value="">Tüm durumlar</option>
              {(current?.byStatus ?? o?.statuses ?? []).map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label} ({nf.format(s.count)})
                </option>
              ))}
            </select>
          </div>
          <Pager page={page} pageSize={data?.pageSize ?? 50} total={data?.total ?? 0} shown={items.length} loading={list.isLoading || overview.isLoading} fetching={list.isFetching} db={data?.db} onPage={setPage} />
          {!list.isLoading && !overview.isLoading && !items.length && !err && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan proje yok.</p>}
          <ul className="mt-3 space-y-2">
            {items.map((j) => (
              <li key={j.id} className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px]">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="break-words font-extrabold leading-snug">{j.name || 'Adsız proje'}</div>
                    <div className="mt-0.5 text-[11.5px] text-canvas-muted">{j.author ? `Yazar: ${j.author}` : 'Yazar girilmemiş'}</div>
                  </div>
                  {j.status && <Pill tone="muted">{j.status}</Pill>}
                </div>
                <div className="mt-1.5 text-[11px] leading-snug text-canvas-muted">
                  {[
                    j.editor ? `Editör: ${j.editor}` : 'Editör atanmamış',
                    j.projectEditor && `Proje editörü: ${j.projectEditor}`,
                    j.text && `Metin: ${j.text}`,
                    j.stage,
                    j.textDue && `Metin teslim ${dateTime(j.textDue)}`,
                    `Son değişiklik ${dateTime(j.modifiedOn)}`,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </ModuleFrame>
  );
}
