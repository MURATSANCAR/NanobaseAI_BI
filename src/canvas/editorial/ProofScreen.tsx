import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
<<<<<<< HEAD
import { BookOpen, Check, Loader2, PenLine, X } from 'lucide-react';
import { ENGINE_ENABLED, deskApi, proofingApi, readableBooksApi, type DeskCheck, type DeskFile, type ProofState } from '../engine';
=======
import { Check, Loader2, PenLine, X } from 'lucide-react';
import { ENGINE_ENABLED, deskApi, proofingApi, type DeskCheck, type DeskFile, type ProofState } from '../engine';
>>>>>>> 709ef8f883bac642f67d70bac686e69a19f8353e
import { Loading, Note, Pill, btn, btnGhost, errText, field, label, nf } from '../admin/ui';
import { dateTime, num } from '../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from './kit';
import { UploadButton, WorkList, fmtBytes, useWorks } from './WorkPicker';
import { ProofFindings, seriousCount } from './ProofFindings';

/** M5 Son Okuma ve Yayın Onayı. Prova PDF'i yüklenir; sayfa, ebat, gömülü yazı tipi, renk uzayı, ISBN ve
 *  forma dosyadan ölçülür. Elle işaretlenen maddeler ve adı yazılı imzacılar tamamlanınca onay oluşur.
 *  İmza, o PDF'in SHA-256'sına atılır: yeni prova imzaları sıfırlar. */

function Report({ f }: { f: DeskFile }) {
  const r = f.report;
  const rows: Array<[string, string]> = [
    ['Sayfa', `${nf.format(r.pages ?? 0)} · ${num(r.signatures16, 2)} forma`],
    ['Ebat', Object.keys(r.sizes || {}).join(', ') || '—'],
    ['Yazı tipi', `${nf.format((r.fonts || []).length)} tip${(r.unembeddedFonts || []).length ? `, ${(r.unembeddedFonts || []).length} gömülü değil` : ', hepsi gömülü'}`],
    ['Görsel', `${nf.format(r.images ?? 0)}${r.rgbImages ? ` · ${nf.format(r.rgbImages)} RGB` : ''}`],
  ];
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <a href={deskApi.fileUrl(f.id)} className="min-w-0 truncate text-[12.5px] font-extrabold text-canvas-violet underline">
          v{f.version} · {f.filename}
        </a>
        <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">{fmtBytes(f.bytes)}</span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-[11px] leading-snug text-canvas-muted">{k}</dt>
            <dd className="font-semibold leading-snug">{v}</dd>
          </div>
        ))}
      </dl>
      {r.versus && (
        <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
          v{r.versus.version} ile farkı: sayfa sayısı {r.versus.pageDelta > 0 ? `+${r.versus.pageDelta}` : nf.format(r.versus.pageDelta)}
          {r.versus.changedPages.length ? `, metni değişen ${nf.format(r.versus.changedPages.length)} sayfa (ilk: ${r.versus.changedPages.slice(0, 8).join(', ')})` : ', ortak sayfaların metni aynı'}
        </p>
      )}
      <p className="mt-1.5 break-all font-mono text-[10.5px] leading-snug text-canvas-muted">SHA-256 {f.sha256}</p>
    </div>
  );
}

function CheckRow({ c, onSet, busy }: { c: DeskCheck; onSet: (passed: boolean | null) => void; busy: boolean }) {
  const tone = c.passed === true ? 'ok' : c.passed === false ? 'err' : 'muted';
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="break-words font-semibold leading-snug">{c.label}</span>
          {c.auto ? <Pill tone="violet">dosyadan</Pill> : null}
          <Pill tone={tone}>{c.passed === true ? 'Geçti' : c.passed === false ? 'Geçmedi' : 'Bekliyor'}</Pill>
        </div>
        {c.evidence && <p className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{c.evidence}</p>}
        {c.checkedBy && <p className="mt-0.5 text-[11px] text-canvas-muted">{c.checkedBy} · {dateTime(c.checkedAt)}</p>}
      </div>
      {!c.auto && (
        <div className="flex shrink-0 gap-1">
          <button type="button" disabled={busy} aria-label={`${c.label}: geçti`} onClick={() => onSet(c.passed === true ? null : true)} className={`${btn} px-2.5 ${c.passed === true ? 'bg-canvas-mint/25 text-emerald-700' : 'bg-slate-100 text-canvas-ink'}`}>
            <Check aria-hidden className="h-4 w-4" />
          </button>
          <button type="button" disabled={busy} aria-label={`${c.label}: geçmedi`} onClick={() => onSet(c.passed === false ? null : false)} className={`${btn} px-2.5 ${c.passed === false ? 'bg-canvas-coral/20 text-red-700' : 'bg-slate-100 text-canvas-ink'}`}>
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
      )}
    </li>
  );
}

