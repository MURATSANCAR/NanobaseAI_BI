import { useId, useRef, useState, type DragEvent, type ReactNode, type Ref } from 'react';
import { FileUp, Loader2, Lock } from 'lucide-react';
import { Note, errText } from '../admin/ui';
import { usePageAccess } from '../useAdmin';
import { acceptLabel, checkFile, dragDepth, fmtSize, lockReason } from './fileDropRules';

/**
 * Ortak dosya yükleme alanı: tıklayınca dosya seçtirir, üstüne dosya sürüklenince vurgulanır, bırakılınca yükler
 * (telefonda dokununca dosya/kamera seçici açılır). Kabul edilen türler ve boyut sınırı her zaman yazılıdır; uygun
 * olmayan dosya sunucuya gitmeden reddedilir. Yetki (`feature`) yoksa alan gizlenmez: pasif görünür ve hangi yetkinin
 * gerektiğini söyler — kişi yüklemeyi neden yapamadığını anlar. Asıl kapı köprüdedir.
 *
 * İki kullanım:
 *  - `run`: dosya seçilince hemen yükler, sonucu `onDone`'a verir, hatayı altında gösterir.
 *  - `onPick`: yalnız seçer (ek alanlı formlar); seçilen dosya `picked` ile gösterilir, gönderimi form yapar.
 */

export type PickedFile = { name: string; size: number } | null | undefined;

export type FileDropProps<T = unknown> = {
  /** input `accept` biçimi: ".docx,.pdf,image/*". Boşsa her tür. */
  accept?: string;
  /** Bayt; verilirse ekranda yazar ve büyük dosya gönderilmeden reddedilir. */
  maxBytes?: number;
  /** Alanın başlığı («Metin dosyası yükle»). */
  title: ReactNode;
  /** Başlığın altındaki kısa açıklama (ne olacağı). */
  hint?: ReactNode;
  /** Gereken işlem yetkisi (`ozellik:` öneki olmadan, ör. `son-okuma.belge`). */
  feature?: string;
  /** Ekranın kendi yetki bilgisi (ör. köprünün `can*` bayrağı, kayıt sahipliği). false ise alan kilitli görünür:
   *  `feature` verildiyse o yetkinin adı, yoksa `deniedText` yazılır. Gizlemek yerine bunu kullanın. */
  allowed?: boolean;
  deniedText?: string;
  multiple?: boolean;
  capture?: 'environment' | 'user';
  /** Yetki dışı bir nedenle pasif (ör. «önce hesap seçin»); neden `disabledReason` ile yazılır. */
  disabled?: boolean;
  disabledReason?: ReactNode;
  /** lg: sayfanın birincil yükleme alanı; sm: panel içi ikincil yükleme; button: başlık şeridindeki düğme boyu
   *  (yine sürükle-bırak alır, kurallar altında yazar). */
  size?: 'lg' | 'sm' | 'button';
  run?: (file: File) => Promise<T>;
  onDone?: (result: T, file: File) => void | Promise<void>;
  onPick?: (file: File) => void;
  picked?: PickedFile;
  /** `onPick` kullanan ekranın kendi yüklemesi sürüyorsa: alan «Yükleniyor…» gösterir, yeni dosya almaz. */
  busy?: boolean;
  /** Yükleme hatasında sunucu mesajı yoksa yazılacak cümle. */
  errorFallback?: string;
  /** Ekran okuyucu ve testler için alanın adı; verilmezse başlık. */
  ariaLabel?: string;
};

export type FileDropViewProps = {
  inputId: string;
  accept?: string;
  maxBytes?: number;
  title: ReactNode;
  hint?: ReactNode;
  multiple?: boolean;
  capture?: 'environment' | 'user';
  size: 'lg' | 'sm' | 'button';
  /** Yetki yoksa açıklaması; varsa alan kilitli görünür. */
  lockedText?: string | null;
  disabled?: boolean;
  disabledReason?: ReactNode;
  busy?: boolean;
  dragging?: boolean;
  error?: string | null;
  picked?: PickedFile;
  ariaLabel?: string;
  inputRef?: Ref<HTMLInputElement>;
  onFiles?: (files: File[]) => void;
  onDrag?: (ev: 'enter' | 'leave' | 'drop') => void;
};

