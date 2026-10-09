import { useEffect, useMemo, useState } from 'react';

import { captureDocumentIdentity } from '../../state/currentDocument';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { searchPsykeForDocument } from '../psyke/psykeApi';
import type { PsykeEntry } from '../psyke/types';
import type {
  ManuscriptProgressionAnchor,
  ProgressionBeat,
  ProgressionKind,
  ProgressionTrack,
} from './types';
import {
  createTrackSubjects,
  defaultProgressionKind,
  progressionKindsForEntry,
  resolvedAnchorCoverage,
  tracksForEntry,
} from './progressionModel';
import { useProgressions } from './useProgressions';

interface Props {
  baseUrl: string;
  entry: PsykeEntry;
  manuscriptAnchor: ManuscriptProgressionAnchor | null;
  manuscriptBlockIds: readonly string[] | null;
}

function move<T>(values: T[], from: number, delta: number): T[] {
  const to = from + delta;
  if (from < 0 || to < 0 || to >= values.length) return values;
  const next = [...values];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

interface BeatRowProps {
  beat: ProgressionBeat;
  index: number;
  count: number;
  saving: boolean;
  manuscriptAnchor: ManuscriptProgressionAnchor | null;
  manuscriptBlockIds: ReadonlySet<string> | null;
  onCommand: (command: Record<string, unknown>) => void;
}

function BeatRow({
  beat,
  index,
  count,
  saving,
  manuscriptAnchor,
  manuscriptBlockIds,
  onCommand,
}: BeatRowProps) {
  const [text, setText] = useState(beat.text);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => setText(beat.text), [beat.id, beat.text]);
  const missingDocumentAnchor = manuscriptBlockIds !== null
    && beat.anchor_kind === 'document_block'
    && (!beat.anchor_ref || !manuscriptBlockIds.has(beat.anchor_ref));
  const anchorText = beat.anchor_kind === 'document_block'
    ? `${beat.anchor_label || 'Manuscript block'}${missingDocumentAnchor ? ' · missing block' : ''}`
    : beat.anchor_kind === 'scene'
      ? (beat.scene_title || 'Pro scene')
      : 'Unanchored';

  return (
    <li className="progression-beat">
      <textarea
        value={text}
        rows={2}
        maxLength={2000}
        aria-label="Progression beat"
        onChange={(event) => setText(event.target.value)}
      />
      <div className="progression-beat-meta">
        <span
          className={missingDocumentAnchor ? 'progression-anchor-missing' : undefined}
          title={missingDocumentAnchor
            ? `The referenced manuscript block (${beat.anchor_ref ?? 'missing id'}) no longer exists in this Whiteboard document.`
            : beat.anchor_ref ?? undefined}
        >{anchorText}</span>
        <span className="progression-mini-actions">
          <button
            type="button"
            disabled={saving || index === 0}
            aria-label="Move beat earlier"
            onClick={() => onCommand({ kind: 'move_beat', beatId: beat.id, delta: -1 })}
          >↑</button>
          <button
            type="button"
            disabled={saving || index === count - 1}
            aria-label="Move beat later"
            onClick={() => onCommand({ kind: 'move_beat', beatId: beat.id, delta: 1 })}
          >↓</button>
        </span>
      </div>
      <div className="progression-beat-actions">
        <button
          type="button"
          disabled={saving || !text.trim() || text === beat.text}
          onClick={() => onCommand({ kind: 'update_beat', beat_id: beat.id, text: text.trim() })}
        >Save text</button>
        {manuscriptAnchor && (
          <button
            type="button"
            disabled={saving}
            title={`Anchor to ${manuscriptAnchor.anchor_label}`}
            onClick={() => onCommand({
              kind: 'update_beat',
              beat_id: beat.id,
              ...manuscriptAnchor,
              scene_id: null,
            })}
          >Anchor here</button>
        )}
        {beat.anchor_kind !== 'unanchored' && (
          <button
            type="button"
            disabled={saving}
            onClick={() => onCommand({
              kind: 'update_beat', beat_id: beat.id, anchor_kind: 'unanchored',
              scene_id: null, anchor_ref: null, anchor_label: '',
            })}
          >Unanchor</button>
        )}
        <button
          type="button"
          className="is-danger"
          disabled={saving}
          onClick={() => setConfirmDelete(true)}
        >Delete</button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        title="Delete progression beat"
        message="Delete this beat from the track? This can’t be undone."
        confirmLabel="Delete"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          onCommand({ kind: 'delete_beat', beat_id: beat.id });
        }}
      />
    </li>
  );
}

