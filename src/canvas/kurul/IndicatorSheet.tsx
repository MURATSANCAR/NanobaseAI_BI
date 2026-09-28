import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, Check, Loader2, Sparkles, Trash2 } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { fmtDay, fmtTime, fmtValue, kurulApi, waitJob, type Comment, type KurulMeta } from './api';
import { ColorBadge, Spark, TrendMark } from './parts';

type MonthlyComment = { metin: string; donem: string; onaylayan: string | null };

function monthlyComment(ayrinti: Record<string, unknown> | undefined): MonthlyComment | null {
  const v = ayrinti?.aylikYorum as Partial<MonthlyComment> | undefined;
  return v && typeof v.metin === 'string' && v.metin ? { metin: v.metin, donem: String(v.donem ?? ''), onaylayan: v.onaylayan ?? null } : null;
}

/** Gösterge ayrıntısı: değer, hedef, önceki, eşik, 12 dönem seyri, kaynak ekrana bağlantı (yalnız o sayfanın yetkisi
 *  olana), bölüm yorumu. Sahip kendi göstergesine yorum yazar (doğrudan onaylı); sekreterin yazdığı ya da Zeki AI'ın
 *  taslağı sahibin ya da genel müdürün onayını bekler. */
export default function IndicatorSheet({ kod, donem, meta, onClose }: { kod: string | null; donem: string; meta: KurulMeta; onClose: () => void }) {
  const qc = useQueryClient();
  const pages = usePageAccess();
  const q = useQuery({ queryKey: ['kurul', 'indicator', kod, donem], queryFn: () => kurulApi.indicator(kod as string, donem), enabled: !!kod });
  const [text, setText] = useState('');
  const [drafting, setDrafting] = useState(false);
  const me = meta.me;
  const g = q.data?.gosterge;
  const mine = !!g?.sahip && g.sahip.toLowerCase() === me.username.toLowerCase();
  const canWrite = (mine && me.canComment) || me.canPrepare;
  const canApprove = (mine && me.canComment) || me.canFreeze;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['kurul', 'indicator', kod] });
    qc.invalidateQueries({ queryKey: ['kurul', 'panel'] });
  };
  const add = useMutation({
    mutationFn: () => kurulApi.addComment(kod as string, donem, text),
    onSuccess: (c) => {
      setText('');
      toast.success(c.durum === 'onayli' ? 'Yorum kaydedildi.' : 'Yorum kaydedildi; göstergenin sahibinin onayını bekliyor.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Yorum kaydedilemedi.')),
  });
  const act = useMutation({
    mutationFn: async ({ c, op }: { c: Comment; op: 'approve' | 'delete' }) =>
      op === 'approve' ? kurulApi.approveComment(c.id) : kurulApi.deleteComment(c.id),
    onSuccess: (_d, v) => {
      toast.success(v.op === 'approve' ? 'Yorum onaylandı.' : 'Taslak silindi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });

  async function draft() {
    setDrafting(true);
    try {
      const j = await kurulApi.draftComment(kod as string, donem);
      const done = await waitJob(j.id);
      if (done.durum === 'hata') toast.error(done.hata || 'Taslak hazırlanamadı.');
      else toast.success('Zeki AI taslağı hazır; okuyup onaylayın.');
    } catch (e) {
      toast.error(errText(e, 'Taslak istenemedi.'));
    } finally {
      setDrafting(false);
      refresh();
    }
  }

  const source = g?.ekran && canOpenRoute(pages, g.ekran) ? g.ekran : null;
  // M45'in CFO onaylı aylık finansal yorumu (yalnız net satış göstergesinin ayrıntısında gelir).
  const monthly = monthlyComment(g?.ayrinti);
  const k = q.data?.kaynaklar;
  return (
    <Sheet open={!!kod} onClose={onClose} title={g?.ad ?? 'Gösterge'} subtitle={g ? `${g.bolumAdi} · ${q.data?.donemAdi ?? ''}` : undefined}>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Gösterge okunamadı.')}</Note>}
      {g && q.data && (
        <div className="flex flex-col gap-4 text-[13px] leading-snug">
          <div className="flex flex-col gap-1.5">
            <ColorBadge durum={g.durum} renk={g.renk} size="md" />
            {g.durum === 'ok' ? (
              <>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[30px] font-bold leading-none tabular-nums tracking-tight">{g.degerMetin}</span>
                  <SqlInfo k={k} alan="gosterge" label={g.ad} />
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-canvas-muted">
                  {g.onceki !== null && (
                    <span className="inline-flex items-center gap-1.5">
                      {g.oncekiEtiket ?? 'Önceki'}: <b className="font-mono tabular-nums text-canvas-ink">{fmtValue(g.onceki, g.birim)}</b>
                      <TrendMark t={g.egilim} />
                      <SqlInfo k={k} alan="gosterge.onceki" label={`${g.ad}: önceki ve eğilim`} />
                    </span>
                  )}
                  {g.hedef !== null && (
                    <span className="inline-flex items-center gap-1">
                      Hedef: <b className="font-mono tabular-nums text-canvas-ink">{fmtValue(g.hedef, g.birim)}</b>
                      <SqlInfo k={k} alan="gosterge.hedef" label={`${g.ad}: hedef`} />
                    </span>
                  )}
                </div>
              </>
            ) : (
              <Note tone="info">{g.not || 'Bu göstergenin kaynağı henüz yok; sayı yazılmaz.'}</Note>
            )}
            {g.durum === 'ok' && g.not && <p className="text-[12px] text-canvas-muted">{g.not}</p>}
          </div>

          {g.aciklama && <p className="text-[12.5px] text-canvas-muted">{g.aciklama}</p>}

          {monthly && (
            <section className="rounded-xl bg-white/80 p-3 ring-1 ring-slate-100">
              <div className={labelCls}>Aylık finansal yorum · {monthly.donem} · onaylayan {monthly.onaylayan ?? '—'}</div>
              <p className="mt-1 whitespace-pre-line text-[12.5px] leading-relaxed">{monthly.metin}</p>
            </section>
          )}

          <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 rounded-xl bg-slate-50 p-3 text-[12px] sm:grid-cols-2">
            <div><dt className={labelCls}>Veri son günü</dt><dd>{fmtDay(g.veriSonGunu)}</dd></div>
            <div><dt className={labelCls}>Ölçüldü</dt><dd>{fmtTime(g.olcum)}</dd></div>
            <div><dt className={labelCls}>Kaynak</dt><dd>{g.kaynak ?? '—'}</dd></div>
            <div><dt className={labelCls}>Sahip</dt><dd>{g.sahip ?? 'atanmadı'}</dd></div>
            <div className="sm:col-span-2">
              <dt className={`${labelCls} flex items-center gap-1`}>
                Renk kuralı
                {(g.esikSari !== null || g.esikKirmizi !== null) && <SqlInfo k={k} alan="gosterge.esikSari" label={`${g.ad}: eşikler`} />}
              </dt>
              <dd>
                {g.esikSari !== null || g.esikKirmizi !== null
                  ? `${g.yonAdi}: sarı ${fmtValue(g.esikSari, g.birim)}, kırmızı ${fmtValue(g.esikKirmizi, g.birim)}`
                  : g.renkKaynagi === 'kaynak'
                    ? 'Eşik tanımlı değil; renk kaynak modülün kendi kuralından.'
                    : 'Eşik tanımlı değil (gösterge kataloğunda girilir).'}
              </dd>
            </div>
          </dl>

          <div>
            <div className={`${labelCls} flex items-center gap-1`}>
              Son {q.data.seri.length} dönem <SqlInfo k={k} alan="seri" label={`${g.ad}: son dönemler`} />
            </div>
            <Spark points={q.data.seri} />
          </div>

          {source && (
            <Link to={source} className={`${btnGhost} self-start`}>
              Kaynak ekranı aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          )}

          <section className="flex flex-col gap-2">
            <h3 className="text-[14px] font-extrabold tracking-tight">Bölüm yorumu</h3>
            {q.data.yorumlar.length === 0 && <p className="text-[12px] text-canvas-muted">Bu dönem için yorum yok.</p>}
            {q.data.yorumlar.map((c) => (
              <div key={c.id} className="rounded-xl bg-white/80 p-3 ring-1 ring-slate-100">
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-canvas-muted">
                  <Pill tone={c.durum === 'onayli' ? 'ok' : c.durum === 'hata' ? 'err' : 'warn'}>{c.durumAdi}</Pill>
                  {c.kaynak === 'zeki' && <Pill tone="violet">Zeki AI taslağı</Pill>}
                  <span>{c.yazan} · {fmtTime(c.yazildi)}</span>
                  {c.onaylayan && <span>· onaylayan {c.onaylayan}</span>}
                </div>
                {c.durum === 'hazirlaniyor' ? (
                  <p className="inline-flex items-center gap-1.5 text-[12px] text-canvas-muted"><Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> Zeki AI yazıyor…</p>
                ) : c.durum === 'hata' ? (
                  <p className="text-[12px] text-red-700">{c.hata}</p>
                ) : (
                  <p className="whitespace-pre-wrap break-words">{c.metin}</p>
                )}
                {(c.durum === 'taslak' || c.durum === 'hata') && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {c.durum === 'taslak' && canApprove && (
                      <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate({ c, op: 'approve' })}>
                        <Check aria-hidden className="h-4 w-4" /> Onayla
                      </button>
                    )}
                    {canWrite && (
                      <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate({ c, op: 'delete' })}>
                        <Trash2 aria-hidden className="h-4 w-4" /> Sil
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            {canWrite ? (
              <div className="flex flex-col gap-2">
                <label htmlFor="kurul-yorum" className={labelCls}>{mine ? 'Yorumunuz (kaydedince onaylı olur)' : 'Yorum (sahibin onayını bekler)'}</label>
                <textarea id="kurul-yorum" className={`${field} min-h-[96px]`} value={text} maxLength={2000}
                  placeholder="Neden bu renkte, ne yapılıyor?" onChange={(e) => setText(e.target.value)} />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={btnPrimary} disabled={!text.trim() || add.isPending} onClick={() => add.mutate()}>
                    {add.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />} Kaydet
                  </button>
                  {meta.modelVar && g.durum === 'ok' && (
                    <button type="button" className={btnGhost} disabled={drafting} onClick={draft}>
                      {drafting ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                      Zeki AI taslağı
                    </button>
                  )}
                </div>
                <p className="text-[11px] text-canvas-muted">Zeki AI yalnız bu göstergenin kayıtlı değerlerini kullanır; olmayan sayı yazarsa taslak kaydedilmez.</p>
              </div>
            ) : (
              !g.sahip && <p className="text-[11.5px] text-canvas-muted">Göstergenin sahibi atanmadığı için yorum yazılamıyor (gösterge kataloğunda atanır).</p>
            )}
          </section>
        </div>
      )}
    </Sheet>
  );
}
