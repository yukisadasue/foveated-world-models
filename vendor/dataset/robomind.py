"""RoboMIND FR3 dual video/state adapter for the official LaWAM batch contract."""
import json
from collections import OrderedDict
from pathlib import Path

import av
import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import Dataset

from .temporal_data import timestamp_pairs

STATE_SCHEMA = 'robomind_fr3_dual_xyz_m_rpy_RzRyRx_rot6d_columns_gripper01_v1'


def states_from_rpy(values):
    """[left xyz/rpy/gripper, right xyz/rpy/gripper] -> two 10D states.

    Use the published roll/pitch/yaw field interpretation, Rz(yaw)Ry(pitch)Rx(roll).
    Retain each arm's source coordinate frame; do not assume a shared world frame.
    """
    result = []
    for offset in (0, 7):
        arm = values[:, offset:offset + 7]
        roll, pitch, yaw = arm[:, 3:6].T
        cr, sr = np.cos(roll), np.sin(roll)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cy, sy = np.cos(yaw), np.sin(yaw)
        col0 = np.stack((cy * cp, sy * cp, -sp), axis=-1)
        col1 = np.stack((cy * sp * sr - sy * cr, sy * sp * sr + cy * cr, cp * sr), axis=-1)
        result.extend((arm[:, :3], col0, col1, arm[:, 6:7]))
    return np.concatenate(result, axis=-1).astype(np.float32)


def read_frame(container, stream, target, image_hw):
    container.seek(int(round(target / float(stream.time_base))), stream=stream, backward=True)
    for frame in container.decode(stream):
        if frame.pts is None:
            continue
        time = float(frame.pts * stream.time_base)
        if abs(time - target) < 1e-5:
            # Preserve the whole overhead image, including hands near the edges.
            h, w = image_hw
            im = ImageOps.pad(frame.to_image().convert('RGB'), (w, h),
                              method=Image.Resampling.BICUBIC, color=(0, 0, 0))
            return torch.from_numpy(np.array(im, copy=True)).permute(2, 0, 1)
        if time > target + 1e-5:
            break
    raise RuntimeError(f'Missing decoded video timestamp {target}')


class RoboMINDDataset(Dataset):
    def __init__(self, manifest, *, image_hw=(256, 256), max_state_dim=32,
                 num_embodiments=32, horizon_seconds=1.2, tolerance_seconds=None,
                 require_observed_endpoints=False):
        self.path = Path(manifest).resolve()
        self.image_hw = tuple(image_hw)
        if len(image_hw) != 2 or min(image_hw) <= 0 or max_state_dim < 20 or num_embodiments <= 1:
            raise ValueError('Require positive image dimensions, state capacity >=20, embodiment capacity >=2')
        self.rows = [json.loads(s) for s in self.path.read_text().splitlines() if s.strip()]
        self.episodes, self.groups = set(), set()
        self.schemas = {1: (STATE_SCHEMA, 20)}
        self._cache = OrderedDict()
        self.pairs = []
        for i, row in enumerate(self.rows):
            if row['state_schema'] != STATE_SCHEMA:
                raise ValueError('Unexpected state schema')
            self.episodes.add(row['episode_id']); self.groups.add(row['split_group'])
            arrays = self._arrays(i)
            t, states = arrays['timestamps'], arrays['states']
            if states.shape != (len(t), 20) or not np.isfinite(states).all():
                raise ValueError('Invalid prepared states')
            if arrays['original_valid'].shape != (len(t), 15):
                raise ValueError('Invalid original validity mask')
            observed = arrays['original_valid'].all(axis=1)
            for a, b, tail in timestamp_pairs(t, horizon=horizon_seconds, tolerance=tolerance_seconds):
                if not require_observed_endpoints or (observed[a] and observed[b]):
                    self.pairs.append((i, a, b, tail))
        self._cache.clear()
        if not self.pairs:
            raise ValueError(f'No usable pairs in {self.path}')

    def _arrays(self, i):
        if i not in self._cache:
            with np.load(self.path.parent / self.rows[i]['array_file'], allow_pickle=False) as data:
                self._cache[i] = {k: data[k] for k in data.files}
            if len(self._cache) > 8:
                self._cache.popitem(last=False)
        self._cache.move_to_end(i)
        return self._cache[i]

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, index):
        i, a, b, tail = self.pairs[index]
        row, data = self.rows[i], self._arrays(i)
        with av.open(row['video_file']) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = 1
            frames = [read_frame(container, stream, float(data['video_pts'][j]), self.image_hw) for j in (a, b)]
        times = data['timestamps'][[a, b]]
        return dict(frames=torch.stack(frames), proprio=torch.from_numpy(data['states'][[a, b]].copy()),
                    embodiment_id=1, dataset_name='RoboMIND-franka_fr3_dual', trajectory_id=row['episode_id'],
                    base_index=a, timestamps=torch.from_numpy(times.copy()), dt=float(times[1] - times[0]),
                    is_tail=tail, split_group=row['split_group'],
                    original_valid=torch.from_numpy(data['original_valid'][[a, b]].copy()),
                    fill_age_seconds=torch.from_numpy(data['fill_age_seconds'][[a, b]].copy()))


def robomind_collate(batch, *, max_state_dim=32):
    from latent_action_model.data_loader.collate import lam_collate
    if max_state_dim < 20:
        raise ValueError('State truncation is forbidden')
    result = lam_collate(batch, max_state_dim=max_state_dim)
    for key in ('timestamps', 'original_valid', 'fill_age_seconds'):
        result[key] = torch.stack([sample[key] for sample in batch])
    result['dt'] = torch.tensor([s['dt'] for s in batch], dtype=torch.float64)
    result['is_tail'] = torch.tensor([s['is_tail'] for s in batch])
    result['split_group'] = [s['split_group'] for s in batch]
    return result


def check_disjoint(*datasets):
    for i, left in enumerate(datasets):
        for right in datasets[i + 1:]:
            if left.episodes & right.episodes:
                raise ValueError('Dataset episode overlap')
            if left.groups & right.groups:
                raise ValueError('Dataset video-shard group overlap')
            if left.schemas != right.schemas:
                raise ValueError('Dataset state schema mismatch')