interface TrackCardProps {
  track: ProgressionTrack;
  globalIndex: number;
  globalCount: number;
  saving: boolean;
  manuscriptAnchor: ManuscriptProgressionAnchor | null;
  manuscriptBlockIds: ReadonlySet<string> | null;
  onCommand: (command: Record<string, unknown>) => void;
}

function TrackCard({
  track,
  globalIndex,
  globalCount,
  saving,
  manuscriptAnchor,
  manuscriptBlockIds,
  onCommand,
}: TrackCardProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(track.title);
  const [description, setDescription] = useState(track.description);
  const [colorLabel, setColorLabel] = useState(track.color_label);
  const [newBeat, setNewBeat] = useState('');
  const [anchorNewBeat, setAnchorNewBeat] = useState(Boolean(manuscriptAnchor));
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    setTitle(track.title);
    setDescription(track.description);
    setColorLabel(track.color_label);
  }, [track.color_label, track.description, track.id, track.kind, track.title]);
  const localCoverage = manuscriptBlockIds === null
    ? null
    : resolvedAnchorCoverage(track, manuscriptBlockIds);

  const dispatch = (command: Record<string, unknown>) => {
    if (command.kind === 'move_beat') {
      const beatIndex = track.beats.findIndex((beat) => beat.id === command.beatId);
      const reordered = move(track.beats, beatIndex, Number(command.delta));
      onCommand({ kind: 'reorder_beats', track_id: track.id, beat_ids: reordered.map((beat) => beat.id) });
      return;
    }
    onCommand(command);
  };

  return (
    <article className="progression-track">
      <header className="progression-track-header">
        <div>
          <strong>{track.title}</strong>
          <span>
            {track.kind} · {localCoverage
              ? `${localCoverage.resolvedAnchors}/${localCoverage.totalBeats} locally resolved${localCoverage.missingDocumentAnchors > 0
                ? ` · ${localCoverage.missingDocumentAnchors} missing manuscript block${localCoverage.missingDocumentAnchors === 1 ? '' : 's'}`
                : ''}`
              : 'local manuscript coverage loading'}
          </span>
          <span title="Core coverage counts structurally valid references; local coverage also verifies that Whiteboard manuscript blocks still exist.">
            Core references: {track.coverage.anchored_beats}/{track.coverage.total_beats} anchored
          </span>
        </div>
        <div className="progression-mini-actions">
          <button type="button" disabled={saving || globalIndex === 0} aria-label="Move track earlier"
            onClick={() => onCommand({ kind: 'move_track', trackId: track.id, delta: -1 })}>↑</button>
          <button type="button" disabled={saving || globalIndex === globalCount - 1} aria-label="Move track later"
            onClick={() => onCommand({ kind: 'move_track', trackId: track.id, delta: 1 })}>↓</button>
          <button type="button" disabled={saving} onClick={() => setEditing((value) => !value)}>Edit</button>
          <button type="button" className="is-danger" disabled={saving}
            onClick={() => setConfirmDelete(true)}>Delete</button>
        </div>
      </header>
      {editing && (
        <div className="progression-form">
          <label>Kind<input value={track.kind} disabled title="A track's subject rules are fixed after creation." /></label>
          <label>Title<input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Description<textarea value={description} rows={2} maxLength={2000} onChange={(event) => setDescription(event.target.value)} /></label>
          <label>Color label<input value={colorLabel} maxLength={100} placeholder="e.g. amber" onChange={(event) => setColorLabel(event.target.value)} /></label>
          <div className="progression-form-actions">
            <button type="button" disabled={saving || !title.trim()} onClick={() => {
              onCommand({
                kind: 'update_track', track_id: track.id,
                title: title.trim(), description: description.trim(), color_label: colorLabel.trim(),
              });
              setEditing(false);
            }}>Save track</button>
            <button type="button" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      )}

      {track.description && !editing ? <p className="progression-description">{track.description}</p> : null}
      {track.beats.length === 0 ? <p className="psyke-hint">No beats yet.</p> : (
        <ol className="progression-beats">
          {track.beats.map((beat, index) => (
            <BeatRow
              key={beat.id}
              beat={beat}
              index={index}
              count={track.beats.length}
              saving={saving}
              manuscriptAnchor={manuscriptAnchor}
              manuscriptBlockIds={manuscriptBlockIds}
              onCommand={dispatch}
            />
          ))}
        </ol>
      )}
      <div className="progression-add-beat">
        <textarea
          rows={2}
          value={newBeat}
          maxLength={2000}
          placeholder="Next change in this progression…"
          aria-label={`Add a beat to ${track.title}`}
          onChange={(event) => setNewBeat(event.target.value)}
        />
        <label className="progression-anchor-choice">
          <input
            type="checkbox"
            checked={anchorNewBeat && manuscriptAnchor !== null}
            disabled={!manuscriptAnchor}
            onChange={(event) => setAnchorNewBeat(event.target.checked)}
          />
          Anchor to current manuscript block
        </label>
        <button type="button" disabled={saving || !newBeat.trim()} onClick={() => {
          onCommand({
            kind: 'create_beat', track_id: track.id, text: newBeat.trim(),
            ...(anchorNewBeat && manuscriptAnchor
              ? { ...manuscriptAnchor, scene_id: null }
              : { anchor_kind: 'unanchored', scene_id: null, anchor_ref: null, anchor_label: '' }),
          });
          setNewBeat('');
        }}>+ Add beat</button>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        title="Delete progression track"
        message={`Delete “${track.title}” and all its beats? This can’t be undone.`}
        confirmLabel="Delete"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          onCommand({ kind: 'delete_track', track_id: track.id });
        }}
      />
    </article>
  );
}

