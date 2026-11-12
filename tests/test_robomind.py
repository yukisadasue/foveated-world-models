import hashlib
import json
from pathlib import Path
import sys

import av
import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/lawam'))
from vendor.dataset.prepare_robomind import prepare_episode, scan_video
from vendor.dataset.robomind import RoboMINDDataset, STATE_SCHEMA, check_disjoint, robomind_collate, states_from_rpy


def inputs():
    t = np.arange(40) / 10
    eef = np.zeros((40, 12)); eef[:, 0] = t
    grip = np.full((40, 2), .5)
    return t, eef, grip


def test_missing_components_and_trim():
    t, eef, grip = inputs()
    grip[[0, 39], 0] = np.nan
    eef[2:4, 0] = np.nan
    eef[10:13, 6] = np.nan
    good = np.ones(40, bool); good[6] = False
    segments, _ = prepare_episode(t, eef, grip, t + 10, good, start=10, end=14)
    assert len(segments) == 2
    assert segments[0]['timestamps'][0] == .1
    assert segments[0]['timestamps'][-1] == .9
    assert segments[1]['timestamps'][0] == 1.3
    assert segments[1]['timestamps'][-1] == 3.8
    assert segments[0]['states'][1, 0] == pytest.approx(.1)
    assert segments[0]['video_pts'][5] == pytest.approx(10.5)
    assert not segments[0]['original_valid'][1, 1]


def test_missing_rows_and_absent_video():
    t, eef, grip = inputs()
    keep = np.arange(40) != 5
    segments, _ = prepare_episode(t[keep], eef[keep], grip[keep], t + 20, np.ones(40, bool), start=20, end=24)
    assert not segments[0]['original_valid'][5, 1]
    assert segments[0]['states'][5, 0] == pytest.approx(.4)
    assert prepare_episode(t, eef, grip, np.array([]), np.array([], bool), start=0, end=4)[0] == []


def test_rotation_wrap_and_source_frames():
    a = np.zeros((2, 14)); a[:, 3] = [np.pi-1e-6, -np.pi+1e-6]
    a[:, 0] = 2; a[:, 7] = 3
    states = states_from_rpy(a)
    assert np.linalg.norm(states[0] - states[1]) < 1e-5
    assert states[0, 0] == 2 and states[0, 10] == 3
    np.testing.assert_allclose(states_from_rpy(np.zeros((1, 14)))[0, 3:9], [1, 0, 0, 0, 1, 0])


def test_real_decode_and_batch(tmp_path):
    from fractions import Fraction
    path = tmp_path / 'video.mp4'
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('mpeg4', rate=10)
        stream.width=48; stream.height=32; stream.pix_fmt='yuv420p'
        for i in range(40):
            frame = av.VideoFrame.from_ndarray(np.full((32,48,3),30+i,np.uint8),format='rgb24')
            frame.pts=i; frame.time_base=Fraction(1,10)
            for packet in stream.encode(frame): container.mux(packet)
        for packet in stream.encode(): container.mux(packet)
    report=scan_video((path,tmp_path/'index.npz')); assert report['frames']==40
    assert report['invalid']==0
    t,eef,grip=inputs()
    with np.load(tmp_path/'index.npz') as data:
        segments,_=prepare_episode(t,eef,grip,data['pts'],data['valid'],start=0,end=4)
    segments[0]['original_valid'][12,0]=False
    np.savez_compressed(tmp_path/'a.npz',**segments[0])
    row=dict(array_file='a.npz',video_file=str(path),episode_id='a',split_group='g',state_schema=STATE_SCHEMA)
    manifest=tmp_path/'train.jsonl';manifest.write_text(json.dumps(row)+'\n')
    ds=RoboMINDDataset(manifest,image_hw=(32,32))
    ev=RoboMINDDataset(manifest,image_hw=(32,32),require_observed_endpoints=True)
    assert len(ds)==4 and len(ev)==2
    batch=robomind_collate([ds[0],ds[-1]])
    assert batch['videos'].shape==(2,2,3,32,32)
    assert batch['videos'].dtype==torch.uint8
    assert batch['states'].shape==(2,2,32)
    assert batch['state_mask'][0,0].sum()==20
    torch.testing.assert_close(batch['dt'],torch.tensor([1.2,.3],dtype=torch.float64))
    assert batch['is_tail'].tolist()==[False,True]
    with pytest.raises(ValueError,match='episode overlap'):check_disjoint(ds,ev)
    ev.episodes={'other'}
    with pytest.raises(ValueError,match='group overlap'):check_disjoint(ds,ev)
    with pytest.raises(ValueError):RoboMINDDataset(manifest,max_state_dim=7)
    row['state_schema']='wrong';manifest.write_text(json.dumps(row)+'\n')
    with pytest.raises(ValueError,match='schema'):RoboMINDDataset(manifest)


def test_pinned_upstream_hashes():
    root=ROOT/'vendor/lawam'
    record=json.loads((root/'UPSTREAM.json').read_text())
    for path,expected in record['files_sha256'].items():
        assert hashlib.sha256((root/path).read_bytes()).hexdigest()==expected


def test_task_stratified_shards_are_disjoint_and_reproducible():
    from vendor.dataset.prepare_robomind import CAMERA, group_splits
    rows=[]
    for i in range(20):
        rows.append({f'videos/{CAMERA}/chunk_index':0, f'videos/{CAMERA}/file_index':i,
                     'tasks':['a' if i<10 else 'b']})
    splits=group_splits(rows)
    assert splits==group_splits(list(reversed(rows)))
    for start in (0,10):
        part=group_splits(rows[start:start+10])
        assert sorted(part.values())==['test']+['train']*8+['validation']
