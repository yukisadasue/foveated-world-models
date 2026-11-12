"""Check downloaded subset sizes, video headers, states, and episode timestamps."""
import argparse
import json
from pathlib import Path

import av
import numpy as np
import pyarrow.parquet as pq


def verify(root):
    plan = json.loads((root / 'download_plan.json').read_text())
    for entry in plan['files']:
        path = root / entry['path']
        if not path.is_file() or path.stat().st_size != entry['bytes']:
            raise ValueError(f'Missing or incomplete file: {path}')
    subset = root / 'franka_fr3_dual'
    info = json.loads((subset / 'meta/info.json').read_text())
    frames = 0
    videos = sorted((subset / 'videos/observation.images.camera_top').rglob('*.mp4'))
    for path in videos:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            if stream.average_rate != info['fps'] or (stream.width, stream.height) != (1280, 720):
                raise ValueError(f'Unexpected video metadata: {path}')
            frames += stream.frames
    if frames != info['total_frames']:
        raise ValueError(f'Video frame count {frames} != {info["total_frames"]}')
    rows = 0
    episodes = set()
    for path in sorted((subset / 'data').rglob('*.parquet')):
        table = pq.read_table(path)
        rows += len(table)
        for key in ('observation.states.end_effector', 'observation.states.joint_position', 'observation.states.gripper'):
            if not np.isfinite(np.asarray(table[key].to_pylist())).all():
                raise ValueError(f'Nonfinite state: {path}: {key}')
        ids = table['episode_index'].to_numpy()
        times = table['timestamp'].to_numpy()
        if not np.isfinite(times).all():
            raise ValueError('Nonfinite timestamps')
        for episode in np.unique(ids):
            if np.any(np.diff(times[ids == episode]) <= 0):
                raise ValueError(f'Nonmonotonic timestamps: {episode}')
            episodes.add(int(episode))
    if rows != info['total_frames'] or len(episodes) != info['total_episodes']:
        raise ValueError('State row/episode count mismatch')
    report = dict(revision=plan['revision'], bytes=plan['bytes'], files=len(plan['files']),
                  videos=len(videos), video_header_frames=frames, state_rows=rows,
                  episodes=len(episodes), state_values_finite=True, timestamps_strictly_increasing=True,
                  timestamp_policy='Trust distributed timestamps; select by time, never fixed frame stride',
                  scope='File sizes, video headers, state values and timestamps; not full video decode or synchronization audit')
    (root / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/data2/yuki_sadasue/datasets/RoboMIND-lerobot'))
    verify(parser.parse_args().root)
