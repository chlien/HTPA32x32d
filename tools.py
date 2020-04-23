"""
A collection of useful functions and data structures for working with data captured by Heimann HTPA32x32d and other thermopile sensor arrays.

Data types:
    * txt - Heimann HTPA recordings in *.TXT,
    * np - NumPy array of thermopile sensor array data, shaped [frames, height, width],
    * csv - thermopile sensor array data in *.csv file, NOT a pandas dataframe!
    * df - pandas dataframe,
    * pc - NumPy array of pseudocolored thermopile sensor array data, shaped [frames, height, width, channels],

Warnings:
    when converting TXT -> other types the array is rotated 90 deg. CW
    numpy array order is 'K'
    txt array order is 'F'
"""
import numpy as np
import pandas as pd
import cv2
import os
import imageio
from scipy.spatial.distance import cdist
import matplotlib.pyplot as plt
import pickle
import itertools
import json
import glob
import collections
import shutil


VERBOSE = False

DTYPE = "float32"
PD_SEP = ","
PD_NAN = np.inf
PD_DTYPE = np.float32
READ_CSV_ARGS = {"skiprows": 1}
PD_TIME_COL = "Time (sec)"
PD_PTAT_COL = "PTAT"

TPA_PREFIX_TEMPLATE = "YYYYMMDD_HHMM_ID{VIEW_IDENTIFIER}"
TPA_NFO_FN = "tpa.nfo"
PROCESSED_OK_KEY = "ALIGNED"
MADE_OK_KEY = "DATASET_PREPARED"

READERS_EXTENSIONS_DICT = {
    "txt": "txt",
    "csv": "csv",
    "pickle": "pickle",
    "pkl": "pickle",
    "p": "pickle",
}

SUPPORTED_EXTENSIONS = list(READERS_EXTENSIONS_DICT.keys())


def remove_extension(filepath):
    return filepath.split(".")[0]


def get_extension(filepath):
    return filepath.split(".")[1]


def ensure_path_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)


def ensure_parent_exists(path):
    ensure_path_exists(os.path.dirname(path))


def read_tpa_file(filepath: str, array_size: int = 32):
    """
    Convert Heimann HTPA file to NumPy array shaped [frames, height, width].
    Currently supported: see SUPPORTED_EXTENSIONS flag

    Parameters
    ----------
    filepath : str
    array_size : int, optional (for txt files only)

    Returns
    -------
    np.array
        3D array of temperature distribution sequence, shaped [frames, height, width].
    list
        list of timestamps
    """
    extension_lowercase = get_extension(filepath).lower()
    assert (extension_lowercase in SUPPORTED_EXTENSIONS)
    reader = READERS_EXTENSIONS_DICT[extension_lowercase]
    if reader == 'txt':
        return txt2np(filepath)
    if reader == 'csv':
        return csv2np(filepath)
    if reader == 'pickle':
        return pickle2np(filepath)


def write_tpa_file(filepath: str, array, timestamps: list) -> bool:
    """
    Convert and save Heimann HTPA NumPy array shaped [frames, height, width] to a txt file.
    Currently supported: see SUPPORTED_EXTENSIONS flag

    Parameters
    ----------
    filepath : str
        Filepath to destination file, including the file name.
    array : np.array
        Temperatue distribution sequence, shaped [frames, height, width].
    timestamps : list
        List of timestamps of corresponding array frames.
    """
    extension_lowercase = get_extension(filepath).lower()
    assert (extension_lowercase in SUPPORTED_EXTENSIONS)
    writer = READERS_EXTENSIONS_DICT[extension_lowercase]
    if writer == 'txt':
        return write_np2txt(filepath, array, timestamps)
    if writer == 'csv':
        return write_np2csv(filepath, array, timestamps)
    if writer == 'pickle':
        return write_np2pickle(filepath, array, timestamps)


