import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ShieldCheck } from 'lucide-react';
import { Note, btnGhost, btnPrimary, errText, field } from '../../admin/ui';
import { engApi, type Question } from './engApi';

/** M58 anket formu: telefon öncelikli, tek sütun, bir ekranda en çok dört soru, ilerleme çubuğu. Oturum aramaz; bağlantıdaki
 *  jeton ya da basılı kod yeter. Portal kabuğu ve menü yüklenmez (kod ile gelen bilgisayarsız çalışan da açabilsin).
 *  Rotalar: /ik/anket/:token (Anketlerim'den), /ik/anket/k ve /ik/anket/k/:kod (basılı kod). */

const PER_PAGE = 4;

export default function SurveyForm() {
  const { token = '', kod = '' } = useParams();
  const nav = useNavigate();
  const [typed, setTyped] = useState('');
  const key = token || kod;
  const form = useQuery({ queryKey: ['hr', 'survey-public', key], queryFn: () => engApi.publicForm(key), enabled: !!key, retry: false });
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [page, setPage] = useState(0);
  const send = useMutation({ mutationFn: () => engApi.submit(key, answers) });
  const pages = useMemo(() => {
    const qs = form.data?.questions ?? [];
    const out: Question[][] = [];
    for (let i = 0; i < qs.length; i += PER_PAGE) out.push(qs.slice(i, i + PER_PAGE));
    return out;
  }, [form.data]);
  const d = form.data;
  const done = send.isSuccess;
  const progress = done ? 100 : pages.length ? Math.round((page / pages.length) * 100) : 0;

  return (
    <div className="min-h-dvh bg-[#f4f2fb] font-canvas text-canvas-ink">
      <div className="mx-auto flex w-full max-w-xl flex-col gap-3 px-4 pb-10 pt-6">
        <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Timaş · Çalışan anketi</div>
        {!key && (
          <div className="flex flex-col gap-2 rounded-2xl bg-white p-4 shadow-sm">
            <h1 className="text-[20px] font-extrabold">Anket kodunuzu girin</h1>
            <p className="text-[13px] text-canvas-muted">İnsan Kaynakları'nın verdiği basılı kartta 10 karakterlik bir kod var. Kod kimseye bağlı değildir.</p>
            <input className={field} value={typed} onChange={(e) => setTyped(e.target.value.toUpperCase())} placeholder="ABCDE-FGHJK" autoCapitalize="characters" autoComplete="off" />
            <button type="button" className={btnPrimary} disabled={typed.replace(/[^A-Z0-9]/gi, '').length !== 10} onClick={() => nav(`/ik/anket/k/${encodeURIComponent(typed)}`)}>Ankete geç</button>
          </div>
        )}
        {form.error && <Note tone="err">{errText(form.error, 'Bağlantı ya da kod geçersiz.')}</Note>}
        {d && (
          <>
            <h1 className="text-[22px] font-extrabold leading-tight">{d.title}</h1>
            <div className="flex items-start gap-2 rounded-2xl bg-emerald-50 p-3 text-[12.5px] leading-snug text-emerald-900">
              <ShieldCheck aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{d.anonymity}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label="Anket ilerlemesi">
              <div className="h-full origin-left rounded-full bg-canvas-violet transition-transform duration-200 ease-out motion-reduce:transition-none" style={{ transform: `scaleX(${progress / 100})` }} />
            </div>
            {done ? (
              <div className="rounded-2xl bg-white p-5 text-center shadow-sm">
                <div className="text-[18px] font-extrabold">Teşekkürler</div>
                <p className="mt-1 text-[13px] text-canvas-muted">{send.data?.message}</p>
              </div>
            ) : d.alreadyResponded ? (
              <Note tone="info">Bu anket bu bağlantıyla cevaplandı. Teşekkürler.</Note>
            ) : !d.open ? (
              <Note tone="warn">Anket şu an cevaba açık değil.</Note>
            ) : (
              <>
                <ol className="flex flex-col gap-3" start={page * PER_PAGE + 1}>
                  {(pages[page] ?? []).map((q) => (
                    <li key={q.key} className="rounded-2xl bg-white p-4 shadow-sm">
                      <QuestionField q={q} value={answers[q.key]} onChange={(v) => setAnswers({ ...answers, [q.key]: v })} />
                    </li>
                  ))}
                </ol>
                {send.error && <Note tone="err">{errText(send.error, 'Gönderilemedi.')}</Note>}
                <div className="flex justify-between gap-2">
                  <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage(page - 1)}>Geri</button>
                  {page < pages.length - 1 ? (
                    <button type="button" className={btnPrimary} onClick={() => { setPage(page + 1); window.scrollTo({ top: 0 }); }}>Devam</button>
                  ) : (
                    <button type="button" className={btnPrimary} disabled={send.isPending || !Object.keys(answers).length} onClick={() => send.mutate()}>Gönder</button>
                  )}
                </div>
                <p className="text-center text-[11.5px] text-canvas-muted">Her soru isteğe bağlıdır. Kapanış: {new Date(d.closesAt).toLocaleDateString('tr-TR')}</p>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function QuestionField({ q, value, onChange }: { q: Question; value: unknown; onChange: (v: unknown) => void }) {
  const opts = q.type === 'enps' ? Array.from({ length: 11 }, (_, i) => i) : q.type === 'likert5' ? [1, 2, 3, 4, 5] : [];
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[14px] font-bold leading-snug">{q.text}</legend>
      {(q.type === 'enps' || q.type === 'likert5') && (
        <>
          <div role="radiogroup" aria-label={q.text} className={`grid gap-1.5 ${q.type === 'enps' ? 'grid-cols-6 sm:grid-cols-11' : 'grid-cols-5'}`}>
            {opts.map((v) => (
              <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(value === v ? undefined : v)}
                className={`h-11 rounded-xl font-mono text-[14px] font-bold transition-transform duration-150 ease-out active:scale-[0.95] ${value === v ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>
                {v}
              </button>
            ))}
          </div>
          <div className="flex justify-between text-[11px] text-canvas-muted">
            <span>{q.type === 'enps' ? 'Hiç önermem' : 'Kesinlikle katılmıyorum'}</span>
            <span>{q.type === 'enps' ? 'Kesinlikle öneririm' : 'Kesinlikle katılıyorum'}</span>
          </div>
        </>
      )}
      {q.type === 'secim' && (
        <div className="flex flex-col gap-1.5">
          {(q.options ?? []).map((o) => (
            <label key={o} className={`flex min-h-11 items-center gap-2 rounded-xl px-3 text-[13px] ${value === o ? 'bg-canvas-violet/10 font-bold' : 'bg-slate-50'}`}>
              <input type="radio" name={q.key} checked={value === o} onChange={() => onChange(o)} />{o}
            </label>
          ))}
        </div>
      )}
      {q.type === 'acik' && (
        <>
          <textarea className={`${field} min-h-[110px]`} value={(value as string) ?? ''} maxLength={3000} onChange={(e) => onChange(e.target.value)} />
          <span className="text-[11px] text-canvas-muted">Ad, telefon ve e-posta otomatik gizlenir; lütfen kendinizi ya da başkasını tanıtan ayrıntı yazmayın.</span>
        </>
      )}
    </fieldset>
  );
}
