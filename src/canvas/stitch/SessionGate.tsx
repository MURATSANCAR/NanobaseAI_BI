import { useEffect, useState } from 'react';
import { ArrowRight, Eye, EyeOff, Loader2, Sparkles } from 'lucide-react';
import { ENGINE_BASE, clearAuthBlock } from '../engine';
import zekiGif from '@/assets/zeki-ai.gif';

/**
 * Oturum kapısı = giriş ekranı. Motor 401 döndüğünde çıkar: veri gelmemesinin
 * sebebi yanlış sorgu değil, düşmüş oturumdur. Giriş `/timas/auth/login` ucuna
 * gider ve Timaş Active Directory'de doğrulanır; çerezi sunucu yazar (HttpOnly), uygulama saklamaz.
 *
 * Tasarım kanvas diliyle aynı: mesh gradyan + nokta ızgara zemin, yüzen ışık
 * lekeleri, cam panel, mercan→mor vurgu, solda ZEKİ kahramanı.
 */
export default function SessionGate({ onDone }: { onDone: () => void }) {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Girişte kart ve kahraman yumuşakça belirsin diye bir kare sonra işaretlenir.
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !pass) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${ENGINE_BASE}/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass }),
      });
      if (res.ok) {
        setPass('');
        clearAuthBlock();
        onDone();
        return;
      }
      const detail = (await res.json().catch(() => null)) as { error?: string } | null;
      setErr(
        detail?.error ??
          (res.status === 401
            ? 'Kullanıcı adı veya şifre doğru değil.'
            : res.status === 429
              ? 'Çok fazla deneme yapıldı. Bir dakika sonra tekrar deneyin.'
              : `Giriş yapılamadı (${res.status}).`),
      );
    } catch {
      setErr('Sunucuya ulaşılamadı.');
    } finally {
      setBusy(false);
    }
  };

  const inMod = mounted ? 'lg-in' : '';

  return (
    <div className="bg-mesh-canvas cv-scroll fixed inset-0 z-[90] overflow-y-auto">
      {/* Nokta ızgara + yüzen ışık lekeleri (dekor, hareketi azaltınca durur) */}
      <div className="dot-grid pointer-events-none absolute inset-0" />
      <div className="lg-orb lg-drift -left-24 top-[-10%] h-72 w-72 bg-coral/25" />
      <div className="lg-orb lg-drift-2 right-[-8%] top-[8%] h-80 w-80 bg-violet/25" />
      <div className="lg-orb lg-drift-3 bottom-[-12%] left-1/3 h-72 w-72 bg-mintSuccess/20" />

      <div className="relative flex min-h-full items-center justify-center px-4 py-8 sm:px-6">
        <div className="grid w-full max-w-[940px] items-center gap-6 lg:grid-cols-[1.15fr_1fr] lg:items-stretch lg:gap-10">
          {/* ── Kahraman: alanı komple kaplayan ZEKİ görseli ── */}
          <div className={`lg-rise ${inMod} flex w-full flex-col items-center lg:items-stretch`}>
            <div className="inline-flex items-center gap-1.5 self-center rounded-full border border-white/70 bg-white/70 px-3 py-1 text-[11px] font-bold uppercase tracking-[.18em] text-canvas-violet shadow-glass-float backdrop-blur lg:self-start">
              <Sparkles className="h-3.5 w-3.5" /> Timaş Yayınları · Kurumsal Zekâ
            </div>
            {/* Görsel kendi çerçevesini doldurur; marka (ZEKİ AI) görselin içinde. */}
            <div className="relative mt-4 w-full flex-1 overflow-hidden rounded-3xl border border-white/80 bg-[#f6f0ea] shadow-canvas-card">
              <img
                src={zekiGif}
                alt="ZEKİ AI — Timaş Kurumsal Asistanı"
                className="block h-full w-full object-contain"
              />
            </div>
          </div>

          {/* ── Giriş kartı ── */}
          <form
            onSubmit={submit}
            className={`glass-panel lg-rise lg-delay ${inMod} w-full rounded-3xl p-5 shadow-canvas-card sm:p-7`}
          >
            <div className={`lg-stagger ${inMod}`}>
              <div>
                <h2 className="text-xl font-extrabold tracking-tight text-ink">Tekrar hoş geldiniz</h2>
                <p className="mt-1 text-[12.5px] leading-snug text-muted">Bilgisayarınıza girdiğiniz Timaş kullanıcı adı ve şifresini kullanın.</p>
              </div>

              <div className="mt-5">
                <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wide text-muted" htmlFor="kullanici">
                  Kullanıcı adı
                </label>
                <input
                  id="kullanici"
                  value={user}
                  onChange={(e) => setUser(e.target.value)}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="kullanici.adi"
                  className="min-h-11 w-full rounded-xl border border-slate-200 bg-white/90 px-3.5 py-2.5 text-base font-semibold text-ink outline-none transition focus:border-violet focus:ring-2 focus:ring-violet/25 sm:text-[13.5px]"
                />
              </div>

              <div className="mt-3.5">
                <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-wide text-muted" htmlFor="parola">
                  Şifre
                </label>
                <div className="relative">
                  <input
                    id="parola"
                    type={show ? 'text' : 'password'}
                    value={pass}
                    onChange={(e) => setPass(e.target.value)}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    className="min-h-11 w-full rounded-xl border border-slate-200 bg-white/90 px-3.5 py-2.5 pr-11 text-base font-semibold text-ink outline-none transition focus:border-violet focus:ring-2 focus:ring-violet/25 sm:text-[13.5px]"
                  />
                  <button
                    type="button"
                    onClick={() => setShow((v) => !v)}
                    aria-label={show ? 'Şifreyi gizle' : 'Şifreyi göster'}
                    className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition hover:bg-white hover:text-ink"
                  >
                    {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {err && (
                <div className="mt-3.5 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700">
                  {err}
                </div>
              )}

              <button
                type="submit"
                disabled={busy || !user || !pass}
                className="mt-5 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-coral to-violet px-4 py-3 text-[15px] font-extrabold text-white shadow-[0_12px_30px_-8px_rgba(255,107,74,0.5)] transition-transform duration-150 ease-out hover:brightness-[1.03] active:scale-[0.97] disabled:opacity-60 disabled:active:scale-100 sm:text-[14px]"
              >
                {busy ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Giriş yapılıyor…
                  </>
                ) : (
                  <>
                    Giriş yap <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>

              <p className="mt-4 text-center text-[11px] font-medium text-muted/80">
                Timaş Yayın Grubu · Kurumsal Zekâ · Yalnız yetkili kullanıcılar
              </p>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
