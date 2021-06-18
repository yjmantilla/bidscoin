import logging
import shutil
from pathlib import Path
from typing import Union
from typing import Union, List, Tuple
from pathlib import Path
from sovabids.apply_rules import load_rules,get_info_from_path
from sovabids.utils import deep_merge,deep_merge_N, flatten,get_supported_extensions,mne_open,parse_string_from_template
try:
    from bidscoin import bidscoin, bids
except ImportError:
    import bidscoin, bids         # This should work if bidscoin was not pip-installed

LOGGER = logging.getLogger(__name__)


def is_sourcefile(file: Path) -> str:
    """
    This plugin function supports assessing whether the file is a valid sourcefile
    :param file:    The file that is assessed
    :return:        The valid dataformat of the file for this plugin
    """

    if is_eeg(file):
        return 'EEG'

    return ''

def is_eeg(file):
    if file.suffix in get_supported_extensions():
        return True
def get_eegfield(attribute,sourcefile,opt=None):
    opt = opt['sova2coin']
    #print('opt',opt)
    rules = {}
    if opt is not None:
        if 'rules_file' in opt:
            rules = load_rules(opt['rules_file'])
            rules = deep_merge(rules,opt)
            #print('rules',rules)
        #print(sourcefile.as_posix())
        info_path = get_info_from_path(sourcefile.as_posix(),rules)
        
        #print('info_path',info_path,sourcefile.__str__())
    # Upon reading RAW MNE makes the assumptions
    raw = mne_open(sourcefile.__str__() 
)
    rules = flatten(info_path)
    #print('flat_rules',rules)
    switcher = {
        'sidecar.SamplingFrequency': float(raw.info['sfreq']),
        'sidecar.PowerLineFrequency':('n/a' if raw.info['line_freq'] is None else
                              float(raw.info['line_freq'])),
        'sidecar.RecordingDuration':float(raw.times[-1]),
    }
    switcher.update(rules)
    return switcher.get(attribute, "n/a")

def get_attribute(dataformat: str, sourcefile: Path, attribute: str,opt:dict=None) -> Union[str, int]:
    """
    This plugin function supports reading attributes from DICOM and PAR dataformats
    :param dataformat:  The bidsmap-dataformat of the sourcefile, e.g. DICOM of PAR
    :param sourcefile:  The sourcefile from which the attribute value should be read
    :param attribute:   The attribute key for which the value should be read
    :return:            The attribute value
    """
    if dataformat == 'EEG':
        return get_eegfield(attribute, sourcefile,opt)


def bidsmapper_plugin(session: Path, bidsmap_new: dict, bidsmap_old: dict, template: dict, store: dict) -> None:
    """
    All the logic to map the Philips PAR/XML fields onto bids labels go into this function
    :param session:     The full-path name of the subject/session raw data source folder
    :param bidsmap_new: The study bidsmap that we are building
    :param bidsmap_old: Full BIDS heuristics data structure, with all options, BIDS labels and attributes, etc
    :param template:    The template bidsmap with the default heuristics
    :param store:       The paths of the source- and target-folder
    :return:
    """

    # Get started
    plugin     = {'sova2coin': bidsmap_new['Options']['plugins']['sova2coin']}
    datasource = bids.get_datasource(session, plugin)
    dataformat = datasource.dataformat
    if not dataformat:
        return

    # Collect the different EEG source files for all runs in the session
    sourcefiles = [sourcefile for sourcefile in session.rglob('*') if is_sourcefile(sourcefile)]

    # Update the bidsmap with the info from the source files
    for sourcefile in sourcefiles:

        # Input checks
        if not sourcefile.name or (not template[dataformat] and not bidsmap_old[dataformat]):
            LOGGER.error(f"No {dataformat} source information found in the bidsmap and template")
            return

        datasource = bids.DataSource(sourcefile, plugin, dataformat)

        if not datasource.is_datasource():
            continue

        # See if we can find a matching run in the old bidsmap
        run, index = bids.get_matching_run(datasource, bidsmap_old)

        # If not, see if we can find a matching run in the template
        if index is None:
            run, _ = bids.get_matching_run(datasource, template)

        # See if we have collected the run somewhere in our new bidsmap
        if not bids.exist_run(bidsmap_new, '', run):

            # Communicate with the user if the run was not present in bidsmap_old or in template, i.e. that we found a new sample
            LOGGER.info(f"Found '{run['datasource'].datatype}' {dataformat} sample: {sourcefile}")

            # Now work from the provenance store
            if store:
                targetfile             = store['target']/sourcefile.relative_to(store['source'])
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                run['provenance']      = str(shutil.copy2(sourcefile, targetfile))
                run['datasource'].path = targetfile

            # Copy the filled-in run over to the new bidsmap
            bids.append_run(bidsmap_new, run)

def get_eegfile(folder: Path, index: int=0) -> Path:
    """
    Gets a eeg-file from the folder

    :param folder:  The full pathname of the folder
    :param index:   The index number of the dicom file
    :return:        The filename of the first dicom-file in the folder.
    """

    files = sorted(folder.iterdir())

    idx = 0
    for file in files:
        if file.stem.startswith('.'):
            LOGGER.warning(f'Ignoring hidden file: {file}')
            continue
        if is_eeg(file):
            if idx == index:
                return file
            else:
                idx += 1

    return Path()