/** Görünüm: durumları dışarıdan alır, kendi başına hook kullanmaz (vitest'te sunucu tarafı çizimle sınanır). */
export function FileDropView({
  inputId,
  accept,
  maxBytes,
  title,
  hint,
  multiple,
  capture,
  size,
  lockedText,
  disabled,
  disabledReason,
  busy,
  dragging,
  error,
  picked,
  ariaLabel,
  inputRef,
  onFiles,
  onDrag,
}: FileDropViewProps) {
  const locked = !!lockedText;
  const off = locked || !!disabled || !!busy;
  const lg = size === 'lg';
  const asButton = size === 'button';
  const rules = `Kabul edilen: ${acceptLabel(accept)}${maxBytes ? ` · en çok ${fmtSize(maxBytes)}` : ''}`;
  const descId = `${inputId}-desc`;

  const stop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div className={asButton ? 'min-w-0 max-w-full' : 'min-w-0'} data-filedrop="" data-locked={locked ? 'true' : undefined}>
      <label
        htmlFor={inputId}
        data-drag={dragging && !off ? 'true' : undefined}
        aria-disabled={off || undefined}
        onDragEnter={(e) => {
          stop(e);
          onDrag?.('enter');
        }}
        onDragOver={(e) => {
          stop(e);
          e.dataTransfer.dropEffect = off ? 'none' : 'copy';
        }}
        onDragLeave={(e) => {
          stop(e);
          onDrag?.('leave');
        }}
        onDrop={(e) => {
          stop(e);
          onDrag?.('drop');
          if (off) return;
          const files = Array.from(e.dataTransfer.files ?? []);
          if (files.length) onFiles?.(files);
        }}
        className={[
          asButton
            ? 'group inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-xl border border-dashed px-3 py-2 sm:min-h-0'
            : 'group flex min-w-0 items-center rounded-2xl border-2 border-dashed',
          // Vurgu yalnız renkte: kenar ve zemin 150 ms'de döner (durum göstergesi, taşıma yok; renk geçişi → ease).
          // Düğme boyu basılınca 0.97'ye iner (basma geri bildirimi); büyük alan ölçeklenmez.
          asButton
            ? `transition-[border-color,background-color,transform] duration-150 ease-out ${off ? '' : 'active:scale-[0.97] motion-reduce:active:scale-100'}`
            : 'transition-[border-color,background-color] duration-150 ease-[ease]',
          'focus-within:outline-none focus-within:ring-2 focus-within:ring-canvas-violet/40',
          asButton ? '' : lg ? 'gap-3 px-4 py-4 sm:px-5 sm:py-5' : 'gap-2.5 px-3 py-2.5',
          off
            ? 'cursor-not-allowed border-slate-200 bg-slate-50/80'
            : 'cursor-pointer border-canvas-violet/35 bg-white/85 data-[drag=true]:border-canvas-violet data-[drag=true]:bg-canvas-violet/[0.07] [@media(hover:hover)]:hover:border-canvas-violet/60',
        ].join(' ')}
      >
        <span
          aria-hidden
          className={[
            'grid shrink-0 place-items-center rounded-xl',
            // İkon bırakma anında 2 px yükselir: güçlü ease-out, 200 ms; azaltılmış harekette kıpırdamaz.
            'transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] group-data-[drag=true]:-translate-y-0.5',
            'motion-reduce:transition-none motion-reduce:group-data-[drag=true]:translate-y-0',
            asButton ? 'h-5 w-5' : lg ? 'h-11 w-11' : 'h-8 w-8',
            asButton
              ? off
                ? 'text-slate-400'
                : 'text-canvas-violet'
              : off
                ? 'bg-slate-100 text-slate-400'
                : 'bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-sm',
          ].join(' ')}
        >
          {busy ? (
            <Loader2 className={`${lg ? 'h-5 w-5' : 'h-4 w-4'} animate-spin`} />
          ) : locked ? (
            <Lock className={lg ? 'h-5 w-5' : 'h-4 w-4'} />
          ) : (
            <FileUp className={lg ? 'h-5 w-5' : 'h-4 w-4'} />
          )}
        </span>
        {asButton ? (
          <span className={`min-w-0 break-words text-[12.5px] font-extrabold leading-snug ${off && !busy ? 'text-canvas-muted' : 'text-canvas-ink'}`}>
            {busy ? 'Yükleniyor…' : dragging && !off ? 'Bırakın' : title}
          </span>
        ) : (
        <span className="min-w-0 flex-1">
          <span className={`block break-words font-extrabold leading-snug ${lg ? 'text-[14px]' : 'text-[12.5px]'} ${off && !busy ? 'text-canvas-muted' : 'text-canvas-ink'}`}>
            {busy ? 'Yükleniyor…' : dragging && !off ? 'Bırakın, yüklensin' : title}
          </span>
          {hint && !busy && <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">{hint}</span>}
          {!off && (
            <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">
              Dosya seçmek için tıklayın ya da dokunun; bilgisayarda dosyayı buraya sürükleyip bırakabilirsiniz.
            </span>
          )}
          <span id={descId} className="mt-1 block text-[11px] font-semibold leading-snug text-canvas-muted">
            {rules}
          </span>
        </span>
        )}
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={accept || undefined}
          multiple={multiple}
          capture={capture}
          disabled={off}
          aria-label={ariaLabel}
          aria-describedby={descId}
          className="sr-only"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = '';
            if (files.length) onFiles?.(files);
          }}
        />
      </label>
      {asButton && (
        <span id={descId} className="mt-1 block px-1 text-[11px] font-semibold leading-snug text-canvas-muted">
          {hint ? <span className="block font-normal">{hint}</span> : null}
          {rules}
        </span>
      )}
      {locked && (
        <p className="mt-1.5 flex items-start gap-1.5 px-1 text-[11.5px] font-semibold leading-snug text-amber-800" role="note">
          {lockedText}
        </p>
      )}
      {!locked && disabled && disabledReason && <p className="mt-1.5 px-1 text-[11.5px] leading-snug text-canvas-muted">{disabledReason}</p>}
      {picked && !busy && (
        <p className="mt-1.5 min-w-0 truncate px-1 text-[11.5px] leading-snug">
          <span className="text-canvas-muted">Seçilen: </span>
          <span className="font-semibold">{picked.name}</span>
          <span className="font-mono tabular-nums text-canvas-muted"> · {fmtSize(picked.size)}</span>
        </p>
      )}
      {error && (
        <div className="mt-2" role="alert">
          <Note tone="err">{error}</Note>
        </div>
      )}
    </div>
  );
}

