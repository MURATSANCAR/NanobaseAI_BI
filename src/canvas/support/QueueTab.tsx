import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, ExternalLink, Loader2, Sparkles, X } from 'lucide-react';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { ENGINE_ENABLED } from '../engine';
import { ContextView } from './CustomerContext';
import { Block, Empty, SlaPill, SourceLine } from './parts';
import { fmtDay, fmtPct, supportApi, type Meta, type QueueItem } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Açık talepler SLA'ya göre sıralı (aşılan → yaklaşan → süre içinde → SLA'sız). Talebe dokununca yanında Zeki AI önerisi,
 *  cevap taslağı ve müşteri bağlamı açılır. Talep masada cevaplanır; burada yalnız okunur ve taslak hazırlanır. */
export default function QueueTab({ meta }: { meta: Meta }) {
  const [scope, setScope] = useState<'mine' | 'all'>('mine');
  const [open, setOpen] = useState<QueueItem | null>(null);
  const q = useQuery({ queryKey: ['support', 'queue', scope], queryFn: () => supportApi.queue(scope), enabled: ENGINE_ENABLED, refetchInterval: 120_000 });
  const labels = Object.fromEntries(meta.classes.map((c) => [c.klass, c.label]));
  const items = q.data?.items ?? [];

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <Block
        info={<SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label="Açık talepler" />}
        title="Açık talepler"
        help={scope === 'mine' ? 'Size atananlar ve henüz kimseye atanmamışlar.' : 'Bütün temsilcilerin açık talepleri.'}
        action={
          meta.me.canAll ? (
            <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Kapsam">
              {(['mine', 'all'] as const).map((s) => (
                <button key={s} type="button" role="tab" aria-selected={scope === s} onClick={() => setScope(s)}
                  className={`min-h-9 rounded-lg px-2.5 text-[12px] font-extrabold ${scope === s ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>
                  {s === 'mine' ? 'Benim' : 'Hepsi'}
                </button>
              ))}
            </div>
          ) : undefined
        }
      >
        {q.isLoading && <Loading />}
        {q.error && <Note tone="err">{errText(q.error, 'Kuyruk okunamadı.')}</Note>}
        {q.data && !q.data.configured && <Note tone="warn">Destek masası bağlantısı ayarlanmamış (Yönetim → Ayarlar → Müşteri hizmetleri).</Note>}
        {q.data?.configured && scope === 'mine' && q.data.agentMapped === false && (
          <Note tone="info">Masadaki kullanıcınız portal hesabınızla eşlenemedi; e-posta adresinin «@» öncesiyle eşleştirildi.</Note>
        )}
        {q.data?.configured && items.length === 0 && <Empty title="Açık talep yok">Kuyruk boş.</Empty>}
        <ul className="flex flex-col gap-1.5">
          {items.map((t) => (
            <li key={t.ref}>
              <button
                type="button"
                onClick={() => setOpen(t)}
                aria-pressed={open?.ref === t.ref}
                className={`w-full rounded-xl border px-3 py-2 text-left transition-transform duration-150 ease-out active:scale-[0.99] ${open?.ref === t.ref ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-100 bg-white/80'}`}
              >
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[11px] text-canvas-muted">{t.ref}</span>
                  <SlaPill state={t.sla} />
                  {t.urgency === 'yüksek' && <Pill tone="err">Acil</Pill>}
                  {t.klass ? <Pill tone="violet">{labels[t.klass] ?? t.klass}</Pill> : t.klassGuess ? <Pill tone="muted">{labels[t.klassGuess] ?? t.klassGuess}?</Pill> : null}
                  {t.hasDraft && <Pill tone="ok">Taslak hazır</Pill>}
                </span>
                <span className="mt-0.5 block truncate text-[13px] font-bold">{t.subject ?? '(konu yok)'}</span>
                <span className="block text-[11.5px] text-canvas-muted">
                  {fmtDay(t.opened)} · {t.status ?? '—'}
                  {t.due ? ` · süre ${new Date(t.due).toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ''}
                  {t.assigned.length ? ` · ${t.assigned.map((a) => a.split('@')[0]).join(', ')}` : ' · atanmamış'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Block>
      {open ? <TicketPanel key={open.ref} item={open} meta={meta} onClose={() => setOpen(null)} /> : (
        <div className="hidden xl:block">
          <Empty title="Bir talep seçin">Zeki AI önerisi, cevap taslağı ve müşterinin siparişi burada açılır.</Empty>
        </div>
      )}
    </div>
  );
}

function TicketPanel({ item, meta, onClose }: { item: QueueItem; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const ins = useQuery({ queryKey: ['support', 'insight', item.ref], queryFn: () => supportApi.insight(item.ref), enabled: ENGINE_ENABLED });
  const [account, setAccount] = useState<string | undefined>(undefined);
  const ctx = useQuery({
    queryKey: ['support', 'context', { ticket: item.ref, account }],
    queryFn: () => supportApi.context({ ticket: item.ref, account }),
    enabled: ENGINE_ENABLED && meta.me.canContext,
    staleTime: 60_000,
  });
  const i = ins.data?.insight ?? null;
  const [text, setText] = useState('');
  useEffect(() => setText(i?.draft ?? ''), [i?.draft]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['support', 'insight', item.ref] });
    qc.invalidateQueries({ queryKey: ['support', 'queue'] });
  };
  const classify = useMutation({ mutationFn: () => supportApi.classify(item.ref), onSuccess: refresh, onError: (e) => toast.error(errText(e, 'Sınıflanamadı.') ?? '') });
  const setClass = useMutation({
    mutationFn: (k: string) => supportApi.setClass(item.ref, k),
    onSuccess: () => {
      refresh();
      toast.success('Konu düzeltildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const draft = useMutation({
    mutationFn: () => supportApi.draft(item.ref),
    onSuccess: (d) => {
      setText(d.draft);
      refresh();
      d.warnings.forEach((w) => toast.warning(w));
      if (d.dropped) toast.message(`${d.dropped} cümle, olgusu olmayan rakam ya da bilgi içerdiği için taslaktan çıkarıldı.`);
    },
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? ''),
  });
  const outcome = useMutation({
    mutationFn: (sent: boolean) => supportApi.outcome(item.ref, sent, sent ? text : undefined),
    onSuccess: (_d, sent) => {
      refresh();
      toast.success(sent ? 'Kaydedildi: taslak gönderildi.' : 'Kaydedildi: taslak kullanılmadı.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Taslak panoya kopyalandı; masada cevaba yapıştırın.');
    } catch {
      toast.error('Kopyalanamadı; metni seçip kopyalayın.');
    }
  };
  const labels = Object.fromEntries(meta.classes.map((c) => [c.klass, c.label]));

  return (
    <div className="flex flex-col gap-3">
      <Block
        title={item.subject ?? item.ref}
        help={<span className="font-mono">{item.ref}</span>}
        action={
          <div className="flex gap-1.5">
            {item.url && (
              <a href={item.url} target="_blank" rel="noreferrer" className={btnGhost}>
                Masada aç <ExternalLink aria-hidden className="h-4 w-4" />
              </a>
            )}
            <button type="button" className={btnGhost} onClick={onClose} aria-label="Kapat">
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
        }
      >
        {ins.isLoading && <Loading />}
        {!ins.isLoading && !i?.klass && !i?.klassGuess && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12.5px] text-canvas-muted">Zeki AI bu talebi henüz sınıflamadı (5 dakikada bir sırayla sınıflar).</span>
            {meta.me.canSuggest && (
              <button type="button" className={btnGhost} disabled={classify.isPending} onClick={() => classify.mutate()}>
                {classify.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                Şimdi sınıfla
              </button>
            )}
          </div>
        )}
        {i && (i.klass || i.klassGuess) && (
          <div className="flex flex-col gap-2 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-bold">Konu:</span>
              {i.klass ? <Pill tone="violet">{labels[i.klass] ?? i.klass}</Pill> : <Pill tone="muted">Sınıflanamadı · en olası {labels[i.klassGuess ?? ''] ?? '—'}</Pill>}
              {i.klassP !== null && i.klassBy === 'zeki' && <span className="text-canvas-muted">olasılık {fmtPct(i.klassP)}</span>}
              {i.klassBy && i.klassBy !== 'zeki' && <span className="text-canvas-muted">{i.klassBy} düzeltti</span>}
              {i.urgency && (
                <>
                  <span className="ml-2 font-bold">Aciliyet:</span>
                  <Pill tone={i.urgency === 'yüksek' ? 'err' : i.urgency === 'düşük' ? 'muted' : 'warn'}>{i.urgency}</Pill>
                </>
              )}
            </div>
            {meta.me.canSuggest && (
              <label className="flex flex-wrap items-center gap-2">
                <span className="text-canvas-muted">Konu yanlışsa:</span>
                <select className={`${field} w-auto`} value={i.klass ?? ''} disabled={setClass.isPending} onChange={(e) => e.target.value && setClass.mutate(e.target.value)}>
                  <option value="">Seçin…</option>
                  {meta.classes.filter((c) => c.active).map((c) => (
                    <option key={c.klass} value={c.klass}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {i.faq && i.faq.matches.length > 0 && (
              <div>
                <span className="font-bold">Benzer SSS:</span>
                <ul className="mt-1 flex flex-col gap-1">
                  {i.faq.matches.map((m) => (
                    <li key={`${m.source}-${m.id}`} className="rounded-lg bg-slate-50 px-2 py-1">
                      <span className="font-semibold">{m.url ? <a href={m.url} target="_blank" rel="noreferrer" className="text-canvas-violet">{m.title}</a> : m.title}</span>
                      <span className="block text-[11.5px] text-canvas-muted">{m.excerpt}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Block>

      {meta.me.canSuggest && (
        <Block title="Cevap taslağı" help="Zeki AI yazar; sipariş no, tarih ve kargo bilgisi CRM/Logo'dan gelir, model rakam uydurmaz. Taslak hiçbir yere gönderilmez.">
          <div className="flex flex-col gap-2">
            <label className="sr-only" htmlFor={`draft-${item.ref}`}>
              Taslak
            </label>
            <textarea id={`draft-${item.ref}`} className={`${field} min-h-[180px] font-normal leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="Taslak henüz yok." />
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnPrimary} disabled={draft.isPending} onClick={() => draft.mutate()}>
                {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                {i?.draft ? 'Yeniden yaz' : 'Taslak yaz'}
              </button>
              <button type="button" className={btnGhost} disabled={!text.trim()} onClick={copy}>
                <Copy aria-hidden className="h-4 w-4" />
                Kopyala
              </button>
              {i?.draft && (
                <>
                  <button type="button" className={btnGhost} disabled={outcome.isPending} onClick={() => outcome.mutate(true)}>
                    Masadan gönderdim
                  </button>
                  <button type="button" className={btnGhost} disabled={outcome.isPending} onClick={() => outcome.mutate(false)}>
                    Kullanmadım
                  </button>
                </>
              )}
            </div>
            <SourceLine>
              «Masadan gönderdim» yalnız taslağın ne kadar değiştiğini ölçer (Zeki AI karnesi); gönderdiğiniz metin saklanmaz.
              {i?.finalSent !== null && i?.finalSent !== undefined && ` Son kayıt: ${i.finalSent ? `gönderildi, değişiklik ${fmtPct(i.editRatio)}` : 'kullanılmadı'}.`}
            </SourceLine>
          </div>
        </Block>
      )}

      {meta.me.canContext ? (
        <Block info={<SqlInfo k={kaynakOf(ctx.data)} alan="_hepsi" label="Müşteri bağlamı" />} title="Müşteri bağlamı" help="Talebi gönderen adresle CRM ve Logo'dan.">
          {ctx.isLoading && <Loading />}
          {ctx.error && <Note tone="err">{errText(ctx.error, 'Bağlam okunamadı.')}</Note>}
          {ctx.data && <ContextView data={ctx.data} onPick={setAccount} />}
        </Block>
      ) : (
        <Note tone="info">Müşteri bağlamı (sipariş, kargo, fatura) için «Müşteri bağlamı ve bayi görünümü» yetkisi gerekir.</Note>
      )}
    </div>
  );
}
