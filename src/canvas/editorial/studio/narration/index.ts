/** Kitap Tasarım Stüdyosu — sesli okuma (seslendirme, okunan kelime vurgulu önizleme, sesler, telaffuz sözlüğü).
 *  Model seçimi ve lisans: docs/analiz/sesli-okuma-model-secimi.md. */
export { default as NarrationSection } from './NarrationSection';
export { default as ReadAlong, wordAt } from './ReadAlong';
export { narrationApi, useNarration, useNarrationPage, NarrationError } from './api';
export { default as SoundEffects } from './SoundEffects';
export { sfxApi, useSfx, SfxError } from './sfxApi';
export type { HumanRecording, LexEntry, NarrationBlock, NarrationJob, NarrationOverview, NarrationPage, NarrationPageRow,
  NarrationSettings, NarrationVoice, NarrationWord } from './api';
