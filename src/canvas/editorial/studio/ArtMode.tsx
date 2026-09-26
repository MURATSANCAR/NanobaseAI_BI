import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Image, Images, Sparkles, Type } from 'lucide-react';
import { studioApi, type StudioArtMode, type StudioJob } from '../../engine';
import { Note, btnGhost, btnPrimary, errText } from '../../admin/ui';
import { Modal } from './dialogs';
import { press } from './shared';

/** Başlangıçta resim seçimi (sözleşme «Başlangıçta resim seçimi»): otomatik (önerilen) / her sayfa / bölüm başları /
 *  resimsiz. Yeni iş formunda seçilir; iş sayfasında gerekçesiyle görünür ve onayla değiştirilir. */

export const ART_MODES: { key: StudioArtMode; title: string; help: string; Icon: typeof Image }[] = [
  { key: 'auto', title: 'Otomatik', help: 'Okur yaşına, türe ve yayınevi kaydına göre karar verilir; gerekçesi gösterilir.', Icon: Sparkles },
  { key: 'every_page', title: 'Her sayfa resimli', help: 'Resimli çocuk kitabı: her sayfada bir resim.', Icon: Images },
  { key: 'chapter', title: 'Yalnız bölüm başlarında', help: 'Her bölümün başında tam sayfa resim, gövde metin.', Icon: Image },
  { key: 'none', title: 'Resimsiz düz metin', help: 'Resim çizilmez; yalnız yerleşim ve dizgi. En hızlısı.', Icon: Type },
];
const TITLE = Object.fromEntries(ART_MODES.map((m) => [m.key, m.title])) as Record<StudioArtMode, string>;

export function ArtModePicker({ value, onChange, disabled }: { value: StudioArtMode; onChange: (m: StudioArtMode) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Resim kullanımı" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {ART_MODES.map(({ key, title, help, Icon }) => {
        const on = value === key;
        return (
          <button key={key} type="button" role="radio" aria-checked={on} disabled={disabled} onClick={() => onChange(key)}
            className={`rounded-2xl border p-2.5 text-left disabled:opacity-50 ${press} ${on ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
            <span className="flex items-center gap-1.5 text-[13px] font-extrabold">
              <Icon className="h-4 w-4 text-canvas-violet" aria-hidden />{title}
              {key === 'auto' && <span className="rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-bold text-canvas-violet">önerilen</span>}
            </span>
            <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{help}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Seçime göre başlatma uyarısının süre cümlesi. */
export function artModeDuration(m: StudioArtMode): string {
  if (m === 'none') return 'Resim çizilmeyecek; yerleşim ve dizgi birkaç dakika sürer.';
  if (m === 'chapter') return 'Bölüm başı resimleri, kapak ve dizgi; süre bölüm sayısına bağlı, bu sırada resim üretimi GPU\'yu kullanır.';
  return 'Sayfa yerleşimi, resimler, kapak ve dizgi yaklaşık 40 dakika sürer; bu sırada resim üretimi GPU\'yu kullanır.';
}

const ILLUSTRATION_TR: Record<string, string> = { HER_SAYFA: 'her sayfa resimli', BOLUM_BASI: 'yalnız bölüm başlarında', YOK: 'resimsiz' };

/** İş sayfasında: mevcut seçim, otomatikse kararın gerekçesi ve onaylı «Değiştir». */
export function ArtModeCard({ job, d }: { job: string; d: StudioJob }) {
  const qc = useQueryClient();
  const current: StudioArtMode = d.job.art_mode ?? 'auto';
  const [open, setOpen] = useState(false);
  const [next, setNext] = useState<StudioArtMode>(current);
  const change = useMutation({
    mutationFn: (m: StudioArtMode) => studioApi.setArtMode(job, m),
    onSuccess: () => { setOpen(false); void qc.invalidateQueries({ queryKey: ['studio', 'job', job] }); },
  });
  const decided = d.profile ? ILLUSTRATION_TR[d.profile.illustration] ?? d.profile.illustration : null;
  const why = d.profile?.art_reason ?? d.profile?.illustration_source ?? null;
  const busy = !!d.busy && !d.busy.error;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 text-[12.5px] leading-snug">
          <div className="font-extrabold">{TITLE[current]}{current === 'auto' && decided ? ` → ${decided}` : ''}</div>
          {current === 'auto' && why && <div className="text-canvas-muted">{why}</div>}
          {current !== 'auto' && <div className="text-canvas-muted">Editörün seçimi; otomatik kararın önüne geçer.</div>}
        </div>
        <button type="button" className={btnGhost} disabled={busy} onClick={() => { setNext(current); change.reset(); setOpen(true); }}
          title={busy ? 'Süren iş bitince değiştirilebilir' : undefined}>Değiştir</button>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Resim kullanımını değiştir"
        description="Sayfa yerleşimi yeni seçime göre yeniden kurulur. Üretilmiş resimler silinmez, «kullanılmayan resimler»e düşer; sayfa düzeni varsa önceki hâli sürüm geçmişinde kalır.">
        <ArtModePicker value={next} onChange={setNext} disabled={change.isPending} />
        {change.error && <div className="mt-2"><Note tone="err">{errText(change.error, 'Değiştirilemedi.')}</Note></div>}
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={() => setOpen(false)}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={next === current || change.isPending} onClick={() => change.mutate(next)}>
            {change.isPending ? 'Yerleşim kuruluyor…' : 'Değiştir ve yeniden kur'}
          </button>
        </div>
      </Modal>
    </div>
  );
}
