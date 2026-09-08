import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, MessagesSquare, ScrollText, Sigma, Table2, X } from 'lucide-react';
import clsx from 'clsx';
import { reviewConcept, reviewQueue, type ReviewItem } from '../lib/engine';

/** Onay kuyruğu — sistemin öğrendiği, ama henüz kimsenin doğrulamadığı iş terimleri.
 *
 *  Sistem bir soruyu "bilmiyorum" diye geri çevirdiğinde çoğu zaman sebep tabloyu bulamaması değil,
 *  sorudaki kelimenin sözlükte olmamasıdır. Kelimeleri veriden ve çalışmış sorgulardan çıkarabiliyor;
 *  çıkaramadığı tek şey, o kelimenin bu şirkette gerçekten ne demek olduğu. Bu ekran onun için:
 *  her satırda terim, işaret ettiği yer ve arkasındaki kanıt var — evet ya da hayır bir tık.
 *
 *  Onay kalıcıdır. Kararı insan kanıtı olarak yazıyoruz, gece koşusu aynı puanı yeniden hesaplayıp
 *  terimi kuyruğa geri atamıyor; yoksa harcanan dakika her gece boşa giderdi. */

const TYPE: Record<string, { label: string; icon: typeof Table2 }> = {
  METRIC: { label: 'ölçü', icon: Sigma },
  COLUMN: { label: 'kolon', icon: Table2 },
  DIMENSION_VALUE: { label: 'değer', icon: ScrollText },
  ENTITY: { label: 'tablo', icon: Table2 },
};

/** Kanıtın kaynağı — bir terimin arkasında ne durduğunu tek kelimeyle söyler. */
const SOURCE: Record<string, string> = {
  EXECUTION: 'çalışmış sorgu',
  VALIDATED_SQL: 'doğrulanmış sorgu',
  HUMAN_ANNOTATION: 'insan notu',
  ALIAS_BINDING: 'sorguda takma ad',
  EXPLICIT_BINDING: 'sorguda açık eşleme',
  PROFILE: 'veri ölçümü',
  DOC: 'kaynak açıklaması',
  LLM_CANDIDATE: 'model önerisi',
};

export function TermReview() {
  const [source, setSource] = useState<'used' | 'all'>('used');
  const q = useQuery({ queryKey: ['review', source], queryFn: () => reviewQueue(source, 150), staleTime: 60_000 });
  const d = q.data;

  return (
    <div className="space-y-4">
      <header className="card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-semibold">Onay Bekleyen Terimler</h2>
            <p className="mt-1 max-w-2xl text-[12px] text-ink-muted">
              Sistem bu kelimeleri verinizden ve çalışmış sorgulardan çıkardı, ama hangisinin gerçekten
              işinizde kullandığınız anlama geldiğini bilemez. Onayladığınız her terim, o kelimeyi
              içeren soruların cevaplanmasını sağlar.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1 rounded-xl border border-line bg-white p-1">
            <Tab active={source === 'used'} onClick={() => setSource('used')} label="kullanımdan gelenler" n={d?.used} />
            <Tab active={source === 'all'} onClick={() => setSource('all')} label="tümü" n={d?.total} />
          </div>
        </div>
      </header>

      {q.isLoading && <div className="card p-6 text-sm text-ink-muted">Kuyruk okunuyor…</div>}
      {q.isError && <div className="card p-6 text-sm text-brand-accent">Kuyruk okunamadı. Motor kapalı olabilir.</div>}
      {d && d.items.length === 0 && (
        <div className="card p-6 text-sm text-ink-muted">Onay bekleyen terim yok — kuyruk boş.</div>
      )}

      <div className="space-y-2">
        {d?.items.map((it) => <Row key={it.id} it={it} source={source} />)}
      </div>
      {d && d.items.length < d.waiting && (
        <div className="text-center text-[11px] text-ink-faint">{d.waiting - d.items.length} terim daha var.</div>
      )}
    </div>
  );
}

function Tab({ active, onClick, label, n }: { active: boolean; onClick: () => void; label: string; n?: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx('rounded-lg px-2.5 py-1 text-[11px] font-medium transition',
        active ? 'bg-brand text-white' : 'text-ink-muted hover:bg-brand-soft hover:text-brand-deep')}
    >
      {label}{n != null ? ` · ${n}` : ''}
    </button>
  );
}

