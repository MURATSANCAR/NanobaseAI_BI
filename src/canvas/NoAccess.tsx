import { ShieldCheck } from 'lucide-react';

/** Yetkisi olmayan kişiye gösterilen tema uyumlu görsel. Yönetim, Veri Sözlüğü ve
 *  Onaylar ekranları menüden gizlenir; adrese elle gidilirse bu kart çıkar. */
export default function NoAccess({
  user,
  title = 'Bu bölüm yöneticilere özel',
  hint,
}: {
  user?: string;
  title?: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center px-4 py-16 text-center motion-safe:animate-scale-in sm:py-20">
      {/* Yumuşak mor halede kalkan: kanvasın cam + violet diliyle aynı. */}
      <div className="relative mb-5">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 rounded-full bg-canvas-violet/25 blur-2xl"
        />
        <div className="grid h-20 w-20 place-items-center rounded-[26px] bg-white/70 shadow-glass-float ring-1 ring-white/60 backdrop-blur">
          <div className="grid h-14 w-14 place-items-center rounded-2xl bg-canvas-violet/10 text-canvas-violet">
            <ShieldCheck className="h-7 w-7" strokeWidth={2.2} />
          </div>
        </div>
      </div>
      <h2 className="text-lg font-extrabold tracking-tight text-canvas-ink sm:text-xl">{title}</h2>
      <p className="mt-2 max-w-sm text-[12.5px] leading-relaxed text-canvas-muted">
        {hint ?? (
          <>
            {user ? <span className="font-semibold text-canvas-ink">{user}</span> : 'Hesabınız'} bu bölümü açma
            yetkisine sahip değil. Erişim, Active&nbsp;Directory’deki yönetici grubunun üyelerine tanımlıdır; bir
            yönetici sizi bu gruba ekleyebilir.
          </>
        )}
      </p>
    </div>
  );
}
