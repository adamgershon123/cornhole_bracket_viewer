import { Check, Clipboard, Download, Share2, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  copyImage,
  createBracketSnapshot,
  createFinalResultSnapshot,
  createPlayerStatusSnapshot,
  createTeamGradesSnapshot,
  createPlayerGradesSnapshot,
  createMatchGradeSnapshot,
  createTaleOfTapeSnapshot,
  downloadImage,
  shareImage,
  type BracketSnapshotData,
  type FinalResultSnapshotInput,
  type PlayerStatusSnapshotInput,
  type SnapshotEventDetails,
  type TaleOfTapeSnapshotInput,
  type TeamGradesSnapshotInput,
  type PlayerGradesSnapshotInput,
  type MatchGradeSnapshotInput,
} from '../lib/shareSnapshot';

function ReportCardShareButton({ label, title, filename, create }: { label: string; title: string; filename: string; create: () => Promise<Blob> }) {
  const [open, setOpen] = useState(false), [blob, setBlob] = useState<Blob>(), [preview, setPreview] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  async function show() { setOpen(true); setBusy(true); setNotice(''); try { const next = await create(); setBlob(next); setPreview(current => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(next); }); } catch (error: any) { setNotice(error.message || 'Snapshot creation failed.'); } finally { setBusy(false); } }
  async function run(action: 'share' | 'copy' | 'download') { if (!blob) return; try { if (action === 'share') await shareImage(blob, filename, title); else if (action === 'copy') await copyImage(blob); else downloadImage(blob, filename); setNotice(action === 'copy' ? 'Image copied — paste it into your message.' : action === 'download' ? 'Image downloaded.' : 'Share sheet opened.'); } catch (error: any) { setNotice(error.message || 'That action is unavailable. Download will preserve the same image.'); } }
  return <><button type="button" onClick={show} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-amber-300/35 bg-amber-300/10 px-4 py-3 text-sm font-black text-amber-100 transition hover:bg-amber-300/20 active:translate-y-px"><Share2 size={18}/>{label}</button>{open && <SnapshotDialog title={title} preview={preview} busy={busy} notice={notice} onClose={() => setOpen(false)} onAction={run}/>}</>;
}

export const ShareTeamGradesButton = ({ input }: { input: TeamGradesSnapshotInput }) => <ReportCardShareButton label="Share Team Grades" title="Team Grade Report Cards" filename={`cheesebaggers-team-grades-${input.eventId}.png`} create={() => createTeamGradesSnapshot(input)}/>;
export const SharePlayerGradesButton = ({ input }: { input: PlayerGradesSnapshotInput }) => <ReportCardShareButton label="Share Player Grades + MVP" title="Player Grades and MVP Rankings" filename={`cheesebaggers-player-grades-${input.eventId}.png`} create={() => createPlayerGradesSnapshot(input)}/>;
export const ShareMatchGradeButton = ({ input }: { input: MatchGradeSnapshotInput }) => <ReportCardShareButton label="Share Complete Match Card" title="Detailed Match Report Card" filename={`cheesebaggers-match-grade-${input.eventId}-${input.report?.matchId}-${input.report?.gameId}.png`} create={() => createMatchGradeSnapshot(input)}/>;

export function SharePlayerStatusSnapshotButton({ input }: { input: PlayerStatusSnapshotInput }) {
  const [open, setOpen] = useState(false);
  const [blob, setBlob] = useState<Blob>();
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const filename = `cheesebaggers-status-${input.eventId}-${input.playerId}.png`;
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  async function show() {
    setOpen(true); setBusy(true); setNotice('');
    try {
      const nextBlob = await createPlayerStatusSnapshot(input);
      setBlob(nextBlob);
      setPreview(current => { if (current) URL.revokeObjectURL(current); return URL.createObjectURL(nextBlob); });
    } catch (error: any) {
      setNotice(error.message || 'Snapshot creation failed.');
    } finally {
      setBusy(false);
    }
  }
  async function run(action: 'share' | 'copy' | 'download') {
    if (!blob) return;
    try {
      if (action === 'share') await shareImage(blob, filename, `${input.playerName} tournament status`);
      else if (action === 'copy') await copyImage(blob);
      else downloadImage(blob, filename);
      setNotice(action === 'copy' ? 'Image copied — paste it into your message.' : action === 'download' ? 'Image downloaded.' : 'Share sheet opened.');
    } catch (error: any) {
      setNotice(error.message || 'That action is unavailable. You can download the image instead.');
    }
  }
  return <>
    <button type="button" onClick={show} className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl border border-amber-300/35 bg-amber-300/10 px-4 text-base font-black text-amber-100 transition active:translate-y-px active:bg-amber-300/20">
      <Share2 size={19}/> Share Status Image
    </button>
    {open && <SnapshotDialog title="Player Tournament Status" preview={preview} busy={busy} notice={notice} onClose={() => setOpen(false)} onAction={run}/>}
  </>;
}

