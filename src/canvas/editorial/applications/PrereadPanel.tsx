import { useEffect, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpenCheck, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import SqlInfo from '../../components/SqlInfo';
import QuoteEvidence from '../QuoteEvidence';
import { errMsg } from './shared';
import { prereadApi, type Draft, type DraftKey, type PrereadResult } from './preread';

/**
 * Öneri 12 — başvuru dosyasının Zeki AI ön okuması: tür, hedef kitle ve yaş, 3–5 cümle özet, konu, temalar, yayın
 * ilkesi işaretleri ve katalogda konusu yakın kitaplar. Her değerin altında dosyadan birebir alıntısı ve sayfası var.
 * Taslak editör raporu formunun yalnız metin alanlarına aktarılır; puanlar ve kabul/red önerisi editörün.
 */
export default function PrereadPanel({ appId, onApply }: { appId: string; onApply?: (d: Draft, keys?: DraftKey[]) => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['applications', 'preread', appId],
    queryFn: () => prereadApi.get(appId),
    enabled: ENGINE_ENABLED,
    refetchInterval: (s) => (s.state.data?.preread?.status === 'hazirlaniyor' ? 2000 : false),
  });
  const [fileId, setFileId] = useState('');
  const files = q.data?.files ?? [];
  useEffect(() => {
    if (!fileId && files.length) setFileId((files.find((f) => f.readable && f.current) ?? files.find((f) => f.readable) ?? files[0]).id);
  }, [fileId, files]);
  const start = useMutation({
    mutationFn: () => prereadApi.start(appId, fileId || undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['applications', 'preread', appId] }),
  });
  const p = q.data?.preread ?? null;
  const shown = p?.result ? p : q.data?.previous ?? null;
  const r = shown?.result ?? null;
  const running = p?.status === 'hazirlaniyor' || start.isPending;
  const chosen = files.find((f) => f.id === fileId);
  const share = p && p.total > 0 ? Math.min(1, p.done / p.total) : 0;

  return (
    <section className="rounded-2xl border border-violet-100 bg-violet-50/40 p-3 text-[12.5px]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 text-[13px] font-extrabold">
            <BookOpenCheck aria-hidden className="h-4 w-4 text-canvas-violet" />
            Dosya ön okuması
            <Pill tone="violet">
              <Sparkles aria-hidden className="mr-0.5 inline h-3 w-3" />
              Zeki AI
            </Pill>
          </h3>
          <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
            Eser dosyası bölüm bölüm okunur; her öneri dosyadaki cümlesiyle gelir. Puan ve karar sizindir. Yazarın kişisel bilgileri okumaya gönderilmez.
          </p>
        </div>
        {r && <SqlInfo k={q.data?.kaynaklar} alan={shown === p ? 'preread' : 'previous'} label="Dosya ön okuması" />}
      </div>

      {q.error && <div className="mt-2"><Note tone="err">{errMsg(q.error, 'Ön okuma getirilemedi.')}</Note></div>}
      {q.data && !q.data.model && <div className="mt-2"><Note tone="info">Zeki AI bu kurulumda bağlı değil; ön okuma yapılamaz.</Note></div>}

      {q.data && (
        <div className="mt-2.5 flex flex-col gap-2 sm:flex-row sm:items-end">
          {files.length === 0 ? (
            <p className="text-canvas-muted">Okunacak eser dosyası yok; önce PDF ya da DOCX yükleyin (özgeçmiş okunmaz).</p>
          ) : (
            <>
              <label className="block min-w-0 flex-1">
                <span className={label}>Dosya</span>
                <select value={fileId} onChange={(e) => setFileId(e.target.value)} className={`${field} mt-1`} disabled={running}>
                  {files.map((f) => (
                    <option key={f.id} value={f.id} disabled={!f.readable}>
                      {f.filename} · {f.round}. tur{f.kindLabel ? ` · ${f.kindLabel}` : ''}{f.readable ? '' : ' (okunamıyor)'}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={`${r ? btnGhost : btnPrimary} w-full sm:w-auto`}
                disabled={running || !q.data.model || !chosen?.readable}
                onClick={() => start.mutate()}
              >
                {running && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
                {running ? 'Okunuyor…' : r ? 'Yeniden oku' : 'Ön okumayı başlat'}
              </button>
            </>
          )}
        </div>
      )}
      {chosen && !chosen.readable && chosen.why && <p className="mt-1 text-[11.5px] text-amber-800">{chosen.why}</p>}
      {start.error && <div className="mt-2"><Note tone="err">{errMsg(start.error)}</Note></div>}

      {p?.status === 'hazirlaniyor' && (
        <div className="mt-2.5" aria-live="polite">
          <p className="font-semibold">{p.filename} okunuyor{p.total > 0 ? ` · ${p.done}/${p.total} adım` : '…'}</p>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-violet-100">
            <div className="h-full origin-left rounded-full bg-canvas-violet transition-transform duration-300 ease-out motion-reduce:transition-none" style={{ transform: `scaleX(${Math.max(0.04, share)})` }} />
          </div>
        </div>
      )}
      {p?.status === 'hata' && <div className="mt-2"><Note tone="err">{p.error}</Note></div>}
      {shown && shown !== p && p?.status === 'hata' && <p className="mt-1 text-[11.5px] text-canvas-muted">Aşağıda önceki başarılı ön okuma görünüyor.</p>}

      {r && shown && <Result r={r} filename={shown.filename} onApply={onApply} />}
    </section>
  );
}

function Block({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl bg-white/85 px-2.5 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className={label}>{title}</div>
        {action}
      </div>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}

function Result({ r, filename, onApply }: { r: PrereadResult; filename: string; onApply?: (d: Draft, keys?: DraftKey[]) => void }) {
  const a = r.alanlar;
  const d = r.taslak;
  const [done, setDone] = useState<DraftKey[]>([]);
  const give = (keys?: DraftKey[]) => {
    if (!onApply) return;
    onApply(d, keys);
    setDone((x) => [...new Set([...x, ...(keys ?? (Object.keys(d) as DraftKey[]).filter((k) => d[k]))])]);
  };
  const push = (key: DraftKey) =>
    onApply && d[key] ? (
      <button type="button" className={`${btnGhost} shrink-0 px-2.5 py-1 text-[11.5px]`} disabled={done.includes(key)} onClick={() => give([key])}>
        {done.includes(key) ? 'Aktarıldı' : 'Forma aktar'}
      </button>
    ) : null;
  const unsure = (x: { neden?: string; olasilik?: number | null } | null) =>
    x?.neden ? <span className="text-canvas-muted">Boş bırakıldı: {x.neden}{x.olasilik != null ? ` (olasılık %${Math.round(x.olasilik * 100)})` : ''}.</span> : <span className="text-canvas-muted">Dosyada dayanağı bulunamadı.</span>;

  return (
    <div className="mt-3 space-y-2">
      <p className="text-[11.5px] text-canvas-muted">
        {filename} · {r.okuma.sayfa} sayfa · {r.pencere.sayi} bölümde okundu
        {r.okuma.not ? ` · ${r.okuma.not}` : ''}
        {r.pencere.okunamayan.length > 0 ? ` · okunamayan bölüm: s. ${r.pencere.okunamayan.join(', ')}` : ''}
      </p>
      {onApply && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/85 px-2.5 py-2">
          <span className="text-[12px]">Taslak raporu formun boş alanlarına aktarın; sonra okuyup düzeltin ve kaydedin.</span>
          <button type="button" className={`${btnPrimary} w-full sm:w-auto`} onClick={() => give()}>
            Boş alanlara aktar
          </button>
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        <Block title="Tür" action={a.tur?.deger ? push('genre') : null}>
          {a.tur?.deger ? (
            <>
              <b className="font-extrabold">{a.tur.ad}</b>
              {a.tur.olasilik != null && <span className="ml-1 text-[11px] text-canvas-muted">olasılık %{Math.round(a.tur.olasilik * 100)}</span>}
              <QuoteEvidence items={a.tur.kanit ?? []} />
            </>
          ) : unsure(a.tur)}
        </Block>
        <Block title="Hedef kitle ve yaş" action={d.ageGroup ? push('ageGroup') : null}>
          {a.kitle?.deger || a.yas?.ad ? (
            <>
              <b className="font-extrabold">{[a.kitle?.deger ? a.kitle.ad : null, a.yas?.ad].filter(Boolean).join(' · ')}</b>
              {a.kitle?.olasilik != null && <span className="ml-1 text-[11px] text-canvas-muted">olasılık %{Math.round(a.kitle.olasilik * 100)}</span>}
              <QuoteEvidence items={[...(a.yas?.kanit ?? []), ...(a.kitle?.kanit ?? [])]} />
            </>
          ) : unsure(a.kitle)}
        </Block>
        <Block title="Konu" action={a.konu ? push('topic') : null}>
          {a.konu ? (
            <>
              <b className="font-extrabold">{a.konu.deger}</b>
              <QuoteEvidence items={a.konu.kanit} />
            </>
          ) : unsure(null)}
        </Block>
        <Block title="Temalar">
          {a.temalar.length ? (
            <ul className="space-y-1.5">
              {a.temalar.map((t) => (
                <li key={t.deger}>
                  <b className="font-extrabold">{t.deger}</b>
                  <QuoteEvidence items={t.kanit} first={1} />
                </li>
              ))}
            </ul>
          ) : <span className="text-canvas-muted">Tema listesinden dosyada dayanağı olan tema bulunamadı.</span>}
        </Block>
      </div>

      <Block title="Özet" action={a.ozet ? push('report') : null}>
        {a.ozet ? (
          <ol className="space-y-1.5">
            {a.ozet.cumleler.map((c, i) => (
              <li key={i}>
                <span className="leading-snug">{c.cumle}</span>
                <QuoteEvidence items={[c.kanit]} />
              </li>
            ))}
            {a.ozet.aday > a.ozet.cumleler.length && (
              <li className="text-[11px] text-canvas-muted">
                Dosyadan {a.ozet.aday} doğrulanmış cümle çıktı; {a.ozet.secim === 'zeki' ? 'Zeki AI' : 'dosya boyunca eşit aralıkla'} {a.ozet.cumleler.length} tanesi seçildi.
              </li>
            )}
          </ol>
        ) : unsure(null)}
      </Block>

      <Block title="Yayın ilkesi işaretleri" action={a.ilke.length ? push('redlineNote') : null}>
        {a.ilke.length ? (
          <ul className="space-y-1.5">
            {a.ilke.map((x, i) => (
              <li key={i}>
                <Pill tone="warn">{x.ad}</Pill>
                <QuoteEvidence items={[x.kanit]} />
              </li>
            ))}
            <li className="text-[11px] text-canvas-muted">İşarettir; ilkeye aykırı olup olmadığına siz karar verirsiniz.</li>
          </ul>
        ) : (
          <span className="text-canvas-muted">Okunan bölümlerde işaret bulunmadı. Bu «sorun yok» anlamına gelmez; kontrol sizindir.</span>
        )}
      </Block>

      <Block title="Katalogda konusu yakın kitaplar" action={r.benzer.items.length ? push('overlapNote') : null}>
        {r.benzer.items.length ? (
          <ol className="space-y-1">
            {r.benzer.items.map((x) => (
              <li key={x.kitapId} className="break-words">
                <span className="font-mono text-canvas-muted">{x.sira}.</span> <b className="font-extrabold">{x.ad}</b>
                <span className="text-canvas-muted">{[x.yazar, x.kitaplik].filter(Boolean).map((t) => ` · ${t}`).join('')}</span>
                {x.gerekce.length > 0 && <span className="block text-[11px] text-canvas-muted">{x.gerekce.join(' · ')}</span>}
              </li>
            ))}
          </ol>
        ) : (
          <span className="text-canvas-muted">{r.benzer.not ?? 'Benzer kitap bulunamadı.'}</span>
        )}
        {r.benzer.kaynak && <p className="mt-1 text-[11px] text-canvas-muted">{r.benzer.kaynak}</p>}
      </Block>

      {r.atilan > 0 && <p className="text-[11px] text-canvas-muted">{r.atilan} öneri dosyada alıntısı bulunamadığı için gösterilmedi.</p>}
    </div>
  );
}
