import { lazy, Suspense, useState } from 'react';
import { ChevronDown, Code2 } from 'lucide-react';
import type { ReportExplain } from './api';

const SqlCode = lazy(() => import('./SqlCode'));

/** Sekmenin altındaki son kullanıcı açıklaması: neye baktık, nasıl okunur, ne kadar tuttu; en altta SQL'ler. */
export default function ExplainPanel({ explain }: { explain: ReportExplain }) {
  return (
    <section className="mg-explain" aria-labelledby="mg-explain-title">
      <h2 id="mg-explain-title">{explain.title}</h2>
      <div className="mg-explain-intro">
        {explain.intro.map((p) => (
          <p key={p}>{p}</p>
        ))}
      </div>

      <div className="mg-explain-grid">
        {explain.sections.map((s) => (
          <div key={s.title} className="mg-explain-card">
            <h3>{s.title}</h3>
            <ul>
              {s.items.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {explain.table && (
        <div className="mg-explain-card">
          <h3>Ne kadar tuttu</h3>
          <div className="mg-explain-table-wrap">
            <table className="mg-explain-table">
              <caption>{explain.table.caption}</caption>
              <thead>
                <tr>
                  {explain.table.head.map((h, i) => (
                    <th key={h} scope="col" className={i > 0 ? 'is-num' : undefined}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {explain.table.rows.map((r) => (
                  <tr key={r[0]}>
                    {r.map((c, i) => (i === 0 ? <th key={i} scope="row">{c}</th> : <td key={i} className="is-num">{c}</td>))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mg-explain-card">
        <h3>Bilmeniz gerekenler</h3>
        <ul>
          {explain.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </div>

      {explain.formulas && explain.formulas.length > 0 && (
        <div className="mg-explain-card">
          <h3>Hesaplamalar</h3>
          <dl className="mg-explain-formulas">
            {explain.formulas.map((f) => (
              <div key={f.name}>
                <dt>{f.name}</dt>
                <dd>{f.text}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {explain.sql.length > 0 && (
        <div className="mg-src-group">
          <h3>
            <Code2 size={13} aria-hidden /> Kullanılan SQL
          </h3>
          {explain.sql.map((s) => (
            <SqlBlock key={s.id} title={s.title} description={s.description} sql={s.sql} />
          ))}
        </div>
      )}
    </section>
  );
}

function SqlBlock({ title, description, sql }: { title: string; description: string; sql: string }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="mg-src">
      <button type="button" className="mg-src-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="mg-src-name">
          <strong>{title}</strong>
          <span>{description}</span>
        </span>
        <ChevronDown size={16} aria-hidden className={`mg-explain-chevron${open ? ' is-open' : ''}`} />
      </button>
      {open && (
        <Suspense fallback={<pre className="mg-sql-code"><code>{sql}</code></pre>}>
          <SqlCode sql={sql} label={title} />
        </Suspense>
      )}
    </article>
  );
}
