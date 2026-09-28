import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Check, Loader2, PenLine, X } from 'lucide-react';
import { ENGINE_ENABLED, bookCatalogApi, deskApi, findCatalogCard, proofingApi, readableBooksApi, type BookCard, type DeskCheck, type DeskFile, type ProofState, type Work } from '../engine';
import { Loading, Note, Pill, btn, btnGhost, errText, field, label, nf } from '../admin/ui';
import { dateTime, num } from '../format';
import { Kpi, KpiRow, ModuleFrame, Panel } from './kit';
import { WorkList, WorkUpload, fmtBytes, useWorks } from './WorkPicker';
import { ProofFindings, seriousCount } from './ProofFindings';
import { WordMapPanel } from './WordMapPanel';
import { DocumentPicker, DocumentResult, DocumentUpload } from './DocumentReview';
import { DocumentPicker, DocumentResult } from './DocumentReview';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

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
/** Değer köprünün kitap adıdır (bulgular onunla eşleşir); ekranda katalogdaki yayınevi başlığı görünür,
 *  yoksa ad olduğu gibi. Böylece «dedem-tekrar-cocuk-oldu» yerine «Dedem Tekrar Çocuk Oldu» yazar. */
function BookChips({ books, cards, picked, onPick }: { books: string[]; cards?: BookCard[]; picked: string | null; onPick: (title: string | null) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="ZEKİ AI'ın okuduğu kitaplar">
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
            {findCatalogCard(cards, t)?.publisher?.title || t}
          </button>
        );
      })}
    </div>
  );
}

const UPLOAD_MODES = { belge: 'Belge incele', prova: 'Baskı provası' } as const;
type UploadMode = keyof typeof UPLOAD_MODES;

/** Son okumanın birincil yükleme alanı: sayfanın üstünde, hiçbir şey seçmeden görünür. «Belge incele»: Word/PDF/metin
 *  belgesi Zeki AI incelemesine girer. «Baskı provası»: prova PDF'i eser dosyasına yüklenir; eser yoksa dosya adından açılır. */
