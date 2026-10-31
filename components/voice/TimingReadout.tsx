const timingLabels: Record<string, string> = {
  endDetection: 'End detection', transcription: 'Transcription',
  firstAudioMs: 'Request → first audio', playbackMs: 'Playback elapsed', totalMs: 'Request → last audio end',
  nativeFirstAudioMs: 'Native first segment preparation', nativePlaybackMs: 'Last native segment playback',
};

export default function TimingReadout({ timings, label }: { timings?: Readonly<Record<string, number | undefined>>; label: string }) {
  const readings = Object.entries(timings ?? {}).filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1]) && entry[1] >= 0);
  if (!readings.length) return null;
  return <p className="handsfree-note" aria-label={label}>{readings.map(([stage, ms]) =>
    `${(Object.hasOwn(timingLabels, stage) ? timingLabels[stage] : undefined) || stage.replace(/([a-z])([A-Z])/g, '$1 $2').replaceAll('_', ' ')}: ${ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`}`,
  ).join(' · ')}</p>;
}