def txt2np(filepath: str, array_size: int = 32):
    """
    Convert Heimann HTPA .txt to NumPy array shaped [frames, height, width].

    Parameters
    ----------
    filepath : str
    array_size : int, optional

    Returns
    -------
    np.array
        3D array of temperature distribution sequence, shaped [frames, height, width].
    list
        list of timestamps
    """
    with open(filepath) as f:
        # discard the first line
        _ = f.readline()
        # read line by line now
        line = "dummy line"
        frames = []
        timestamps = []
        while line:
            line = f.readline()
            if line:
                split = line.split(" ")
                frame = split[0: array_size ** 2]
                timestamp = split[-1]
                frame = np.array([int(T) for T in frame], dtype=DTYPE)
                frame = frame.reshape([array_size, array_size], order="F")
                frame *= 1e-2
                frames.append(frame)
                timestamps.append(float(timestamp))
        frames = np.array(frames)
        # the array needs rotating 90 CW
        frames = np.rot90(frames, k=-1, axes=(1, 2))
    return frames, timestamps


def write_np2txt(output_fp: str, array, timestamps: list) -> bool:
    """
        Convert and save Heimann HTPA NumPy array shaped [frames, height, width] to a txt file.

        Parameters
        ----------
        output_fp : str
            Filepath to destination file, including the file name.
        array : np.array
            Temperatue distribution sequence, shaped [frames, height, width].
        timestamps : list
            List of timestamps of corresponding array frames.
        """
    ensure_parent_exists(output_fp)
    frames = np.rot90(array, k=1, axes=(1, 2))
    with open(output_fp, 'w') as file:
        file.write('HTPA32x32d\n')
        for step, t in zip(frames, timestamps):
            line = ""
            for val in step.flatten("F"):
                line += ("%02.2f" % val).replace(".", "")[:4] + " "
            file.write("{}t: {}\n".format(line, t))


def write_np2pickle(output_fp: str, array, timestamps: list) -> bool:
    """
    Convert and save Heimann HTPA NumPy array shaped [frames, height, width] to a pickle file.

    Parameters
    ----------
    output_fp : str
        Filepath to destination file, including the file name.
    array : np.array
        Temperatue distribution sequence, shaped [frames, height, width].
    timestamps : list
        List of timestamps of corresponding array frames.
    """
    ensure_parent_exists(output_fp)
    with open(output_fp, "wb") as f:
        pickle.dump((array, timestamps), f)
    return True


def pickle2np(filepath: str):
    """
    Convert Heimann HTPA .txt to NumPy array shaped [frames, height, width].

    Parameters
    ----------
    filepath : str

    Returns
    -------
    np.array
        3D array of temperature distribution sequence, shaped [frames, height, width].
    list
        list of timestamps
    """
    with open(filepath, "rb") as f:
        frames, timestamps = pickle.load(f)
    return frames, timestamps


def write_np2csv(output_fp: str, array, timestamps: list) -> bool:
    """
    Convert and save Heimann HTPA NumPy array shaped [frames, height, width] to .CSV dataframe.
    CSV should preferably represent the data collected without preprocessing, cropping or any data manipulation.  

    Parameters
    ----------
    output_fp : str
        Filepath to destination file, including the file name.
    array : np.array
        Temperatue distribution sequence, shaped [frames, height, width].
    timestamps : list
        List of timestamps of corresponding array frames.
    """
    ensure_parent_exists(output_fp)
    # initialize csv template (and append frames later)
    # prepend first row for compability with legacy format
    first_row = pd.DataFrame({"HTPA 32x32d": []})
    first_row.to_csv(output_fp, index=False, sep=PD_SEP)
    headers = {PD_TIME_COL: [], PD_PTAT_COL: []}
    df = pd.DataFrame(headers)
    for idx in range(np.prod(array.shape[1:])):
        df.insert(len(df.columns), "P%04d" % idx, [])
    df.to_csv(output_fp, mode="a", index=False, sep=PD_SEP)

    for idx in range(array.shape[0]):
        frame = array[idx, ...]
        timestamp = timestamps[idx]
        temps = list(frame.flatten())
        row_data = [timestamp, PD_NAN]
        row_data.extend(temps)
        row = pd.DataFrame([row_data])
        row = row.astype(PD_DTYPE)
        row.to_csv(output_fp, mode="a", header=False, sep=PD_SEP, index=False)
    return True