function Signers({ s, onChanged }: { s: ProofState; onChanged: () => void }) {
  const [role, setRole] = useState('');
  const [username, setUsername] = useState('');
  type Signer = { role: string; username: string; display?: string };
  const list: Signer[] = s.signatures.map((x) => ({ role: x.role, username: x.username, display: x.display || undefined }));
  const save = useMutation({ mutationFn: (next: Signer[]) => deskApi.setSigners(s.work.id, next), onSuccess: onChanged });
  const sign = useMutation({ mutationFn: () => deskApi.sign(s.work.id), onSuccess: onChanged });
  const mine = s.signatures.find((x) => x.mine);
  const err = errText(save.error || sign.error, 'İmza kaydedilemedi.');

  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Yayın onay imzaları</h2>
      <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Her imza, o anki prova dosyasının SHA-256 özetine atılır. Yeni prova yüklenince imzalar sıfırlanır. Bu bir e-imza değildir; portal oturumundaki AD hesabının kaydıdır.
      </p>
      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
      <ul className="mt-2 space-y-1.5">
        {s.signatures.map((x) => (
          <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <span className="min-w-0">
              <span className="block break-words font-semibold leading-snug">{x.role}</span>
              <span className="block text-[11px] text-canvas-muted">{x.display || x.username}</span>
            </span>
            <span className="flex shrink-0 items-center gap-1.5">
              {x.signedAt ? <Pill tone="ok">İmzalandı · {dateTime(x.signedAt)}</Pill> : <Pill tone="muted">Bekliyor</Pill>}
              <button
                type="button"
                aria-label={`${x.role} imzacısını çıkar`}
                disabled={save.isPending}
                onClick={() => save.mutate(list.filter((y) => !(y.role === x.role && y.username === x.username)))}
                className={`${btnGhost} px-2`}
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            </span>
          </li>
        ))}
      </ul>
      <form
        className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          if (role.trim() && username.trim()) {
            save.mutate([...list, { role: role.trim(), username: username.trim().toLowerCase() }]);
            setRole('');
            setUsername('');
          }
        }}
      >
        <label className="block">
          <span className={label}>Rol</span>
          <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Genel Yayın Yönetmeni" className={`${field} mt-1`} />
        </label>
        <label className="block">
          <span className={label}>AD hesabı</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="adsoyad" className={`${field} mt-1`} />
        </label>
        <button type="submit" disabled={!role.trim() || !username.trim() || save.isPending} className={`${btnGhost} self-end`}>
          Ekle
        </button>
      </form>
      {mine && !mine.signedAt && (
        <button type="button" disabled={sign.isPending || s.blocking.failed > 0} onClick={() => sign.mutate()} className={`${btn} mt-3 w-full justify-center bg-gradient-to-r from-canvas-coral to-canvas-violet text-white shadow-md`}>
          {sign.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <PenLine aria-hidden className="h-4 w-4" />}
          {s.blocking.failed > 0 ? 'Geçmeyen kontrol var' : `${mine.role} olarak imzala`}
        </button>
      )}
    </Panel>
  );
}

