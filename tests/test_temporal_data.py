from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vendor.dataset.temporal_data import clean_intervals, nearest_indices, timestamp_pairs


def test_time_selection_not_frame_arithmetic_and_tail():
    t = np.array([0, .1, .7, 1.19, 1.23, 1.7, 2.38, 2.8])
    assert timestamp_pairs(t) == [(0, 3, False), (3, 6, False), (6, 7, True)]
    assert nearest_indices([0, 2], [1]).tolist() == [0]
    assert timestamp_pairs([0]) == []
    assert timestamp_pairs([0, 1.2]) == [(0, 1, False)]


def test_reject_far_nearest_without_clamping_normal_pair():
    assert timestamp_pairs([0, .5, 1.5, 1.6], tolerance=.02) == [(2, 3, True)]


def test_short_hold_and_exact_threshold_split():
    t = np.arange(13)/10
    x = np.stack([t, 10+t], axis=1); valid = np.ones_like(x, dtype=bool)
    valid[2:4, 0] = False  # .2s missing
    valid[7:10, 1] = False  # .3s missing, must not fill
    y, original, age, spans = clean_intervals(t, x, valid)
    np.testing.assert_equal(y[2:4, 0], [.1, .1])
    np.testing.assert_allclose(age[2:4, 0], [.1, .2])
    assert spans == [(0, 7), (10, 13)]
    assert not original[2, 0] and original[2, 1]
    assert y[2, 1] == x[2, 1]


def test_trim_endpoints_and_no_hold_across_absent_time():
    t = np.array([0., .1, .2, .3, .7, .8, .9, 1.])
    x = t[:, None]; good = np.ones_like(x, bool); good[[0, 3, 4, 7]] = False
    _, _, _, spans = clean_intervals(t, x, good)
    assert spans == [(1, 3), (5, 7)]


def test_all_invalid_and_single_observation_produce_no_intervals():
    t=np.arange(4)/10;x=t[:,None]
    assert clean_intervals(t,x,np.zeros_like(x,bool))[3]==[]
    good=np.zeros_like(x,bool);good[2]=True
    assert clean_intervals(t,x,good)[3]==[]


def test_float32_timestamp_quantization_does_not_create_false_tail():
    t=np.asarray([1000,1001.2],dtype=np.float32).astype(np.float64)
    assert timestamp_pairs(t)==[(0,1,False)]


def test_same_time_horizon_across_sampling_rates():
    for hz in (10, 15, 30, 50, 60):
        times = np.arange(3 * hz + 1) / hz
        pairs = timestamp_pairs(times)
        assert len(pairs) == 3
        np.testing.assert_allclose([times[b] - times[a] for a, b, tail in pairs], [1.2, 1.2, .6])
        assert [tail for _, _, tail in pairs] == [False, False, True]


def test_noninteger_horizon_in_frame_units_still_selects_nearest():
    for hz in (7, 12, 24, 29.97):
        times=np.arange(100)/hz
        pairs=timestamp_pairs(times)
        assert pairs and pairs[0][0]==0 and pairs[-1][1]==len(times)-1
        for a,b,tail in pairs:
            if tail:
                assert b==len(times)-1
            else:
                assert b==int(np.argmin(np.abs(times-(times[a]+1.2))))
        assert all(left[1]==right[0] for left,right in zip(pairs,pairs[1:]))