def csv2np(csv_fp: str):
    """
    Read and convert .CSV dataframe to a Heimann HTPA NumPy array shaped [frames, height, width]

    Parameters
    ----------
    csv_fp : str
        Filepath to the csv file tor read.

    Returns
    -------
    array : np.array
        Temperatue distribution sequence, shape [frames, height, width].
    timestamps : list
        List of timestamps of corresponding array frames.
    """
    df = pd.read_csv(csv_fp, **READ_CSV_ARGS)
    timestamps = df[PD_TIME_COL]
    array = df.drop([PD_TIME_COL, PD_PTAT_COL], axis=1).to_numpy(dtype=DTYPE)
    array = reshape_flattened_frames(array)
    return array, timestamps


def apply_heatmap(array, cv_colormap: int = cv2.COLORMAP_JET) -> np.ndarray:
    """
    Applies pseudocoloring (heatmap) to a sequence of thermal distribution. Same as np2pc().
    np2pc() is preffered.

    Parameters
    ----------
    array : np.array
         (frames, height, width)
    cv_colormap : int, optional

    Returns
    -------
    np.array
         (frames, height, width, channels)
    """
    min, max = array.min(), array.max()
    shape = array.shape
    array_normalized = (255 * ((array - min) / (max - min))).astype(np.uint8)
    heatmap_flat = cv2.applyColorMap(array_normalized.flatten(), cv_colormap)
    return heatmap_flat.reshape([shape[0], shape[1], shape[2], 3])


def np2pc(array, cv_colormap: int = cv2.COLORMAP_JET) -> np.ndarray:
    """
    Applies pseudocoloring (heatmap) to a sequence of thermal distribution. Same as apply_heatmap().
    np2pc() is preffered.

    Parameters
    ----------
    array : np.array
         (frames, height, width)
    cv_colormap : int, optional

    Returns
    -------
    np.array
         (frames, height, width, channels)
    """
    return apply_heatmap(array, cv_colormap)


def save_frames(array, dir_name: str, extension: str = ".bmp") -> bool:
    """
    Exctracts and saves frames from a sequence array into a folder dir_name

    Parameters
    ----------
    array : np.array
         (frames, height, width, channels)

    Returns
    -------
    bool
        True if success
    """
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    for idx, frame in enumerate(array):
        cv2.imwrite(os.path.join(dir_name, "%d" % idx + extension), frame)
    return True


def flatten_frames(array):
    """
    Flattens array of shape [frames, height, width] into array of shape [frames, height*width]

    Parameters
    ----------
    array : np.array
         (frames, height, width)

    Returns
    -------
    np.array
        flattened array (frames, height, width)
    """
    _, height, width = array.shape
    return array.reshape((-1, height * width))


def write_pc2gif(array, fp: str, fps=10, loop: int = 0, duration=None):
    """
    Converts and saves NumPy array of pseudocolored thermopile sensor array data, shaped [frames, height, width, channels], into a .gif file

    Parameters
    ----------
    array : np.array
        Pseudocolored data (frames, height, width, channels).
    fp : str
        The filepath to write to.
    fps : float, optional
        Default 10, approx. equal to a typical thermopile sensor array FPS value.
    loop : int, optional
        The number of iterations. Default 0 (meaning loop indefinitely).
    duration : float, list, optional
        The duration (in seconds) of each frame. Either specify one value
        that is used for all frames, or one value for each frame.
        Note that in the GIF format the duration/delay is expressed in
        hundredths of a second, which limits the precision of the duration. (from imageio doc)

    Returns
    -------
    bool
        True if success.
    """
    ensure_parent_exists(fp)
    if not duration:
        duration = 1 / fps
    with imageio.get_writer(fp, mode="I", duration=duration, loop=loop) as writer:
        for frame in array:
            writer.append_data(frame[:, :, ::-1])
    return True


