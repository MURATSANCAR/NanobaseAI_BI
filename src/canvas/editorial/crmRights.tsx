import { Check, Minus, X } from 'lucide-react';
import type { BookRights, CrmLicense, CrmRight } from '../engine';
import { Pill, nf } from '../admin/ui';
import { crmLabel } from '../format';
import { day } from './assign/parts';

/** CRM sözleşme hakları ve lisans şartları: sözleşme sayfası, kitap 360 ve kişi kartı aynı parçaları kullanır.
 *  Kaynak köprüdeki `crm_rights.py`; CRM'de boş alan «girilmemiş»tir, «yok» diye gösterilmez. */

const TERM_LABEL: Record<string, string> = {
  originalTitle: 'Eserin orijinal adı',
  originalLanguage: 'Orijinal dili',
  soldTo: 'Telif satılan ülke',
  rightsFrom: 'Hakkı devreden firma',
  rightsTransferDate: 'Mali hak devir tarihi',
  publishingDirector: 'Yayın yönetmeni',
  renewEveryYears: 'Yenilenme sıklığı (yıl)',
  renewalStart: 'Yenileme başlangıcı',
  renewalEnd: 'Yenileme bitişi',
  terminated: 'Fesih tarihi',
  unpublishedTermination: 'Yayınlanmazsa fesih tarihi',
  unpublishedTerminationMonths: 'Yayınlanmazsa fesih süresi (ay)',
  minFirstPrint: 'En az ilk baskı adedi',
  maxReprints: 'En çok baskı tekrarı',
  maxPrintRun: 'En çok baskı adedi',
  overPrintQty: 'Fazla basım (adet)',
  overPrintPct: 'Fazla basım (%)',
  firstPrintGift: 'İlk baskı hediye (adet)',
  firstPrintGiftPct: 'İlk baskı hediye (%)',
  reprintGift: 'Tekrar baskı hediye (adet)',
  reportEveryMonths: 'Rapor verme süresi (ay)',
  paymentType: 'Telif tipi',
  basis: 'Telif esası',
  paymentMethod: 'Ödeme şekli',
  paymentDays: 'Vade (gün)',
  currency: 'Para birimi',
  advance: 'Avans',
  flatFee: 'Tek ödeme tutarı',
  imageFee: 'Görsel bedeli',
  purchaseDiscountPct: 'Satın alma indirimi (%)',
  consentDate: 'Muvafakatname tarihi',
  consentEnd: 'Muvafakatname bitişi',
  consentParty: 'Muvafakatname tarafı',
  ebookConsentDate: 'E-kitap muvafakatname tarihi',
  ebookConsentEnd: 'E-kitap muvafakatname bitişi',
  protocolDate: 'Ek protokol tarihi',
  protocolEnd: 'Ek protokol bitişi',
};
const DATES = new Set(['renewalStart', 'renewalEnd', 'terminated', 'unpublishedTermination', 'rightsTransferDate', 'consentDate', 'consentEnd', 'ebookConsentDate', 'ebookConsentEnd', 'protocolDate', 'protocolEnd']);
const OPTIONS = new Set(['paymentType', 'basis', 'paymentMethod', 'currency']);
/** Lisans şartlarının ekrandaki sırası: kimlik → süre → baskı → para → belgeler. */
const ORDER = Object.keys(TERM_LABEL);

function termValue(key: string, v: string | number): string {
  if (DATES.has(key)) return day(String(v));
  if (OPTIONS.has(key)) return crmLabel(String(v));
  if (typeof v === 'number') return nf.format(v);
  return String(v);
}