export function ShareFinalResultButton({ input }: { input: FinalResultSnapshotInput }) {
  const [open, setOpen] = useState(false);
  const [blob, setBlob] = useState<Blob>();
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const filename = `cheesebaggers-final-result-${input.eventId}.png`;

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function show() {
    setOpen(true);
    setBusy(true);
    setNotice('');
    try {
      const nextBlob = await createFinalResultSnapshot(input);
      setBlob(nextBlob);
      setPreview(current => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(nextBlob);
      });
    } catch (error: any) {
      setNotice(error.message || 'Snapshot creation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function run(action: 'share' | 'copy' | 'download') {
    if (!blob) return;
    try {
      if (action === 'share') await shareImage(blob, filename, 'Cheesebaggers Final Game Result');
      else if (action === 'copy') await copyImage(blob);
      else downloadImage(blob, filename);
      setNotice(action === 'copy' ? 'Image copied — paste it into your message.' : action === 'download' ? 'Image downloaded.' : 'Share sheet opened.');
    } catch (error: any) {
      setNotice(error.message || 'That action is unavailable. You can download the image instead.');
    }
  }

  return <>
    <button type="button" onClick={show} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-amber-300/35 bg-amber-300/10 px-4 py-3 text-base font-black text-amber-200 transition hover:bg-amber-300/20 active:translate-y-px active:bg-amber-300/30">
      <Share2 size={19}/> Share Final Result
    </button>
    {open && <SnapshotDialog title="Final Game Result" preview={preview} busy={busy} notice={notice} onClose={() => setOpen(false)} onAction={run}/>}
  </>;
}

export function ShareBracketSnapshotButton({ data, eventId, event }: { data: BracketSnapshotData; eventId: string; event?: SnapshotEventDetails }) {
  const [open, setOpen] = useState(false);
  const [blob, setBlob] = useState<Blob>();
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const filename = `cheesebaggers-bracket-${eventId}.png`;

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  async function show() {
    setOpen(true);
    setBusy(true);
    setNotice('');
    try {
      const nextBlob = await createBracketSnapshot(data, eventId, event);
      setBlob(nextBlob);
      setPreview(current => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(nextBlob);
      });
    } catch (error: any) {
      setNotice(error.message || 'Snapshot creation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function run(action: 'share' | 'copy' | 'download') {
    if (!blob) return;
    setNotice('');
    try {
      if (action === 'share') {
        await shareImage(blob, filename, 'Cheesebaggers Bracket Prediction');
        setNotice('Share sheet opened.');
      } else if (action === 'copy') {
        await copyImage(blob);
        setNotice('Image copied — paste it into your message.');
      } else {
        downloadImage(blob, filename);
        setNotice('Image downloaded.');
      }
    } catch (error: any) {
      setNotice(error.message || 'That action is unavailable. You can download the image instead.');
    }
  }

  return <>
    <button
      type="button"
      onClick={show}
      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-amber-300/35 bg-amber-300/10 px-4 py-3 text-base font-black text-amber-200 transition hover:bg-amber-300/20 active:translate-y-px active:bg-amber-300/30"
    >
      <Share2 size={19}/> Share Snapshot
    </button>
    {open && <div className="fixed inset-0 z-[100] flex items-end justify-center bg-black/80 p-0 backdrop-blur-sm md:items-center md:p-6" role="dialog" aria-modal="true" aria-label="Share bracket snapshot">
      <div className="max-h-[94vh] w-full overflow-y-auto rounded-t-[28px] border border-white/15 bg-zinc-950 p-4 shadow-2xl md:max-w-3xl md:rounded-[28px] md:p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-black uppercase tracking-[.16em] text-amber-300">Ready to share</div>
            <h3 className="mt-1 text-2xl font-black text-white">Bracket Prediction Snapshot</h3>
          </div>
          <button type="button" onClick={() => setOpen(false)} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/5 text-white active:bg-white/15" aria-label="Close"><X/></button>
        </div>
        <div className="mt-5 flex min-h-52 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black p-3">
          {busy && <div className="text-lg font-bold text-zinc-300">Creating your share image…</div>}
          {!busy && preview && <img src={preview} alt="Bracket prediction share preview" className="max-h-[52vh] w-auto rounded-lg object-contain" />}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <ActionButton icon={<Share2/>} label="Share Image" onClick={() => run('share')} disabled={!blob}/>
          <ActionButton icon={<Clipboard/>} label="Copy Image" onClick={() => run('copy')} disabled={!blob}/>
          <ActionButton icon={<Download/>} label="Download" onClick={() => run('download')} disabled={!blob}/>
        </div>
        {notice && <div className="mt-4 flex items-start gap-2 rounded-xl border border-sky-300/20 bg-sky-300/10 p-3 text-sm font-bold text-sky-100"><Check className="mt-0.5 shrink-0" size={18}/>{notice}</div>}
        <p className="mt-4 text-sm leading-6 text-zinc-400">On a phone, Share Image opens the normal sharing menu. If your browser blocks image copying, Download always preserves the same share-ready card.</p>
      </div>
    </div>}
  </>;
}

export function ShareTaleOfTapeButton({ input }: { input: TaleOfTapeSnapshotInput }) {
  const [open, setOpen] = useState(false);
  const [blob, setBlob] = useState<Blob>();
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const filename = `cheesebaggers-tale-of-the-tape-${input.eventId}.png`;

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  async function show() {
    setOpen(true);
    setBusy(true);
    setNotice('');
    try {
      const nextBlob = await createTaleOfTapeSnapshot(input);
      setBlob(nextBlob);
      setPreview(current => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(nextBlob);
      });
    } catch (error: any) {
      setNotice(error.message || 'Snapshot creation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function run(action: 'share' | 'copy' | 'download') {
    if (!blob) return;
    setNotice('');
    try {
      if (action === 'share') {
        await shareImage(blob, filename, 'Cheesebaggers Tale of the Tape');
        setNotice('Share sheet opened.');
      } else if (action === 'copy') {
        await copyImage(blob);
        setNotice('Image copied — paste it into your message.');
      } else {
        downloadImage(blob, filename);
        setNotice('Image downloaded.');
      }
    } catch (error: any) {
      setNotice(error.message || 'That action is unavailable. You can download the image instead.');
    }
  }

  return <>
    <button type="button" onClick={show} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-amber-300/35 bg-amber-300/10 px-4 py-3 text-base font-black text-amber-200 transition hover:bg-amber-300/20 active:translate-y-px active:bg-amber-300/30">
      <Share2 size={19}/> Share Tale of the Tape
    </button>
    {open && <SnapshotDialog title="Tale of the Tape Snapshot" preview={preview} busy={busy} notice={notice} onClose={() => setOpen(false)} onAction={run}/>}
  </>;
}

function SnapshotDialog({ title, preview, busy, notice, onClose, onAction }: {
  title: string;
  preview: string;
  busy: boolean;
  notice: string;
  onClose: () => void;
  onAction: (action: 'share' | 'copy' | 'download') => void;
}) {
  return <div className="fixed inset-0 z-[100] flex items-end justify-center bg-black/80 p-0 backdrop-blur-sm md:items-center md:p-6" role="dialog" aria-modal="true" aria-label={`Share ${title.toLowerCase()}`}>
    <div className="max-h-[94vh] w-full overflow-y-auto rounded-t-[28px] border border-white/15 bg-zinc-950 p-4 shadow-2xl md:max-w-3xl md:rounded-[28px] md:p-6">
      <div className="flex items-center justify-between gap-4">
        <div><div className="text-sm font-black uppercase tracking-[.16em] text-amber-300">Ready to share</div><h3 className="mt-1 text-2xl font-black text-white">{title}</h3></div>
        <button type="button" onClick={onClose} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/5 text-white active:bg-white/15" aria-label="Close"><X/></button>
      </div>
      <div className="mt-5 flex min-h-52 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black p-3">
        {busy && <div className="text-lg font-bold text-zinc-300">Creating your share image…</div>}
        {!busy && preview && <img src={preview} alt={`${title} share preview`} className="max-h-[52vh] w-auto rounded-lg object-contain" />}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <ActionButton icon={<Share2/>} label="Share Image" onClick={() => onAction('share')} disabled={!preview}/>
        <ActionButton icon={<Clipboard/>} label="Copy Image" onClick={() => onAction('copy')} disabled={!preview}/>
        <ActionButton icon={<Download/>} label="Download" onClick={() => onAction('download')} disabled={!preview}/>
      </div>
      {notice && <div className="mt-4 flex items-start gap-2 rounded-xl border border-sky-300/20 bg-sky-300/10 p-3 text-sm font-bold text-sky-100"><Check className="mt-0.5 shrink-0" size={18}/>{notice}</div>}
      <p className="mt-4 text-sm leading-6 text-zinc-400">On a phone, Share Image opens the normal sharing menu. Copy Image is best for pasting directly into a conversation.</p>
    </div>
  </div>;
}

function ActionButton({ icon, label, onClick, disabled }: { icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean }) {
  return <button type="button" onClick={onClick} disabled={disabled} className="flex min-h-14 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[.06] px-4 text-base font-black text-white transition hover:bg-white/[.12] active:translate-y-px active:bg-white/[.18] disabled:cursor-wait disabled:opacity-40">
    {icon}{label}
  </button>;
}
