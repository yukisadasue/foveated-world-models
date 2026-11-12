# Official Stage-1 source snapshot

Source: https://github.com/RLinf/LaWAM

Pinned commit: `c12168d9077edea67fe7c1b70d08b80b8e65a9c8`

Only the 12 files listed in `UPSTREAM.json` were fetched. Their contents are
unchanged; SHA-256 digests allow local verification. Four `__init__.py` package
markers were added locally. The earlier proposed tree was described as 13 files,
but its actual file count is 12.

The upstream root at this revision did not list a LICENSE file. No license is
assigned or changed by this extraction; preserve upstream notices and attribution.

The project-specific launcher, manifest dataset and configs live outside this
directory. They replace the upstream LightningCLI/StarVLA data integration while
reusing the official model, loss, augmentation and collator implementations.

No Stage-2 code, Git history, datasets or model weights are stored here.
