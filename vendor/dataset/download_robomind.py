from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from huggingface_hub import HfApi, hf_hub_download
import json, shutil
import argparse
parser=argparse.ArgumentParser(description='Download only RoboMIND FR3 dual top videos, states, and metadata')
parser.add_argument('--root', type=Path, default=Path('/data2/yuki_sadasue/datasets/RoboMIND-lerobot'))
ROOT=parser.parse_args().root.resolve()
ROOT.mkdir(parents=True, exist_ok=True)
REPO='Traly/RoboMIND-lerobot'
REV='71d7062c0e60351606674a55f51066454be7296d'
PREFIX='franka_fr3_dual/'
info=HfApi().dataset_info(REPO,revision=REV,files_metadata=True)
files=[f for f in info.siblings if f.rfilename=='README.md' or any(f.rfilename.startswith(PREFIX+p) for p in ['data/','meta/','videos/observation.images.camera_top/'])]
plan={'repo':REPO,'revision':REV,'bytes':sum(f.size for f in files),'files':[{'path':f.rfilename,'bytes':f.size} for f in files]}
(ROOT/'download_plan.json').write_text(json.dumps(plan,indent=2))
print('PLAN',len(files),plan['bytes'],flush=True)
def get(f):
 dst=ROOT/f.rfilename
 sample=ROOT.parent/'candidate-checks/RoboMIND'/f.rfilename
 if not dst.exists() and sample.is_file() and sample.stat().st_size==f.size:
  dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(sample,dst)
 if not dst.exists() or dst.stat().st_size!=f.size:
  hf_hub_download(REPO,f.rfilename,repo_type='dataset',revision=REV,local_dir=ROOT)
 if dst.stat().st_size!=f.size:raise RuntimeError(f.rfilename)
 return f.rfilename
with ThreadPoolExecutor(max_workers=6) as pool:
 futures=[pool.submit(get,f) for f in files]
 for i,f in enumerate(as_completed(futures),1):print(i,len(files),f.result(),flush=True)
(ROOT/'DOWNLOAD_COMPLETE.json').write_text(json.dumps({'repo':REPO,'revision':REV,'files':len(files),'bytes':plan['bytes'],'verification':'all selected files present with expected source sizes'},indent=2))
print('COMPLETE',flush=True)
