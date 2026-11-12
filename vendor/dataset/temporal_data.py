"""Dataset-independent timestamp selection and bounded missing-data repair."""
import numpy as np


def nearest_indices(times, targets):
    """Nearest timestamp, preferring the earlier observation on a tie."""
    times = np.asarray(times, dtype=np.float64)
    if times.ndim != 1 or not len(times) or not np.isfinite(times).all() or not np.isfinite(targets).all() or np.any(np.diff(times) <= 0):
        raise ValueError('Timestamps must be nonempty and strictly increasing')
    targets = np.asarray(targets, dtype=np.float64)
    hi = np.clip(np.searchsorted(times, targets), 0, len(times) - 1)
    lo = np.maximum(hi - 1, 0)
    return np.where(abs(times[lo] - targets) <= abs(times[hi] - targets) + 1e-10, lo, hi)


def clean_intervals(times, values, valid, *, max_gap=0.3):
    """Forward-fill bounded short missing runs; split long gaps; trim real endpoints.

    Missing duration is [first invalid timestamp, next valid timestamp), not the
    number of missing rows. Invalid leading/trailing runs are never extrapolated.
    Returns repaired values, original validity, age since source, and [start,end).
    """
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values).copy()
    original = np.asarray(valid, dtype=bool) & np.isfinite(values)
    if values.shape != original.shape or values.shape[0] != len(times):
        raise ValueError('Invalid values/validity shape')
    if len(times) == 0 or np.any(~np.isfinite(times)) or np.any(np.diff(times) <= 0):
        raise ValueError('Invalid timestamps')
    repaired = original.copy()
    age = np.zeros_like(values, dtype=np.float64)
    # Even absent table rows cannot hide a >= 0.3 s time discontinuity.
    cuts = np.r_[0, np.flatnonzero(np.diff(times) >= max_gap - 1e-6) + 1, len(times)]
    intervals = []
    for begin, end in zip(cuts[:-1], cuts[1:]):
        for d in range(values.shape[1]):
            missing = ~original[begin:end, d]
            edges = np.diff(np.r_[False, missing, False].astype(np.int8))
            for a, b in zip(np.flatnonzero(edges == 1) + begin,
                            np.flatnonzero(edges == -1) + begin):
                if a == begin or b == end or times[b] - times[a] >= max_gap - 1e-6:
                    continue
                values[a:b, d] = values[a - 1, d]
                repaired[a:b, d] = True
                age[a:b, d] = times[a:b] - times[a - 1]
        complete = repaired[begin:end].all(axis=1)
        edges = np.diff(np.r_[False, complete, False].astype(np.int8))
        for a, b in zip(np.flatnonzero(edges == 1) + begin,
                        np.flatnonzero(edges == -1) + begin):
            actual = np.flatnonzero(original[a:b].all(axis=1)) + a
            if len(actual) >= 2:
                intervals.append((int(actual[0]), int(actual[-1] + 1)))
    return values, original, age, intervals


def timestamp_pairs(times, *, horizon=1.2, tolerance=None):
    """Walk from each selected timestamp to nearest t+horizon, including tail."""
    times = np.asarray(times, dtype=np.float64)
    if times.ndim != 1 or not np.isfinite(times).all() or not np.isfinite(horizon) or horizon <= 0 or (tolerance is not None and (not np.isfinite(tolerance) or tolerance < 0)) or np.any(np.diff(times) <= 0):
        raise ValueError('Invalid timestamp pair options')
    # Upstream timestamps are float32; account for their quantization at large times.
    time_epsilon = max(1e-6, 2 * float(np.spacing(np.float32(np.max(np.abs(times)))))) if len(times) else 1e-6
    pairs = []
    i = 0
    while i < len(times) - 1:
        target = times[i] + horizon
        tail = bool(target > times[-1] + time_epsilon)
        j = len(times) - 1 if tail else int(nearest_indices(times, target))
        if j <= i:
            raise ValueError('Horizon did not advance time')
        if tail or tolerance is None or abs(times[j] - target) <= tolerance + 1e-6:
            pairs.append((i, j, tail))
        i = j
    return pairs
