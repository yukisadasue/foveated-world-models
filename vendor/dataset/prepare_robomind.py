"""Decode top videos, audit observations, and prepare timestamp-indexed intervals."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

import av
import numpy as np
import pyarrow.parquet as pq

from .robomind import STATE_SCHEMA, states_from_rpy
from .temporal_data import clean_intervals, nearest_indices

CAMERA = 'observation.images.camera_top'


def scan_video(job):
    path, cache = map(Path, job)
    fingerprint = f'{path.resolve()}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
    if cache.exists():
        with np.load(cache, allow_pickle=False) as saved:
            if str(saved['fingerprint']) == fingerprint:
                return {'video': str(path), 'frames': len(saved['pts']), 'invalid': int((~saved['valid']).sum())}
    pts, valid = [], []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 2
        for frame in container.decode(stream):
            if frame.pts is None:
                raise ValueError(f'Frame without PTS: {path}')
            pts.append(float(frame.pts * stream.time_base))
            # Reject near-black missing-camera frames, retain legitimate static scenes.
            thumbnail = frame.reformat(width=32, height=18, format='rgb24').to_ndarray()
            valid.append(not frame.is_corrupt and thumbnail.max() > 1)
    if not pts or np.any(np.diff(pts) <= 0):
        raise ValueError(f'Empty or nonmonotonic video: {path}')
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, pts=np.array(pts), valid=np.array(valid, bool), fingerprint=fingerprint)
    return {'video': str(path), 'frames': len(pts), 'invalid': int(np.sum(~np.array(valid)))}


def prepare_episode(times, eef, gripper, video_pts, video_valid, *, start, end,
                    max_gap=.3, sync_tolerance=.02):
    """Align by time only; include unmatched video times to expose absent state rows."""
    times = np.asarray(times, np.float64)
    if not len(times) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('Invalid episode timestamps')
    if eef.shape != (len(times), 12) or gripper.shape != (len(times), 2):
        raise ValueError('Unexpected state shape')
    keep = (video_pts >= start - 1e-6) & (video_pts < end - 1e-6)
    pts, good_video = video_pts[keep], video_valid[keep]
    if not len(pts):
        return [], {'missing_video': True}
    video_times = pts - start
    nearest_state = nearest_indices(times, video_times)
    unmatched = video_times[np.abs(times[nearest_state] - video_times) > sync_tolerance]
    timeline = np.sort(np.r_[times, unmatched])
    si, vi = nearest_indices(times, timeline), nearest_indices(video_times, timeline)
    state_match = np.abs(times[si] - timeline) <= sync_tolerance
    video_match = (np.abs(video_times[vi] - timeline) <= sync_tolerance) & good_video[vi]
    # Per arm: xyz, roll/pitch/yaw, gripper. First column is video PTS.
    values = np.column_stack((pts[vi], eef[si, :6], gripper[si, 0], eef[si, 6:], gripper[si, 1]))
    valid = np.isfinite(values)
    valid[:, 0] &= video_match
    valid[:, 1:] &= state_match[:, None]
    for col in (7, 14):
        valid[:, col] &= (values[:, col] >= 0) & (values[:, col] <= 1)
    # Pose is atomic per arm: never synthesize an orientation from mixed timestamps.
    for cols in (slice(1, 7), slice(8, 14)):
        valid[:, cols] = valid[:, cols].all(axis=1)[:, None]
    fixed, original, age, spans = clean_intervals(timeline, values, valid, max_gap=max_gap)
    segments = []
    for a, b in spans:
        segments.append(dict(timestamps=timeline[a:b], video_pts=fixed[a:b, 0],
                             states=states_from_rpy(fixed[a:b, 1:]), original_valid=original[a:b],
                             fill_age_seconds=age[a:b]))
    return segments, dict(rows=len(timeline), invalid_values=int((~original).sum()),
                          filled_values=int((age > 0).sum()), intervals=len(spans))


def group_for_row(row):
    c, f = row[f'videos/{CAMERA}/chunk_index'], row[f'videos/{CAMERA}/file_index']
    return f'franka_fr3_dual/videos/{CAMERA}/chunk-{c:03d}/file-{f:03d}.mp4'


def group_splits(meta):
    """Deterministic task-stratified shard split; no shard crosses splits."""
    counts = defaultdict(Counter)
    for row in meta:
        counts[group_for_row(row)].update(row['tasks'])
    by_task = defaultdict(list)
    for group, tasks in counts.items():
        dominant = sorted(tasks, key=lambda task: (-tasks[task], task))[0]
        by_task[dominant].append(group)
    result = {}
    for task, groups in by_task.items():
        groups.sort(key=lambda group: hashlib.sha256(group.encode()).hexdigest())
        n = max(1, round(len(groups) * .1)) if len(groups) >= 3 else 0
        for i, group in enumerate(groups):
            result[group] = 'test' if i < n else 'validation' if i < 2*n else 'train'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/data2/yuki_sadasue/datasets/RoboMIND-lerobot'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--max-gap-seconds', type=float, default=.3)
    parser.add_argument('--sync-tolerance-seconds', type=float, default=.02)
    args = parser.parse_args()
    if args.max_gap_seconds <= 0 or args.sync_tolerance_seconds < 0:
        parser.error('Invalid gap/sync tolerance')
    root = args.root.resolve()
    subset = root / 'franka_fr3_dual'
    output = (args.output or root / 'preprocessed').resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'arrays').mkdir(exist_ok=True)
    meta = pq.read_table(subset / 'meta/episodes').to_pylist()
    splits = group_splits(meta)
    jobs = {}
    for row in meta:
        c, f = row[f'videos/{CAMERA}/chunk_index'], row[f'videos/{CAMERA}/file_index']
        rel = f'videos/{CAMERA}/chunk-{c:03d}/file-{f:03d}.mp4'
        jobs[rel] = (subset / rel, output / 'video_index' / f'{c:03d}-{f:03d}.npz')
    reports = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for report in pool.map(scan_video, jobs.values()):
            reports.append(report)
            print(f'video {len(reports)}/{len(jobs)} frames={report["frames"]} invalid={report["invalid"]}', flush=True)
    tables = {}
    rows = {s: [] for s in ('train', 'validation', 'test')}
    audit = []
    index_cache = {}
    for row in meta:
        key = (row['data/chunk_index'], row['data/file_index'])
        if key not in tables:
            table = pq.read_table(subset / f'data/chunk-{key[0]:03d}/file-{key[1]:03d}.parquet')
            tables[key] = {name: np.asarray(table[name].to_pylist()) for name in
                           ('episode_index', 'timestamp', 'observation.states.end_effector', 'observation.states.gripper')}
        table = tables[key]
        episode = int(row['episode_index'])
        mask = table['episode_index'] == episode
        c, f = row[f'videos/{CAMERA}/chunk_index'], row[f'videos/{CAMERA}/file_index']
        rel = f'videos/{CAMERA}/chunk-{c:03d}/file-{f:03d}.mp4'
        if rel not in index_cache:
            with np.load(jobs[rel][1], allow_pickle=False) as data:
                index_cache[rel] = (data['pts'], data['valid'])
        pts, valid = index_cache[rel]
        segments, report = prepare_episode(table['timestamp'][mask], table['observation.states.end_effector'][mask],
            table['observation.states.gripper'][mask], pts, valid,
            start=row[f'videos/{CAMERA}/from_timestamp'], end=row[f'videos/{CAMERA}/to_timestamp'],
            max_gap=args.max_gap_seconds, sync_tolerance=args.sync_tolerance_seconds)
        group = f'franka_fr3_dual/{rel}'
        split = splits[group]
        audit.append(dict(episode_id=episode, split=split, **report))
        for i, segment in enumerate(segments):
            array_file = f'arrays/episode-{episode:06d}-{i:03d}.npz'
            np.savez_compressed(output / array_file, **segment)
            rows[split].append(dict(episode_id=str(episode), split_group=group, state_schema=STATE_SCHEMA,
                                   array_file=array_file, video_file=str(subset / rel), tasks=row['tasks'],
                                   observations=len(segment['timestamps'])))
    for split, records in rows.items():
        if not records:
            raise ValueError(f'Empty split: {split}')
        (output / f'{split}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in records))
    summary = dict(source_revision=json.loads((root / 'download_plan.json').read_text())['revision'],
                   camera=CAMERA, max_gap_seconds=args.max_gap_seconds, sync_tolerance_seconds=args.sync_tolerance_seconds,
                   split_policy='Group by top video shard; stratify by dominant task, SHA256 ordering, about 80/10/10; original recording IDs unavailable',
                   state_schema=STATE_SCHEMA, videos=reports,
                   splits={s: dict(intervals=len(rs), episodes=len({r['episode_id'] for r in rs}),
                                   groups=len({r['split_group'] for r in rs}), observations=sum(r['observations'] for r in rs),
                                   task_intervals=dict(Counter(task for r in rs for task in r['tasks'])))
                           for s, rs in rows.items()},
                   invalid_values=sum(r.get('invalid_values', 0) for r in audit),
                   filled_values=sum(r.get('filled_values', 0) for r in audit))
    (output / 'audit.json').write_text(json.dumps(audit, indent=2))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != 'videos'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
