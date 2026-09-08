import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Link2, MessagesSquare, Pencil, ScrollText, Sigma, Table2, X } from 'lucide-react';
import clsx from 'clsx';
import { catalogTable, reviewConcept, reviewQueue, type ReviewItem } from '../lib/engine';

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
  RELATIONSHIP: { label: 'bağlantı', icon: Link2 },
  DEFAULT_FILTER: { label: 'varsayılan süzgeç', icon: ScrollText },
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

type Decision = { decision: 'APPROVE' | 'REJECT' | 'CORRECT'; column?: string };

function Row({ it, source }: { it: ReviewItem; source: string }) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [fixing, setFixing] = useState(false);
  const [column, setColumn] = useState('');
  const [done, setDone] = useState<'APPROVE' | 'REJECT' | 'CORRECT' | null>(null);
  // Kolon listesi yalnız düzeltme açıldığında istenir: kuyruk yüz satır, envanter sekiz megabayt.
  const cols = useQuery({
    queryKey: ['catalog-table', it.mapping?.entity],
    queryFn: () => catalogTable(it.mapping!.entity),
    enabled: fixing && Boolean(it.mapping?.entity),
    staleTime: 10 * 60_000,
  });
  const m = useMutation({
    mutationFn: (d: Decision) => reviewConcept(it.id, d.decision, note, { column: d.column }),
    onSuccess: (_r, d) => {
      setDone(d.decision);
      void qc.invalidateQueries({ queryKey: ['review', source] });
    },
  });
  const t = TYPE[it.type] ?? { label: it.type.toLowerCase(), icon: ScrollText };
  const Icon = t.icon;

  if (done) {
    return (
      <div className="card flex items-center gap-2 p-3 text-[12px] text-ink-muted">
        <span className={clsx('rounded px-1.5 py-0.5 text-[10px] font-semibold',
          done === 'APPROVE' ? 'bg-ok/15 text-ok' : done === 'CORRECT' ? 'bg-brand-soft text-brand-deep' : 'bg-line text-ink-faint')}>
          {done === 'APPROVE' ? 'onaylandı' : done === 'CORRECT' ? 'düzeltildi' : 'reddedildi'}
        </span>
        <span className="min-w-0 flex-1 truncate">{it.plain}</span>
      </div>
    );
  }

  return (
    <div className="card p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep">
          <Icon size={10} /> {t.label}
        </span>
        {/* Kararın verildiği cümle. Tablo adı değil — tablo adını okuyabilen kişi zaten bu ekrana
            ihtiyaç duymuyor; bu ekran işi bilen ama şemayı bilmeyen kişi için var. */}
        <p className="min-w-0 flex-1 text-[13.5px] leading-snug text-ink">{it.plain}</p>
      </div>

      {/* Verinin kendisi: bir eşlemenin doğru olup olmadığının en kolay kanıtı, o alanda gerçekten
          ne yazdığıdır. Seçilen değerler koyu, gerisi bağlam. */}
      {it.observed.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px]">
          <span className="rounded bg-ok/10 px-1 py-0.5 text-[10px] text-ok">alanda ne var</span>
          {it.observed.map((o) => (
            <span key={o.value} className={clsx('rounded px-1.5 py-0.5 text-[10px]',
              it.mapping?.values?.includes(o.value) ? 'bg-brand text-white' : 'bg-[#F6F3F0] text-ink-muted')}>
              {o.label ?? (o.value || '(boş)')} · {o.rows.toLocaleString('tr-TR')}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1 text-[10px] text-ink-faint">
          <MessagesSquare size={10} />
          {Object.entries(it.evidence).map(([k, n]) => (
            <span key={k} className="rounded bg-[#F6F3F0] px-1.5 py-0.5">{SOURCE[k] ?? k.toLowerCase()}{n > 1 ? ` ×${n}` : ''}</span>
          ))}
          {it.counterEvidence > 0 && <span className="rounded bg-brand-accent/15 px-1.5 py-0.5 text-brand-accent">{it.counterEvidence} çelişen kanıt</span>}
          <span className="text-ink-faint/70">· {it.mapping?.entity}{it.mapping?.column ? `.${it.mapping.column}` : ''}</span>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <button type="button" disabled={m.isPending} onClick={() => m.mutate({ decision: 'APPROVE' })}
            className="inline-flex items-center gap-1 rounded-lg bg-brand px-2.5 py-1.5 text-[11px] font-medium text-white disabled:opacity-50">
            <Check size={11} /> doğru
          </button>
          <button type="button" disabled={m.isPending} onClick={() => setFixing((v) => !v)}
            className={clsx('inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-50',
              fixing ? 'border-brand bg-brand-soft text-brand-deep' : 'border-line bg-white text-ink-muted')}>
            <Pencil size={11} /> düzelt
          </button>
          <button type="button" disabled={m.isPending} onClick={() => m.mutate({ decision: 'REJECT' })}
            className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2.5 py-1.5 text-[11px] text-ink-muted disabled:opacity-50">
            <X size={11} /> yanlış
          </button>
        </div>
      </div>

      {/* Üçüncü yol. "Yanlış" bilgiyi atar; "düzelt" onu alır. Kişinin kendi cümlesi tabloya not
          olarak yazılır ve modelin gördüğü yere gider — doğru kolonu da seçerse terim onun adına
          o kolona tanımlanır. */}
      {fixing && (
        <div className="mt-2.5 rounded-xl border border-dashed border-brand/40 bg-brand-soft/30 p-2.5">
          <label className="block text-[11px] font-medium text-brand-deep">Bu terim sizce ne demek?</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder={`Örnek: "${it.term}" bizde ${it.mapping?.entity === 'CLCARD' ? 'müşterinin satış kanalını' : 'başka bir şeyi'} anlatır, çünkü…`}
            className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-[12px] outline-none focus:border-brand"
          />
          <div className="mt-1.5 flex flex-wrap items-end gap-2">
            <div>
              <label className="block text-[10px] text-ink-muted">doğru alan (biliyorsanız)</label>
              <select
                value={column}
                onChange={(e) => setColumn(e.target.value)}
                className="mt-0.5 rounded-lg border border-line bg-white px-2 py-1 text-[11px] outline-none focus:border-brand"
              >
                <option value="">— değiştirme, sadece açıklama —</option>
                {(cols.data?.tables?.[0]?.columns ?? []).map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}{c.description ? ` — ${c.description.split('(')[0].trim()}` : ''}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              disabled={m.isPending || !note.trim()}
              onClick={() => m.mutate({ decision: 'CORRECT', column: column || undefined })}
              className="rounded-lg bg-brand px-3 py-1.5 text-[11px] font-medium text-white disabled:opacity-40"
            >
              düzeltmeyi kaydet
            </button>
            {!note.trim() && <span className="text-[10px] text-ink-faint">açıklama olmadan kaydedilmez</span>}
          </div>
        </div>
      )}
      {m.isError && <div className="mt-1 text-[10px] text-brand-accent">kaydedilemedi</div>}
    </div>
  );
}
