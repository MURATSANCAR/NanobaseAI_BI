import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Check, ChevronDown, Link2, MessagesSquare, Pencil, ScrollText, Search, Sigma, Table2, X } from 'lucide-react';
import clsx from 'clsx';
import { catalogTable, conceptProvenance, reviewConcept, reviewQueue, type Provenance, type ReviewItem } from '../lib/engine';

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
  const [why, setWhy] = useState(false);
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
        {/* Rozetler kanıtın adıydı, kendisi değil. Onlara basınca kanıt açılır: terimin geçtiği
            sorular, kaynağın cümlesi, alanda ölçülenler ve onaylanınca üretilecek SQL parçası. */}
        <button
          type="button"
          onClick={() => setWhy((v) => !v)}
          className="flex flex-wrap items-center gap-1 text-left text-[10px] text-ink-faint hover:text-ink-muted"
        >
          <MessagesSquare size={10} />
          {Object.entries(it.evidence).map(([k, n]) => (
            <span key={k} className="rounded bg-[#F6F3F0] px-1.5 py-0.5">{SOURCE[k] ?? k.toLowerCase()}{n > 1 ? ` ×${n}` : ''}</span>
          ))}
          {it.counterEvidence > 0 && <span className="rounded bg-brand-accent/15 px-1.5 py-0.5 text-brand-accent">{it.counterEvidence} çelişen kanıt</span>}
          <span className="text-ink-faint/70">· {it.mapping?.entity}{it.mapping?.column ? `.${it.mapping.column}` : ''}</span>
          <span className={clsx('ml-0.5 inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 font-medium',
            why ? 'bg-brand-soft text-brand-deep' : 'text-brand-deep/70')}>
            <Search size={9} /> nereden çıktı
            <ChevronDown size={9} className={clsx('transition', why && 'rotate-180')} />
          </span>
        </button>

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

      {why && <Why id={it.id} />}

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

/** Çelişen kanıtın türü — insanın anlayacağı hâliyle. */
const CONFLICT: Record<string, string> = {
  VALUE_MISMATCH: 'iddia edilen değer veride bulunamadı',
  COLUMN_MISMATCH: 'kolon uyuşmuyor',
  DRIFT: 'kaynak değişti, dayanak yerinde değil',
  HUMAN_REJECT: 'bir kişi reddetmiş',
  DOC_CONTRADICTION: 'kaynağın kendi açıklaması bunu tutmuyor',
  SENSE_MINORITY: 'aynı kelimenin daha baskın başka bir anlamı var',
  SENSE_CONFLICT: 'aynı kelime başka şeylere de bağlanmış',
  EXECUTION_FAILED: 'denenince sorgu çalışmadı',
  EXECUTION_EMPTY: 'denenince boş döndü',
  MEASURE_DISAGREEMENT: 'iki ölçü birbirini tutmuyor',
};

const nf = (n: number) => n.toLocaleString('tr-TR');
const pctOf = (v: number) => `%${Math.round(v * 100)}`;

/** Kanıtın sayıları cümleye çevrilir: «precision 0.83» kimseye bir şey söylemez, «bu kelimenin
 *  geçtiği sorguların %83'ünde bu süzgeç vardı» aynı sayının okunabilir hâlidir. */
function facts(d: Record<string, unknown>): string[] {
  const n = (k: string) => (typeof d[k] === 'number' ? (d[k] as number) : null);
  const out: string[] = [];
  if (n('precision') != null) out.push(`bu kelimenin geçtiği sorguların ${pctOf(n('precision')!)}'inde bu süzgeç vardı`);
  if (n('term_total') != null) out.push(`kelime ${nf(n('term_total')!)} soruda geçmiş`);
  if (n('recall') != null) out.push(`bu süzgecin kullanıldığı sorguların ${pctOf(n('recall')!)}'i bu kelimeyle sorulmuş`);
  if (n('fit') != null) out.push(`verideki uyum ${pctOf(n('fit')!)}`);
  if (n('distinct') != null) out.push(`alanda ${nf(n('distinct')!)} ayrı değer var`);
  if (n('share') != null) out.push(`satırların ${pctOf(n('share')!)}'i bu süzgece uyuyor`);
  if (n('rows') != null) out.push(`deneme sorgusu ${nf(n('rows')!)} satır döndürdü`);
  if (n('value') != null) out.push(`ölçülen sonuç ${nf(Math.round(n('value')!))}`);
  if (n('confidence') != null) out.push(`modelin kendi güveni ${pctOf(n('confidence')!)}`);
  if (Array.isArray(d.aliases) && d.aliases.length) out.push(`sorgudaki takma adlar: ${(d.aliases as string[]).join(', ')}`);
  if (d.ref) out.push(`işaret ettiği: ${String(d.ref)}`);
  if (d.by) out.push(`yazan: ${String(d.by)}`);
  const counts = d.counts as Record<string, number> | undefined;
  if (counts && typeof counts === 'object') {
    out.push(Object.entries(counts).map(([k, v]) => `${k} · ${nf(v)}`).join('   '));
  }
  return out;
}

