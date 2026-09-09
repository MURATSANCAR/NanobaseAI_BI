import { useEffect, useState, type ReactNode, type FormEvent } from 'react';
import { ArrowRight, BookOpen, Eye, EyeOff, LockKeyhole, UserRound, LogOut } from 'lucide-react';

const moduleTitle = document.title;
const auth = `${import.meta.env.BASE_URL}auth/`;
// Capture once, before StrictMode mounts effects twice. Remove the invitation
// from the address bar immediately; never persist it or the password.
const initialInvitation = new URLSearchParams(window.location.hash.slice(1)).get('test');
if (initialInvitation) window.history.replaceState(null, '', window.location.pathname + window.location.search);

export function LoginGate({ children }: { children: ReactNode }) {
  const [invitation, setInvitation] = useState(initialInvitation);
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<string | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [test, setTest] = useState(false);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    document.title = user ? moduleTitle : 'Zeki AI | Timaş Yayın Grubu';
  }, [user]);

  useEffect(() => {
    function acceptInvitation() {
      const token = new URLSearchParams(window.location.hash.slice(1)).get('test');
      if (!token) return;
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
      setInvitation(token);
    }
    window.addEventListener('hashchange', acceptInvitation);
    return () => window.removeEventListener('hashchange', acceptInvitation);
  }, []);

  useEffect(() => {
    let active = true;
    if (invitation) { setUser(null); setReady(false); }
    (async () => {
      try {
        const response = await fetch(auth + (invitation ? 'prefill' : 'session'), {
          cache: 'no-store', headers: invitation ? { 'X-Test-Invite': invitation } : {},
        });
        const data = await response.json();
        if (!active) return;
        if (response.ok && invitation) {
          setUsername(data.username); setPassword(data.password); setTest(true);
        } else if (response.ok) setUser(data.username);
        else if (invitation) setError(data.error || 'Test bağlantısının süresi dolmuş. Hesabınızla giriş yapabilirsiniz.');
        else if (response.status === 401) {
          const remembered = await fetch(auth + 'prefill', { cache: 'no-store' });
          if (remembered.ok && active) {
            const saved = await remembered.json();
            if (active) { setUsername(saved.username); setPassword(saved.password); setTest(true); }
          }
        }
      } catch { if (active) setError('Giriş servisine ulaşılamadı. Lütfen sayfayı yenileyin.'); }
      finally { if (active) setReady(true); }
    })();
    return () => { active = false; };
  }, [invitation]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(auth + 'login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
      if (response.status === 429) throw new Error('Çok fazla giriş denemesi yapıldı. Bir dakika sonra tekrar deneyin.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Giriş yapılamadı. Tekrar deneyin.');
      setPassword(''); setUser(data.username);
    } catch (e) { setError(e instanceof Error ? e.message : 'Bağlantı kurulamadı.'); }
    finally { setBusy(false); }
  }

  async function logout() {
    setBusy(true);
    try {
      const response = await fetch(auth + 'logout', { method: 'POST' });
      if (!response.ok) throw new Error('Çıkış yapılamadı.');
      // Reload clears query caches and conversation state between test users.
      window.location.replace(import.meta.env.BASE_URL);
    } catch { setBusy(false); window.alert('Çıkış yapılamadı. Lütfen tekrar deneyin.'); }
  }

  if (user) return <>{children}<button onClick={logout} disabled={busy} title={`${user} · Oturumu kapat`} className="fixed bottom-3 left-3 z-40 flex items-center gap-2 rounded-full border border-line bg-white px-3 py-2 text-xs text-ink-muted shadow-card"><LogOut size={14} />Çıkış</button></>;

  return <main className="login-page">
    <header className="login-brand"><span className="login-mark"><BookOpen size={24} /></span><div><strong>TİMAŞ <span>AI</span></strong><small>KURUMSAL ÇALIŞMA PLATFORMU</small></div></header>
    <div className="login-layout">
      <section className="login-story">
        <span className="login-eyebrow">TİMAŞ YAYIN GRUBU · ZEKİ AI</span>
        <h1>Tek bir giriş.<br /><em>Birlikte daha fazlası.</em></h1>
        <p>Uygulamalarınız ve çalışma alanlarınız tek bir yerde.<br />Zeki AI ile işinize yeni bir bakış kazandırın.</p>
        <div className="login-illustration"><img src={`${import.meta.env.BASE_URL}zeki-ai.gif`} alt="Zeki AI, Timaş yapay zekâ asistanı" /><span>İşinize eşlik eden akıllı yardımcınız.</span></div>
      </section>
      <section className="login-card" aria-labelledby="login-title">
        <span className="login-card-icon"><LockKeyhole size={22} /></span>
        <h2 id="login-title">Hoş geldiniz.</h2>
        <p className="login-intro">Timaş kurumsal çalışma platformuna giriş yapın.</p>
        {test && <div className="login-test"><span />TEST ÇALIŞMA ALANI<p>Giriş bilgileriniz hazır. Başlamak için giriş yapın.</p></div>}
        <form onSubmit={login}>
          <label htmlFor="portal-username">Kullanıcı adı</label>
          <div className="login-field"><UserRound size={18} /><input id="portal-username" autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} disabled={!ready || busy} /></div>
          <label htmlFor="portal-password">Şifre</label>
          <div className="login-field"><LockKeyhole size={18} /><input id="portal-password" type={show ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} disabled={!ready || busy} /><button type="button" aria-label={show ? 'Şifreyi gizle' : 'Şifreyi göster'} onClick={() => setShow(!show)}>{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="login-submit" disabled={!ready || busy} type="submit">{!ready ? 'Hazırlanıyor…' : busy ? 'Giriş yapılıyor…' : 'Sisteme giriş yap'}<ArrowRight size={18} /></button>
        </form>
        <div className="login-footnote"><LockKeyhole size={13} /> Güvenli oturum · Size özel çalışma alanı</div>
      </section>
    </div>
    <footer className="login-footer"><span>Timaş Yayın Grubu</span><span>Zeki AI ile desteklenir.</span></footer>
  </main>;
}
