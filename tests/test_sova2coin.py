from bidscoin.plugins.sova2coin import is_eeg,is_sourcefile,get_eegfield,get_attribute,get_eegfile,bidsmapper_plugin
from pathlib import Path
from bidscoin.bids import load_bidsmap
from bidscoin.bidscoin import lsdirs
p = Path(r"Y:\code\sovabids\_data\lemon2\sub-010003\ses-001\sub-010003.vhdr")
pnot = Path(r"Y:\code\sovabids\_data\lemon2\sub-010003\ses-001\sub-010003.eeg")

assert is_sourcefile(p)=='EEG'
assert is_sourcefile(pnot)==''
assert get_eegfield('SamplingFrequency',p) == 2500.0
assert get_attribute('EEG',p,'SamplingFrequency') == 2500.0

session_path = Path(r"Y:\code\sovabids\_data\lemon2\sub-010003")
lsdirs(session_path)
folder = session_path
wildcard='*'
[fname for fname in sorted(folder.glob(wildcard)) if fname.is_dir() and not fname.name.startswith('.')]

bidsmap, yamlfile = load_bidsmap(Path(r'Y:\code\bidscoin\bidscoin\heuristics\bidsmap_sovabids.yaml'))
bidsmapper_plugin(session=session_path, bidsmap_new=bidsmap, bidsmap_old=bidsmap, template=bidsmap, store=bidsmap)


