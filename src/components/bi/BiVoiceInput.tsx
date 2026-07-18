import { Mic, MicOff } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getLocale, t } from '@/i18n';

type Props = {
  onTranscript: (text: string) => void;
  disabled?: boolean;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((ev: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};

export default function BiVoiceInput({ onTranscript, disabled }: Props) {
  const [listening, setListening] = useState(false);
  const [supported, setSupported] = useState(false);
  const recRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    const W = window as Window & { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike };
    const SR = W.SpeechRecognition || W.webkitSpeechRecognition;
    setSupported(Boolean(SR));
    if (!SR) return;
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = false;
    const loc = getLocale();
    rec.lang = loc === 'tr' ? 'tr-TR' : 'en-US';
    rec.onresult = (ev) => {
      const text = ev.results[0]?.[0]?.transcript ?? '';
      if (text) onTranscript(text);
      setListening(false);
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
  }, [onTranscript]);

  const toggle = useCallback(() => {
    const rec = recRef.current;
    if (!rec || disabled) return;
    if (listening) {
      rec.stop();
      setListening(false);
      return;
    }
    setListening(true);
    rec.start();
  }, [disabled, listening]);

  if (!supported) return null;

  return (
    <button
      type="button"
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition-colors ${
        listening
          ? 'border-red-300 bg-red-50 text-red-600'
          : 'border-violet-200 bg-white text-violet-600 hover:bg-violet-50'
      }`}
      onClick={toggle}
      disabled={disabled}
      title={t('bi.voiceInput')}
    >
      {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
    </button>
  );
}