/** Kişinin işlem yetkisi var mı. Yetki henüz bilinmiyorsa açık say: alan bir an kilitli görünüp açılmasın; köprü zaten sınar. */
export function useFeatureAllowed(feature: string | undefined): boolean {
  const access = usePageAccess();
  if (!feature || access === null || access === 'all') return true;
  return access.has(`ozellik:${feature}`);
}

export function FileDrop<T = unknown>({
  accept,
  maxBytes,
  title,
  hint,
  feature,
  allowed: allowedProp,
  deniedText,
  multiple,
  capture,
  disabled,
  disabledReason,
  size = 'lg',
  run,
  onDone,
  onPick,
  picked,
  busy: busyProp,
  errorFallback = 'Dosya yüklenemedi.',
  ariaLabel,
}: FileDropProps<T>) {
  const inputId = useId();
  const allowed = useFeatureAllowed(feature);
  const [depth, setDepth] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const take = async (all: File[]) => {
    const files = multiple ? all : all.slice(0, 1);
    const extra = !multiple && all.length > 1 ? ` Yalnız ilk dosya alındı («${all[0].name}»); bu alan tek dosya kabul eder.` : '';
    const bad = files.map((f) => checkFile(f, accept, maxBytes)).filter((x): x is string => !!x);
    const good = files.filter((f) => !checkFile(f, accept, maxBytes));
    setError(bad.length ? bad.join(' ') + extra : extra.trim() || null);
    if (!good.length) return;
    if (!run) {
      good.forEach((f) => onPick?.(f));
      return;
    }
    setBusy(true);
    try {
      for (const f of good) {
        const r = await run(f);
        await onDone?.(r, f);
      }
    } catch (e) {
      setError(errText(e, errorFallback));
    } finally {
      setBusy(false);
    }
  };

  return (
    <FileDropView
      inputId={inputId}
      inputRef={input}
      accept={accept}
      maxBytes={maxBytes}
      title={title}
      hint={hint}
      multiple={multiple}
      capture={capture}
      size={size}
      lockedText={lockReason({ feature, featureAllowed: allowed, allowed: allowedProp, deniedText })}
      disabled={disabled}
      disabledReason={disabledReason}
      busy={busy || !!busyProp}
      dragging={depth > 0}
      error={error}
      picked={picked}
      ariaLabel={ariaLabel ?? (typeof title === 'string' ? title : undefined)}
      onDrag={(ev) => setDepth((d) => dragDepth(d, ev))}
      onFiles={(fs) => void take(fs)}
    />
  );
}

/** Başlık şeridindeki küçük yükleme (eski `FilePick` imzası; İK, ihale ve risk ekranları). Düğme boyundadır ama
 *  yine sürükle-bırak alır, türleri/sınırı altında yazar, yetki yoksa kilitli görünür. Dosyayı seçip çağırana verir. */
export function FilePick({
  label,
  accept,
  disabled,
  disabledReason,
  onPick,
  feature,
  allowed,
  deniedText,
  maxBytes,
  hint,
  busy,
  capture,
}: {
  label: string;
  accept: string;
  disabled?: boolean;
  disabledReason?: ReactNode;
  onPick: (f: File) => void;
  feature?: string;
  allowed?: boolean;
  deniedText?: string;
  maxBytes?: number;
  hint?: ReactNode;
  busy?: boolean;
  capture?: 'environment' | 'user';
}) {
  return (
    <FileDrop
      size="button"
      busy={busy}
      capture={capture}
      title={label}
      hint={hint}
      accept={accept}
      maxBytes={maxBytes}
      feature={feature}
      allowed={allowed}
      deniedText={deniedText}
      disabled={disabled}
      disabledReason={disabledReason}
      onPick={onPick}
    />
  );
}

export default FileDrop;