def timestamps2frame_durations(timestamps: list, last_frame_duration=None) -> list:
    """
    Produces frame durations list to make gifs produced with write_pc2gif() more accurate temporally, 
    
    Parameters
    ----------
    timestamps : list
        List of timestamps of corresponding array frames.
    last_frame_duration : float, optional
        List of N timestamps gives information about durations of N-1 initial frames, 
        if not given, the function will duplicate the last value in the produced list to make up for the missing frame duration.

    Returns
    -------
    list
        List of frame durations.
    """
    frame_durations = [x_t2 - x_t1 for x_t1,
                       x_t2 in zip(timestamps, timestamps[1:])]
    if not last_frame_duration:
        last_frame_duration = frame_durations[-1]
    frame_durations.append(last_frame_duration)
    return frame_durations


def reshape_flattened_frames(array):
    """
    Reshapes array shaped [frames, height*width] into array of shape [frames, height, width]

    Parameters
    ----------
    array : np.array
         flattened array (frames, height*width)

    Returns
    -------
    np.array
        reshaped array (frames, height, width)
    """
    _, elements = array.shape
    height = int(elements ** (1 / 2))
    width = height
    return array.reshape((-1, height, width))


def crop_center(array, crop_height, crop_width):
    """
    Crops the center portion of an infrared sensor array image sequence.


    Parameters
    ---------
    array : np.array
        (frames, height, width)
    crop_height : int
        height of the cropped patch, if -1 then equal to input's height
    crop_width : int
        width of the cropped patch, if -1 then equal to input's width

    Returns
    -------
    np.array
        cropped array (frames, crop_height, crop_width)
    """
    _, height, width = array.shape
    crop_height = height if (crop_height == -1) else crop_height
    start_y = height//2 - crop_height//2
    crop_width = width if (crop_width == -1) else crop_width
    start_x = width//2 - crop_width//2
    return array[:, start_y:start_y+crop_height, start_x:start_x+crop_width]


def match_timesteps(*timestamps_lists):
    """
    Aligns timesteps of given timestamps.


    Parameters
    ---------
    *timestamps_list : list, np.array
        lists-like data containing timestamps 
    Returns
    -------
    list
        list of indices of timesteps corresponding to input lists so that input lists are aligned
    
    Example:
        ts1 = [1, 2, 3, 4, 5]
        ts2 = [1.1, 2.1, 2.9, 3.6, 5.1, 6, 6.1]
        ts3 = [0.9, 1.2, 2, 3, 4.1, 4.2, 4.3, 4.9]
        idx1, idx2, idx3 = match_timesteps(ts1, ts2, ts3)
    now ts1[idx1], ts2[idx2] and ts3[idx3] will be aligned
    """
    ts_list = [np.array(ts).reshape(-1, 1) for ts in timestamps_lists]
    min_len_idx = np.array([len(ts) for ts in ts_list]).argmin()
    min_len_ts = ts_list[min_len_idx]
    indices_list = [None] * len(ts_list)
    for idx, ts in enumerate(ts_list):
        if (idx == min_len_idx):
            indices_list[idx] = list(range(len(min_len_ts)))
        else:
            indices_list[idx] = list(cdist(min_len_ts, ts).argmin(axis=-1))
    return indices_list


def resample_np_tuples(arrays, indices=None, step=None):
    """
    Resampling for 3D arrays
    #TODO
    #TODO START, STOP
    """
    if step:
        return [array[range(0, len(array), step)] for array in arrays]
    if indices:
        if len(arrays) != len(indices):
            raise ValueError('Iterables have different lengths')
        resampled_arrays = []
        for array, ids in zip(arrays, indices):
            resampled_arrays.append(array[ids])
        return resampled_arrays
    return arrays


