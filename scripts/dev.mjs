#!/usr/bin/env node
// One command for the whole local setup:   node scripts/dev.mjs   (or: pnpm dev:all, from web/)
//   node scripts/dev.mjs --tunnel     also opens a phone link (Cloudflare quick tunnel) and prints it
//
// It starts and watches everything, so nothing is restarted by hand:
//   - Postgres (Docker; starts Docker Desktop if it is closed) and runs database migrations
//   - Ollama (the local vision model)
//   - the API, restarted at once when you change app/.env (code changes reload by themselves)
//   - the phone build: rebuilt on every change to web/ and served on :4173 (what the tunnel shows)
// Press Ctrl+C once to stop everything it started, including leftovers. Run it again any time: it first clears stale processes.
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, watch } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const API = join(ROOT, 'api')
const WEB = join(ROOT, 'web')
const ENV = join(ROOT, '.env')
const WANT_TUNNEL = process.argv.includes('--tunnel')
const IS_WIN = process.platform === 'win32'
const WEB_RX = WEB.replace(/[\\^$.*+?()[\]{}|]/g, '\\$&') // the web folder, escaped for a regular expression

const COLORS = { api: 36, build: 35, web: 34, ollama: 33, tunnel: 32, dev: 90 }
const say = (who, text) => text.split(/\r?\n/).filter((l) => l.trim()).forEach((l) => console.log(`\x1b[${COLORS[who] ?? 0}m${who.padEnd(6)}\x1b[0m ${l}`))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const run = (cmd, args, opts = {}) => spawnSync(cmd, args, { encoding: 'utf8', shell: IS_WIN, ...opts })

async function up(url, tries = 40) {
  for (let i = 0; i < tries; i++) {
    try { if ((await fetch(url, { signal: AbortSignal.timeout(2000) })).ok) return true } catch { /* not yet */ }
    await sleep(1500)
  }
  return false
}

// ---------------------------------------------------------------- stale processes (the cause of "I changed it and nothing changed")
function clearStale(only = 'all') { // only='api': leave the phone build and web server alone (used when .env changes)
  if (!IS_WIN) return
  const ps = `
    $procs = Get-CimInstance Win32_Process
    $alive = $procs.ProcessId
    $procs | Where-Object {
      ($_.CommandLine -match 'uvicorn app.main:app' -or (${only === 'all' ? '$true' : '$false'} -and $_.CommandLine -match '${WEB_RX}.*vite.*\\b(preview|build)\\b') -or ($_.CommandLine -match 'spawn_main' -and $alive -notcontains $_.ParentProcessId))
      -and $_.ProcessId -ne ${process.pid} -and $_.ProcessId -ne $PID
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }`
  // -EncodedCommand: the script goes in as base64, so Windows shell quoting cannot mangle it
  const out = spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(ps, 'utf16le').toString('base64')], { encoding: 'utf8' }).stdout?.trim()
  if (out) say('dev', `cleared stale processes: ${out.split(/\s+/).join(', ')}`)
}

const children = new Map()
function killTree(child) {
  if (!child?.pid) return
  if (IS_WIN) spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  else try { process.kill(-child.pid, 'SIGTERM') } catch { /* gone */ }
}
function start(name, cmd, args, opts = {}) {
  const child = spawn(cmd, args, { shell: IS_WIN, detached: !IS_WIN, windowsHide: true, ...opts })
  children.set(name, child)
  child.stdout.on('data', (d) => say(name, String(d)))
  child.stderr.on('data', (d) => say(name, String(d)))
  child.on('exit', (code) => { if (children.get(name) === child && !shuttingDown && !restarting.has(name)) say(name, `stopped (exit ${code})`) })
  return child
}
let shuttingDown = false
const restarting = new Set()
function shutdown() {
  if (shuttingDown) return
  shuttingDown = true
  console.log('\nstopping everything…')
  for (const c of children.values()) killTree(c)
  setTimeout(() => process.exit(0), 500)
}
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)

