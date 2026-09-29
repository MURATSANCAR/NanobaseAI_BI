import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Check, FileDiff, FileSearch, Sparkles } from 'lucide-react';
import { canSeePage, usePageAccess } from '../../useAdmin';
import { Note, Pill, btnGhost, btnPrimary } from '../../admin/ui';
import SqlInfo from '../../components/SqlInfo';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';
import QuoteEvidence from '../QuoteEvidence';
import type { Meta, Terms } from './api';
import { ACCEPT_FILES, applySuggestion, conflicts, extractApi, suggestionRows, type Suggestion } from './extract';
import { errMsg, money } from './ui';

/**
 * Öneri 13 — imzalı ya da karşı taraftan gelen sözleşme belgesinden şartlar. Belge yüklenir, arka planda okunur
 * (taranmış sayfa OCR), her şart belgede birebir alıntısıyla «önerilen» olarak listelenir. «Uygula» yalnız o alanı
 * forma yazar; kaydı yine kişi yapar. Aynı alana belgede farklı değer çıkarsa öneri yok, adaylar yan yana görünür.
 */
export default function DocumentExtract({
  meta,
  terms,
  onApply,
  contractKey,
  lock,
}: {
  meta: Meta;
  terms: Terms;
  onApply: (next: Terms, keys: string[], extractId: string, s: Suggestion) => void;
  contractKey?: string;
  lock?: boolean;
}) {
  const [id, setId] = useState<string | null>(null);
  const [applied, setApplied] = useState<string[]>([]);
  const prior = useQuery({
    queryKey: ['contracts', 'extracts', contractKey ?? ''],
    queryFn: () => extractApi.forContract(contractKey as string),
    enabled: !!contractKey,
    staleTime: 60_000,
  });
  useEffect(() => {
    if (!id && prior.data?.items[0]) setId(prior.data.items[0].id);
  }, [id, prior.data]);
  const q = useQuery({
    queryKey: ['contracts', 'extract', id],
    queryFn: () => extractApi.get(id as string),
    enabled: !!id,
    refetchInterval: (s) => (s.state.data?.item.status === 'hazirlaniyor' ? 1500 : false),
  });
  const upload = useMutation({
    mutationFn: (file: File) => extractApi.upload(file, contractKey),
    onSuccess: (x) => {
      setApplied([]);
      setId(x.id);
    },
  });
  const item = q.data?.item;
  const r = item?.result ?? null;
  const rows = r ? suggestionRows(r, meta) : [];
  const clashes = r ? conflicts(r, meta.labels) : [];
  const apply = (keys: string[]) => {
    if (!r || !item) return;
    const next = [...new Set([...applied, ...keys])];
    setApplied(next);
    onApply(applySuggestion(terms, r.oneri, keys), next, item.id, r.oneri);
  };
  const pending = rows.filter((x) => !applied.includes(x.key));
  const canCompare = canSeePage(usePageAccess(), 'sozlesme-karsilastirma');
  const running = item?.status === 'hazirlaniyor' || upload.isPending;
  const share = item && item.total > 0 ? Math.min(1, item.done / item.total) : 0;

  return (
    <section className="rounded-2xl border border-violet-100 bg-violet-50/40 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 text-[13px] font-extrabold">
            <FileSearch aria-hidden className="h-4 w-4 text-canvas-violet" />
            Belgeden şartları oku
          </h3>
          <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
            İmzalı ya da gelen sözleşmeyi yükleyin (PDF, Word, taranmış görüntü). Oran, avans, süre ve haklar belgedeki cümlesiyle önerilir; forma siz aktarırsınız. CRM'e yazılmaz.
          </p>
        </div>
        <div className="w-full sm:w-auto">
          <FileDrop
            size="button"
            title={item ? 'Başka belge oku' : 'Belge yükle'}
            accept={ACCEPT_FILES}
            maxBytes={10 * MB}
            disabled={lock || running}
            busy={upload.isPending}
            onPick={(f) => upload.mutate(f)}
          />
        </div>
      </div>

      {upload.error && <div className="mt-2"><Note tone="err">{errMsg(upload.error)}</Note></div>}
      {q.error && <div className="mt-2"><Note tone="err">{errMsg(q.error, 'Belge okuması getirilemedi.')}</Note></div>}

      {item && (
        <div className="mt-3 space-y-2.5">
          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-canvas-muted">
            <a href={extractApi.fileUrl(item.id)} target="_blank" rel="noreferrer" className="min-w-0 max-w-full truncate font-bold text-canvas-violet hover:underline">
              {item.filename}
            </a>
            {r?.kaynak === 'zeki' ? (
              <Pill tone="violet">
                <Sparkles aria-hidden className="mr-0.5 inline h-3 w-3" />
                Zeki AI
              </Pill>
            ) : r ? (
              <Pill tone="muted">Kurala göre okundu</Pill>
            ) : null}
            {r && <span>{r.okuma.sayfa} sayfa · {r.pencere.sayi} bölümde okundu</span>}
            <SqlInfo k={q.data?.kaynaklar} alan="item" label="Belgeden şart okuması" />
            {r && rows.length > 0 && canCompare && (
              <Link
                to={`/telif-sozlesme/karsilastirma?sekme=sozlesme&sozlesme=${encodeURIComponent(`belge-${item.id}`)}`}
                className="inline-flex min-h-11 items-center gap-1 font-bold text-canvas-violet hover:underline sm:min-h-0"
              >
                <FileDiff aria-hidden className="h-3.5 w-3.5" />
                Şartları emsalle karşılaştır
              </Link>
            )}
          </div>

          {running && (
            <div aria-live="polite">
              <p className="text-[12px] font-semibold">Belge okunuyor{item.total > 0 ? ` · ${item.done}/${item.total} bölüm` : '…'}</p>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-violet-100">
                <div
                  className="h-full origin-left rounded-full bg-canvas-violet transition-transform duration-300 ease-out motion-reduce:transition-none"
                  style={{ transform: `scaleX(${Math.max(0.04, share)})` }}
                />
              </div>
            </div>
          )}
          {item.status === 'hata' && <Note tone="err">{item.error}</Note>}

          {r && (
            <>
              {r.okuma.not && <Note tone="info">{r.okuma.not}</Note>}
              {r.neden && <Note tone="info">{r.neden}</Note>}
              {r.oneri.gecersiz && <Note tone="warn">Önerinin bir kısmı şart kurallarına uymuyor: {r.oneri.gecersiz} Uygulamadan önce kontrol edin.</Note>}
              {rows.length === 0 ? (
                <p className="text-[12px] text-canvas-muted">Belgede alıntısıyla doğrulanabilen şart bulunamadı.</p>
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[12px] font-bold">{rows.length} önerilen şart</span>
                    <button type="button" className={`${btnPrimary} w-full sm:w-auto`} disabled={lock || !pending.length} onClick={() => apply(pending.map((x) => x.key))}>
                      {pending.length ? `Hepsini forma aktar (${pending.length})` : 'Hepsi aktarıldı'}
                    </button>
                  </div>
                  <ul className="divide-y divide-violet-100 rounded-xl bg-white/80">
                    {rows.map((x) => {
                      const done = applied.includes(x.key);
                      return (
                        <li key={x.key} className="px-2.5 py-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{x.label}</div>
                              <div className="break-words text-[13px] font-extrabold tabular-nums">{x.text}</div>
                            </div>
                            <button
                              type="button"
                              className={`${btnGhost} shrink-0 px-3`}
                              disabled={lock || done}
                              onClick={() => apply([x.key])}
                              aria-label={`${x.label}: forma aktar`}
                            >
                              {done ? <Check aria-hidden className="h-4 w-4 text-emerald-600" /> : null}
                              {done ? 'Aktarıldı' : 'Aktar'}
                            </button>
                          </div>
                          <QuoteEvidence items={x.evidence} />
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
              {clashes.length > 0 && (
                <div className="rounded-xl bg-amber-50 p-2.5 text-[12px]">
                  <div className="font-extrabold text-amber-900">Belgede farklı değerler geçen alanlar — öneri yok, siz seçin</div>
                  <ul className="mt-1.5 space-y-2">
                    {clashes.map((c) => (
                      <li key={c.key}>
                        <span className="font-bold">{c.label}</span>
                        <ul className="mt-0.5 space-y-1">
                          {c.items.map((it, i) => (
                            <li key={i}>
                              <span className="font-semibold tabular-nums">
                                {typeof it.deger === 'number' && (c.key === 'advance' || c.key === 'flatFee') ? money(it.deger, r.oneri.currency ?? 'TRY') : String(it.deger)}
                              </span>
                              <QuoteEvidence items={it.kanit} first={1} />
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {r.atilan > 0 && (
                <p className="text-[11px] text-canvas-muted">{r.atilan} değer belgede alıntısı bulunamadığı ya da alıntıyla uyuşmadığı için önerilmedi.</p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