function ProofUploads({
  works,
  workId,
  onWork,
  onDoc,
}: {
  works: Work[];
  workId: string | null;
  onWork: (id: string) => void;
  onDoc: (id: string) => void;
}) {
  const [mode, setMode] = useState<UploadMode>('belge');
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="px-1 text-[13px] font-extrabold">Dosya yükle</h2>
        <div className="grid w-full grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1 sm:w-auto" role="tablist" aria-label="Ne yüklenecek">
          {(Object.keys(UPLOAD_MODES) as UploadMode[]).map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={mode === k}
              onClick={() => setMode(k)}
              className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                mode === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
              }`}
            >
              {UPLOAD_MODES[k]}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2.5">
        {mode === 'belge' ? (
          <DocumentUpload onUploaded={onDoc} />
        ) : (
          <WorkUpload bare kind="proof" works={works} selected={workId} onUploaded={onWork} />
        )}
      </div>
    </Panel>
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
  // Yüklenen belge (?belge=): seçiliyken sağ sütun belgenin incelemesi
  const doc = params.get('belge');
  const pickDoc = (id: string | null) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id) next.set('belge', id);
        else next.delete('belge');
        return next;
      },
      { replace: true },
    );
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
  // Aynı anahtar Kitap 360 ile ortak: katalog bir kez gelir.
  const catalog = useQuery({ queryKey: ['editorial', 'bookCatalog'], queryFn: bookCatalogApi.list, enabled: ENGINE_ENABLED && noWork, staleTime: 5 * 60_000 });
  // URL'deki kitap listede yoksa (ad değişmiş, liste henüz gelmemiş) yine de seçilebilir kalsın.
  const chips = picked && !readable.includes(picked) ? [picked, ...readable] : readable;
  // Motorun otomatik denetimleri; eşleşme köprüde kitap adıyla yapılır, prova PDF'inden bağımsızdır.
  // Eser dosyası seçiliyse eserin adı, yoksa URL'den seçilen kitap.
  const title = s?.work.title ?? (noWork ? picked : null) ?? '';
  const proofing = useQuery({ queryKey: ['editorial', 'proofing', title], queryFn: () => proofingApi.get(title), enabled: ENGINE_ENABLED && !!title, staleTime: 60_000 });
  const pr = proofing.data;
  const hasProofing = !!pr && pr.configured && !!pr.bookId && pr.checks.length > 0;
  const engineOff = !ENGINE_ENABLED || books.data?.configured === false;

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
      crumb="Son Okuma"
      title="Son okuma ve yayın onayı"
      lead="Prova PDF'inden sayfa, ebat, gömülü yazı tipi, renk uzayı, ISBN ve forma ölçülür; elle işaretlenen maddeler ve imzalar tamamlanınca onay oluşur. Matbaaya gönderim ve ERP tetikleme yoktur."
      source={s ? s.work.title : noWork && picked ? findCatalogCard(catalog.data?.items, picked)?.publisher?.title || picked : 'Editoryal masa'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {/* Birincil eylem: belge ya da prova yükleme. Liste boşken de burada; seçim beklemez. */}
      <ProofUploads
        works={items}
        workId={workId}
        onWork={(id) => {
          setWorkId(id);
          pickDoc(null);
        }}
        onDoc={pickDoc}
      />

      {((s?.versions.length ?? 0) > 0 || hasProofing) && (
        <KpiRow>
          {s && (
            <>
              <Kpi info={<SqlInfo k={kaynakOf(s)} alan="_hepsi" label="Prova sürümü" />} label="Prova sürümü" value={s.versions[0] ? `v${s.versions[0].version}` : '—'} help={s.versions[0] ? dateTime(s.versions[0].uploadedAt) : 'Prova yüklenmedi'} />
              <Kpi info={<SqlInfo k={kaynakOf(s)} alan="_hepsi" label="Dosyadan geçen" />} label="Dosyadan geçen" value={`${nf.format(auto.filter((c) => c.passed === true).length)}/${nf.format(auto.length)}`} help="Otomatik ölçülen madde" />
              <Kpi info={<SqlInfo k={kaynakOf(s)} alan="_hepsi" label="Elle işaretlenen" />} label="Elle işaretlenen" value={`${nf.format(manual.filter((c) => c.passed !== null).length)}/${nf.format(manual.length)}`} help="Gözle kontrol maddesi" />
              <Kpi info={<SqlInfo k={kaynakOf(s)} alan="_hepsi" label="İmza" />} label="İmza" value={`${nf.format(s.signatures.filter((x) => x.signedAt).length)}/${nf.format(s.signatures.length)}`} help={s.approved ? 'Yayın onayı tamam' : 'Onay bekliyor'} />
            </>
          )}
          {hasProofing && <Kpi info={<SqlInfo k={kaynakOf(pr)} alan="_hepsi" label="Zeki AI bulguları" />} label="ZEKİ AI bulgusu" value={nf.format(seriousCount(pr))} help={`Uyarı ve hata · ${nf.format(pr?.findings.length ?? 0)} bulgu toplam`} />}
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

          <DocumentPicker selected={doc} onSelect={pickDoc} />

          {s && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold">Prova dosyası</h2>
              <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
                Baskıya giden PDF. Yeni sürüm için üstteki alanda «Baskı provası»nı seçip dosyayı bırakın; kontroller yeniden ölçülür, imzalar sıfırlanır.
              </p>
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
          {/* Belge seçiliyse (?belge=) sağ sütun belgenin incelemesidir; kitap/eser görünümü onunla yer değiştirir. */}
          {doc ? (
            <DocumentResult key={doc} id={doc} />
          ) : (
          <>
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
                error={picked ? errText(proofing.error, 'ZEKİ AI son okuma raporu okunamadı.') : null}
                picker={
                  engineOff ? null : books.isLoading ? (
                    <Loading />
                  ) : books.error ? (
                    <Note tone="err">{errText(books.error, 'Okunmuş kitap listesi alınamadı.')}</Note>
                  ) : chips.length ? (
                    <BookChips books={chips} cards={catalog.data?.items} picked={picked} onPick={pick} />
                  ) : null
                }
                idle={
                  engineOff
                    ? 'ZEKİ AI motor bağlantısı tanımlı değil; otomatik son okuma bu kurulumda kapalı.'
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
              <p className="py-10 text-center text-[12.5px] leading-snug text-canvas-muted">Bu eserde henüz prova yok. Üstteki alanda «Baskı provası»nı seçip baskıya giden PDF'i bırakın.</p>
            </Panel>
          ) : (
            <>
              <Panel>
                <h2 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
                  Dosyadan okunanlar
                  <SqlInfo k={kaynakOf(s)} alan="_hepsi" label="Prova dosyasının ölçüleri" />
                </h2>
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
          {s && <ProofFindings report={pr} loading={proofing.isLoading} error={errText(proofing.error, 'ZEKİ AI son okuma raporu okunamadı.')} />}
          {/* Kelime haritası: aynı kitabın motordaki kaydıyla (eser dosyası ya da seçilen kitap). */}
          {pr?.configured && pr.bookId && (s || picked) ? <WordMapPanel key={pr.bookId} bookId={pr.bookId} findings={pr.findings.filter((f) => f.check === 'word_variety')} /> : null}
          </>
          )}
        </div>
      </div>
    </ModuleFrame>
  );
}