def save_temperature_histogram(array, fp="histogram.png", bins=None, xlabel='Temperature grad. C', ylabel='Number of pixels', title='Histogram of temperature', grid=True, mu=False, sigma=False):
    """
    Saves a histogram of measured temperatures


    Parameters
    ---------
    array : np.array
        (frames, height, width)
    fp : str
        filepath to save plotted histogram to
    bins, xlabel, ylabel, title, grid
        as in pyplot
    """
    data = array.flatten()
    hist = plt.hist(data, bins=bins)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    text = r'{}{}{}'.format('$\mu={0:.2f} \degree C$'.format(data.mean()) if mu else '', ', ' if (
        mu and sigma) else '', '$\sigma={0:.2f} \degree C$'.format(data.std()) if sigma else '')
    plt.title("{} {}".format(title, text))
    plt.grid(grid)
    plt.savefig(fp)
    plt.close('all')
    return True


def resample_timestamps(timestamps, indices=None, step=None):
    """
    Resampling for timestamps
    #TODO
    #TODO START, STOP
    """
    ts_array = [np.array(ts) for ts in timestamps]
    return [list(ts) for ts in resample_np_tuples(ts_array, indices, step)]


def debug_HTPA32x32d_txt(filepath: str, array_size=32):
    """
    Debug Heimann HTPA .txt by attempting to convert to NumPy array shaped [frames, height, width].

    Parameters
    ----------
    filepath : str
    array_size : int, optional

    Returns
    -------
    int
        line that raises error, -1 if no error
    """
    with open(filepath) as f:
        line_n = 1
        _ = f.readline()
        line = "dummy line"
        frames = []
        timestamps = []
        while line:
            line_n += 1
            line = f.readline()
            if line:
                try:
                    split = line.split(" ")
                    frame = split[0: array_size ** 2]
                    timestamp = split[-1]
                    frame = np.array([int(T) for T in frame], dtype=DTYPE)
                    frame = frame.reshape([array_size, array_size], order="F")
                    frame *= 1e-2
                    frames.append(frame)
                    timestamps.append(float(timestamp))
                except:
                    split = line.split(" ")
                    frame = split[0: array_size ** 2]
                    timestamp = split[-1]
                    T_idx = 0
                    for T in frame:
                        try:
                            _ = int(T)
                        except:
                            break
                        T_idx += 1
                    print("{} caused error at line {} (t: {}), bit {} (= {})".format(
                        filepath, line_n, timestamp, T_idx, frame[T_idx]))
                    for idx in range(-3, 3 + 1):
                        try:
                            print("bit {}: {}".format(
                                T_idx-idx, frame[T_idx-idx]))
                        except:
                            pass
                    return line_n
        frames = np.array(frames)
        # the array needs rotating 90 CW
        frames = np.rot90(frames, k=-1, axes=(1, 2))
    return -1


class _TPA_Sample():
    def test_alignment(self):
        lengths = [len(ts) for ts in self.timestamps]
        return all(l == lengths[0] for l in lengths)

    def test_synchronization(self, max_error):
        pairs = itertools.combinations(self.timestamps, 2)
        for pair in pairs:
            if (np.abs(np.array(pair[0]) - np.array(pair[1])).max() > max_error):
                return False
        return True


class TPA_Sample_from_filepaths(_TPA_Sample):
    """
    # TODO
    """

    def __init__(self, filepaths):
        self.filepaths = filepaths
        self.ids = [self._read_ID(fp) for fp in self.filepaths]
        samples = [read_tpa_file(fp) for fp in self.filepaths]
        self.arrays = [sample[0] for sample in samples]
        self.timestamps = [sample[1] for sample in samples]

    def _read_ID(self, filepath):
        fn = os.path.basename(filepath)
        name = remove_extension(fn)
        return name.split("ID")[-1]

    def write(self):
        raise Exception(
            "You are trying to overwrite files. Use TPA_Sample_from_data if you need to modify arrays.")

    def align_timesteps(self):
        raise Exception(
            "Use TPA_Sample_from_data if you need to modify arrays.")


