import { useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, Download, Pencil, Trash2, UserCheck } from 'lucide-react';
import { ENGINE_ENABLED, editorialSearchApi } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import SearchSelect from '../../components/SearchSelect';
import { ModuleFrame, Panel, useDebounced } from '../kit';
import { fmtDay, usePeopleOptions } from '../authors/shared';
import { applicationsApi, boardApi, type AppDetail } from './api';
import ApplicationForm from './ApplicationForm';
import EvaluationPanel from './EvaluationPanel';
import LettersPanel from './LettersPanel';
import NoteSheet from './NoteSheet';
import ReportPanel from './ReportPanel';
import { ACTION_TEXT, DECISION_TONE, StatusPill, TallyView, errMsg, fmtBytes, invalidateApps, useAppMeta } from './shared';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** Tek başvuru: dosya, editör değerlendirmesi, kurula çıkış, Yayın Kurulu Raporu, kurul kararı, yazışma, geçmiş. */

const STEPS = [
  { key: 'basvuru', title: 'Başvuru' },
  { key: 'editor', title: 'Editör raporu' },
  { key: 'kurul', title: 'Yayın kurulu' },
  { key: 'karar', title: 'Karar' },
];

function stepOf(a: AppDetail): number {
  if (a.status === 'yeni') return 0;
  if (a.status === 'degerlendirmede' || a.status === 'revizyon') return 1;
  if (a.status === 'kurul_bekliyor' || a.status === 'kurulda') return 2;
  return 3;
}

function Steps({ a }: { a: AppDetail }) {
  const at = stepOf(a);
  const closed = a.status === 'kabul' || a.status === 'red' || a.status === 'geri_cekildi';
  return (
    <ol className="grid grid-cols-4 gap-1.5" aria-label="Başvurunun adımları">
      {STEPS.map((s, i) => {
        const done = i < at || (closed && i === at);
        const current = i === at && !closed;
        return (
          <li key={s.key} className="min-w-0">
            <span className={`block h-1.5 rounded-full ${done ? (a.status === 'red' || a.status === 'geri_cekildi') && i === at ? 'bg-rose-400' : 'bg-canvas-mint' : current ? 'bg-canvas-violet' : 'bg-slate-200'}`} />
            <span className={`mt-1 block truncate text-[11px] ${current ? 'font-extrabold text-canvas-ink' : 'text-canvas-muted'}`}>{s.title}</span>
          </li>
        );
      })}
    </ol>
  );
}

type Sheet = null | 'red' | 'revizyon' | 'geri_cekildi' | 'reopen';

