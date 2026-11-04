import type { User } from './api'

type Lang = User['language']
export type VoiceKey =
  | 'ok' | 'retake_blurry' | 'retake_dark' | 'retake_glare' | 'retake_stamp' | 'retake_signature' | 'retake_lr' | 'retake_not_pod' | 'review' | 'saved_offline'

/** Spoken prompts. TODO(pilot): replace with recorded audio by a native speaker, and have these
 *  Hindi/Marathi lines reviewed — they were drafted without a native review. */
const TEXT: Record<Lang, Record<VoiceKey, string>> = {
  hi: {
    ok: 'ठीक है। रसीद मिल गई।',
    retake_blurry: 'फोटो साफ़ नहीं है। कृपया दोबारा खींचिए।',
    retake_dark: 'फोटो बहुत अँधेरा है। रोशनी में दोबारा खींचिए।',
    retake_glare: 'फोटो में चमक है। रसीद को थोड़ा तिरछा करके दोबारा खींचिए।',
    retake_stamp: 'मुहर दिखाई नहीं दे रही। मुहर के साथ दोबारा फोटो खींचिए।',
    retake_signature: 'हस्ताक्षर दिखाई नहीं दे रहे। हस्ताक्षर के साथ दोबारा फोटो खींचिए।',
    retake_lr: 'एल आर नंबर मेल नहीं खा रहा। सही रसीद की फोटो खींचिए।',
    retake_not_pod: 'यह रसीद नहीं लग रही। रसीद की फोटो खींचिए।',
    review: 'रसीद जाँच के लिए भेज दी गई है।',
    saved_offline: 'नेटवर्क नहीं है। फोटो सुरक्षित है, नेटवर्क आते ही चली जाएगी।',
  },
  mr: {
    ok: 'ठीक आहे. पावती मिळाली.',
    retake_blurry: 'फोटो स्पष्ट नाही. कृपया पुन्हा काढा.',
    retake_dark: 'फोटो खूप अंधारा आहे. प्रकाशात पुन्हा काढा.',
    retake_glare: 'फोटोत चकाकी आहे. पावती थोडी तिरपी करून पुन्हा काढा.',
    retake_stamp: 'शिक्का दिसत नाही. शिक्क्यासह पुन्हा फोटो काढा.',
    retake_signature: 'सही दिसत नाही. सहीसह पुन्हा फोटो काढा.',
    retake_lr: 'एल आर क्रमांक जुळत नाही. योग्य पावतीचा फोटो काढा.',
    retake_not_pod: 'ही पावती वाटत नाही. पावतीचा फोटो काढा.',
    review: 'पावती तपासणीसाठी पाठवली आहे.',
    saved_offline: 'नेटवर्क नाही. फोटो सुरक्षित आहे, नेटवर्क येताच जाईल.',
  },
  en: {
    ok: 'All good. Receipt received.',
    retake_blurry: 'The photo is not clear. Please take it again.',
    retake_dark: 'The photo is too dark. Take it again in better light.',
    retake_glare: 'There is glare on the photo. Tilt the receipt a little and take it again.',
    retake_stamp: 'The stamp is not visible. Take the photo again with the stamp.',
    retake_signature: 'The signature is not visible. Take the photo again with the signature.',
    retake_lr: 'The LR number does not match. Photograph the correct receipt.',
    retake_not_pod: 'This does not look like the receipt. Photograph the receipt.',
    review: 'The receipt has been sent for checking.',
    saved_offline: 'No network. The photo is safe and will upload when the network returns.',
  },
}

const BCP47: Record<Lang, string> = { hi: 'hi-IN', mr: 'mr-IN', en: 'en-IN' }

export const voiceText = (lang: Lang, key: string): string =>
  TEXT[lang][(key in TEXT.en ? key : 'review') as VoiceKey]

export function speak(lang: Lang, key: string): void {
  if (!('speechSynthesis' in window)) return
  const synth = window.speechSynthesis
  const voices = synth.getVoices()
  // Many Android phones ship no Marathi voice; Hindi reads Devanagari acceptably.
  const wanted = BCP47[lang]
  const voice = voices.find((v) => v.lang === wanted) ?? (lang === 'mr' ? voices.find((v) => v.lang === 'hi-IN') : undefined)
  const u = new SpeechSynthesisUtterance(voiceText(lang, key))
  u.lang = voice?.lang ?? wanted
  if (voice) u.voice = voice
  u.rate = 0.9
  synth.cancel()
  synth.speak(u)
}