export function ProgressionsPanel({
  baseUrl,
  entry,
  manuscriptAnchor,
  manuscriptBlockIds,
}: Props) {
  const {
    snapshot,
    loading,
    saving,
    error,
    recoveryPending,
    refresh,
    execute,
    retryPending,
    abandonPending,
  } = useProgressions(baseUrl);
  const [adding, setAdding] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [colorLabel, setColorLabel] = useState('');
  const [kind, setKind] = useState<ProgressionKind>(defaultProgressionKind(entry.entry_type));
  const [allEntries, setAllEntries] = useState<PsykeEntry[]>([]);
  const [partnerId, setPartnerId] = useState('');
  const [partnerError, setPartnerError] = useState<string | null>(null);
  const entryId = Number(entry.id);
  const tracks = useMemo(() => tracksForEntry(snapshot?.tracks ?? [], entry), [entry, snapshot]);
  const manuscriptBlockIdSet = useMemo(
    () => manuscriptBlockIds === null
      ? null
      : new Set(manuscriptBlockIds.filter((id) => typeof id === 'string' && id.trim())),
    [manuscriptBlockIds],
  );
  const commandsDisabled = saving || recoveryPending;

  useEffect(() => {
    setAdding(false);
    setKind(defaultProgressionKind(entry.entry_type));
    setTitle('');
    setDescription('');
    setColorLabel('');
    setPartnerId('');
  }, [entry.entry_type, entry.id]);

  useEffect(() => {
    const identity = captureDocumentIdentity();
    const controller = new AbortController();
    setPartnerError(null);
    void searchPsykeForDocument(baseUrl, identity.documentId, '', controller.signal, identity.incarnation)
      .then((response) => setAllEntries(response.results))
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setPartnerError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => controller.abort();
  }, [baseUrl, entry.id]);

  const partnerEntries = allEntries.filter((candidate) => Number(candidate.id) !== entryId);
  const validRelationshipPartner = kind !== 'relationship'
    || partnerEntries.some((candidate) => candidate.id === partnerId);

  const command = (raw: Record<string, unknown>) => {
    if (!snapshot) return;
    if (raw.kind === 'move_track') {
      const index = snapshot.tracks.findIndex((track) => track.id === raw.trackId);
      const reordered = move(snapshot.tracks, index, Number(raw.delta));
      void execute({ kind: 'reorder_tracks', track_ids: reordered.map((track) => track.id) });
      return;
    }
    void execute(raw as never);
  };

  if (!Number.isSafeInteger(entryId) || entryId < 1) {
    return <p className="psyke-hint psyke-error">This PSYKE entry has no valid core identity.</p>;
  }
  if (loading && !snapshot) return <p className="psyke-hint">Loading progressions…</p>;

  return (
    <section className="progressions-panel" aria-label={`Progressions for ${entry.name}`}>
      <div className="progressions-toolbar">
        <span>{tracks.length} track{tracks.length === 1 ? '' : 's'}</span>
        <button type="button" disabled={commandsDisabled} onClick={() => setAdding((value) => !value)}>+ Track</button>
        <button type="button" disabled={loading || saving} onClick={() => void refresh()} aria-label="Refresh progressions">↻</button>
      </div>
      {manuscriptAnchor ? (
        <p className="progression-location">Current manuscript anchor: {manuscriptAnchor.anchor_label}</p>
      ) : (
        <p className="progression-location">Open the main manuscript and place the caret to anchor beats.</p>
      )}
      {error && <p className="psyke-hint psyke-error">{error}</p>}
      {recoveryPending && (
        <div className="progression-recovery" role="alert">
          <p>
            A Progressions save has an uncertain outcome. Whiteboard retained the exact command and
            Idempotency-Key; other progression edits are paused until it is resolved.
          </p>
          <div>
            <button type="button" disabled={saving} onClick={() => void retryPending()}>
              Retry exact save
            </button>
            <button type="button" className="is-danger" disabled={saving} onClick={() => setConfirmAbandon(true)}>
              Abandon recovery…
            </button>
          </div>
        </div>
      )}
      {adding && (
        <div className="progression-form progression-new-track">
          <label>Kind<select value={kind} onChange={(event) => {
            setKind(event.target.value as ProgressionKind);
            setPartnerId('');
          }}>
            {progressionKindsForEntry(entry.entry_type).map((value) => <option key={value} value={value}>{value}</option>)}
          </select></label>
          {kind === 'relationship' && (
            <label>Second subject<select value={partnerId} onChange={(event) => setPartnerId(event.target.value)}>
              <option value="">Choose another PSYKE entry…</option>
              {partnerEntries.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>{candidate.name} ({candidate.entry_type})</option>
              ))}
            </select></label>
          )}
          {kind === 'relationship' && partnerEntries.length === 0 && (
            <p className="psyke-hint">Add another PSYKE entry before creating a relationship track.</p>
          )}
          {partnerError && kind === 'relationship' && <p className="psyke-hint psyke-error">{partnerError}</p>}
          <label>Title<input autoFocus value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Description<textarea value={description} rows={2} maxLength={2000} onChange={(event) => setDescription(event.target.value)} /></label>
          <label>Color label<input value={colorLabel} maxLength={100} placeholder="e.g. ocean blue" onChange={(event) => setColorLabel(event.target.value)} /></label>
          <div className="progression-form-actions">
            <button type="button" disabled={commandsDisabled || !title.trim() || !validRelationshipPartner} onClick={async () => {
              const subjects = createTrackSubjects(kind, entryId, Number(partnerId));
              const result = await execute({
                kind: 'create_track', track_kind: kind, title: title.trim(),
                description: description.trim(), color_label: colorLabel.trim(),
                ...subjects,
              });
              if (result) {
                setAdding(false);
                setTitle('');
                setDescription('');
                setColorLabel('');
              }
            }}>Create</button>
            <button type="button" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}
      {!adding && tracks.length === 0 && !error ? (
        <p className="psyke-hint">No progression tracks involve this entry yet.</p>
      ) : null}
      <div className="progression-track-list">
        {tracks.map((track) => {
          const globalIndex = snapshot?.tracks.findIndex((candidate) => candidate.id === track.id) ?? -1;
          return (
            <TrackCard
              key={track.id}
              track={track}
              globalIndex={globalIndex}
              globalCount={snapshot?.tracks.length ?? 0}
              saving={commandsDisabled}
              manuscriptAnchor={manuscriptAnchor}
              manuscriptBlockIds={manuscriptBlockIdSet}
              onCommand={command}
            />
          );
        })}
      </div>
      {saving && <p className="progression-saving" role="status">Saving progression…</p>}
      <ConfirmDialog
        open={confirmAbandon}
        title="Abandon Progressions recovery"
        message="The server may already have committed this command. Abandon only after checking the project; repeating the edit later could duplicate it. Forget the retained command and Idempotency-Key?"
        confirmLabel="Abandon recovery"
        onCancel={() => setConfirmAbandon(false)}
        onConfirm={() => {
          setConfirmAbandon(false);
          abandonPending();
        }}
      />
    </section>
  );
}
