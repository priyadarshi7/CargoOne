import { CircleCheck, Download, FileUp, TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, download, postFile, type ImportReport } from '../lib/api'

/** Two steps, so nothing is changed by accident: (1) the file is checked and a report shows exactly what would
 *  happen; (2) only then does "Import" write it. Re-importing the same file is safe. */
export default function ImportTrips() {
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
      setError(e instanceof ApiError ? e.message : 'Could not read the file.')
    } finally {
      setBusy(false)
    }
  }, [])

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
      setError(e instanceof ApiError ? e.message : 'Import failed.')
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
          <h1 className="text-2xl font-semibold">Import trips</h1>
          <p className="text-sm text-muted">Upload the day&apos;s trips as CSV or Excel, with LR and e-way bill numbers. Re-uploading the same file is safe.</p>
        </div>
        <button onClick={() => void download('/imports/trips/template', 'trips-template.csv')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-sm hover:border-accent hover:text-accent">
          <Download size={16} aria-hidden /> Download template
        </button>
      </div>

      <label className="grid cursor-pointer place-items-center gap-3 rounded-2xl border-2 border-dashed border-line px-6 py-12 text-center hover:border-accent">
        <FileUp size={32} className="text-muted" aria-hidden />
        <span className="font-medium">{file ? file.name : 'Choose a .csv or .xlsx file'}</span>
        <span className="text-xs text-muted">Columns: Trip ID, Client, Vehicle, Destination, Freight, LR No, E-way Bill No (optional: Origin, Delivery Date, Branch, Driver Phone)</span>
        <input ref={input} type="file" accept=".csv,.xlsx,.xlsm,.txt" className="sr-only" aria-label="Trip file"
          onChange={(e) => { setDone(null); setFile(e.target.files?.[0] ?? null) }} />
      </label>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={createClients} onChange={(e) => setCreateClients(e.target.checked)} />
        Create clients that do not exist yet (billing cycle starts as weekly)
      </label>

      {error && <p role="alert" className="rounded-lg bg-bad-soft px-4 py-3 text-sm text-bad">{error}</p>}
      {busy && <p className="text-sm text-muted">Working…</p>}

      {done && (
        <div className="flex items-start gap-3 rounded-xl bg-ok-soft px-5 py-4 text-ok" role="status">
          <CircleCheck className="mt-0.5 shrink-0" size={20} aria-hidden />
          <div>
            <p className="font-medium">Imported: {done.created} new, {done.updated} updated, {done.unchanged} already up to date{done.skipped ? `, ${done.skipped} left unchanged` : ''}.</p>
            {done.errors.length > 0 && <p className="text-sm">{done.errors.length} row(s) were not imported - see the list you checked, fix them in the sheet and upload again.</p>}
            <Link to="/office/trips" className="text-sm underline underline-offset-2">View trips</Link>
          </div>
        </div>
      )}

      {report && (
        <section className="space-y-6" aria-label="Check result">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {tile('will be created', report.created, 'text-ok')}
            {tile('will be updated', report.updated)}
            {tile('already up to date', report.unchanged)}
            {tile('left unchanged', report.skipped)}
            {tile('rows with problems', report.errors.length, report.errors.length ? 'text-bad' : '')}
          </div>

          {(report.new_clients.length > 0 || report.new_branches.length > 0 || report.new_vehicles > 0) && (
            <p className="text-sm text-muted">
              Also new: {[report.new_clients.length && `${report.new_clients.length} client(s) (${report.new_clients.join(', ')})`,
                report.new_branches.length && `${report.new_branches.length} branch(es) (${report.new_branches.join(', ')})`,
                report.new_vehicles && `${report.new_vehicles} vehicle(s)`].filter(Boolean).join(' · ')}
            </p>
          )}

          {report.errors.length > 0 && (
            <div>
              <h2 className="mb-2 flex items-center gap-2 font-semibold text-bad"><TriangleAlert size={18} aria-hidden /> Fix these rows in your sheet</h2>
              <div className="overflow-x-auto rounded-xl border border-line">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="bg-wash text-muted"><tr><th className="px-4 py-2 font-medium">Row</th><th className="px-4 py-2 font-medium">Trip</th><th className="px-4 py-2 font-medium">Problem</th></tr></thead>
                  <tbody>{report.errors.slice(0, 100).map((e) => (
                    <tr key={`${e.row}-${e.message}`} className="border-t border-line"><td className="px-4 py-2 tabular-nums">{e.row}</td><td className="px-4 py-2">{e.trip_code ?? '—'}</td><td className="px-4 py-2">{e.message}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              {report.errors.length > 100 && <p className="mt-2 text-xs text-muted">Showing the first 100 of {report.errors.length}.</p>}
            </div>
          )}

          {report.warnings.length > 0 && (
            <ul className="space-y-1 text-sm text-muted">{report.warnings.slice(0, 20).map((w) => <li key={w.row}>Row {w.row} ({w.trip_code}): {w.message}</li>)}</ul>
          )}

          <div className="flex items-center gap-4">
            <button disabled={busy || importable === 0} onClick={() => void commit()}
              className="rounded-lg bg-accent px-5 py-2.5 font-medium text-white disabled:opacity-50">
              {importable === 0 ? 'Nothing to import' : `Import ${importable} trip${importable === 1 ? '' : 's'}`}
            </button>
            {report.errors.length > 0 && importable > 0 && <span className="text-sm text-muted">Rows with problems are skipped; the rest are imported.</span>}
          </div>
        </section>
      )}
    </div>
  )
}
