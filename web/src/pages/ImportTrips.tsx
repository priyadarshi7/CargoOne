import { CircleCheck, Download, FileUp, TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, download, postFile, type ImportReport } from '../lib/api'
import { useI18n } from '../lib/i18n'

/** Two steps, so nothing is changed by accident: (1) the file is checked and a report shows exactly what would
 *  happen; (2) only then does "Import" write it. Re-importing the same file is safe. */
export default function ImportTrips() {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [createClients, setCreateClients] = useState(false)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [done, setDone] = useState<ImportReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const check = useCallback(async (f: File, create: boolean) => {
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      setReport(await postFile<ImportReport>(`/imports/trips?dry_run=true&create_clients=${create}`, f))
    } catch (e) {
      setReport(null)
      setError(e instanceof ApiError ? e.message : t('imp.readFail'))
    } finally {
      setBusy(false)
    }
  }, [t])

  useEffect(() => { if (file) void check(file, createClients) }, [file, createClients, check])

  async function commit() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      setDone(await postFile<ImportReport>(`/imports/trips?dry_run=false&create_clients=${createClients}`, file))
      setReport(null)
      setFile(null)
      if (input.current) input.current.value = ''
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('imp.failed'))
    } finally {
      setBusy(false)
    }
  }

  const importable = report ? report.created + report.updated : 0
  const tile = (label: string, n: number, tone = '') => (
    <div className="rounded-xl border border-line p-4"><div className={`text-2xl font-semibold tabular-nums ${tone}`}>{n}</div><div className="text-sm text-muted">{label}</div></div>
  )

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t('imp.title')}</h1>
          <p className="text-sm text-muted">{t('imp.sub')}</p>
        </div>
        <button onClick={() => void download('/imports/trips/template', 'trips-template.csv')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-sm hover:border-accent hover:text-accent">
          <Download size={16} aria-hidden /> {t('imp.template')}
        </button>
      </div>

      <label className="grid cursor-pointer place-items-center gap-3 rounded-2xl border-2 border-dashed border-line px-6 py-12 text-center hover:border-accent">
        <FileUp size={32} className="text-muted" aria-hidden />
        <span className="font-medium">{file ? file.name : t('imp.choose')}</span>
        <span className="text-xs text-muted">{t('imp.columns')}</span>
        <input ref={input} type="file" accept=".csv,.xlsx,.xlsm,.txt" className="sr-only" aria-label="Trip file"
          onChange={(e) => { setDone(null); setFile(e.target.files?.[0] ?? null) }} />
      </label>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={createClients} onChange={(e) => setCreateClients(e.target.checked)} />
        {t('imp.create')}
      </label>

      {error && <p role="alert" className="rounded-lg bg-bad-soft px-4 py-3 text-sm text-bad">{error}</p>}
      {busy && <p className="text-sm text-muted">{t('imp.working')}</p>}

      {done && (
        <div className="flex items-start gap-3 rounded-xl bg-ok-soft px-5 py-4 text-ok" role="status">
          <CircleCheck className="mt-0.5 shrink-0" size={20} aria-hidden />
          <div>
            <p className="font-medium">{t('imp.done', { c: done.created, u: done.updated, n: done.unchanged })}{done.skipped ? t('imp.doneSkipped', { n: done.skipped }) : ''}.</p>
            {done.errors.length > 0 && <p className="text-sm">{t('imp.doneErrors', { n: done.errors.length })}</p>}
            <Link to="/office/trips" className="text-sm underline underline-offset-2">{t('imp.view')}</Link>
          </div>
        </div>
      )}

      {report && (
        <section className="space-y-6" aria-label={t('imp.result')}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {tile(t('imp.willCreate'), report.created, 'text-ok')}
            {tile(t('imp.willUpdate'), report.updated)}
            {tile(t('imp.upToDate'), report.unchanged)}
            {tile(t('imp.leftUnchanged'), report.skipped)}
            {tile(t('imp.problems'), report.errors.length, report.errors.length ? 'text-bad' : '')}
          </div>

          {(report.new_clients.length > 0 || report.new_branches.length > 0 || report.new_vehicles > 0) && (
            <p className="text-sm text-muted">
              {t('imp.alsoNew')}: {[report.new_clients.length && `${report.new_clients.length} client(s) (${report.new_clients.join(', ')})`,
                report.new_branches.length && `${report.new_branches.length} branch(es) (${report.new_branches.join(', ')})`,
                report.new_vehicles && `${report.new_vehicles} vehicle(s)`].filter(Boolean).join(' · ')}
            </p>
          )}

          {report.errors.length > 0 && (
            <div>
              <h2 className="mb-2 flex items-center gap-2 font-semibold text-bad"><TriangleAlert size={18} aria-hidden /> {t('imp.fix')}</h2>
              <div className="overflow-x-auto rounded-xl border border-line">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="bg-wash text-muted"><tr><th className="px-4 py-2 font-medium">{t('imp.row')}</th><th className="px-4 py-2 font-medium">{t('imp.tripCol')}</th><th className="px-4 py-2 font-medium">{t('imp.problemCol')}</th></tr></thead>
                  <tbody>{report.errors.slice(0, 100).map((e) => (
                    <tr key={`${e.row}-${e.message}`} className="border-t border-line"><td className="px-4 py-2 tabular-nums">{e.row}</td><td className="px-4 py-2">{e.trip_code ?? '—'}</td><td className="px-4 py-2">{e.message}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              {report.errors.length > 100 && <p className="mt-2 text-xs text-muted">{t('imp.firstN', { n: 100, total: report.errors.length })}</p>}
            </div>
          )}

          {report.warnings.length > 0 && (
            <ul className="space-y-1 text-sm text-muted">{report.warnings.slice(0, 20).map((w) => <li key={w.row}>{t('imp.row')} {w.row} ({w.trip_code}): {w.message}</li>)}</ul>
          )}

          <div className="flex items-center gap-4">
            <button disabled={busy || importable === 0} onClick={() => void commit()}
              className="rounded-lg bg-ink px-5 py-2.5 font-medium text-surface disabled:opacity-50">
              {importable === 0 ? t('imp.nothing') : importable === 1 ? t('imp.btn1') : t('imp.btn', { n: importable })}
            </button>
            {report.errors.length > 0 && importable > 0 && <span className="text-sm text-muted">{t('imp.skippedNote')}</span>}
          </div>
        </section>
      )}
    </div>
  )
}