const dateTr = (s: string | null) => (s ? new Date(s).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' }) : '');

function Field({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex gap-1.5">
      <span className="shrink-0 text-ink-faint">{k}</span>
      <span className="min-w-0 text-ink-muted">{v}</span>
    </div>
  );
}

/** Bir sorgu, kanıt olarak: sorulan soru ve onu cevaplayan SQL — iddiayı taşıyan satırlar işaretli.
 *  Uzun sorgu katlanır; okunması gereken satır zaten işaretli olandır. */
function Pair({ ex }: { ex: Provenance['evidence'][number]['examples'][number] }) {
  const [all, setAll] = useState(false);
  const near = new Set<number>();
  ex.hits.forEach((i) => [i - 1, i, i + 1].forEach((j) => j >= 0 && j < ex.lines.length && near.add(j)));
  const long = ex.lines.length > 9 && ex.hits.length > 0;
  const show = all || !long ? ex.lines.map((_, i) => i) : [...near].sort((a, b) => a - b);

  return (
    <div className="mt-1.5">
      <p className="text-[11.5px] italic leading-snug text-ink">“{ex.question}”</p>
      <div className="mt-1 overflow-x-auto scroll-thin rounded-lg bg-ink p-2 font-mono text-[10px] leading-relaxed text-white/60">
        {show.map((i, k) => (
          <div key={i}>
            {k > 0 && show[k - 1] !== i - 1 && <div className="select-none text-white/25">⋯</div>}
            <div className={clsx('whitespace-pre', ex.hits.includes(i) && 'rounded bg-brand/50 px-1 text-white')}>{ex.lines[i]}</div>
          </div>
        ))}
      </div>
      <div className="mt-0.5 flex items-center gap-2 text-[10px] text-ink-faint">
        {long && (
          <button type="button" onClick={() => setAll((v) => !v)} className="text-brand-deep/80 hover:underline">
            {all ? 'yalnız ilgili satırlar' : `sorgunun tamamı (${ex.lines.length} satır)`}
          </button>
        )}
        <span>{ex.source === 'runtime_validated' ? 'bu kurulumda çalışmış' : ex.source}{ex.at ? ` · ${dateTr(ex.at)}` : ''}</span>
      </div>
    </div>
  );
}

/** «Bu nereden çıktı?» — kararın dayanağı, kararın verildiği yerde.
 *
 *  Onay ekranı bir kelimeyi değil bir iddiayı sorar, ve iddianın dayanağı bu ekrana kadar hiç
 *  gelmiyordu: kişi «doğrulanmış sorgu ×2» yazan bir rozete bakıp evet demek zorundaydı. Burada
 *  dayanağın kendisi var — terimin geçtiği sorular ve onları cevaplayan SQL, kaynağın kendi cümlesi,
 *  alanda ölçülen sayılar — ve ayrı bir başlıkta, onaylanınca sorgulara girecek SQL parçası. */
function Why({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['provenance', id], queryFn: () => conceptProvenance(id), staleTime: 5 * 60_000 });

  if (q.isLoading) return <div className="mt-2.5 rounded-xl border border-line bg-page/60 p-3 text-[11px] text-ink-faint">kanıt okunuyor…</div>;
  if (q.isError || !q.data) return <div className="mt-2.5 rounded-xl border border-line bg-page/60 p-3 text-[11px] text-brand-accent">kanıt okunamadı.</div>;

  const p = q.data;
  const t = p.target;

  return (
    <div className="mt-2.5 space-y-3 rounded-xl border border-line bg-page/60 p-3">
      {t && (
        <section>
          <h4 className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">onaylarsanız sorgulara bu girecek</h4>
          {t.sql && (
            <pre className="mt-1 overflow-x-auto scroll-thin whitespace-pre-wrap break-words rounded-lg bg-ink p-2 font-mono text-[10.5px] leading-relaxed text-white/90">{t.sql}</pre>
          )}
          {t.readable && <p className="mt-1 text-[11px] leading-snug text-ink-muted">okunuşu: {t.readable}</p>}
          <div className="mt-1.5 space-y-0.5 text-[11px]">
            <Field k="tablo" v={<>
              <span className="font-mono">{t.table}</span>
              {t.tableExample && <span className="text-ink-faint"> · bu kurulumda {t.tableExample}</span>}
              {t.tableRows != null && <span className="text-ink-faint"> · {nf(t.tableRows)} satır</span>}
            </>} />
            {t.column && <Field k="alan" v={<>
              <span className="font-mono">{t.column}</span>
              {t.columnType && <span className="text-ink-faint"> · {t.columnType}</span>}
            </>} />}
            {/* Kaynağın kendi cümlesi ile bizim çıkardığımız ayrı durur: biri müşterinin yazdığı,
                diğeri bu sistemin sonucu. Karışırlarsa hangisine güvenileceği belli olmaz. */}
            {t.columnDoc && <Field k="kaynağın açıklaması" v={t.columnDoc} />}
            {t.derived.map((d) => <Field key={d.text} k={`çıkarım (${d.source})`} v={d.text} />)}
          </div>
        </section>
      )}

      <section>
        <h4 className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">bu nereden çıktı</h4>
        {p.evidence.length === 0 && <p className="mt-1 text-[11px] text-ink-muted">Kayıtlı kanıt yok — bu terim yalnız bir öneri.</p>}
        <div className="mt-1 space-y-2.5">
          {p.evidence.map((e, i) => (
            <div key={i} className="border-l-2 border-line pl-2.5">
              <div className="flex flex-wrap items-baseline gap-1.5 text-[11px]">
                <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep">{SOURCE[e.kind] ?? e.kind.toLowerCase()}</span>
                <span className="font-mono text-[10px] text-ink-faint">{e.source}</span>
                {e.at && <span className="text-[10px] text-ink-faint">· {dateTr(e.at)}</span>}
              </div>
              {facts(e.detail).length > 0 && (
                <p className="mt-0.5 text-[11px] leading-snug text-ink-muted">{facts(e.detail).join(' · ')}</p>
              )}
              {typeof e.detail.snippet === 'string' && (
                <p className="mt-1 rounded-lg bg-white px-2 py-1.5 text-[11px] leading-snug text-ink">“{e.detail.snippet}”</p>
              )}
              {typeof e.detail.rationale === 'string' && (
                <p className="mt-1 rounded-lg bg-white px-2 py-1.5 text-[11px] leading-snug text-ink-muted">model: “{e.detail.rationale}”</p>
              )}
              {e.examples.map((ex, k) => <Pair key={k} ex={ex} />)}
              {/* Bulunamayan kanıt sessizce düşürülmez: karar verilirken sayılmış bir sorgu artık
                  gösterilemiyorsa, ekran daha az kanıt varmış gibi davranmamalı. */}
              {e.missing > 0 && (
                <p className="mt-1 text-[10px] text-ink-faint">{e.seenIn} sorguya dayanıyor; {e.missing} tanesi artık bilgi paketinde değil.</p>
              )}
            </div>
          ))}
        </div>
      </section>

      {p.conflicts.length > 0 && (
        <section>
          <h4 className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-brand-accent">
            <AlertTriangle size={10} /> bunun aksini söyleyen
          </h4>
          <div className="mt-1 space-y-1">
            {p.conflicts.map((c, i) => (
              <p key={i} className="text-[11px] leading-snug text-ink-muted">
                <span className="text-brand-accent">{CONFLICT[c.type] ?? c.type.toLowerCase()}</span>
                {facts(c.detail).length > 0 && <> · {facts(c.detail).join(' · ')}</>}
                {Object.keys(c.detail).filter((k) => !['snippet', 'rationale'].includes(k)).length > 0 && facts(c.detail).length === 0 && (
                  <span className="font-mono text-[10px] text-ink-faint"> {JSON.stringify(c.detail)}</span>
                )}
              </p>
            ))}
          </div>
        </section>
      )}

      {p.producedBy.length > 0 && (
        <p className="text-[10px] text-ink-faint">
          nasıl bulundu: {[...new Set(p.producedBy.map((x) => x.how || x.by))].join(' · ')}
          {p.producedBy[0]?.at ? ` · ${dateTr(p.producedBy[0].at)}` : ''}
        </p>
      )}
    </div>
  );
}
