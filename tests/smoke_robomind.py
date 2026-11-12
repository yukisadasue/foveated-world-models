"""Real RoboMIND + frozen DINO: loader checks, two steps, save and resume."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/lawam'))
from vendor.dataset.robomind import RoboMINDDataset, check_disjoint, robomind_collate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-root', type=Path, default=Path('/data2/yuki_sadasue/datasets/RoboMIND-lerobot/preprocessed'))
    args = parser.parse_args()
    datasets = {s: RoboMINDDataset(args.prepared_root / f'{s}.jsonl', require_observed_endpoints=s!='train')
                for s in ('train','validation','test')}
    check_disjoint(*datasets.values())
    report = {}
    for name, ds in datasets.items():
        for index in np.linspace(0, len(ds)-1, min(8,len(ds)), dtype=int):
            batch = robomind_collate([ds[int(index)]])
            assert torch.isfinite(batch['states']).all()
            assert batch['videos'].shape == (1,2,3,256,256)
        report[name] = dict(pairs=len(ds), tail_pairs=int(sum(p[3] for p in ds.pairs)),
                            episodes=len(ds.episodes), groups=len(ds.groups))
    with tempfile.TemporaryDirectory(prefix='lawam-robomind-') as directory:
        temp = Path(directory)
        command = [sys.executable,str(ROOT/'train_stage1.py'),'--config',str(ROOT/'configs/stage1_smoke.yaml'),
                   '--train-manifest',str(args.prepared_root/'train.jsonl'),
                   '--val-manifest',str(args.prepared_root/'validation.jsonl'),'--output',str(temp/'run')]
        subprocess.run(command,check=True,cwd=ROOT)
        checkpoint=temp/'run/checkpoints/final.ckpt'
        saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
        assert saved['global_step']==2 and saved['optimizer_states']
        assert all(torch.isfinite(v).all() for v in saved['state_dict'].values() if v.is_floating_point())
        del saved
        config=yaml.safe_load((temp/'run/resolved_config.yaml').read_text())
        config['trainer']['max_steps']=3
        (temp/'resume.yaml').write_text(yaml.safe_dump(config))
        command[command.index('--config')+1]=str(temp/'resume.yaml')
        subprocess.run(command+['--resume',str(checkpoint)],check=True,cwd=ROOT)
        saved=torch.load(checkpoint,map_location='cpu',weights_only=False)
        assert saved['global_step']==3
    report['smoke']='PASS: sampled loaders; real DINO; tiny IDM/LaWM; two steps, checkpoint, resume to step 3'
    (args.prepared_root/'loader_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
