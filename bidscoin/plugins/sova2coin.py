import logging
import shutil
from pathlib import Path
from typing import Union
from typing import Union, List, Tuple
from pathlib import Path
import mne
from sovabids.rules import load_rules,get_info_from_path
from sovabids.utils import mne_open,deep_merge,deep_merge_N, flatten,get_supported_extensions,mne_open

from collections import OrderedDict
from ruamel.yaml.comments import CommentedMap,CommentedSeq
from mne_bids import write_raw_bids,BIDSPath
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
    if opt is not None:
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
    raw = mne_open(sourcefile.__str__())
    if opt is not None:
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

def formatData(t,s=0):
    string = ''
    if isinstance(t,CommentedSeq):
        n = len(t)
        t = {str(i):t[i] for i in range(n)}
    if isinstance(t,OrderedDict) or isinstance(t,CommentedMap):

        t = dict(t)
    if not isinstance(t,dict) and not isinstance(t,list):
        string+="\n"+("\t"*s+str(t))
    else:
        for key in t:
            string+="\n"+("\t"*s+str(key))
            if not isinstance(t,list):
                string+=formatData(t[key],s+1)
    return string

def bidscoiner_plugin(session: Path, bidsmap: dict, bidsfolder: Path, personals: dict) -> None:
    """
    The plugin to convert the runs in the source folder and save them in the bids folder. Each saved datafile should be
    accompanied with a json sidecar file. The bidsmap options for this plugin can be found in:

    bidsmap_new/old['Options']['plugins']['README']

    See also the dcm2niix2bids plugin for reference implementation

    :param session:     The full-path name of the subject/session raw data source folder
    :param bidsmap:     The full mapping heuristics from the bidsmap YAML-file
    :param bidsfolder:  The full-path name of the BIDS root-folder
    :param personals:   The dictionary with the personal information
    :return:            Nothing
    """
    # Get started and see what dataformat we have
    plugin     = {'sova2coin': bidsmap['Options']['plugins']['sova2coin']}
    datasource = bids.get_datasource(session, plugin)
    dataformat = datasource.dataformat
    if not dataformat:
        LOGGER.info(f"No {__name__} sourcedata found in: {session}")
        return

    # Make a list of all the data sources / runs
    #manufacturer = 'UNKNOWN'
    sources      = []
    if dataformat == 'EEG':
        sources      = bidscoin.lsdirs(session)
        print('HEY',sources,'len',len(sources))
        #manufacturer = datasource.attributes('Manufacturer')
    else:
        LOGGER.exception(f"Unsupported dataformat '{dataformat}'")

    # Get valid BIDS subject/session identifiers from the (first) DICOM- or PAR/XML source file
    subid, sesid = datasource.subid_sesid(bidsmap[dataformat]['subject'], bidsmap[dataformat]['session'])
    if not subid:
        return
    LOGGER.info(f'Using subid: {subid} and sesid {sesid} for {session} -> {bidsfolder}')

        # Process all the source files or run subfolders
    sourcefile = Path()

    # Collect the different EEG source files for all runs in the session
    sourcefiles = [sourcefile for sourcefile in session.rglob('*') if is_sourcefile(sourcefile)]

    for source in sourcefiles:

        # Get a data source
        if dataformat == 'EEG':
            sourcefile = source
        elif dataformat == 'PAR':
            sourcefile = source
        if not sourcefile.name:
            continue

        # Get a matching run from the bidsmap and update its run['datasource'] object
        datasource          = bids.DataSource(sourcefile, plugin, dataformat)
        run, index          = bids.get_matching_run(datasource, bidsmap)
        datasource          = run['datasource']
        datasource.path     = sourcefile
        datasource.plugins  = plugin
        datatype            = datasource.datatype

        # Check if we should ignore this run
        if datatype == bids.ignoredatatype:
            LOGGER.info(f"Leaving out: {source}")
            continue

        # Check if we already know this run
        if index is None:
            LOGGER.error(f"Skipping unknown '{datatype}' run: {sourcefile}\n-> Re-run the bidsmapper and delete {bidsses} to solve this warning")
            continue
        LOGGER.info(f"Processing: {source}")

        raw = mne_open(sourcefile.as_posix())
        l=[]
        for field,value in run['attributes'].items():
            if '.' in field:
                tree_list = field.split('.')
                tree_dict = value
                for key in reversed(tree_list):
                    tree_dict = {key: tree_dict}
                l.append(tree_dict)
        meta = deep_merge_N(l)
        entities=meta['entities']
        bids_path = BIDSPath(**entities,root=bidsfolder.as_posix())
        #print(bids_path)
        #TODO: Clean output folder before writing.
        write_raw_bids(raw, bids_path=bids_path,overwrite=True)
