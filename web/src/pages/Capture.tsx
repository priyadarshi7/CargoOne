import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CaptureFlow } from '../components/CaptureFlow'
import { api, type Trip } from '../lib/api'
import { useI18n } from '../lib/i18n'

/** Logged-in driver: capture for one of their own trips. */
export default function Capture() {
  const { id = '' } = useParams()
  const { lang, setLang } = useI18n()
  const [trip, setTrip] = useState<Trip | null>(null)

  useEffect(() => {
    api<Trip[]>('/trips/mine').then((ts) => setTrip(ts.find((t) => t.id === id) ?? null)).catch(() => undefined)
  }, [id])

  return <CaptureFlow tripId={id} destination={trip?.destination ?? ''} lang={lang} onLang={setLang} backTo="/driver" />
}