class TPA_Sample_from_data(_TPA_Sample):
    """
    # TODO
    """

    def __init__(self, arrays, timestamps, ids, output_filepaths = None):
        self.filepaths = None
        self.ids = ids.copy()
        self.arrays = arrays.copy()
        self.timestamps = timestamps.copy()
        if output_filepaths:
            self.filepaths = output_filepaths

    def make_filepaths(self, parent_dir, prefix, extension):
        self.filepaths = [os.path.join(
            parent_dir, prefix+"ID"+id+"."+extension) for id in self.ids]

    def write(self):
        assert self.filepaths
        for fp, array, ts in zip(self.filepaths, self.arrays, self.timestamps):
            write_tpa_file(fp, array, ts)

    def align_timesteps(self, reset_T0 = False):
        indexes = match_timesteps(*self.timestamps)
        for i in range(len(self.ids)):
            self.arrays[i] = self.arrays[i][indexes[i]]
            timestamps = np.array(self.timestamps[i])[indexes[i]]
            self.timestamps[i] = list(timestamps)
        if reset_T0:
            sample_T0_min = np.min([ts[0] for ts in self.timestamps])
            timestamps = [np.array(ts)-sample_T0_min for ts in self.timestamps]
            self.timestamps = timestamps
        return True


def _TPA_get_file_prefix(filepath):
    name = remove_extension(os.path.basename(filepath))
    return name.split("ID")[0]


class _TPA_File_Manager():
    def __init__(self):
        self.configured = False
        if VERBOSE:
            self._make_log = "make.log"
            if os.path.exists(self._make_log):
                os.remove(self._make_log)
        self._log_msgs = []

    def _log(self, log_msg):
        if VERBOSE:
            print(log_msg)
            with open(self._make_log, 'a') as f:
                f.write(log_msg+"\n")

    def _generate_config_template(self, output_json_filepath, fill_dict=None):
        template = {}
        for key in self._json_required_keys:
            template[key] = ""
        if fill_dict:
            for key in fill_dict:
                template[key] = fill_dict[key]
        with open(output_json_filepath, 'w') as f:
            json.dump(template, f)
        return True

    def _validate_config(self):
        keys_missing = []
        for key in self._json_required_keys:
            try:
                self._json[key]
            except KeyError:
                keys_missing.append(key)
        if len(keys_missing):
            msg = "Keys required {}".format(self._json_required_keys)
            self._log(msg)
            msg = "Keys missing {}".format(keys_missing)
            self._log(msg)
            return False
        try:
            if (self._json["PREPARE"] and self._json["MAKE"]):
                raise Exception(
                    "MAKE and PREPARE flags cannot be set at the same time to TRUE")
        except KeyError:
            pass
        return True

    def _remove_missing_views(self, prefixes, prefixes2filter):
        # filter out samples that miss views
        counter = collections.Counter(prefixes)
        view_number = len(self.view_IDs)
        for prefix in counter.keys():
            prefix_view_number = counter[prefix]
            if (prefix_view_number < view_number):
                prefixes2filter.remove(prefix)
                self._log('[WARNING] Ignoring prefix {} because it misses {} views'.format(
                    prefix, view_number-prefix_view_number))
        return prefixes2filter


