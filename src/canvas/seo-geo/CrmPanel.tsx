import { Check, ExternalLink, Minus } from 'lucide-react';
import { FLAG_LABEL, RIGHTS_LABEL, RIGHTS_TONE, type CrmBook } from './api';

/** Ürünün CRM kitap kartı: internette gösterim hakkı (Google önizlemesi, tadımlık PDF), yayın durumu ve SEO/GEO'ya
 *  kaynak olabilecek bilgiler. Yalnız okunur; hak kararı ön süzgeçtir, kesin söz telif biriminindir. */
export default function CrmPanel({ book, tsoft }: { book: CrmBook | null; tsoft?: { words: number; hasMeta: boolean } }) {
  if (!book) {
    return (
      <section className="sg-card" aria-label="CRM kitap kartı">
        <h2>CRM kitap kartı</h2>
        <p className="sg-sub" style={{ margin: 0 }}>
          Bu ürünün barkodu CRM’deki hiçbir kitap kartıyla eşleşmedi; hak ve yayın durumu bilinmiyor. Barkod ya da CRM kartındaki EAN-13 kontrol edilmeli.
        </p>
      </section>
    );
  }
  const age = book.ageFrom || book.ageTo ? `${book.ageFrom ?? '?'}–${book.ageTo ?? '?'} yaş` : null;
  const facts: Array<[string, React.ReactNode]> = [
    ['Yayın durumu', book.statusLabel],
    ['Yazar', book.authors],
    ['Çizer', book.illustrators],
    ['Çevirmen', book.translators],
    ['Özgün ad', [book.originalTitle, book.originalLanguage].filter(Boolean).join(' · ') || null],
    ['İlk yayın', [book.firstPublished, book.firstCountry].filter(Boolean).join(' · ') || null],
    ['Önceki yayınevi', book.previousPublisher],
    ['Hedef kitle', [book.audience, age].filter(Boolean).join(' · ') || null],
    ['Tür', book.genres],
    ['Web kategorisi', book.webCategories],
    ['Anahtar kelime', [book.keywords, book.hashtags].filter(Boolean).join(' · ') || null],
    ['E-kitap ISBN', book.ebookIsbn],
    ['Tadımlık PDF', book.previewPdf && <Ext href={book.previewPdf}>Aç</Ext>],
    ['Video', book.video && <Ext href={book.video}>Aç</Ext>],
  ];
  const texts: Array<[string, string | null]> = [
    ['Spot', book.spot],
    ['Özet', book.summary],
    ['Tanıtım metni', book.promo],
    ['Öne çıkan yanları', book.highlights],
    ['Alıntılar', book.quotes],
  ];
  const hints = [
    tsoft && tsoft.words < 80 && (book.summary || book.promo) && 'T-soft açıklaması kısa; CRM’deki özet ve tanıtım metni açıklamaya kaynak olabilir.',
    book.video && 'CRM’de tanıtım videosu var; ürün sayfasında video şeması (VideoObject) kullanılabilir.',
    book.originalTitle && 'Özgün ad sayfada ve şemada (translationOfWork) yer alırsa özgün adla yapılan aramalarda da bulunur.',
  ].filter(Boolean) as string[];

  return (
    <section className="sg-card" aria-label="CRM kitap kartı">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div style={{ minWidth: 0 }}>
          <h2>CRM kitap kartı ve haklar</h2>
          <p className="sg-sub" style={{ margin: 0 }}>{book.name}</p>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className={`sg-chip ${RIGHTS_TONE[book.rights]}`}>{RIGHTS_LABEL[book.rights]}</span>
          {book.statusFlag && <span className="sg-chip bad">{FLAG_LABEL[book.statusFlag]}</span>}
        </div>
      </div>

      {book.statusFlag && (
        <p className="sg-banner err" style={{ marginTop: 12 }}>
          CRM’de bu kitap <b>{book.statusLabel}</b> durumunda ama T-soft’ta satışta. Önerilerde ve Google Kitaplar’da önceliği yok; ürünün sitede kalıp kalmayacağına yayın birimi karar vermeli.
        </p>
      )}
      <p className="sg-sub" style={{ margin: '12px 0 0' }}>
        <b>İnternette gösterim hakkı:</b> {book.rightsWhy} Google Kitaplar önizlemesi ve tadımlık PDF bu hakka bağlıdır; kesin karar telif biriminindir.
      </p>

      {book.contracts.length > 0 && (
        <div className="sg-table-wrap" style={{ marginTop: 12 }}>
          <table className="sg-table">
            <caption className="sg-tag" style={{ textAlign: 'left', paddingBottom: 6 }}>TELİF ALIŞ SÖZLEŞMELERİ</caption>
            <thead>
              <tr>
                <th>Taraf</th>
                <th>Durum</th>
                <th style={{ textAlign: 'center' }}>İnternet</th>
                <th style={{ textAlign: 'center' }}>E-kitap</th>
                <th style={{ textAlign: 'center' }}>Z-kitap</th>
                <th style={{ textAlign: 'center' }}>Sesli</th>
              </tr>
            </thead>
            <tbody>
              {book.contracts.map((c, i) => (
                <tr key={`${c.name}-${i}`} style={c.inForce ? undefined : { color: 'var(--sg-muted)' }}>
                  <td style={{ minWidth: 160 }}>
                    {c.parties.join(', ') || '—'}
                    <div className="sg-mono" style={{ fontSize: 11, color: 'var(--sg-muted)' }}>{c.name}</div>
                    {c.note && <div style={{ fontSize: 11.5, marginTop: 4 }}>Not: {c.note}</div>}
                  </td>
                  <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    {c.publicDomain ? 'Koruma dışı' : c.inForce ? (c.openEnded ? 'Süresiz' : `Yürürlükte · ${c.ends ?? '—'}`) : `Yürürlükte değil${c.ends ? ` · ${c.ends}` : ''}`}
                  </td>
                  <Yes on={c.internet} label="İnternette gösterim" />
                  <Yes on={c.ebook} label="E-kitap" />
                  <Yes on={c.zbook} label="Z-kitap" />
                  <Yes on={c.audiobook} label="Sesli kitap" />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="sg-tag" style={{ marginTop: 16 }}>SEO VE YAPAY ZEKÂ İÇİN CRM’DEKİ BİLGİ</p>
      <dl className="sg-facts">
        {facts
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
      {texts.some(([, v]) => v) && (
        <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
          {texts
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <details key={k} className="sg-more">
                <summary>{k}</summary>
                <p>{v}</p>
              </details>
            ))}
        </div>
      )}
      {hints.length > 0 && (
        <ul className="sg-hints">
          {hints.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Yes({ on, label }: { on: boolean; label: string }) {
  return (
    <td style={{ textAlign: 'center' }} aria-label={`${label}: ${on ? 'var' : 'yok'}`}>
      {on ? <Check size={15} color="#0f7a51" aria-hidden /> : <Minus size={15} color="#c2361b" aria-hidden />}
    </td>
  );
}

function Ext({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
      {children} <ExternalLink size={11} aria-hidden />
    </a>
  );
}
