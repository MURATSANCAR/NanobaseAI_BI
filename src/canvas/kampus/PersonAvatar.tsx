import { photoUrl } from '../engine';

const TONES = [
  'bg-amber-100 text-amber-800 ring-amber-300',
  'bg-sky-100 text-sky-800 ring-sky-300',
  'bg-emerald-100 text-emerald-800 ring-emerald-300',
  'bg-violet/10 text-violet ring-violet/30',
  'bg-rose-100 text-rose-800 ring-rose-300',
  'bg-slate-200 text-slate-700 ring-slate-300',
];

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toLocaleUpperCase('tr'))
    .join('') || '?';

/** Aynı kişi her yerde aynı renkte görünsün: renk hesap adından türetilir. */
const toneOf = (key: string) => TONES[[...key].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % TONES.length];

/** Kişinin fotoğrafı; yoksa baş harfleri. */
export default function PersonAvatar({
  username,
  name,
  photoVersion,
  src,
  className = 'h-9 w-9 rounded-xl text-xs',
}: {
  username: string;
  name: string;
  photoVersion: number | null;
  /** Yüklenmeden önceki yerel önizleme. */
  src?: string | null;
  className?: string;
}) {
  const url = src ?? photoUrl(username, photoVersion);
  if (url) {
    return <img src={url} alt="" className={`shrink-0 object-cover ring-1 ring-slate-200 ${className}`} />;
  }
  return (
    <div aria-hidden className={`flex shrink-0 items-center justify-center font-bold ring-1 ${toneOf(username || name)} ${className}`}>
      {initials(name)}
    </div>
  );
}