class TPA_Preparer(_TPA_File_Manager):
    def __init__(self):
        _TPA_File_Manager.__init__(self)
        self._json_required_keys = ["raw_input_dir", "processed_destination_dir", "view_IDs",
                                    "tpas_extension", "MAKE", "PREPARE"]

    def generate_config_template(self, output_json_filepath):
        self._generate_config_template(
            output_json_filepath, {"MAKE": 0, "PREPARE": 1})

    def config(self, json_filepath):
        with open(json_filepath) as f:
            self._json = json.load(f)
        assert self._validate_config()
        assert self._json["PREPARE"]
        self.raw_input_dir = self._json["raw_input_dir"]
        self.processed_destination_dir = self._json["processed_destination_dir"]
        self.view_IDs = self._json["view_IDs"]
        self.tpas_extension = self._json["tpas_extension"]
        self.configured = True
        return True

    def prepare(self):
        if not self.configured:
            msg = "Configure with config() first"
            self._log(msg)
            raise Exception(msg)
        ensure_path_exists(self.raw_input_dir)
        glob_patterns = [os.path.join(
            self.raw_input_dir, "*ID"+id+"."+self.tpas_extension) for id in self.view_IDs]
        files = []
        for pattern in glob_patterns:
            files.extend(glob.glob(pattern))
        prefixes = [_TPA_get_file_prefix(f) for f in files]
        prefixes2process = list(set(prefixes))
        prefixes2process_number0 = len(prefixes2process)
        # filter out samples that miss views
        prefixes2process = self._remove_missing_views(prefixes, prefixes2process)
        self._log("Reading, aligning and removing T0 from samples...")
        for prefix in prefixes2process:
            raw_fp_prefix = os.path.join(self.raw_input_dir, prefix)
            processed_fp_prefix = os.path.join(self.processed_destination_dir, prefix)
            raw_fps = [raw_fp_prefix + "ID" + view_id + "." + self.tpas_extension for view_id in self.view_IDs]
            processed_fps = [processed_fp_prefix + "ID" + view_id + "." + self.tpas_extension for view_id in self.view_IDs]
            raw_sample = TPA_Sample_from_filepaths(raw_fps)
            processed_sample =  TPA_Sample_from_data(raw_sample.arrays, raw_sample.timestamps, raw_sample.ids, processed_fps)
            processed_sample.align_timesteps(reset_T0=True)
            processed_sample.write()
        self._write_nfo()
        self._write_labels_file(prefixes2process)
        self._write_make_file()
        self._log("Writing nfo, labels and json files...")
        self._log("OK")
        
    def _write_nfo(self):
        filepath = os.path.join(self.processed_destination_dir, TPA_NFO_FN)
        data = {PROCESSED_OK_KEY : 1}
        with open(filepath, 'w') as f:
            json.dump(data, f)
    
    def _write_labels_file(self, prefixes2label):
        filepath = os.path.join(self.processed_destination_dir, "labels.json")
        data = {prefix:"" for prefix in prefixes2label}
        with open(filepath, 'w') as f:
            json.dump(data, f)

    def _write_make_file(self):
        filepath = os.path.join(self.processed_destination_dir, "make_config.json")
        dataset_maker = TPA_Dataset_Maker()
        fill_dict = {}
        fill_dict.update({"view_IDs":self.view_IDs})
        fill_dict.update({"tpas_extension":self.tpas_extension})
        fill_dict.update({"processed_input_dir":self.processed_destination_dir})
        fill_dict.update({"labels_filepath":os.path.join(self.processed_destination_dir, "labels.json")})
        fill_dict.update({"MAKE":1})
        fill_dict.update({"PREPARE":0})
        dataset_maker.generate_config_template(filepath, fill_dict)