/** Eser dosyası yokken motorun okuduğu kitaplardan seçim: çipler sarar, yatay kaydırma yok. */
function BookChips({ books, picked, onPick }: { books: string[]; picked: string | null; onPick: (title: string | null) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Motorun okuduğu kitaplar">
      <BookOpen aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
      {books.map((t) => {
        const active = picked === t;
        return (
          <button
            key={t}
            type="button"
            aria-pressed={active}
            onClick={() => onPick(active ? null : t)}
            className={`min-h-10 max-w-full whitespace-normal break-words rounded-full px-3 py-1 text-left text-[11.5px] font-semibold transition-[transform,background-color,box-shadow] duration-150 ease-out active:scale-[0.97] ${
              active ? 'bg-canvas-violet text-white shadow-sm' : 'bg-white text-canvas-ink ring-1 ring-slate-200 hover:ring-canvas-violet/40'
            }`}
          >
            {t}
          </button>
        );
      })}
    </div>
  );
}

export default function ProofScreen() {
  const qc = useQueryClient();
  const works = useWorks();
  const [workId, setWorkId] = useState<string | null>(null);
  const [isbn, setIsbn] = useState('');
  const items = works.data?.items ?? [];
  // Eser dosyası yokken seçilen kitap URL'de taşınır (?kitap=): sayfa yenilenince aynı kitap açılır.
  const [params, setParams] = useSearchParams();
  const picked = params.get('kitap');
  const pick = (t: string | null) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (t) next.set('kitap', t);
        else next.delete('kitap');
        return next;
      },
      { replace: true },
    );

  useEffect(() => {
    if (!workId && items.length) setWorkId(items[0].id);
  }, [workId, items]);

  const state = useQuery({ queryKey: ['editorial', 'proof', workId], queryFn: () => deskApi.proof(workId as string), enabled: ENGINE_ENABLED && !!workId });
  const s = state.data;
  useEffect(() => setIsbn(s?.work.isbn || ''), [s?.work.isbn, workId]);
<<<<<<< HEAD
  // Motorun okuduğu kitaplar; yalnız eser dosyası yokken gerekir. Anahtar AskBox ile ortak, önbellek paylaşılır.
  const noWork = !workId && !works.isLoading;
  const books = useQuery({
    queryKey: ['editorial', 'readableBooks'],
    queryFn: readableBooksApi.list,
    enabled: ENGINE_ENABLED && noWork,
    staleTime: 5 * 60_000,
    refetchInterval: (query) => (query.state.data?.loading ? 15000 : 5 * 60_000),
  });
  const readable = books.data?.items ?? [];
  // URL'deki kitap listede yoksa (ad değişmiş, liste henüz gelmemiş) yine de seçilebilir kalsın.
  const chips = picked && !readable.includes(picked) ? [picked, ...readable] : readable;
  // Motorun otomatik denetimleri; eşleşme köprüde kitap adıyla yapılır, prova PDF'inden bağımsızdır.
  // Eser dosyası seçiliyse eserin adı, yoksa URL'den seçilen kitap.
  const title = s?.work.title ?? (noWork ? picked : null) ?? '';
  const proofing = useQuery({ queryKey: ['editorial', 'proofing', title], queryFn: () => proofingApi.get(title), enabled: ENGINE_ENABLED && !!title, staleTime: 60_000 });
  const pr = proofing.data;
  const hasProofing = !!pr && pr.configured && !!pr.bookId && pr.checks.length > 0;
  const engineOff = !ENGINE_ENABLED || books.data?.configured === false;
=======
  // Motorun otomatik denetimleri; eşleşme köprüde kitap adıyla yapılır, prova PDF'inden bağımsızdır.
  const title = s?.work.title ?? '';
  const proofing = useQuery({ queryKey: ['editorial', 'proofing', title], queryFn: () => proofingApi.get(title), enabled: ENGINE_ENABLED && !!title, staleTime: 60_000 });
  const pr = proofing.data;
  const hasProofing = !!pr && pr.configured && !!pr.bookId && pr.checks.length > 0;
