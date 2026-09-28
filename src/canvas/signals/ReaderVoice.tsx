import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Printer } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { btnGhost, errText } from '../admin/ui';
import { voiceApi, type VoiceLabel, type VoiceSource, type VoiceTopic } from './api';
import { topicHow } from './format';

/** Okur sesi (öneri 15): tek ortak sınıflayıcının konusu. Etiket gece yazılır (kural, iade nedeni ya da Zeki AI kapalı
 *  küme + eşik); ekran yalnız okur. Model seçtiyse çipte «Zeki AI» yazar; eşik altı «Belirsiz». */

const TOPIC_CLASS: Record<VoiceTopic, string> = {
  kargo: 'bg-sky-50 text-sky-800 ring-sky-200',
  baski: 'bg-red-50 text-red-800 ring-red-200',
  icerik: 'bg-violet-50 text-violet-800 ring-violet-200',
  fiyat: 'bg-amber-50 text-amber-900 ring-amber-200',
  ovgu: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  diger: 'bg-slate-100 text-slate-700 ring-slate-200',
};

export function useVoiceLabels(kaynak: VoiceSource, enabled = true) {
  return useQuery({
    queryKey: ['okur-sesi', 'labels', kaynak],
    queryFn: () => voiceApi.labels(kaynak),
    enabled: ENGINE_ENABLED && enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function TopicChip({ label }: { label?: VoiceLabel }) {
  if (!label) return null;
  const cls = label.konu ? TOPIC_CLASS[label.konu] : 'bg-white text-canvas-muted ring-slate-200';
  const how = topicHow(label);
  return (
    <span
      title={`Okur sesi konusu · ${how}${label.olasilik != null ? ` · olasılık %${Math.round(label.olasilik * 100)}` : ''}`}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ring-1 ring-inset ${cls}`}
    >
      {label.konuAdi}
      {label.yontem === 'zeki' && <span className="font-semibold opacity-70">· Zeki AI</span>}
    </span>
  );
}

/** Kaynak × konu özeti ve baskı/cilt hatası kümesi uyarıları. `sources`: bu ekranın kaynakları (özet satırı). */
export function ReaderVoicePanel({ sources }: { sources: VoiceSource[] }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['okur-sesi', 'summary'], queryFn: voiceApi.summary, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000, retry: false });
  const seen = useMutation({
    mutationFn: (key: string) => voiceApi.seen(key),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okur-sesi', 'summary'] }); toast.success('Uyarı görüldü olarak işaretlendi.'); },
    onError: (e) => toast.error(errText(e, 'İşaretlenemedi.') ?? ''),
  });
  const s = q.data;
  if (!s) return null;
  const rows = sources.map((k) => ({ k, t: s.kaynakKonu[k] })).filter((r) => r.t);
  const open = s.uyarilar.filter((a) => a.durum !== 'kapandi');
  const topics = Object.keys(s.konular) as VoiceTopic[];
  if (!rows.length && !open.length) return null;
  return (
    <section aria-label="Okur sesi" className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Okur sesi · son {s.gun} gün<SqlInfo k={s.kaynaklar} alan="kaynakKonu" label="Okur sesi: kaynak × konu" /></h2>
        <span className="text-[11px] text-canvas-muted">Konu kuralla ya da Zeki AI ile seçilir; metin maskeli, saklanmaz.</span>
      </div>
      {rows.map(({ k, t }) => (
        <div key={k} className="mt-2">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{s.kaynakAdlari[k]}</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {topics.filter((tp) => (t?.[tp] ?? 0) > 0).map((tp) => (
              <span key={tp} className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-bold ring-1 ring-inset ${TOPIC_CLASS[tp]}`}>
                {s.konular[tp]} <span className="font-mono tabular-nums">{t?.[tp]}</span>
              </span>
            ))}
            {(t?.belirsiz ?? 0) > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md bg-white px-1.5 py-0.5 text-[11.5px] font-bold text-canvas-muted ring-1 ring-inset ring-slate-200">
                Belirsiz <span className="font-mono tabular-nums">{t?.belirsiz}</span>
              </span>
            )}
          </div>
        </div>
      ))}
      {open.length > 0 && (
        <div className="mt-3">
          <div className="flex items-center gap-1.5 text-[12.5px] font-extrabold text-red-800">
            <Printer aria-hidden className="h-4 w-4" />
            Baskı / cilt hatası kümesi (üretime iç uyarı)
            <SqlInfo k={s.kaynaklar} alan="uyarilar" label="Baskı / cilt hatası kümesi" />
          </div>
          <p className="mt-0.5 text-[11px] leading-snug text-canvas-muted">
            Son {s.ayarlar.defectDays} günde aynı kitapta en az {s.ayarlar.defectMin} okur metni. {s.ayarlar.iceAlici ? 'Üretim alıcılarına iç e-posta gider.' : 'İç alıcı tanımlı değil: yalnız ekranda.'}
          </p>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {open.map((a) => (
              <li key={a.anahtar} className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl border border-red-100 bg-red-50/60 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="break-words text-[12.5px] font-semibold leading-snug">{a.ad || a.anahtar}</div>
                  <div className="text-[11px] text-canvas-muted">
                    <span className="font-mono">{a.anahtar}</span> · {a.sayi} kayıt · {Object.entries(a.kaynaklar).map(([k, n]) => `${s.kaynakAdlari[k as VoiceSource] ?? k} ${n}`).join(', ')}
                    {a.durum === 'goruldu' && a.goren ? ` · ${a.goren} gördü` : ''}
                  </div>
                </div>
                {s.uretim && a.durum === 'acik' && (
                  <button type="button" className={btnGhost} disabled={seen.isPending} onClick={() => seen.mutate(a.anahtar)}>
                    <Check aria-hidden className="h-4 w-4" />Görüldü
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
