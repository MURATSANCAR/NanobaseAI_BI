import { useQuery } from '@tanstack/react-query';
import { adminApi, type AdminUnit } from '../engine';
import { AuditRow } from './AuditLog';
import { Card, Loading, Note, Pill, Section, btnGhost, errText, fmtUnitTime, nf } from './ui';
import type { AdminTab } from './AdminScreen';

function Tile({ label, value, sub, tone, onClick }: { label: string; value: number; sub: string; tone?: 'err' | 'warn'; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-2xl border border-slate-100 bg-white/80 p-4 text-left transition-transform duration-150 ease-out active:scale-[0.98]"
    >
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-1 text-3xl font-extrabold tabular-nums tracking-tight">{nf.format(value)}</div>
      <div className={`mt-0.5 text-[12px] font-semibold ${tone === 'err' ? 'text-red-700' : tone === 'warn' ? 'text-amber-700' : 'text-canvas-muted'}`}>{sub}</div>
    </button>
  );
}

const unitTone = (u: AdminUnit) => (u.state === 'active' ? 'ok' : u.state === 'failed' ? 'err' : 'warn');
const unitLabel = (u: AdminUnit) =>
  u.state === 'active' ? 'Çalışıyor' : u.state === 'failed' ? 'Hata' : u.state === 'inactive' ? 'Durdu' : u.state === 'unknown' ? 'Bilinmiyor' : u.state;

export default function Overview({ go }: { go: (t: AdminTab) => void }) {
  const q = useQuery({ queryKey: ['admin', 'overview'], queryFn: adminApi.overview, refetchInterval: 60_000, retry: false });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <Note tone="err">{errText(q.error, 'Durum okunamadı.')}</Note>;
  const { counts: c, email, engine, services, timers, recent } = q.data;
  const certified = engine.catalog?.CERTIFIED ?? 0;

  return (
    <div className="space-y-6">
      <Section title="Genel durum" help="Sistemde tanımlı her şeyin özeti ve servislerin durumu.">
        {!email.configured && (
          <Note tone="warn">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>E-posta ayarı yok: uyarılar ve planlı raporlar üretiliyor ama kimseye gitmiyor.</span>
              <button type="button" onClick={() => go('settings')} className={btnGhost}>
                E-postayı ayarla
              </button>
            </div>
          </Note>
        )}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile label="Planlı rapor" value={c.reports} sub={c.reportsFailed ? `${c.reportsActive} etkin · ${c.reportsFailed} hatalı` : `${c.reportsActive} etkin`} tone={c.reportsFailed ? 'err' : undefined} onClick={() => go('reports')} />
          <Tile label="Uyarı" value={c.alerts} sub={c.alertsTriggered ? `${c.alertsActive} etkin · ${c.alertsTriggered} tetiklendi` : `${c.alertsActive} etkin`} tone={c.alertsTriggered ? 'warn' : undefined} onClick={() => go('alerts')} />
          <Tile label="Pano kartı" value={c.cards} sub={c.cardsFailed ? `${c.cardsFailed} kartta hata` : 'hatasız'} tone={c.cardsFailed ? 'err' : undefined} onClick={() => go('cards')} />
          <Tile label="Kişi" value={c.users} sub={`${c.admins} yönetici`} onClick={() => go('people')} />
        </div>
      </Section>

      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        <Card className="min-w-0">
          <div className="text-[13px] font-extrabold">Servisler</div>
          <ul className="mt-2 divide-y divide-slate-100">
            {services.map((s) => (
              <li key={s.unit} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-[12.5px] font-semibold">{s.label}</div>
                  <div className="truncate font-mono text-[11px] text-canvas-muted">{s.unit}</div>
                </div>
                <Pill tone={unitTone(s)}>{unitLabel(s)}</Pill>
              </li>
            ))}
          </ul>
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 text-[12px] [&>div]:min-w-0">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Dil modeli</div>
              <div className="truncate font-semibold">{engine.model}</div>
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Katalog</div>
              <div className="font-semibold tabular-nums">
                {nf.format(engine.profiles)} tablo · {nf.format(certified)} sertifikalı terim
              </div>
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Veritabanı</div>
              <div className="font-semibold">{engine.db ? 'Bağlı' : 'Bağlı değil'}</div>
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">E-posta</div>
              <div className="truncate font-semibold">{email.configured ? email.sender : 'Ayarlanmadı'}</div>
            </div>
          </div>
        </Card>

        <Card className="min-w-0">
          <div className="text-[13px] font-extrabold">Zamanlanmış işler</div>
          <ul className="mt-2 divide-y divide-slate-100">
            {timers.map((t) => (
              <li key={t.unit} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-[12.5px] font-semibold">
                    {t.label} <span className="font-normal text-canvas-muted">· {t.every}</span>
                  </div>
                  <div className="text-[11px] tabular-nums text-canvas-muted">
                    son {fmtUnitTime(t.last)} · sıradaki {fmtUnitTime(t.next)}
                  </div>
                </div>
                <Pill tone={unitTone(t)}>{unitLabel(t)}</Pill>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card>
        <div className="flex items-center justify-between">
          <div className="text-[13px] font-extrabold">Son değişiklikler</div>
          <button type="button" onClick={() => go('audit')} className="min-h-11 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
            Tümünü gör
          </button>
        </div>
        {recent.length ? (
          <ul className="mt-1 divide-y divide-slate-100">
            {recent.map((a) => (
              <AuditRow key={a.id} item={a} />
            ))}
          </ul>
        ) : (
          <div className="py-4 text-[12px] text-canvas-muted">Henüz kayıt yok. Bundan sonra yapılan her ekleme, değişiklik ve silme burada görünür.</div>
        )}
      </Card>
    </div>
  );
}