function Row({ it, source }: { it: ReviewItem; source: string }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [done, setDone] = useState<'APPROVE' | 'REJECT' | null>(null);
  const m = useMutation({
    mutationFn: (decision: 'APPROVE' | 'REJECT') => reviewConcept(it.id, decision, note),
    onSuccess: (_r, decision) => {
      setDone(decision);
      void qc.invalidateQueries({ queryKey: ['review', source] });
    },
  });
  const t = TYPE[it.type] ?? { label: it.type.toLowerCase(), icon: ScrollText };
  const Icon = t.icon;
  const target = it.mapping
    ? `${it.mapping.entity}.${it.mapping.column ?? ''}${it.mapping.values?.length ? ` ${it.mapping.operator ?? '='} ${it.mapping.values.join(', ')}` : ''}`
    : '—';

  if (done) {
    return (
      <div className="card flex items-center gap-2 p-3 text-[12px] text-ink-muted">
        <span className={clsx('rounded px-1.5 py-0.5 text-[10px] font-semibold', done === 'APPROVE' ? 'bg-ok/15 text-ok' : 'bg-line text-ink-faint')}>
          {done === 'APPROVE' ? 'onaylandı' : 'reddedildi'}
        </span>
        <b className="text-ink">{it.term}</b> → {target}
      </div>
    );
  }

  return (
    <div className="card p-3.5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep">
              <Icon size={10} /> {t.label}
            </span>
            <b className="font-display text-[15px]">{it.term}</b>
            <span className="text-ink-faint">→</span>
            <code className="rounded bg-[#F6F3F0] px-1.5 py-0.5 text-[11px] text-ink">{target}</code>
            {it.mapping?.formula && (
              <code className="max-w-full truncate rounded bg-[#F6F3F0] px-1.5 py-0.5 text-[11px] text-ink-muted">{it.mapping.formula}</code>
            )}
          </div>

          {/* Kaynağın kendi açıklaması: kolonun ne olduğunu Logo'nun sözlüğü söylüyorsa, kararı veren
              kişinin tabloyu tanımasına gerek kalmaz. */}
          {it.columnMeaning && (
            <div className="mt-1.5 text-[11px] text-ink-muted"><span className="rounded bg-line px-1 text-[10px]">kaynak</span> {it.columnMeaning}</div>
          )}

          {/* Verinin kendisi. Bir değer eşlemesi doğru mu — en kolay cevabı, o kolonda gerçekten
              hangi değerlerin kaç satırda geçtiğidir. */}
          {it.observed.length > 0 && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px]">
              <span className="rounded bg-ok/10 px-1 text-[10px] text-ok">veride</span>
              {it.observed.map((o) => (
                <span key={o.value} className={clsx('rounded px-1.5 py-0.5 text-[10px]',
                  it.mapping?.values?.includes(o.value) ? 'bg-brand text-white' : 'bg-[#F6F3F0] text-ink-muted')}>
                  {o.value} · {o.rows.toLocaleString('tr-TR')}
                </span>
              ))}
            </div>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[10px] text-ink-faint">
            <MessagesSquare size={10} />
            {Object.entries(it.evidence).map(([k, n]) => (
              <span key={k} className="rounded bg-[#F6F3F0] px-1.5 py-0.5">{SOURCE[k] ?? k.toLowerCase()}{n > 1 ? ` ×${n}` : ''}</span>
            ))}
            {it.counterEvidence > 0 && <span className="rounded bg-brand-accent/15 px-1.5 py-0.5 text-brand-accent">{it.counterEvidence} çelişen kanıt</span>}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-stretch gap-1.5" style={{ width: 190 }}>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="not (isteğe bağlı)"
            className="rounded-lg border border-line px-2 py-1 text-[11px] outline-none focus:border-brand"
          />
          <div className="flex gap-1.5">
            <button
              type="button"
              disabled={m.isPending}
              onClick={() => m.mutate('APPROVE')}
              className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg bg-brand px-2 py-1.5 text-[11px] font-medium text-white disabled:opacity-50"
            >
              <Check size={11} /> doğru
            </button>
            <button
              type="button"
              disabled={m.isPending}
              onClick={() => m.mutate('REJECT')}
              className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg border border-line bg-white px-2 py-1.5 text-[11px] text-ink-muted disabled:opacity-50"
            >
              <X size={11} /> yanlış
            </button>
          </div>
          {m.isError && <div className="text-[10px] text-brand-accent">kaydedilemedi</div>}
        </div>
      </div>
    </div>
  );
}
