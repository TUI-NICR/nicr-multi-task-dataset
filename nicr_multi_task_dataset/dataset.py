# -*- coding: utf-8 -*-
"""
.. codeauthor:: Daniel Seichter <daniel.seichter@tu-ilmenau.de>
.. codeauthor:: Dominik Hoechemer <dominik.seichter@tu-ilmenau.de>

"""
import os

from . import img_utils
from .io_utils import get_files_by_extension
from .io_utils import read_json


# Sets
TRAIN_SET = 'train'
VALID_SET = 'valid'
TEST_SET = 'test'
SETS = (TRAIN_SET, VALID_SET, TEST_SET)

# Subfolders
_PATCH_SUBFOLDER = 'instances'
_JSON_SUBFOLDER = 'json'

# Define basename suffixes
_DEPTH_PATCH_SUFFIX = '_Depth.pgm'
_JSON_SUFFIX = '.json'
_MASK_SUFFIX = '_Mask.png'


class MultiTaskDataset(object):
    """
    Dataset container class.

    Parameters
    ----------
    dataset_basepath : str
        Path to dataset root, e.g. '/datasets/NICR-Multi-Task-Dataset/'.
    set_name : str
        Set to load, should be one of 'train', 'valid' or 'test'.
    """
    def __init__(self, dataset_basepath, set_name):
        assert set_name in SETS

        # store arguments
        self._dataset_basepath = dataset_basepath
        self._set_name = set_name

        # get all json files
        # therefore iterate over all sample categories
        set_path = os.path.join(self._dataset_basepath, self._set_name)
        categories = sorted(os.listdir(set_path))
        self._samples = []

        for category_name in categories:
            json_path = os.path.join(set_path, category_name, _JSON_SUBFOLDER)
            json_files = get_files_by_extension(json_path,
                                                extension='.json',
                                                flat_structure=True,
                                                recursive=True,
                                                follow_links=True)
            # load samples
            for fp in json_files:
                self._samples.append(Sample.from_filepath(fp))

    @property
    def dataset_basepath(self):
        return self._dataset_basepath

    @property
    def set_name(self):
        return self._set_name

    def strip_to_multiple_of_batch_size(self, batch_size):
        """
        Strip samples to multiple of the given batch size.

        Parameters
        ----------
        batch_size : int
            The batch size.

        """
        n_batches = len(self._samples) // batch_size
        self._samples = self._samples[:n_batches*batch_size]

    def __len__(self):
        return len(self._samples)

    def __getitem__(self, index):
        return self._samples[index]


class Sample(object):
    """
    Simple container for a single dataset sample.

    Parameters
    ----------
    basepath : str
        Path to dataset root, e.g. '/datasets/NICR-Multi-Task-Dataset/'.
    set_name : str
        Set to load, should be one of 'train', 'valid' or 'test'.
    category_name : str
        Category of the sample, e.g. 'person-sitting'.
    tape_name : str
        Recording name of the sample, e.g.,
        'p13_tape-iros2020-2020-01-31_14-11-44.891674'
    basename : str
        Basename of the sample, e.g. '10078_10000'.
    """
    def __init__(self, basepath, set_name, category_name, tape_name, basename):
        self._basepath = basepath
        self._set_name = set_name
        self._category_name = category_name
        self._tape_name = tape_name
        self._basename = basename

        # determine person name, e.g., a Name, or negative
        if category_name.split('-')[0] == 'person':
            self._person_name = tape_name.split('_')[0]
        else:
            self._person_name = 'negative'

        # determine json filepath
        self._json_filepath = self._build_filepath(_JSON_SUBFOLDER,
                                                   _JSON_SUFFIX)
        self._json = None

    def _build_filepath(self, subfolder, suffix):
        return os.path.join(self._basepath,
                            self._set_name,
                            self._category_name,
                            subfolder,
                            self._tape_name,
                            self._basename+suffix)

    @property
    def basepath(self):
        return self._basepath

    @property
    def set_name(self):
        return self._set_name

    @property
    def category_name(self):
        return self._category_name

    @property
    def tape_name(self):
        return self._tape_name

    @property
    def person_name(self):
        return self._person_name

    @property
    def basename(self):
        return self._basename

    @property
    def is_person(self):
        return self.json['Class'] != 'negative'

    @property
    def posture_class(self):
        if self.json['Class'] == 'standing':
            return 0
        elif self.json['Class'] == 'squatting':
            return 1
        elif self.json['Class'] == 'sitting':
            return 2
        elif self.json['Class'] == 'other':
            return 3
        # negative or person without posture
        return -100   # default ignore_index in PyTorch

    @property
    def posture_name(self):
        return self.json['Class']

    @property
    def orientation(self):
        return -100.    # default ignore_index in PyTorch

    @property
    def json(self):
        if not self._json:
            self._json = read_json(self._json_filepath)
        return self._json

    def get_depth_patch_filepath(self):
        return self._build_filepath(_PATCH_SUBFOLDER, _DEPTH_PATCH_SUFFIX)

    def get_depth_patch(self):
        return img_utils.load(self.get_depth_patch_filepath())

    def get_mask_filepath(self):
        return self._build_filepath(_PATCH_SUBFOLDER, _MASK_SUFFIX)

    def get_mask_patch(self):
        mask_full_image = img_utils.load(self.get_mask_filepath())
        roi_x_min = self.json['ROI_X']
        roi_x_max = self.json['ROI_Width'] + roi_x_min

        roi_y_min = self.json['ROI_Y']
        roi_y_max = self.json['ROI_Height'] + roi_y_min

        roi_x = [roi_x_min, roi_x_max]
        roi_y = [roi_y_min, roi_y_max]
        return mask_full_image[slice(*roi_y), slice(*roi_x), ...]

    @classmethod
    def from_filepath(cls, filepath):
        """
        Instantiate the entire sample object from a single given filepath to
        one of the depth/mask/json file.

        Parameters
        ----------
        filepath : str
            Filepath where to derive the basename from.

        Returns
        -------
        sample : Sample
            The sample object.

        """
        # Example Filepath:
        # '/NICR-Multi-Task-Dataset/train/person-squatting-2/instances/
        # p14_tape-1-2019-08-13_10-45-05.729928/10101_10000_Depth.pgm'

        # determine tape name (recording name), e.g.,
        # 'p14_tape-1-2019-08-13_10-45-05.729928'
        path, tape_name = os.path.split(os.path.dirname(filepath))

        # determine category name, e.g. 'person-squatting-2'
        path, _ = os.path.split(path)
        path, category_name = os.path.split(path)

        # determine set name, e.g., 'train'
        # determine basepath, e.g., '/NICR-Multi-Task-Dataset'
        basepath, set_name = os.path.split(path)

        # determine sample basename, e.g. 14384_10000
        basename = _get_sample_basename(filepath)

        return cls(basepath=basepath,
                   set_name=set_name,
                   category_name=category_name,
                   tape_name=tape_name,
                   basename=basename)


def load_set(dataset_basepath, set_name):
    """
    Load a specific set of the dataset.

    Parameters
    ----------
    dataset_basepath : str
        Path to dataset root, e.g. '/datasets/NICR-Multi-Task-Dataset/'.
    set_name : str
        Set to load, should be one of 'train', 'valid' or 'test'.

    Returns
    -------
    dataset : MultiTaskDataset

    """
    return MultiTaskDataset(dataset_basepath, set_name)


def _get_sample_basename(filepath):
    basename = os.path.basename(filepath)
    # remove possible suffixes
    for suffix in [_JSON_SUFFIX, _DEPTH_PATCH_SUFFIX]:
        basename = basename.replace(suffix, '')
    return basename
