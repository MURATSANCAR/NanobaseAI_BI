import { useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, Plus, Trash2, X } from 'lucide-react';
import { btnGhost, field } from '../admin/ui';

/** Sıralı kart listesi düzenleyicisinin ortak parçaları: anket şablonu soruları (M58) ve değerlendirme formu bölümleri (M56).
 *  Kayıt anahtarı (`key`) ekranda düzenlenmez: var olan maddede aynen korunur (sonuçlar anahtarla gruplanır), yeni maddede
 *  kaydederken metinden üretilir. */

let seq = 0;
/** Yeni kart ve satırlar için oturumluk kimlik (React anahtarı); sunucuya gitmez. */
export const localId = () => `yeni-${++seq}`;

/** Satır: seçenek ya da yetkinlik maddesi. `key`/`orig` yalnız sunucudan gelen maddede dolu. */
export type Row = { id: string; text: string; key?: string | null; orig?: Record<string, unknown> | null };

/** Metin sadeleştirme: sunucunun `clean` işleviyle aynı (boşluklar teke iner, baş/son kırpılır). */
export const tidy = (s: string) => s.split(/\s+/).filter(Boolean).join(' ');

export function moveAt<T>(list: T[], i: number, dir: -1 | 1): T[] {
  const j = i + dir;
  if (j < 0 || j >= list.length) return list;
  const next = list.slice();
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

const TR: Record<string, string> = { ç: 'c', ğ: 'g', ı: 'i', ö: 'o', ş: 's', ü: 'u', â: 'a', î: 'i', û: 'u' };

/** Yeni madde için kayıt anahtarı: başlangıç şablonlarındaki gibi kısa, küçük harf, a-z0-9_ (ör. «is_yuku»).
 *  Metnin ilk üç kelimesinden üretilir; `taken` içindekilerle çakışırsa _2, _3… eklenir ve üretilen anahtar `taken`a yazılır. */
export function makeKey(text: string, fallback: string, taken: Set<string>): string {
  const words = text
    .toLocaleLowerCase('tr-TR')
    .replace(/[çğıöşüâîû]/g, (c) => TR[c] ?? c)
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .slice(0, 3);
  let base = '';
  for (const w of words) {
    const next = base ? `${base}_${w}` : w;
    if (next.length > 24) break;
    base = next;
  }
  if (!base) base = (words[0] ?? '').slice(0, 24) || fallback;
  let key = base;
  for (let n = 2; taken.has(key); n++) key = `${base}_${n}`;
  taken.add(key);
  return key;
}

/** Kare simge düğmesi; dokunma alanı 40 px. */
export const iconBtn =
  'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100';

/** Tek kart: başlık satırında sıra ve ↑ ↓ sil düğmeleri; altında düzenleme alanları ve kartın eksikleri. */
export function ItemCard({ label, index, total, problems, onMove, onRemove, children }: {
  /** Ör. «3. soru» */
  label: string;
  index: number;
  total: number;
  problems: string[];
  onMove: (dir: -1 | 1) => void;
  onRemove: () => void;
  children: ReactNode;
}) {
  return (
    <li className="flex min-w-0 flex-col gap-2.5 rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex items-center gap-1.5">
        <span className="min-w-0 flex-1 text-[13px] font-extrabold">{label}</span>
        <button type="button" className={iconBtn} disabled={index === 0} onClick={() => onMove(-1)} aria-label={`Yukarı taşı (${label})`} title="Yukarı taşı">
          <ArrowUp aria-hidden className="h-4 w-4" />
        </button>
        <button type="button" className={iconBtn} disabled={index === total - 1} onClick={() => onMove(1)} aria-label={`Aşağı taşı (${label})`} title="Aşağı taşı">
          <ArrowDown aria-hidden className="h-4 w-4" />
        </button>
        <button type="button" className={`${iconBtn} hover:!bg-red-50 hover:text-red-700`} onClick={onRemove} aria-label={`Sil (${label})`} title="Sil">
          <Trash2 aria-hidden className="h-4 w-4" />
        </button>
      </div>
      {children}
      {problems.length > 0 && (
        <ul className="flex flex-col gap-0.5 rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold leading-snug text-amber-800">
          {problems.map((p, i) => <li key={i}>{p}</li>)}
        </ul>
      )}
    </li>
  );
}

/** Metin satırları listesi (seçenekler, yetkinlik maddeleri): her satır bir kutu ve kaldır düğmesi; Enter yeni satır açar. */
export function TextRows({ rows, onChange, noun, addLabel, placeholder, maxLength }: {
  rows: Row[];
  onChange: (rows: Row[]) => void;
  /** Ekran okuyucu için satır adı: «seçenek», «madde». */
  noun: string;
  addLabel: string;
  placeholder: string;
  maxLength: number;
}) {
  // Yalnız «ekle» ile açılan satıra odak verilir; kart yeniden açıldığında odak çalınmaz.
  const [focusId, setFocusId] = useState<string | null>(null);
  const add = () => {
    const id = localId();
    setFocusId(id);
    onChange([...rows, { id, text: '' }]);
  };
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((r, i) => (
        <div key={r.id} className="flex min-w-0 items-center gap-1.5">
          <input
            className={`${field} min-h-10 min-w-0 flex-1`}
            value={r.text}
            maxLength={maxLength}
            placeholder={placeholder}
            aria-label={`${i + 1}. ${noun}`}
            autoFocus={r.id === focusId}
            onChange={(e) => onChange(rows.map((x) => (x.id === r.id ? { ...x, text: e.target.value } : x)))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                e.preventDefault();
                add();
              }
            }}
          />
          <button type="button" className={iconBtn} onClick={() => onChange(rows.filter((x) => x.id !== r.id))} aria-label={`Kaldır (${i + 1}. ${noun})`} title="Kaldır">
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
      ))}
      <div>
        <button type="button" className={btnGhost} onClick={add}>
          <Plus aria-hidden className="h-4 w-4" />
          {addLabel}
        </button>
      </div>
    </div>
  );
}

/** Kaydet düğmesinin yanında tek satırlık engel açıklaması. */
export function BlockedReason({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="text-[12px] font-semibold leading-snug text-amber-800 sm:text-right">
      {children}
    </p>
  );
}
