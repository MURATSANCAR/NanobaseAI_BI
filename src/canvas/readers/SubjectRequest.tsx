import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Loader2, Search } from 'lucide-react';
import { Loading, Note, Pill, Section, btnPrimary, errText, field, label } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { CHANNELS, fmtDay, readersApi } from './api';
import { ConsentPill, ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';

/** KVKK ilgili kişi başvurusu: bir e-posta/telefona ait bütün okur kayıtları, izinler, girdiği listeler, yüklemeler. */
export default function SubjectRequest() {
  const meta = useMeta();
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const m = useMutation({ mutationFn: () => readersApi.subject({ email: email.trim() || undefined, phone: phone.trim() || undefined }) });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim() || phone.trim()) m.mutate();
  };
  if (meta.isLoading) return <Loading />;
  if (!meta.data?.me.canPersonal) {
    return <Note tone="info">KVKK başvurusu araması kişisel veri yetkisi ister (Yönetim → Yetki → «Okur: kişisel veriyi görme»).</Note>;
  }
  const d = m.data;
  return (
    <Section
      title="KVKK başvurusu"
      help="Başvuru sahibinin e-posta ya da telefonuyla, ona ait bütün okur kayıtlarını, izinlerini, girdiği dışa aktarımları ve yükleme satırlarını bulun. Arama kayda geçer."
    >
      <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <div>
          <label className={label} htmlFor="kvkk-eposta">E-posta</label>
          <input id="kvkk-eposta" type="email" className={field} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
        </div>
        <div>
          <label className={label} htmlFor="kvkk-tel">Cep telefonu</label>
          <input id="kvkk-tel" type="tel" className={field} value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="off" />
        </div>
        <button type="submit" className={btnPrimary} disabled={m.isPending || (!email.trim() && !phone.trim())}>
          {m.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Search aria-hidden className="h-4 w-4" />}Bul
        </button>
      </form>
      {m.error && <Note tone="err">{errText(m.error, 'Aranamadı.')}</Note>}
      {d && d.readers.length === 0 && d.uploads.length === 0 && <EmptyHint title="Bu bilgiyle portalda kayıt yok" why="Başvuru sahibinin e-postasını ya da cep telefonunu tam ve doğru yazdığınızdan emin olun." />}
      {d && (d.readers.length > 0 || d.uploads.length > 0) && (
        <p className="flex items-center gap-1 text-[11.5px] text-canvas-muted">{d.readers.length} okur kaydı · {d.uploads.length} yükleme satırında geçiyor<SqlInfo k={d.kaynaklar} alan="readers[]" label="KVKK başvurusu sonucu" /></p>
      )}
      {d?.readers.map((c) => (
        <Panel key={c.id}>
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`${ROOT}/kisi/${c.id}`} className="font-mono text-[14px] font-extrabold text-canvas-violet hover:underline">{c.id}</Link>
            {c.status !== 'aktif' && <Pill tone="muted">{c.status}</Pill>}
            {c.minor && <Pill tone="warn">18 yaş altı</Pill>}
          </div>
          <p className="mt-1 text-[12px] text-canvas-muted">Kaynaklar: {c.sources.map((s) => s.label).join(', ') || '—'} · ilk kayıt {fmtDay(c.firstSeen)}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {[...CHANNELS, 'kvkk' as const].map((ch) => <ConsentPill key={ch} prefix={meta.data?.channels[ch]} status={c.consents[ch].status} />)}
          </div>
          <h3 className="mt-3 text-[12.5px] font-extrabold">Dışa aktarımlar ve olaylar</h3>
          <ul className="mt-1 space-y-0.5 text-[12px]">
            {c.timeline.filter((t) => t.kind === 'disa_aktarim' || t.kind === 'etkinlik').map((t, i) => <li key={i}>{fmtDay(t.at)} — {t.text}</li>)}
            {!c.timeline.some((t) => t.kind === 'disa_aktarim') && <li className="text-canvas-muted">Hiçbir dışa aktarım listesine girmemiş.</li>}
          </ul>
        </Panel>
      ))}
      {d && d.uploads.length > 0 && (
        <Note tone="info">
          Saklama süresi dolmamış {d.uploads.length} yükleme satırında geçiyor:{' '}
          {d.uploads.map((u) => <Link key={`${u.import}-${u.row}`} className="mr-2 underline" to={`${ROOT}/yuklemeler/${u.import}`}>satır {u.row}</Link>)}
        </Note>
      )}
    </Section>
  );
}