/** Hak çipleri. `compact`: yalnız var olanlar ve «n hak yok» özeti (liste satırları için). */
export function RightChips({ rights, compact }: { rights: CrmRight[] | undefined; compact?: boolean }) {
  if (!rights?.length) return null;
  const yes = rights.filter((r) => r.granted === true);
  const no = rights.filter((r) => r.granted === false);
  const blank = rights.filter((r) => r.granted == null);
  if (compact) {
    return (
      <span className="flex flex-wrap gap-1">
        {yes.map((r) => (
          <span key={r.key} className="rounded-md bg-canvas-violet/10 px-1.5 py-0.5 text-[10.5px] font-bold text-canvas-violet">
            {r.label}
          </span>
        ))}
        {no.length > 0 && (
          <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-semibold text-canvas-muted" title={no.map((r) => r.label).join(', ')}>
            {nf.format(no.length)} hak yok
          </span>
        )}
        {!yes.length && !no.length && <span className="text-[11px] text-canvas-muted">Haklar CRM'de girilmemiş</span>}
      </span>
    );
  }
  const group = (items: CrmRight[], title: string, icon: 'yes' | 'no' | 'blank') =>
    items.length > 0 && (
      <div>
        <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{title}</div>
        <ul className="mt-1 flex flex-wrap gap-1.5">
          {items.map((r) => (
            <li
              key={r.key}
              className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-semibold ${icon === 'yes' ? 'bg-emerald-50 text-emerald-800' : icon === 'no' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-canvas-muted'}`}
            >
              {icon === 'yes' ? <Check aria-hidden className="h-3.5 w-3.5" /> : icon === 'no' ? <X aria-hidden className="h-3.5 w-3.5" /> : <Minus aria-hidden className="h-3.5 w-3.5" />}
              {r.label}
            </li>
          ))}
        </ul>
      </div>
    );
  return (
    <div className="space-y-2">
      {group(yes, 'Verilen haklar', 'yes')}
      {group(no, 'Verilmeyen haklar', 'no')}
      {group(blank, "CRM'de girilmemiş", 'blank')}
    </div>
  );
}

/** Lisans şartları: bayraklar, bölge/dil, dolu şart alanları ve CRM'deki açıklamalar. */
export function LicenseTerms({ license }: { license: CrmLicense | undefined }) {
  if (!license) return null;
  const keys = ORDER.filter((k) => license.terms[k] != null && license.terms[k] !== '');
  const empty = !keys.length && !license.flags.length && !license.countries.length && !license.languages.length && !license.rightsNote && !license.royaltyNote;
  if (empty) return <p className="text-[12px] text-canvas-muted">CRM'de lisans şartı girilmemiş.</p>;
  return (
    <div className="space-y-2.5 text-[12.5px]">
      {license.flags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {license.flags.map((f) => (
            <Pill key={f.key} tone="violet">
              {f.label}
            </Pill>
          ))}
        </div>
      )}
      {(license.countries.length > 0 || license.languages.length > 0) && (
        <dl className="grid gap-1 sm:grid-cols-[180px_minmax(0,1fr)]">
          {license.countries.length > 0 && (
            <>
              <dt className="text-canvas-muted">Ülkeler</dt>
              <dd className="break-words font-semibold">{license.countries.join(', ')}</dd>
            </>
          )}
          {license.languages.length > 0 && (
            <>
              <dt className="text-canvas-muted">Diller</dt>
              <dd className="break-words font-semibold">{license.languages.join(', ')}</dd>
            </>
          )}
        </dl>
      )}
      {keys.length > 0 && (
        <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[220px_minmax(0,1fr)]">
          {keys.map((k) => (
            <div key={k} className="contents">
              <dt className="text-canvas-muted">{TERM_LABEL[k]}</dt>
              <dd className="break-words font-semibold tabular-nums">{termValue(k, license.terms[k])}</dd>
            </div>
          ))}
        </dl>
      )}
      {license.rightsNote && (
        <div className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-snug text-amber-900">
          <b className="font-bold">Haklar açıklaması:</b> <span className="whitespace-pre-line">{license.rightsNote}</span>
        </div>
      )}
      {license.royaltyNote && (
        <div className="rounded-xl bg-slate-50 px-3 py-2 text-[12px] leading-snug">
          <b className="font-bold">Telif açıklaması:</b> <span className="whitespace-pre-line">{license.royaltyNote}</span>
        </div>
      )}
    </div>
  );
}

/** Liste satırında açılır ayrıntı: haklar + lisans. Yerel <details> — klavye ve ekran okuyucu kendiliğinden çalışır. */
export function RightsDetails({ rights, license }: { rights?: CrmRight[]; license?: CrmLicense }) {
  if (!rights?.length && !license) return null;
  return (
    <details className="group mt-1.5">
      <summary className="inline-flex min-h-9 cursor-pointer list-none items-center gap-1 rounded-lg text-[11.5px] font-bold text-canvas-violet [&::-webkit-details-marker]:hidden">
        Haklar ve lisans
        <span aria-hidden className="transition-transform duration-150 ease-out group-open:rotate-90 motion-reduce:transition-none">›</span>
      </summary>
      <div className="mt-1.5 space-y-2.5 rounded-xl border border-slate-100 bg-white/90 p-3">
        <RightChips rights={rights} />
        <LicenseTerms license={license} />
      </div>
    </details>
  );
}

const STATE: Record<BookRights['items'][number]['state'], { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' }> = {
  var: { label: 'Var', tone: 'ok' },
  kismi: { label: 'Kısmi', tone: 'warn' },
  yok: { label: 'Yok', tone: 'err' },
  girilmemis: { label: 'Girilmemiş', tone: 'muted' },
};

/** Kitabın hakları: yürürlükteki Telif Alış sözleşmelerinin hepsinde olan hak «var». */
export function BookRightsPanel({ rights }: { rights: BookRights | undefined }) {
  if (!rights) return null;
  if (!rights.basis) {
    return <p className="px-1 text-[12px] text-canvas-muted">Yürürlükte Telif Alış sözleşmesi yok; kitabın hakları CRM'den çıkarılamıyor.</p>;
  }
  return (
    <div className="space-y-2">
      <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">
        Yürürlükteki {nf.format(rights.basis)} Telif Alış sözleşmesinden. Hak, bu sözleşmelerin hepsinde varsa «Var»; bir kısmında varsa eksik olduğu sözleşme yazılır.
      </p>
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {rights.items.map((r) => (
          <li key={r.key} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <span className="min-w-0">
              <span className="block font-semibold">{r.label}</span>
              {r.state === 'kismi' && (
                <span className="block break-words text-[11px] text-canvas-muted">
                  {nf.format(r.yes)}/{nf.format(r.of)} sözleşmede · eksik: {r.missing.join(', ')}
                </span>
              )}
            </span>
            <Pill tone={STATE[r.state].tone}>{STATE[r.state].label}</Pill>
          </li>
        ))}
      </ul>
      {(rights.countries.length > 0 || rights.languages.length > 0) && (
        <p className="px-1 text-[12px]">
          {rights.countries.length > 0 && (
            <>
              <span className="text-canvas-muted">Ülkeler: </span>
              <b className="font-semibold">{rights.countries.join(', ')}</b>
            </>
          )}
          {rights.countries.length > 0 && rights.languages.length > 0 && ' · '}
          {rights.languages.length > 0 && (
            <>
              <span className="text-canvas-muted">Diller: </span>
              <b className="font-semibold">{rights.languages.join(', ')}</b>
            </>
          )}
        </p>
      )}
      {rights.notes.map((n, i) => (
        <div key={i} className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-snug text-amber-900">
          <b className="font-bold">{n.no ?? 'Sözleşme'} · haklar açıklaması:</b> <span className="whitespace-pre-line">{n.text}</span>
        </div>
      ))}
    </div>
  );
}