// ---------------------------------------------------------------- 1. database
async function database() {
  if (run('docker', ['info']).status !== 0) {
    const exe = 'C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe'
    if (IS_WIN && existsSync(exe)) { say('dev', 'starting Docker Desktop…'); spawn(exe, [], { detached: true, stdio: 'ignore' }).unref() }
    for (let i = 0; i < 60 && run('docker', ['info']).status !== 0; i++) await sleep(3000)
    if (run('docker', ['info']).status !== 0) throw new Error('Docker is not running. Open Docker Desktop and run this again.')
  }
  run('docker', ['compose', 'up', '-d', 'db'], { cwd: ROOT })
  for (let i = 0; i < 30; i++) {
    if (run('docker', ['compose', 'exec', '-T', 'db', 'pg_isready', '-U', 'cargoone'], { cwd: ROOT }).status === 0) break
    await sleep(1500)
  }
  const m = run('uv', ['run', 'alembic', 'upgrade', 'head'], { cwd: API })
  if (m.status !== 0) say('dev', `migrations failed:\n${(m.stderr || m.stdout || '').slice(-600)}`)
  else say('dev', 'database ready, migrations up to date')
}

// ---------------------------------------------------------------- 2. ollama
async function ollama() {
  if (await up('http://localhost:11434/api/version', 1)) return say('ollama', 'already running')
  start('ollama', 'ollama', ['serve'])
  say('ollama', (await up('http://localhost:11434/api/version', 20)) ? 'ready' : 'did not start (is Ollama installed?). The local AI reader will not work.')
}

// ---------------------------------------------------------------- 3. api (restarts when .env changes)
function startApi(only = 'all') {
  clearStale(only)
  return start('api', 'uv', ['run', 'uvicorn', 'app.main:app', '--port', '8000', '--reload'], { cwd: API })
}
function watchEnv() {
  if (!existsSync(ENV)) return say('dev', `no ${ENV} (copy .env.example)`)
  let timer
  watch(ENV, () => {
    clearTimeout(timer)
    timer = setTimeout(async () => {
      say('dev', '.env changed: restarting the API')
      restarting.add('api')
      killTree(children.get('api'))
      await sleep(1200)
      restarting.delete('api')
      startApi('api') // clears leftovers of the API only: the phone build and web server keep running
      say('api', (await up('http://localhost:8000/health', 40)) ? 'back up with the new settings' : 'did not come back, see messages above')
    }, 600)
  })
  say('dev', 'watching .env: saving it restarts the API by itself')
}

// ---------------------------------------------------------------- 4. phone build (rebuilds on every change, served on 4173)
async function web() {
  const first = run('pnpm', ['exec', 'vite', 'build'], { cwd: WEB })
  say('build', first.status === 0 ? 'built' : `first build failed:\n${(first.stderr || first.stdout || '').slice(-800)}`)
  start('build', 'pnpm', ['exec', 'vite', 'build', '--watch'], { cwd: WEB })
  start('web', 'pnpm', ['exec', 'vite', 'preview', '--port', '4173', '--strictPort'], { cwd: WEB })
}

// ---------------------------------------------------------------- 5. tunnel (optional)
function tunnel() {
  const child = start('tunnel', 'cloudflared', ['tunnel', '--url', 'http://localhost:4173'])
  const seen = (d) => { const m = String(d).match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/); if (m) console.log(`\n  PHONE LINK  ${m[0]}\n`) }
  child.stdout.on('data', seen)
  child.stderr.on('data', seen)
}

// ---------------------------------------------------------------- go
try {
  clearStale()
  await database()
  await ollama()
  startApi()
  watchEnv()
  await web()
  if (WANT_TUNNEL) tunnel()
  const [a, w] = await Promise.all([up('http://localhost:8000/health'), up('http://localhost:4173/api/health')])
  console.log(`\n  API    http://localhost:8000          ${a ? 'ok' : 'NOT UP'}\n  Phone  http://localhost:4173          ${w ? 'ok (reaches the API)' : 'NOT UP'}\n  Edit web/ or api/ code or app/.env: it updates by itself. Ctrl+C stops everything.\n`)
} catch (e) {
  console.error(`\n${e.message}`)
  shutdown()
}