class TPA_Dataset_Maker(_TPA_File_Manager):
    '''
    #TODO CALL A TPA_Preparer FIRST
    '''

    def __init__(self):
        _TPA_File_Manager.__init__(self)
        self._json_required_keys = ["dataset_destination_dir", "view_IDs",
                                    "processed_input_dir", "labels_filepath", "tpas_extension", "MAKE", "PREPARE"]

    def config(self, json_filepath):
        with open(json_filepath) as f:
            self._json = json.load(f)
        assert self._validate_config()
        assert self._json["MAKE"]
        self.dataset_destination_dir = self._json["dataset_destination_dir"]
        self.view_IDs = self._json["view_IDs"]
        self.processed_input_dir = self._json["processed_input_dir"]
        if not os.path.exists(os.path.join(self.processed_input_dir, TPA_NFO_FN)):
            raise Exception("{} doesn't exist. Process your data first using TPA_Preparer".format(
                os.path.join(self.processed_input_dir, TPA_NFO_FN)))
        with open(os.path.join(self.processed_input_dir, TPA_NFO_FN)) as f:
            nfo = json.load(f)
        assert nfo[PROCESSED_OK_KEY]
        self.labels_filepath = self._json["labels_filepath"]
        if not os.path.exists(self._json["labels_filepath"]):
            msg = "Specified label file doesn't exist {}".format(
                self._json["labels_filepath"])
            self._log(msg)
            raise Exception(msg)
        self.tpas_extension = self._json["tpas_extension"]
        self.configured = True
        return True

    def generate_config_template(self, output_json_filepath, fill_dict = None):
        init_fill_dict = {"MAKE": 1, "PREPARE": 0}
        if fill_dict:
            init_fill_dict.update(fill_dict)
        self._generate_config_template(
            output_json_filepath, fill_dict=init_fill_dict)

    def make(self):
        if not self.configured:
            msg = "Configure with config() first"
            self._log(msg)
            raise Exception(msg)
        ensure_path_exists(self.dataset_destination_dir)
        glob_patterns = [os.path.join(
            self.processed_input_dir, "*ID"+id+"."+self.tpas_extension) for id in self.view_IDs]
        files = []
        for pattern in glob_patterns:
            files.extend(glob.glob(pattern))
        prefixes = [_TPA_get_file_prefix(f) for f in files]
        prefixes2make = list(set(prefixes))
        prefixes2make_number0 = len(prefixes2make)
        # filter out samples that miss views
        prefixes2make = self._remove_missing_views(prefixes, prefixes2make)
        # filter out samples that miss a label
        self._labels = self._read_labels_file(self.labels_filepath)
        for prefix in prefixes2make:
            if (prefix not in self._labels):
                prefixes2make.remove(prefix)
                self._log('[WARNING] Ignoring prefix {} because it misses a label'.format(
                    prefix))
        for prefix in prefixes2make:
            if not self._labels[prefix]:
                prefixes2make.remove(prefix)
                self._log('[WARNING] Ignoring prefix {} because it misses a label'.format(
                    prefix))
        for prefix in prefixes2make:
            if not (type(self._labels[prefix]) == int):
                prefixes2make.remove(prefix)
                self._log('[WARNING] Ignoring prefix {} because the label is incorrect (it is not an integer)'.format(
                    prefix))
        # process the files
        fps2copy = []
        fps2output = []
        for prefix in prefixes2make:
            fp_prefix = os.path.join(self.processed_input_dir, prefix)
            fp_o_prefix = os.path.join(self.dataset_destination_dir, prefix)
            fps = []
            fps_o = []
            for view_id in self.view_IDs:
                fp = fp_prefix + "ID" + view_id + "." + self.tpas_extension
                fp_o = fp_o_prefix + "ID" + view_id + "." + self.tpas_extension
                fps.append(fp)
                fps_o.append(fp_o)
            fps2copy.append(fps)
            fps2output.append(fps_o)
        prefixes2make_number = len(set(prefixes2make))
        prefixes_ignored = prefixes2make_number0 - prefixes2make_number
        self._log("[INFO] {} prefixes ignored out of initial {}".format(
            prefixes_ignored, prefixes2make_number0))
        if (prefixes_ignored == prefixes2make_number0):
            self._log("[WARNING] All files ignored, dataset is empty.")
            self._log("FAILED")
            return False
        self._log("[INFO] Making dataset...")
        self._log("[INFO] Copying files...")
        for src_tuple, dst_tuple in zip(fps2copy, fps2output):
            for src, dst in zip(src_tuple, dst_tuple):
                shutil.copy2(src, dst)
        self._log("Writing nfo, labels and json files...")
        self._write_nfo()
        self._copy_labels_file()
        self._log("OK")
        return True
        
    def _write_nfo(self):
        filepath = os.path.join(self.dataset_destination_dir, TPA_NFO_FN)
        data = {MADE_OK_KEY : 1}
        with open(filepath, 'w') as f:
            json.dump(data, f)
    
    def _copy_labels_file(self):
        src = os.path.join(self.labels_filepath)
        dst = os.path.join(self.dataset_destination_dir, "labels.json")
        shutil.copy2(src, dst)

    def _read_labels_file(self, json_filepath):
        with open(json_filepath) as f:
            data = json.load(f)
        for key in data.keys():
            if (len(key.split("ID")) > 1):
                old_key = key
                new_key = key.split("ID")[0]
                data[new_key] = data.pop(old_key)
        return data