function Actions({ a, onEdit }: { a: AppDetail; onEdit: () => void }) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const me = meta.data?.me;
  const people = usePeopleOptions();
  const [sheet, setSheetRaw] = useState<Sheet>(null);
  const [assignee, setAssignee] = useState('');
  const [sessionId, setSessionId] = useState('');
  const canWrite = !!me?.canWrite;
  const mineOrManager = !!me && (a.evaluator === me.username || me.canManage);
  const sessions = useQuery({
    queryKey: ['board', 'sessions', 'planli'],
    queryFn: () => boardApi.list('planli'),
    enabled: ENGINE_ENABLED && a.status === 'kurul_bekliyor',
  });
  const runnable = (sessions.data?.items ?? []).filter((s) => me && (me.canRunBoard || s.chair === me.username));

  const done = async (msg: string) => {
    setSheet(null);
    await invalidateApps(qc);
    toast.success(msg);
  };
  const assign = useMutation({
    mutationFn: (who: string) => applicationsApi.assign(a.id, who, people.byUser.get(who) ?? (who === me?.username ? me.display : who)),
    onSuccess: () => done('Editör atandı'),
    onError: (e) => toast.error(errMsg(e)),
  });
  const decide = useMutation({
    mutationFn: ({ action, note }: { action: 'kurula' | 'revizyon' | 'red' | 'geri_cekildi'; note: string }) => applicationsApi.decide(a.id, action, note),
    onSuccess: (_, v) =>
      done({ kurula: 'Yayın kuruluna çıkarıldı; rapor hazırlanıyor', revizyon: 'Revizyon istendi; yazı taslağı hazır', red: 'Reddedildi ve arşive alındı', geri_cekildi: 'Geri çekildi olarak arşivlendi' }[v.action]),
  });
  const reopen = useMutation({
    mutationFn: (note: string) => applicationsApi.reopen(a.id, note),
    onSuccess: () => done('Başvuru yeniden açıldı'),
  });
  // Panel her açılışta temiz: önceki denemenin hatası taşınmaz.
  const setSheet = (v: Sheet) => {
    decide.reset();
    reopen.reset();
    setSheetRaw(v);
  };
  const agenda = useMutation({
    mutationFn: () => boardApi.addAgenda(sessionId, a.id),
    onSuccess: () => done('Kurul gündemine eklendi'),
    onError: (e) => toast.error(errMsg(e)),
  });

  const submitted = !!a.evaluation?.submitted;
  const blocks: ReactNode[] = [];
  if (a.status === 'yeni' && canWrite) {
    blocks.push(
      <div key="assign" className="space-y-2">
        <p className="text-[12.5px]">Başvuruyu değerlendirecek editör seçilmedi.</p>
        <button type="button" className={`${btnPrimary} w-full`} disabled={assign.isPending} onClick={() => me && assign.mutate(me.username)}>
          <UserCheck aria-hidden className="h-4 w-4" />
          Değerlendirmeyi üstlen
        </button>
      </div>,
    );
  }
  if ((a.status === 'yeni' || a.status === 'degerlendirmede') && me?.canManage) {
    blocks.push(
      <div key="reassign" className="space-y-1.5">
        <span className={label}>{a.evaluator ? 'Başka editöre ata' : 'Editöre ata'}</span>
        <SearchSelect label="Editör" placeholder="Kişi seçin" options={people.options} value={assignee} onChange={setAssignee} />
        <button type="button" className={`${btnGhost} w-full`} disabled={!assignee || assign.isPending} onClick={() => assign.mutate(assignee)}>
          Ata
        </button>
      </div>,
    );
  }
  if (a.status === 'degerlendirmede' && mineOrManager && canWrite) {
    blocks.push(
      <div key="decide" className="space-y-1.5">
        <p className="text-[12.5px]">{submitted ? 'Editör raporu tamam. Kararınız:' : 'Karar için önce editör raporunu tamamlayın.'}</p>
        <button type="button" className={`${btnPrimary} w-full`} disabled={!submitted || decide.isPending} onClick={() => decide.mutate({ action: 'kurula', note: '' }, { onError: (e) => toast.error(errMsg(e)) })}>
          Yayın kuruluna çıkar
        </button>
        <div className="grid grid-cols-2 gap-1.5">
          <button type="button" className={btnGhost} disabled={!submitted} onClick={() => setSheet('revizyon')}>
            Revizyon iste
          </button>
          <button type="button" className={`${btnGhost} !text-rose-700`} disabled={!submitted} onClick={() => setSheet('red')}>
            Reddet
          </button>
        </div>
      </div>,
    );
  }
  if (a.status === 'kurul_bekliyor') {
    blocks.push(
      <div key="agenda" className="space-y-1.5">
        <p className="text-[12.5px]">Rapor tamam; kurul gündemi bekleniyor.</p>
        {runnable.length > 0 ? (
          <>
            <select aria-label="Kurul oturumu" value={sessionId} onChange={(e) => setSessionId(e.target.value)} className={`${field} w-full`}>
              <option value="">Oturum seçin</option>
              {runnable.map((s) => (
                <option key={s.id} value={s.id}>
                  {fmtDay(s.date)} · {s.title}
                </option>
              ))}
            </select>
            <button type="button" className={`${btnPrimary} w-full`} disabled={!sessionId || agenda.isPending} onClick={() => agenda.mutate()}>
              Gündeme ekle
            </button>
          </>
        ) : (
          <p className="text-[11.5px] text-canvas-muted">
            Hazırlanan kurul oturumu yok ya da gündem yetkiniz yok.{' '}
            <Link to="/yayin-kurulu" className="font-bold text-canvas-violet hover:underline">
              Yayın kurulu →
            </Link>
          </p>
        )}
      </div>,
    );
  }
  if (a.status === 'kurulda') {
    const s = a.board.find((b) => b.state === 'planli' && !b.decision);
    blocks.push(
      <div key="kurulda" className="space-y-1.5 text-[12.5px]">
        <p>Kurul gündeminde{s ? `: ${fmtDay(s.date)}` : ''}.</p>
        {s && (
          <Link to={`/yayin-kurulu/oturum/${s.sessionId}?basvuru=${a.id}`} className={`${btnPrimary} w-full`}>
            Kurul oturumuna git
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        )}
      </div>,
    );
  }
  if ((a.status === 'revizyon' || a.status === 'red' || a.status === 'geri_cekildi') && mineOrManager && canWrite) {
    blocks.push(
      <div key="reopen" className="space-y-1.5">
        <p className="text-[12.5px]">{a.status === 'revizyon' ? 'Revize dosya gelince yeni turu açın (dosyayı da ekleyin).' : 'Arşivde. Yeniden ele alınacaksa açın.'}</p>
        <button type="button" className={`${btnGhost} w-full`} onClick={() => setSheet('reopen')}>
          Yeniden aç
        </button>
      </div>,
    );
  }
  if (['yeni', 'degerlendirmede', 'revizyon', 'kurul_bekliyor'].includes(a.status) && mineOrManager && canWrite) {
    blocks.push(
      <button key="withdraw" type="button" className={`${btnGhost} w-full !text-canvas-muted`} onClick={() => setSheet('geri_cekildi')}>
        Yazar geri çekti
      </button>,
    );
  }
  const open = ['yeni', 'degerlendirmede', 'revizyon', 'kurul_bekliyor', 'kurulda'].includes(a.status);

  const sheetCfg = {
    red: { title: 'Başvuruyu reddet', noteLabel: 'Gerekçe (yazara gidecek yazının temeli)', confirm: 'Reddet ve arşivle', tone: 'danger' as const },
    revizyon: { title: 'Yazardan revizyon iste', noteLabel: 'Revizyon beklenen noktalar', confirm: 'Revizyon iste', tone: 'primary' as const },
    geri_cekildi: { title: 'Yazar başvuruyu geri çekti', noteLabel: 'Ne zaman, nasıl bildirildi', confirm: 'Arşivle', tone: 'primary' as const },
    reopen: { title: 'Başvuruyu yeniden aç', noteLabel: 'Neden (revize dosya geldi, yeniden değerlendirme…)', confirm: 'Yeniden aç', tone: 'primary' as const },
  };
  const cfg = sheet ? sheetCfg[sheet] : null;
  const pending = decide.isPending || reopen.isPending;
  const error = sheet === 'reopen' ? reopen.error : decide.error;

  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Sıradaki adım</h2>
        {canWrite && open && (
          <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={onEdit}>
            <Pencil aria-hidden className="h-3.5 w-3.5" />
            Düzenle
          </button>
        )}
      </div>
      <div className="mt-2 space-y-3">
        {blocks.length ? blocks : <p className="text-[12.5px] text-canvas-muted">{open ? 'Bu adımda sizin için işlem yok.' : 'Başvuru kapandı.'}</p>}
      </div>
      {cfg && (
        <NoteSheet
          open
          onClose={() => setSheet(null)}
          title={cfg.title}
          subtitle={`${a.no} · ${a.title}`}
          noteLabel={cfg.noteLabel}
          required
          confirm={cfg.confirm}
          tone={cfg.tone}
          pending={pending}
          error={error ? errMsg(error) : null}
          onConfirm={(note) => (sheet === 'reopen' ? reopen.mutate(note) : decide.mutate({ action: sheet as 'red' | 'revizyon' | 'geri_cekildi', note }))}
        />
      )}
    </Panel>
  );
}