>>>>>>> 709ef8f883bac642f67d70bac686e69a19f8353e

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['editorial', 'proof', workId] });
    void qc.invalidateQueries({ queryKey: ['editorial', 'works'] });
  };
  const setIsbnM = useMutation({ mutationFn: () => deskApi.updateWork(workId as string, { isbn }), onSuccess: refresh });
  const setCheck = useMutation({ mutationFn: (v: { id: string; passed: boolean | null }) => deskApi.setCheck(v.id, v.passed), onSuccess: refresh });
  const err = errText(works.error || state.error || setIsbnM.error || setCheck.error, 'Prova durumu okunamadı.');
  const auto = (s?.checks ?? []).filter((c) => c.auto);
  const manual = (s?.checks ?? []).filter((c) => !c.auto);

  return (
    <ModuleFrame
      route="/son-okuma"
      code="M5"
      crumb="Son Okuma"
      title="Son okuma ve yayın onayı"
      lead="Prova PDF'inden sayfa, ebat, gömülü yazı tipi, renk uzayı, ISBN ve forma ölçülür; elle işaretlenen maddeler ve imzalar tamamlanınca onay oluşur. Matbaaya gönderim ve ERP tetikleme yoktur."
      source={s ? s.work.title : noWork && picked ? picked : 'Editoryal masa'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

<<<<<<< HEAD
      {((s?.versions.length ?? 0) > 0 || hasProofing) && (
        <KpiRow>
          {s && (
            <>
              <Kpi label="Prova sürümü" value={s.versions[0] ? `v${s.versions[0].version}` : '—'} help={s.versions[0] ? dateTime(s.versions[0].uploadedAt) : 'Prova yüklenmedi'} />
              <Kpi label="Dosyadan geçen" value={`${nf.format(auto.filter((c) => c.passed === true).length)}/${nf.format(auto.length)}`} help="Otomatik ölçülen madde" />
              <Kpi label="Elle işaretlenen" value={`${nf.format(manual.filter((c) => c.passed !== null).length)}/${nf.format(manual.length)}`} help="Gözle kontrol maddesi" />
              <Kpi label="İmza" value={`${nf.format(s.signatures.filter((x) => x.signedAt).length)}/${nf.format(s.signatures.length)}`} help={s.approved ? 'Yayın onayı tamam' : 'Onay bekliyor'} />
            </>
          )}
=======
      {s && (s.versions.length > 0 || hasProofing) && (
        <KpiRow>
          <Kpi label="Prova sürümü" value={s.versions[0] ? `v${s.versions[0].version}` : '—'} help={s.versions[0] ? dateTime(s.versions[0].uploadedAt) : 'Prova yüklenmedi'} />
          <Kpi label="Dosyadan geçen" value={`${nf.format(auto.filter((c) => c.passed === true).length)}/${nf.format(auto.length)}`} help="Otomatik ölçülen madde" />
          <Kpi label="Elle işaretlenen" value={`${nf.format(manual.filter((c) => c.passed !== null).length)}/${nf.format(manual.length)}`} help="Gözle kontrol maddesi" />
          <Kpi label="İmza" value={`${nf.format(s.signatures.filter((x) => x.signedAt).length)}/${nf.format(s.signatures.length)}`} help={s.approved ? 'Yayın onayı tamam' : 'Onay bekliyor'} />
>>>>>>> 709ef8f883bac642f67d70bac686e69a19f8353e
          {hasProofing && <Kpi label="ZEKİ AI bulgusu" value={nf.format(seriousCount(pr))} help={`Uyarı ve hata · ${nf.format(pr?.findings.length ?? 0)} bulgu toplam`} />}
        </KpiRow>
      )}

      {s && (s.approved || s.blocking.failed > 0) && (
        <Note tone={s.approved ? 'ok' : 'err'}>
          {s.approved
            ? `Yayın onayı tamam: bütün kontroller geçti ve ${nf.format(s.signatures.length)} imza bu provaya atıldı.`
            : `${nf.format(s.blocking.failed)} kontrol maddesi geçmedi; prova imzalanamaz.`}
        </Note>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)] lg:items-start lg:gap-4">
        <div className="space-y-3 lg:space-y-4">
          <WorkList
            works={items}
            selected={workId}
            onSelect={setWorkId}
            progress={(x) => (x.proof ? `Prova v${x.proof.version} · ${nf.format(x.signatures.signed)}/${nf.format(x.signatures.total)} imza` : 'Prova yüklenmedi')}
          />

          {s && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold">Prova dosyası</h2>
              <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">Baskıya giden PDF. Yeni yükleme yeni sürüm açar, kontrolleri yeniden ölçer ve imzaları sıfırlar.</p>
              <div className="mt-2">
                <UploadButton workId={s.work.id} kind="proof" accept=".pdf" onDone={refresh}>
                  Prova yükle
                </UploadButton>
              </div>
              <form
                className="mt-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!setIsbnM.isPending) setIsbnM.mutate();
                }}
              >
                <span className={label}>ISBN</span>
                <div className="mt-1 flex gap-1.5">
                  <input value={isbn} onChange={(e) => setIsbn(e.target.value)} inputMode="numeric" placeholder="978…" className={field} />
                  <button type="submit" disabled={setIsbnM.isPending} className={btnGhost}>
                    Kaydet
                  </button>
                </div>
                <p className="mt-1 text-[11px] leading-snug text-canvas-muted">Girilince sağlaması hesaplanır ve prova metninde geçip geçmediği aranır.</p>
              </form>
            </Panel>
          )}
        </div>

        <div className="space-y-3 lg:space-y-4">
          {!s ? (
            !noWork ? (
              // Eser seçili ama durumu henüz gelmedi ya da okunamadı.
              <Panel>{state.error ? <Note tone="err">{errText(state.error, 'Prova durumu okunamadı.')}</Note> : <Loading />}</Panel>
            ) : (
              // Eser dosyası yok: motorun okuduğu kitaplar arasından seçim; bulgular seçilen kitap adıyla gelir.
              <ProofFindings
                key={picked ?? ''}
                report={picked ? pr : undefined}
                loading={!!picked && proofing.isLoading}
                error={picked ? errText(proofing.error, 'Zeki AI son okuma raporu okunamadı.') : null}
                picker={
                  engineOff ? null : books.isLoading ? (
                    <Loading />
                  ) : books.error ? (
                    <Note tone="err">{errText(books.error, 'Okunmuş kitap listesi alınamadı.')}</Note>
                  ) : chips.length ? (
                    <BookChips books={chips} picked={picked} onPick={pick} />
                  ) : null
                }
                idle={
                  engineOff
                    ? 'Zeki AI motor bağlantısı tanımlı değil; otomatik son okuma bu kurulumda kapalı.'
                    : books.isLoading || books.error
                      ? null
                      : !chips.length
                        ? books.data?.loading
                          ? 'Okunmuş kitaplar getiriliyor; liste gelince burada seçilebilir.'
                          : 'Motorun okuduğu kitap yok. Bir kitap okunup denetimleri koşunca burada listelenir.'
                        : 'Bulgularını görmek için bir kitap seçin.'
                }
              />
            )
          ) : !s.versions.length ? (
            <Panel>
              <p className="py-10 text-center text-[12.5px] leading-snug text-canvas-muted">Bu eserde henüz prova yok. Soldan baskıya giden PDF'i yükleyin.</p>
            </Panel>
          ) : (
            <>
              <Panel>
                <h2 className="px-1 text-[13px] font-extrabold">Dosyadan okunanlar</h2>
                <div className="mt-2 space-y-2">
                  {s.versions.map((f) => (
                    <Report key={f.id} f={f} />
                  ))}
                </div>
              </Panel>

              <Panel>
                <h2 className="px-1 text-[13px] font-extrabold">Kontrol listesi</h2>
                <ul className="mt-2 space-y-1.5">
                  {s.checks.map((c) => (
                    <CheckRow key={c.id} c={c} busy={setCheck.isPending} onSet={(passed) => setCheck.mutate({ id: c.id, passed })} />
                  ))}
                </ul>
              </Panel>

              <Signers s={s} onChanged={refresh} />
            </>
          )}
          {s && <ProofFindings report={pr} loading={proofing.isLoading} error={errText(proofing.error, 'Zeki AI son okuma raporu okunamadı.')} />}
        </div>
      </div>
    </ModuleFrame>
  );
}
