import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { BookOpenCheck, Check, RotateCcw, Save } from 'lucide-react';
import { studioApi } from '../../../engine';
import { Note, errText } from '../../../admin/ui';
import { Img, ago, press } from '../shared';
import { marketingApi, type MarketingView } from './api';
import { Approval, Generate, Section, field, ghostBtn, gradientBtn, label } from './parts';

const words = (t: string) => t.split(/\s+/).filter(Boolean).length;

function FillBar({ fill, fits }: { fill?: number; fits?: boolean }) {
  if (fill == null) return null;
  const pct = Math.round(fill * 100);
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200/80" aria-hidden>
        <div className={`h-full rounded-full ${fits ? 'bg-emerald-500' : 'bg-rose-500'}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className={`shrink-0 font-bold ${fits ? 'text-emerald-700' : 'text-rose-700'}`}>
        {fits ? `alanın %${pct}'i` : `alanı aşıyor (%${pct})`}
      </span>
    </div>
  );
}

export default function BackCoverTab({ jobId, v, refresh }: { jobId: string; v: MarketingView; refresh: () => void }) {
  const bc = v.back_cover;
  const server = bc.draft?.text ?? '';
  const [text, setText] = useState(server);
  useEffect(() => setText(server), [server]);
  const dirty = text.trim() !== server.trim();
  const approvedNow = !!bc.approved && bc.approved.text.trim() === text.trim();
  const appliedNow = !!bc.applied && !!bc.approved && bc.applied.text === bc.approved.text;

  const gen = useMutation({ mutationFn: () => marketingApi.generate(jobId, 'back-cover'), onSettled: refresh });
  const save = useMutation({ mutationFn: () => marketingApi.saveBack(jobId, text), onSuccess: refresh });
  const approve = useMutation({ mutationFn: () => marketingApi.approveBack(jobId, text), onSuccess: refresh });
  const apply = useMutation({ mutationFn: () => marketingApi.applyBack(jobId), onSuccess: refresh });
  const revert = useMutation({ mutationFn: () => marketingApi.revertBack(jobId), onSuccess: refresh });
  const err = errText(gen.error || save.error || approve.error || apply.error || revert.error, '');
  const busy = save.isPending || approve.isPending || apply.isPending || revert.isPending;

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
      <div className="flex min-w-0 flex-col gap-4">
        <Generate task={v.tasks['back-cover']} has={bc.options.length > 0} onRun={() => gen.mutate()} pending={gen.isPending} what="Arka kapak yazısı" />
        {bc.area && (
          <p className="text-[12px] text-canvas-muted">
            Arka kapak yazı alanı {bc.area.width_mm} × {bc.area.height_mm} mm
            {bc.capacity ? ` · yaklaşık ${bc.capacity.words} kelime sığar` : ''}. Seçenekler bu alana göre ölçüldü.
          </p>
        )}
        {err && <Note tone="err">{err}</Note>}

        {bc.options.length > 0 && (
          <Section title="Seçenekler">
            <ul className="grid min-w-0 gap-2 md:grid-cols-3">
              {bc.options.map((o) => (
                <li key={o.id} className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] font-extrabold text-canvas-violet">{o.angle || o.id}</span>
                    <span className="shrink-0 font-mono text-[11px] text-canvas-muted">{o.words} kelime</span>
                  </div>
                  <FillBar fill={o.fill} fits={o.fits} />
                  <p className="line-clamp-6 whitespace-pre-line break-words text-[12.5px] leading-snug">{o.text}</p>
                  <button type="button" className={`${ghostBtn} mt-auto`} onClick={() => setText(o.text)}>Bunu düzenle</button>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {(bc.draft || bc.options.length > 0) && (
          <Section title="Arka kapak yazısı" aside={<Approval approved={approvedNow ? bc.approved : null} />}>
            <label className="flex flex-col gap-1">
              <span className={label}>Metin · paragrafları boş satırla ayırın</span>
              <textarea className={field} rows={9} value={text} onChange={(e) => setText(e.target.value)} maxLength={20000} />
            </label>
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-canvas-muted">
              <span>{words(text)} kelime{bc.capacity ? ` / ~${bc.capacity.words}` : ''}</span>
              {!dirty && bc.draft?.fill != null ? <div className="w-full sm:w-64"><FillBar fill={bc.draft.fill} fits={bc.draft.fits} /></div>
                : dirty ? <span>Kaydedince alana göre ölçülür</span> : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={ghostBtn} disabled={!dirty || busy || !text.trim()} onClick={() => save.mutate()}>
                <Save className="h-4 w-4" aria-hidden />Taslağı kaydet
              </button>
              <button type="button" disabled={busy || !text.trim() || approvedNow} onClick={() => approve.mutate()}
                className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border-2 border-emerald-500 bg-white px-4 text-[13px] font-bold text-emerald-700 disabled:opacity-50 ${press}`}>
                <Check className="h-4 w-4" aria-hidden />{approvedNow ? 'Onaylandı' : 'Onayla'}
              </button>
              <button type="button" className={gradientBtn} disabled={!approvedNow || busy || appliedNow} onClick={() => apply.mutate()}
                title={approvedNow ? 'Kapak açılımı bu yazıyla yeniden dizilir' : 'Kapağa yalnız onaylı yazı uygulanır'}>
                <BookOpenCheck className="h-4 w-4" aria-hidden />{apply.isPending ? 'Kapak diziliyor…' : appliedNow ? 'Kapakta' : 'Kapağa uygula'}
              </button>
              {bc.applied && (
                <button type="button" className={ghostBtn} disabled={busy} onClick={() => revert.mutate()}>
                  <RotateCcw className="h-4 w-4" aria-hidden />Kayıtlı tanıtım metnine dön
                </button>
              )}
            </div>
            {bc.approved && !bc.approved.fits && approvedNow && (
              <Note tone="warn">Onaylı yazı arka kapak alanını aşıyor; kapağa uygulanırsa barkod ya da yaş rozetiyle çakışabilir. Kısaltmanız önerilir.</Note>
            )}
          </Section>
        )}
        {bc.crm && (
          <details className="rounded-2xl border border-slate-200 bg-white/60 p-3 text-[12.5px]">
            <summary className="cursor-pointer font-bold">Kayıtlı tanıtım metni (yayınevi kaydı)</summary>
            <p className="mt-2 whitespace-pre-line break-words text-canvas-muted">{bc.crm}</p>
          </details>
        )}
      </div>

      <Section title="Kapak açılımı">
        <Img src={studioApi.coverUrl(jobId, 1000, String(bc.applied?.at ?? 'crm'))} alt="Kapak açılımı: arka kapak solda"
          fallback="Kapak henüz dizilmedi" className="w-full rounded-xl border border-slate-200 bg-white" />
        <p className="text-[11.5px] text-canvas-muted">
          {bc.applied ? `Arka kapakta pazarlama yazısı · ${bc.applied.by}, ${ago(bc.applied.at)}` : 'Arka kapakta yayınevinin kayıtlı tanıtım metni.'}
        </p>
      </Section>
    </div>
  );
}