function Files({ a, canWrite }: { a: AppDetail; canWrite: boolean }) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const [kind, setKind] = useState(a.status === 'revizyon' || a.round > 1 ? 'revizyon' : 'dosya');
  const del = useMutation({
    mutationFn: (id: string) => applicationsApi.deleteFile(id),
    onSuccess: async () => {
      await invalidateApps(qc);
      toast.success('Dosya silindi');
    },
    onError: (e) => toast.error(errMsg(e)),
  });
  const open = !['kabul', 'red', 'geri_cekildi'].includes(a.status);
  return (
    <div className="space-y-2">
      {a.files.length === 0 && <p className="text-[12.5px] text-canvas-muted">Dosya yüklenmedi. Eser dosyasını aşağıdaki alana bırakın.</p>}
      <ul className="space-y-1.5">
        {a.files.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2">
            <span className="min-w-0 break-words text-[12.5px]">
              <b className="font-semibold">{f.filename}</b>
              <span className="text-canvas-muted">
                {' '}
                · {f.kindLabel}
                {f.round > 1 && ` (${f.round}. tur)`} · {fmtBytes(f.bytes)} · {fmtDay(f.uploadedAt)}
              </span>
            </span>
            <span className="flex shrink-0 gap-1.5">
              <a href={applicationsApi.fileUrl(f.id)} className={`${btnGhost} !min-h-9 !py-1`} download={f.filename}>
                <Download aria-hidden className="h-4 w-4" />
                İndir
              </a>
              {canWrite && open && (
                <button type="button" aria-label={`${f.filename} dosyasını sil`} className={`${btnGhost} !min-h-9 !py-1`} disabled={del.isPending} onClick={() => del.mutate(f.id)}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {/* Dosya ekleme her zaman görünür; yetki yoksa kilitli, başvuru kapandıysa pasif (nedeni yazılı). */}
      <div className="grid gap-2 sm:grid-cols-[minmax(0,200px)_minmax(0,1fr)] sm:items-start">
        <label className="block min-w-0">
          <span className={label}>Dosya türü</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={`${field} mt-1`}>
            {(meta.data?.fileKinds ?? []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <FileDrop
          size="sm"
          multiple
          title="Eser dosyası ekle"
          accept=".pdf,.docx,.doc"
          maxBytes={(meta.data?.fileMaxMb ?? 10) * MB}
          feature="basvuru.yaz"
          allowed={canWrite}
          disabled={!open}
          disabledReason="Başvuru sonuçlandı; yeni dosya eklenmez."
          run={(f) => applicationsApi.upload(a.id, kind, f)}
          onDone={async () => {
            await invalidateApps(qc);
            toast.success('Dosya yüklendi');
          }}
        />
      </div>
    </div>
  );
}

function Dossier({ a }: { a: AppDetail }) {
  const row = (k: string, v: string | null | undefined) =>
    v ? (
      <div>
        <dt className={label}>{k}</dt>
        <dd className="mt-0.5 whitespace-pre-line break-words text-[12.5px] leading-snug">{v}</dd>
      </div>
    ) : null;
  return (
    <dl className="space-y-2.5">
      {row('Özet', a.summary)}
      <div className="grid gap-2.5 sm:grid-cols-3">
        {row('Hedef kitle', [a.audienceLabel, a.ageFrom != null || a.ageTo != null ? `${a.ageFrom ?? ''}–${a.ageTo ?? ''} yaş` : null].filter(Boolean).join(', ') || null)}
        {row('Sayfa tahmini', nf.format(a.pageEstimate))}
        <div className="flex items-end"><SqlInfo k={kaynakOf(a)} alan="_hepsi" label="Başvuru dosyasının sayıları" /></div>
        {row('Tür', a.genre)}
        {row('Kategori', a.categoryName)}
        {row('Seri', a.series)}
        {row('Geliş', `${a.channelLabel} · ${fmtDay(a.receivedOn)}`)}
      </div>
      {row('Yayınevi notu', a.publisherNote)}
      <div className="border-t border-slate-100 pt-2.5">
        <div className="text-[13px] font-extrabold">
          {a.authorName}
          {a.crmContactId && <Pill tone="violet">CRM'de kayıtlı</Pill>}
        </div>
        <p className="text-[11.5px] text-canvas-muted">{[a.authorEmail, a.authorPhone, a.agencyName && `Ajans: ${a.agencyName}`, a.agencyContact].filter(Boolean).join(' · ') || 'İletişim bilgisi yok'}</p>
      </div>
      {row('Biyografi', a.authorBio)}
      {row('Uzmanlık', a.authorExpertise)}
      {row('Yayıncılık geçmişi', a.authorHistory)}
    </dl>
  );
}

function BoardHistoryPanel({ a }: { a: AppDetail }) {
  if (!a.board.length) return null;
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Yayın kurulu</h2>
      <ul className="mt-2 space-y-3">
        {a.board.map((b) => (
          <li key={b.sessionId} className="rounded-2xl bg-slate-50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link to={`/yayin-kurulu/oturum/${b.sessionId}?basvuru=${a.id}`} className="text-[13px] font-extrabold hover:underline">
                {fmtDay(b.date)} · {b.title}
              </Link>
              <Pill tone={b.decision ? DECISION_TONE[b.decision] ?? 'muted' : 'violet'}>{b.decisionLabel ?? 'Karar bekleniyor'}</Pill>
            </div>
            {b.note && <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{b.note}</p>}
            {(b.printRun || b.price || b.royalty || b.publishOn) && (
              <p className="mt-1 text-[11.5px] text-canvas-muted">
                {[b.printRun && `İlk baskı ${nf.format(b.printRun)}`, b.price && `Fiyat ${nf.format(b.price)} ₺`, b.royalty && `Telif %${nf.format(b.royalty)}`, b.publishOn && `Yayın ${fmtDay(b.publishOn)}`]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
            {b.decision && (
              <div className="mt-2">
                <TallyView tally={b.tally} compact />
              </div>
            )}
            {b.votes && b.votes.length > 0 && (
              <ul className="mt-2 space-y-1 text-[12px]">
                {b.votes.map((v) => (
                  <li key={v.member} className="rounded-lg bg-white px-2.5 py-1.5">
                    <b>{v.memberName}</b> · {v.voteLabel}
                    {v.mission != null && <span className="font-mono text-canvas-muted"> · {v.mission}/{v.publishing}/{v.commercial}</span>}
                    {v.note && <span className="block text-canvas-muted">{v.note}</span>}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function CrmLink({ a, canWrite }: { a: AppDetail; canWrite: boolean }) {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const q = useDebounced(text.trim(), 350);
  const search = useQuery({
    queryKey: ['applications', 'crm-projects', q],
    queryFn: () => editorialSearchApi.search(q, 'proje'),
    enabled: ENGINE_ENABLED && q.length >= 3,
    staleTime: 60_000,
  });
  const link = useMutation({
    mutationFn: (id: string) => applicationsApi.linkCrm(a.id, id),
    onSuccess: async () => {
      await invalidateApps(qc);
      toast.success('CRM proje kartı bağlandı');
      setText('');
    },
    onError: (e) => toast.error(errMsg(e)),
  });
  const fields = useMemo(
    () =>
      [
        `Proje adı: ${a.title}`,
        `Olası yazar: ${a.authorName}`,
        a.categoryName && `Kitaplık: ${a.categoryName}`,
        `Tahmini sayfa: ${a.pageEstimate}`,
        a.series && `Seri: ${a.series}`,
        `Proje fikri: ${a.summary.split('\n')[0].slice(0, 300)}`,
        `Oluşturma kanalı: ${a.channelLabel}`,
        ...a.board
          .filter((b) => b.decision === 'kabul')
          .slice(0, 1)
          .flatMap((b) => [`Yayın kurulu kararı: Kabul (${fmtDay(b.date)})`, b.printRun ? `Baskı adedi: ${b.printRun}` : null, b.publishOn ? `Önerilen yayın tarihi: ${fmtDay(b.publishOn)}` : null]),
      ]
        .filter(Boolean)
        .join('\n'),
    [a],
  );
  if (a.status !== 'kabul') return null;
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">CRM proje kartı</h2>
      {a.crmProjectId ? (
        <div className="mt-2 space-y-2 text-[12.5px]">
          <p>
            Bağlı: <b>{a.crmProjectName ?? a.crmProjectId}</b>
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Link to={`/yazar-giris/${a.crmProjectId}`} className={btnGhost}>
              Yazar giriş sürecinde aç
            </Link>
            <Link to="/editor-atama" className={btnGhost}>
              Editör atama
            </Link>
            {canWrite && (
              <button type="button" className={btnGhost} disabled={link.isPending} onClick={() => link.mutate('')}>
                Bağı kaldır
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-2 space-y-2 text-[12.5px]">
          <p className="text-canvas-muted">
            CRM'e portaldan yazılmıyor. Proje kartını CRM'de açın (alanlar aşağıda), sonra buradan bağlayın; editör ataması ve takvim CRM projesi üzerinden yürür.
          </p>
          <pre className="max-w-full overflow-x-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-2.5 font-[inherit] text-[12px]">{fields}</pre>
          <button type="button" className={btnGhost} onClick={() => navigator.clipboard?.writeText(fields).then(() => toast.success('Alanlar kopyalandı'))}>
            Alanları kopyala
          </button>
          {canWrite && (
            <div className="space-y-1.5">
              <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="CRM'de proje adıyla ara" className={field} />
              {search.isFetching && <p className="text-[11.5px] text-canvas-muted">CRM aranıyor…</p>}
              <ul className="space-y-1">
                {(search.data?.projects ?? []).map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5">
                    <span className="min-w-0 break-words">
                      <b>{p.title}</b>
                      {p.note && <span className="text-canvas-muted"> · {p.note}</span>}
                    </span>
                    <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={link.isPending} onClick={() => link.mutate(p.id)}>
                      Bağla
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function History({ a }: { a: AppDetail }) {
  return (
    <Panel>
      <details>
        <summary className="cursor-pointer text-[15px] font-extrabold">Geçmiş ({nf.format(a.log.length)})</summary>
        <ol className="mt-2 space-y-1.5 text-[12px]">
          {a.log.map((x, i) => (
            <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-2 border-t border-slate-100 pt-1.5 first:border-t-0 first:pt-0">
              <span className="min-w-0 break-words">
                <b>{ACTION_TEXT[x.action] ?? x.action}</b>
                <span className="text-canvas-muted"> · {x.actorName}</span>
                {typeof x.detail?.not === 'string' && x.detail.not && <span className="block text-canvas-muted">«{x.detail.not}»</span>}
              </span>
              <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">{new Date(x.at).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })}</span>
            </li>
          ))}
        </ol>
      </details>
    </Panel>
  );
}

export default function ApplicationScreen() {
  const { id = '' } = useParams();
  const meta = useAppMeta();
  const [editing, setEditing] = useState(false);
  const q = useQuery({ queryKey: ['applications', 'detail', id], queryFn: () => applicationsApi.get(id), enabled: ENGINE_ENABLED && !!id });
  const a = q.data;
  const me = meta.data?.me;
  const canWrite = !!me?.canWrite;
  const canEvaluate = !!a && !!me && canWrite && a.status === 'degerlendirmede' && (a.evaluator === me.username || me.canManage);

  return (
    <ModuleFrame
      route="/basvurular"
      crumb="Başvurular"
      title={a ? a.title : 'Başvuru'}
      lead={a ? [a.no, a.authorName, a.categoryName, a.evaluatorName && `Editör: ${a.evaluatorName}`].filter(Boolean).join(' · ') : ''}
      source={a ? a.statusLabel : 'Portal'}
      presence="Kaynak: portal"
      aside={
        a ? (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={a.status} label={a.statusLabel} />
              {a.round > 1 && <Pill tone="muted">{a.round}. tur</Pill>}
              <Link to="/basvurular" className="ml-auto text-[12px] font-bold text-canvas-violet hover:underline">
                Bütün başvurular
              </Link>
            </div>
            <Steps a={a} />
          </div>
        ) : undefined
      }
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Başvuru okunamadı.')}</Note>}
      {a && (
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,400px)] lg:items-start lg:gap-4">
          <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
            <Panel>
              <h2 className="text-[15px] font-extrabold">Başvuru dosyası</h2>
              <div className="mt-2">
                <Dossier a={a} />
              </div>
              <div className="mt-3 border-t border-slate-100 pt-3">
                <h3 className="mb-2 text-[13px] font-extrabold">Dosyalar</h3>
                <Files a={a} canWrite={canWrite} />
              </div>
            </Panel>
            <EvaluationPanel app={a} editable={canEvaluate} />
            <ReportPanel appId={a.id} canWrite={canWrite} status={a.status} />
          </div>
          <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
            <Actions a={a} onEdit={() => setEditing(true)} />
            {a.decisionNote && ['kabul', 'red', 'geri_cekildi', 'revizyon'].includes(a.status) && (
              <Panel>
                <h2 className="text-[15px] font-extrabold">Karar notu</h2>
                <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{a.decisionNote}</p>
                {a.decidedAt && <p className="mt-1 text-[11px] text-canvas-muted">{fmtDay(a.decidedAt)}</p>}
              </Panel>
            )}
            <CrmLink a={a} canWrite={canWrite} />
            <BoardHistoryPanel a={a} />
            <LettersPanel app={a} canWrite={canWrite} />
            <History a={a} />
          </div>
        </div>
      )}
      {a && <ApplicationForm open={editing} app={a} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} />}
    </ModuleFrame>
  );
}
