import { useEffect, useState } from 'react';
import { ENGINE_BASE, clearAuthBlock } from '../engine';

/**
 * Oturum kapısı. Motor 401 döndüğünde çıkar: veri gelmemesinin sebebi
 * yanlış sorgu değil, düşmüş oturumdur. Giriş `/timas/auth/login` ucuna
 * Basic başlıkla gider; çerezi sunucu yazar (HttpOnly), uygulama saklamaz.
 */
export default function SessionGate({ onDone }: { onDone: () => void }) {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [prefilled, setPrefilled] = useState(false);

  // Sunucu bir demo kullanıcısı tanımlamışsa alanları o doldurur.
  // Parola uygulamada gömülü değildir; sunucudan gelir ve süresi doludur.
  useEffect(() => {
    let alive = true;
    fetch(`${ENGINE_BASE}/auth/prefill`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((v: { username?: string; password?: string } | null) => {
        if (!alive || !v?.username) return;
        setUser(v.username);
        if (v.password) setPass(v.password);
        setPrefilled(true);
      })
      .catch(() => {
        /* tanımlı değilse alanlar boş kalır */
      });
    return () => {
      alive = false;
    };
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !pass) return;
    setBusy(true);
    setErr(null);
    try {
      // Uç JSON gövde bekliyor; Basic başlık 400 döner.
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
      setErr(detail?.error ?? (res.status === 401 ? 'Kullanıcı adı veya parola hatalı.' : `Giriş yapılamadı (${res.status}).`));
    } catch {
      setErr('Sunucuya ulaşılamadı.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/20 backdrop-blur-[2px]">
      <form onSubmit={submit} className="glass-panel w-[360px] rounded-3xl p-6 shadow-canvas-card">
        <div className="text-[11px] font-bold uppercase tracking-[.18em] text-muted">Timaş Yayınları</div>
        <h2 className="mt-1 text-lg font-extrabold tracking-tight text-ink">Oturum kapandı</h2>
        <p className="mt-1.5 text-[12px] leading-snug text-muted">
          Devam etmek için giriş yapın.
        </p>

        <label className="mt-4 block text-[11px] font-bold text-muted" htmlFor="kullanici">
          Kullanıcı adı
        </label>
        <input
          id="kullanici"
          value={user}
          onChange={(e) => setUser(e.target.value)}
          autoComplete="username"
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[13px] font-semibold text-ink outline-none focus:border-violet"
        />

        <label className="mt-3 block text-[11px] font-bold text-muted" htmlFor="parola">
          Parola
        </label>
        <input
          id="parola"
          type="password"
          value={pass}
          onChange={(e) => setPass(e.target.value)}
          autoComplete="current-password"
          className="mt-1 w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[13px] font-semibold text-ink outline-none focus:border-violet"
        />

        {prefilled && (
          <div className="mt-3 rounded-xl bg-canvas-violet/10 px-3 py-2 text-[11.5px] font-semibold text-canvas-violet">
            Demo kullanıcısı dolduruldu. Giriş yap deyip devam edebilirsiniz.
          </div>
        )}

        {err && <div className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700">{err}</div>}

        <button
          type="submit"
          disabled={busy || !user || !pass}
          className="mt-4 w-full rounded-xl bg-gradient-to-r from-coral to-violet px-4 py-2.5 text-[13px] font-extrabold text-white shadow-md transition disabled:opacity-60"
        >
          {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
        </button>
      </form>
    </div>
  );
}
