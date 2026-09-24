import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { ENGINE_ENABLED, type IntakeAgendaItem } from '../../engine';
import { intakeAgendaOptions, intakeBoardOptions, intakeMeetingsOptions } from '../queries';
import { Loading, Note, Pill, btnGhost, errText, field, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from '../kit';
import { waitingText } from './parts';

/** Yayın kurulu: bir toplantının gündemi ve kararları. Toplantı, CRM'de aynı güne yazılmış kurul kayıtlarıdır;
 *  ileri tarihli kayıt tutulmadığı için gelecek toplantı gösterilmez. */

const tone = (code: number | null) => (code === 1 ? 'ok' : code === 100000000 ? 'err' : code === 100000002 ? 'warn' : 'muted');
const longDate = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' });
const dayLabel = (d: string) => longDate.format(new Date(`${d}T12:00:00`));

function AgendaRow({ it, no, open, onToggle, opinionsVisible }: { it: IntakeAgendaItem; no: number; open: boolean; onToggle: () => void; opinionsVisible: boolean }) {
  const extra = [it.printRun && `Baskı ${it.printRun}`, it.price && `Fiyat ${it.price}`, it.royalty && `Telif %${it.royalty}`, it.advance && `Avans ${it.advance}`, it.publishOn && `Yayın ${dateTime(it.publishOn)}`].filter(Boolean);
  return (
    <li className="border-t border-slate-100 first:border-t-0">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-start gap-3 py-3 text-left">
        <span className="w-6 shrink-0 pt-0.5 font-mono text-[12px] tabular-nums text-canvas-muted">{String(no).padStart(2, '0')}</span>
        <span className="min-w-0 flex-1">
          <span className="block break-words text-[13.5px] font-extrabold leading-snug">{it.project || 'Projeye bağlanmamış kayıt'}</span>
          <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">
            {[it.author && `Yazar: ${it.author}`, it.editor ? `Editör: ${it.editor}` : 'Editör yok'].filter(Boolean).join(' · ')}
          </span>
          <span className="mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
            <Pill tone={it.report ? 'muted' : 'warn'}>Editör raporu: {it.report ? 'var' : 'CRM\'de yok'}</Pill>
            {opinionsVisible && it.opinionCount != null && <Pill tone="muted">{nf.format(it.opinionCount)} görüş</Pill>}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          <Pill tone={tone(it.decisionCode)}>{it.decision || 'Karar girilmedi'}</Pill>
          <ChevronDown aria-hidden className={`h-4 w-4 text-canvas-muted transition-transform duration-200 ease-out ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {open && (
        <div className="mb-3 ml-9 space-y-2 rounded-2xl bg-slate-50 p-3 text-[12.5px]">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kurul karar notu</div>
            <p className="mt-0.5 whitespace-pre-line leading-snug">{it.note || 'Not girilmemiş.'}</p>
          </div>
          {extra.length > 0 && <p className="text-[11.5px] text-canvas-muted">{extra.join(' · ')}</p>}
          {opinionsVisible && (it.opinions?.length ?? 0) > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Üye görüşleri</div>
              <ul className="mt-1 space-y-1.5">
                {it.opinions!.map((o, i) => (
                  <li key={i} className="rounded-xl bg-white px-3 py-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <b className="font-extrabold">{o.by || 'Adı yok'}</b>
                      <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{dateTime(o.on)}</span>
                    </div>
                    {o.verdict && <div className="font-semibold">{o.verdict}</div>}
                    {o.text && <p className="whitespace-pre-line leading-snug text-canvas-muted">{o.text}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {it.projectId && (
            <Link to={`/yazar-giris/${it.projectId}`} className="inline-flex text-[12px] font-bold text-canvas-violet hover:underline">
              Proje sayfasına git →
            </Link>
          )}
        </div>
      )}
    </li>
  );
}

export default function MeetingScreen() {
  const meetings = useQuery(intakeMeetingsOptions());
  const list = meetings.data?.items ?? [];
  const [day, setDay] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    if (!day && list[0]) setDay(list[0].date);
  }, [day, list]);
  const agenda = useQuery(intakeAgendaOptions(day));
  const board = useQuery(intakeBoardOptions());
  const at = list.findIndex((m) => m.date === day);
  const m = at >= 0 ? list[at] : null;
  const items = agenda.data?.items ?? [];
  const preparing = (board.data?.items ?? []).filter((c) => c.phase === 2);
  const err = errText(meetings.error || agenda.error, 'Kurul kayıtları okunamadı.');

  return (
    <ModuleFrame
      route="/yayin-kurulu"
      crumb="Yayın kurulu"
      title={m ? `Yayın kurulu · ${dayLabel(m.date)}` : 'Yayın kurulu'}
      lead={m ? `Gündemde ${nf.format(m.total)} proje · ${nf.format(m.total - m.pending)} karar verildi · ${nf.format(m.pending)} bekliyor` : 'Kurul toplantıları ve kararları, CRM kurul kayıtlarından.'}
      source="Kaynak: CRM kurul kayıtları"
      aside={
        list.length > 0 ? (
          <div className="flex items-center gap-1.5">
            <button type="button" className={`${btnGhost} px-2.5`} aria-label="Önceki toplantı" disabled={at < 0 || at >= list.length - 1} onClick={() => { setDay(list[at + 1].date); setOpen(null); }}>
              <ChevronLeft aria-hidden className="h-4 w-4" />
            </button>
            <select aria-label="Toplantı" value={day} onChange={(e) => { setDay(e.target.value); setOpen(null); }} className={field}>
              {list.map((x) => (
                <option key={x.date} value={x.date}>
                  {dayLabel(x.date)} · {nf.format(x.total)} proje
                </option>
              ))}
            </select>
            <button type="button" className={`${btnGhost} px-2.5`} aria-label="Sonraki toplantı" disabled={at <= 0} onClick={() => { setDay(list[at - 1].date); setOpen(null); }}>
              <ChevronRight aria-hidden className="h-4 w-4" />
            </button>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {m && (
        <KpiRow>
          <Kpi label="Kabul" value={nf.format(m.accepted)} help="Onaylanan proje" />
          <Kpi label="Red" value={nf.format(m.rejected)} help="Uygun bulunmayan" />
          <Kpi label="Yeniden değerlendirme" value={nf.format(m.revisit)} help="Geliştirilip tekrar gelecek" />
          <Kpi label="Karar bekliyor" value={nf.format(m.pending)} help="Bekleme ya da karar girilmemiş" />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:items-start lg:gap-4">
        <Panel>
          <h2 className="text-[15px] font-extrabold">Gündem</h2>
          {(meetings.isLoading || agenda.isLoading) && <Loading />}
          {!agenda.isLoading && day && items.length === 0 && !err && <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu toplantıya kayıtlı proje yok.</p>}
          <ol className={`mt-1 ${agenda.isFetching && !agenda.isLoading ? 'opacity-60' : ''}`}>
            {items.map((it, i) => (
              <AgendaRow
                key={it.id ?? i}
                it={it}
                no={i + 1}
                open={open === it.id}
                onToggle={() => setOpen((v) => (v === it.id ? null : it.id))}
                opinionsVisible={!!agenda.data?.opinionsVisible}
              />
            ))}
          </ol>
          {agenda.data && !agenda.data.opinionsVisible && items.length > 0 && (
            <p className="mt-2 text-[11px] text-canvas-muted">Üyelerin adlı görüşlerini yöneticiler görür.</p>
          )}
        </Panel>

        <Panel>
          <h2 className="text-[15px] font-extrabold">Kurula hazırlanan projeler</h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">Kurul evresindeki, kararı henüz verilmemiş projeler.</p>
          {board.data?.loading && <p className="mt-3 text-[12px] text-canvas-muted">CRM okunuyor…</p>}
          {board.data && !board.data.loading && preparing.length === 0 && <p className="mt-3 text-[12.5px] text-canvas-muted">Şu an kurula hazırlanan proje yok.</p>}
          <ul className="mt-2">
            {preparing.map((c) => (
              <li key={c.id} className="border-t border-slate-100 py-2.5 first:border-t-0">
                <Link to={`/yazar-giris/${c.id}`} className="block hover:underline">
                  <span className="block break-words text-[13px] font-extrabold leading-snug">{c.name || 'Adsız proje'}</span>
                </Link>
                <span className="block text-[11.5px] text-canvas-muted">{c.author || 'Yazar girilmemiş'}</span>
                <span className={`mt-1 inline-block text-[11.5px] font-semibold ${c.late ? 'text-red-700' : 'text-canvas-ink'}`}>
                  {c.line}
                  {c.waitingDays != null && <span className="font-mono font-normal text-canvas-muted"> · {waitingText(c)}</span>}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </ModuleFrame>
  );
}
