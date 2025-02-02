# conx - a neural network library
#
# Copyright (c) Douglas S. Blank <doug.blank@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor,
# Boston, MA 02110-1301  USA

import numbers
import PIL
import base64
import itertools
import functools
import operator
import random
import io
import numpy as np
#~dk
#import keras
from tensorflow import keras

from keras.utils import to_categorical
import matplotlib.pyplot as plt
from urllib.parse import urlparse
import requests
import zipfile
import types
import math
import tqdm
import sys
import os
import re

try:
    from IPython import get_ipython
except:
    get_ipython = lambda: None

#------------------------------------------------------------------------
# configuration settings

AVAILABLE_COLORMAPS = sorted(list(plt.cm.cmap_d.keys()))
CURRENT_COLORMAP = "seismic_r"
ERROR_COLORMAP = "seismic_r"
_PROGRESS_BAR = 'standard'

SEED = None

array = np.array

def progress_bar(*args, **kwargs):
    if _PROGRESS_BAR is None:
        if args:
            return lambda i: i
        else:
            return None
    elif _PROGRESS_BAR == "notebook":
        return tqdm.tqdm_notebook(*args, **kwargs)
    elif _PROGRESS_BAR == "standard":
        return tqdm.tqdm(*args, **kwargs)
    else:
        raise Exception("no such progress bar: use None, 'notebook', or 'standard'")

def set_progress_bar(mode):
    global _PROGRESS_BAR
    if mode in [None, 'notebook', 'standard']:
        _PROGRESS_BAR = mode
    else:
        raise Exception("no such progress mode: use None, 'notebook', or 'standard'")

def get_progress_bar():
    return _PROGRESS_BAR

def set_colormap(s):
    """
    Set the global colormap for displaying all network activations.

    Arguments:
        s (str) - valid name of a matplotlib colormap.

    See also:
        AVAILABLE_COLORMAPS - complete list of valid colormap names

    Examples:
        >>> cm = get_colormap()
        >>> set_colormap(AVAILABLE_COLORMAPS[0])
        >>> cm != get_colormap()
        True
        >>> set_colormap(cm)
        >>> cm == get_colormap()
        True
    """
    global CURRENT_COLORMAP
    assert s in AVAILABLE_COLORMAPS, "Unknown colormap: %s" % s
    CURRENT_COLORMAP = s

def set_error_colormap(s):
    """
    Set the error color map for display error values.

    Arguments:
        s (str) - valid name of a matplotlib colormap.

    See also:
        AVAILABLE_COLORMAPS - complete list of valid colormap names

    Examples:
        >>> cm = get_error_colormap()
        >>> set_error_colormap(AVAILABLE_COLORMAPS[0])
        >>> cm == get_error_colormap()
        False
        >>> set_error_colormap(cm)
        >>> cm != get_error_colormap()
        False
    """
    global ERROR_COLORMAP
    assert s in AVAILABLE_COLORMAPS, "Unknown colormap: %s" % s
    ERROR_COLORMAP = s

def get_error_colormap():
    """
    Get the global error colormap.

    Returns:
        The valid name of the global error colormap.

    Examples:
        >>> cm = get_error_colormap()
        >>> set_error_colormap(AVAILABLE_COLORMAPS[0])
        >>> cm != get_error_colormap()
        True
        >>> set_error_colormap(cm)
        >>> cm == get_error_colormap()
        True
    """
    return ERROR_COLORMAP

def get_colormap():
    """
    Get the global colormap.

    Returns:
        The valid name of the global colormap.

    Examples:
        >>> cm = get_colormap()
        >>> set_colormap(AVAILABLE_COLORMAPS[0])
        >>> cm == get_colormap()
        False
        >>> set_colormap(cm)
        >>> cm != get_colormap()
        False
    """
    return CURRENT_COLORMAP

#------------------------------------------------------------------------
# utility classes

#------------------------------------------------------------------------
# utility functions

def get_dtype(item):
    """
    Attempt to get the datatype from an item.

    >>> get_dtype(1)
    'float32'

    >>> get_dtype(True)
    'bool'

    >>> get_dtype(1.1)
    'float32'

    >>> get_dtype([1])
    'float32'

    >>> get_dtype([[[1, 2, 3]]])
    'float32'

    >>> get_dtype(np.array([True, False, True], dtype=bool))
    'bool'
    """
    if hasattr(item, "dtype"):
        return item.dtype.name
    elif isinstance(item, bool):
        return "bool"
    elif isinstance(item, str):
        return "str"
    elif isinstance(item, numbers.Real):
        return "float32"
    else:
        try:
            return get_dtype(item[0])
        except:
            return None

def clear_session():
    """
    Needed to clear the session if memory is growing.
    """
    from keras import backend as K
    K.clear_session()

def is_array_like(item):
    """
    Checks to see if something is array-like.

    >>> import numpy as np
    >>> is_array_like([])
    True
    >>> is_array_like(tuple())
    True
    >>> is_array_like(np.ndarray([]))
    True

    >>> is_array_like("hello")
    False
    >>> is_array_like(1)
    False
    >>> is_array_like(2.3)
    False
    >>> is_array_like(np)
    False
    """
    return (not hasattr(item, "strip") and
            (hasattr(item, "__getitem__") or
             hasattr(item, "__iter__")))

def find_factors(n):
    """
    Find the integer factors of n.
    """
    return set(functools.reduce(
        operator.add,
        ([i, n//i] for i in range(1, int(pow(n, 0.5) + 1)) if n % i == 0)))

def find_dimensions(n):
    """
    Find the best (most square) dimensions of n.
    """
    if n == 0:
        return (0, 0)
    factors = find_factors(n)
    sqrt = int(pow(n, 0.5))
    d1 = n // sqrt
    d2 = math.ceil(n / d1)
    return sorted([d1, d2])

def view_image_list(images, labels=None, layout=None, spacing=0.1,
                    scale=1, title=None, pivot=False):
    """
    View a list of images.

    Arguments:
        images (list) - a list of images
        labels (str) - list of optional labels for each image
        layout (tuple or list) - optional (rows, cols). Default: (1,n)
        spacing (float) - space between images. Default: 0.1
        scale (float) - size of entire resulting image. Default: 1
        title (str) - optional title for console window.
        pivot (bool) - rotates layout of images

    layout (rows, cols) can be:
        * None - find square-ish dimensions automatically
        * (int, int) - set the layout; if more than can fit, don't show them
        * (None, int) - determine rows automatically
        * (int, None) - determine cols automatically

    """
    if labels is not None:
        labels = [label for label in labels]
    if not 0 <= spacing <= 1:
        print("spacing must be between 0 and 1")
        return
    if not scale > 0:
        print("scale must be > 0")
    if layout is None or layout == (None, None):
        layout = find_dimensions(len(images))
    if layout[0] is None:
        layout = (math.ceil(len(images)/layout[1]), layout[1])
    elif layout[1] is None:
        layout = (layout[0], math.ceil(len(images)/layout[0]))
    rows, cols = layout
    border = spacing / max(rows, cols)
    if pivot:
        rows, cols = cols, rows
    fig, axes = plt.subplots(rows, cols, squeeze=False,
                             figsize=(cols*scale, rows*scale),
                             num=title,
                             gridspec_kw={'wspace': spacing,
                                          'hspace': spacing,
                                          'left': border,
                                          'right': 1-border,
                                          'bottom': border,
                                          'top': 1-border})
    if title is not None:
        fig.canvas.set_window_title(title)
    k = 0
    rows, cols = axes.shape
    for ax in axes.reshape(axes.size):
        ax.axis('off')
    if pivot:
        for c in range(cols):
            for r in range(rows):
                if k >= len(images):
                    plt.show(block=False)
                    return  # no more images to display
                axes[r][c].imshow(images[k])
                if labels is not None:
                    axes[r][c].set_title(labels[k])
                k += 1
    else:
        for r in range(rows):
            for c in range(cols):
                if k >= len(images):
                    plt.show(block=False)
                    return  # no more images to display
                axes[r][c].imshow(images[k])
                if labels is not None:
                    axes[r][c].set_title(labels[k])
                k += 1
    plt.show(block=False)
    if k < len(images):
        print("WARNING: could not view all images with layout %s" % (layout,), file=sys.stderr)

def view_network(net, title=None, background=(255, 255, 255, 255),
                 data="train", scale=1.0, **kwargs):
    """
    View a network and train or test data.

    Arguments:
        data (str) = "train" or "test"

    Common settings:
        show_targets (bool) - True will show target pattern
        show_errors (bool) - Ture will show error pattern

    Additional settings:
        font_size
        font_family
        border_top
        border_bottom
        hspace
        vspace
        image_maxdim
        image_pixels_per_unit
        activation
        arrow_color
        arrow_width
        border_width
        border_color
        pixels_per_unit
        precision
        svg_scale
        svg_rotate
        svg_preferred_size
        svg_max_width
    """
    from IPython.display import clear_output

    if data not in ["test", "train"]:
        print("Invalid data to view; data should be 'train', or 'test'")
        return
    if len(net.dataset) == 0:
        ## try to get a picture of the network, if one:
        image = net.picture(dynamic=kwargs.get("dynamic", False), format="image")
        if image:
            return view_image(image, title=title, scale=scale)
        return
    if net.model is None:
        print("Please compile network")
        return
    if data == "test" and len(net.dataset.test_inputs) == 0:
        print("Please split data")
        return
    for key in kwargs:
        if key == "dynamic": continue
        net.config[key] = kwargs[key]
    current = 0
    if title is None:
        title = net.name
    while True:
        clear_output(wait=True)
        if data == "train":
            print("%s Training data #%d" % (net.name, current))
            view_image(net.picture(net.dataset.train_inputs[current],
                                   dynamic=kwargs.get("dynamic", False),
                                   format="image"),
                       title=title, scale=scale)
            last = len(net.dataset.train_inputs) - 1
        else:
            print("%s Test data #%d" % (net.name, current))
            view_image(net.picture(net.dataset.test_inputs[current],
                                   dynamic=kwargs.get("dynamic", False),
                                   format="image"),
                       title=title, scale=scale)
            last = len(net.dataset.test_inputs) - 1
        retval = input("Enter # (0-%s) to view, return for next, q to quit: " % (last,))
        if retval.lower() in ["q", "quit"]:
            return
        elif retval == "":
            current += 1
        else:
            try:
                current = int(retval)
            except:
                print("Invalid input")
                continue
        current = current % (last + 1)

def view(item, title=None, background=(255, 255, 255, 255), scale=1.0, **kwargs):
    """
    Show an item from the console. item can any one of the following:

    * Network
    * HTML
    * SVG image
    * PIL.Image
    * list of PIL.images
    * Image filename (png or jpg)
    * array (to be converted via array_to_image)

    For more information on each option, see:

    * view_network
    * view_svg
    * view_image
    * view_image_list
    * array_to_image
    """
    from IPython.display import Image, HTML, SVG
    from conx import Network
    import webbrowser
    import tempfile
    if isinstance(item, str):
        if item.startswith("<svg ") or item.startswith("<SVG "):
            return view_svg(item, title, background, scale=scale)
        else:
            ## assume it is a file:
            item = os.path.expanduser(item)
            return view_image(PIL.Image.open(item), title, scale=scale)
    elif isinstance(item, Network):
        return view_network(item, title=title, background=background, scale=scale, **kwargs)
    elif hasattr(item, "_repr_image_"):
        return view_image(item._repr_image_(), title=title, scale=scale)
    elif isinstance(item, PIL.Image.Image):
        return view_image(item, title=title, scale=scale)
    elif isinstance(item, HTML):
        if item.data.startswith("<svg ") or item.data.startswith("<SVG "):
            return view_svg(item.data, title, background, scale=scale)
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as fp:
                fp.write(item.data.encode("utf-8"))
                fp.close()
                return webbrowser.open(fp.name)
    elif isinstance(item, SVG):
        return view_svg(item.data, title, background, scale=scale)
    elif isinstance(item, (tuple, list)) and len(item) > 0:
        if hasattr(item[0], "_repr_image_"):
            return view_image_list([dv._repr_image_() for dv in item], title=title, scale=scale, **kwargs)
        elif isinstance(item[0], PIL.Image.Image):
            return view_image_list(item, title=title, scale=scale, **kwargs)
        elif isinstance(item[0], SVG):
            images = [svg_to_image(svg.data) for svg in item]
            return view_image_list(images, title=title, scale=scale, **kwargs)
        elif isinstance(item[0], str):
            images = [image(s) for s in item]
            return view_image_list(images, title=title, scale=scale, **kwargs)
        else:
            print("I don't know how to view this item")
    elif isinstance(item, (np.ndarray,)):
        return view_image(array_to_image(item), title=title, scale=scale)
    else:
        print("I don't know how to view this item")

def svg_to_image(svg, background=(255, 255, 255, 255)):
    import cairosvg
    if isinstance(svg, bytes):
        pass
    elif isinstance(svg, str):
        svg = svg.encode("utf-8")
    else:
        raise Exception("svg_to_image takes a str, rather than %s" % type(svg))

    image_bytes = cairosvg.svg2png(bytestring=svg)
    image = PIL.Image.open(io.BytesIO(image_bytes))
    if background is not None:
        ## create a blank image, with background:
        canvas = PIL.Image.new('RGBA', image.size, background)
        try:
            canvas.paste(image, mask=image)
        except:
            canvas = None ## fails on images that don't need backgrounds
        if canvas:
            return canvas
        else:
            return image
    else:
        return image

def view_svg(svg, title=None, background=(255, 255, 255, 255), scale=1.0):
    """
    Takes the actual SVG string.
    """
    image = svg_to_image(svg, background)
    return view_image(image, title, scale=scale)

def view_image(image, title=None, scale=1.0):
    size = plt.rcParams["figure.figsize"]
    fig = plt.figure(figsize=(size[0] * scale, size[1] * scale),
                     num=title)
    if title is not None:
        fig.canvas.set_window_title(title)
    frame = plt.gca()
    frame.axes.get_xaxis().set_visible(False)
    frame.axes.get_yaxis().set_visible(False)
    plt.imshow(image)
    plt.show(block=False)
    return

def count_params(weights):
    """
    Count the total number of scalars composing the weights.

    Arguments
        weights: An iterable containing the weights on which to compute params

    Returns:
        The total number of scalars composing the weights
    """
    import keras.backend as K
    return int(np.sum([K.count_params(p) for p in set(weights)]))

def download(url, directory="./", force=False, unzip=True, filename=None,
             verbose=1):
    """
    Download a file into a local directory.

    Arguments:
        url (str) - the URL of file to download
        directory (str) - directory to download file into
        force (bool) - to force a new download
        unzip (bool) - unzip .zip file; use unzip=True with force=True to re-unzip
        verbose (int) - if greater than zero, display the filenames in a ZIP file

    >>> download("https://raw.githubusercontent.com/Calysto/conx/master/README.md",
    ...          "/tmp/testme", force=True) # doctest: +ELLIPSIS
    Downloading ...
    >>> download("https://raw.githubusercontent.com/Calysto/conx/master/README.md",
    ...          "/tmp/testme") # doctest: +ELLIPSIS
    Using cached ...
    """
    directory = os.path.expanduser(directory)
    result = urlparse(url)
    if filename is None:
        filename = result.path.split("/")[-1]
    file_path = os.path.join(directory, filename)
    ## First, download the file:
    if not os.path.isfile(file_path) or force:
        print("Downloading %s to '%s'..." % (url, file_path))
        os.makedirs(directory, exist_ok=True)
        response = requests.get(url, stream=True)
        total_length = response.headers.get('content-length')
        if total_length:
            bar = progress_bar(total=int(total_length))
        with open(file_path, 'wb') as f:
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
                if total_length:
                    if bar:
                        bar.update(4096)
        print("Done!")
    else:
        print("Using cached %s as '%s'." % (url, file_path))
    ## Now, if it is a zip file, check to unzip:
    if file_path.endswith(".zip") and os.path.isfile(file_path):
        try:
            zip_ref = zipfile.ZipFile(file_path, 'r')
        except zipfile.BadZipFile:
            print("URL appears to be invalid for zip file. Try deleteing the file and re-trying.")
            return
        # first, count existing unzipped files:
        total_count = 0
        for name in zip_ref.namelist():
            total_count += 1
        # next, report existing:
        if unzip:
            print("Unzipping files...")
            for name in zip_ref.namelist():
                name_path = os.path.join(directory, name)
                if not os.path.exists(name_path) or force:
                    zip_ref.extract(name, directory)
            print ("Done!")
        else:
            print("Not unzipping files.")
        if verbose:
            print("Items available from downloaded zip file:")
        exist_count = 0
        for name in zip_ref.namelist():
            name_path = os.path.join(directory, name)
            if os.path.exists(name_path):
                if verbose:
                    print("    ", name_path)
                exist_count += 1
        print("Available: %s of %s." % (exist_count, total_count))
        if exist_count != total_count:
            print("%s item(s) have been deleted. Use download(..., unzip=True) restore them" %
                  (total_count - exist_count,))
        zip_ref.close()

def replace_value(data, value=0, new_value=sys.float_info.min):
    """
    Replace all values in an array with new value.
    """
    data = np.asarray(data).astype('float64')
    data[data == value] = new_value
    return data

def choice(seq=None, p=None, temperature=None, index=False):
    """
    Get a random choice from sequence, optionally given a probability
    distribution and temperature.

    Arguments:
        seq - a list of choices, or None if choices are range(len(p))
        p - a list of probabilities, or None if even chance
        temperature - randomness control
           * 0.0 - biggest p wins deterministically
           * 1.0 - use p as regular probabilities
           * > 1.0 - ignore p, randomness
        index - return the index rather than value?

    Returns:
        One of the choices (or index), picked with given probabilty
        and temperature.

    Examples:
        >>> choice(1)
        0

        >>> choice([42])
        42

        >>> choice("abcde", p=[0, 1, 0, 0, 0])
        'b'

        >>> choice(p=[0, 0, 1, 0, 0])
        2

        >>> choice("aaaaa")
        'a'
        >>> choice("ab", p=[0, 1], temperature=1.0)
        'b'

    Deterministically use p to determine winner (temperature is low,
    close to zero):

        >>> bin = [0, 0]
        >>> for i in range(1000):
        ...     bin[choice([0, 1], p=[0.4, 0.6], temperature=0.01)] += 1
        >>> assert bin[0] == 0, bin[0]
        >>> assert bin[1] == 1000, bin[1]

    Use p as regular propabilities (temperature is close to 1):

        >>> bin = [0, 0]
        >>> for i in range(1000):
        ...     bin[choice([0, 1], p=[0.4, 0.6], temperature=1.0)] += 1
        >>> assert bin[0] < bin[1], "%s < %s" % (bin[0], bin[1])

    High randomness, (temperature is greater than 1):

        >>> bin = [0, 0]
        >>> for i in range(1000):
        ...     bin[choice([0, 1], p=[0.4, 0.6], temperature=100.0)] += 1
        >>> assert abs(bin[0] - bin[1]) <= 50, "%s <= 50" % abs(bin[0] - bin[1])
    """
    if seq is None and p is None:
        raise Exception("seq and p can't both be None")
    elif seq is None:
        seq = len(p)
        length = seq
    else:
        length = seq if isinstance(seq, numbers.Real) else len(seq)
    if temperature is not None:
        if p is None:
            raise Exception("p can't be None with temperature")
        p = np.array(p) ** (1.0 / temperature)
    if p is not None:
        # Make sure that it sums to 1.0
        # or else np.random.choice will crash
        total = sum(p)
        p = [item/total for item in p]
    pick = np.random.choice(length, 1, p=p)[0]
    if index:
        return pick
    else:
        ## Allow seq to be a number:
        if isinstance(seq, numbers.Real):
            return pick
        else:
            return seq[pick]

def frange(start, stop=None, step=1.0, raw=False):
    """
    Like range(), but with floats.

    May not be exactly correct due to rounding issues.

    Arguments:
        start (float or int) - start of range, or stop of
            if stop not given
        stop (float, int, or None) - end of range or None, if
            start is the stop of range
        step (float) - the step size

    Returns:
        A list of floats.

    Examples:
        >>> len(frange(-1, 1, .1))
        20
    """
    if stop is None:
        stop = start
        start = 0.0
    v = np.arange(start, stop, step)
    if not raw:
        v = v.tolist()
    return v

def argmax(seq):
    """
    Find the index of the maximum value in seq.

    Arguments:
        seq (list) - sequence of numbers

    Returns:
        The index of maximum value in list.

    >>> argmax([0.1, 0.2, 0.3, 0.1])
    2
    """
    return np.argmax(seq)

def argmin(seq):
    """
    Find the index of the minimum value in seq.

    Arguments:
        seq (list) - sequence of numbers

    Returns:
        The index of minimum value in list.

    >>> argmin([0.5, 0.2, 0.3, 0.1])
    3
    """
    return np.argmin(seq)

def minimum(seq):
    """
    Find the minimum value in seq.

    Arguments:
        seq (list) - sequence or matrix of numbers

    Returns:
        The minimum value in list or matrix.

    >>> minimum([5, 2, 3, 1])
    1
    >>> minimum([[5, 2], [3, 1]])
    1
    >>> minimum([[[5], [2]], [[3], [1]]])
    1
    """
    try:
        seq[0][0]
        return min([minimum(v) for v in seq])
    except:
        return np.array(seq).min()

def maximum(seq):
    """
    Find the maximum value in seq.

    Arguments:
        seq (list) - sequence or matrix of numbers

    Returns:
        The maximum value in list or matrix.

    >>> maximum([0.5, 0.2, 0.3, 0.1])
    0.5
    >>> maximum([[0.5, 0.2], [0.3, 0.1]])
    0.5
    >>> maximum([[[0.5], [0.2]], [[0.3], [0.1]]])
    0.5
    """
    try:
        seq[0][0]
        return max([maximum(v) for v in seq])
    except:
        return np.array(seq).max()

def crop_image(image, x1, y1, x2, y2):
    """
    Given an image an crop rectangle
    x1, y1, x2, y2, return the cropped image.


    >>> m = [[[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]],
    ...      [[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]]]
    >>> img = array_to_image(m)
    >>> crop_image(img, 0, 0, 1, 1) # doctest: +ELLIPSIS
    <PIL.Image.Image image mode=RGB size=1x1 at ...>
    """
    return image.crop((x1, y1, x2, y2))

def image(img, resize=None, gray=False):
    """
    Given a filename, load it. Optionally, given a picture,
    resize it.

    >>> m = [[[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]],
    ...      [[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]]]
    >>> img = array_to_image(m)
    >>> img                      # doctest: +ELLIPSIS
    <PIL.Image.Image image mode=RGB size=2x2 at ...>

    >>> image(img, resize=(4,4)) # doctest: +ELLIPSIS
    <PIL.Image.Image image mode=RGB size=4x4 at ...>
    """
    if isinstance(img, str):
        img = os.path.expanduser(img)
        img = PIL.Image.open(img)
    if gray:
        img = img.convert('L')
    if resize is not None:
        img = img.resize(resize)
    return img

def image_remove_alpha(image):
    """
    Given an image with an alpha channel, return an
    image with alpha channel removed.
    """
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image

def image_resize(image, resize=None):
    """
    Given an image and resize tuple (w,h), return an
    image with new size.
    """
    if resize is not None:
        image = image.resize(resize)
    return image

def image_to_array(img, resize=None, raw=False):
    """
    Convert an image filename or PIL.Image into a matrix (list of
    lists).


    >>> m = [[[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]],
    ...      [[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]]]
    >>> img = array_to_image(m)
    >>> np.array(img).tolist()
    [[[0, 255, 255], [255, 0, 0]], [[0, 255, 255], [255, 0, 0]]]
    >>> image_to_array(img)
    [[[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]], [[0.0, 1.0, 1.0], [1.0, 0.0, 0.0]]]

    """
    if isinstance(img, str):
        img = os.path.expanduser(img)
        img = PIL.Image.open(img)
    if resize is not None:
        img = img.resize(resize)
    if img.mode == "L":
        pass ## ok, we'll make a 2D array
    elif img.mode == "LA":
        img = img.convert("L") ## drop alpha
    elif img.mode != "RGB":
        img = img.convert("RGB") ## force no alpha
    img = (np.array(img, "float16") / 255.0)
    if not raw:
        img = img.tolist()
    return img

def array_to_image(array, scale=1.0, minmax=None, colormap=None, shape=None):
    """
    Convert a matrix (with shape, or given shape) to a PIL.Image.

    >>> m = [[[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]],
    ...      [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]]
    >>> img = array_to_image(m)
    >>> np.array(img).tolist()
    [[[255, 255, 255], [0, 0, 0]], [[0, 0, 0], [255, 255, 255]]]
    >>> image_to_array(img)
    [[[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]]

    >>> m = [1.0, 1.0, 1.0, 0.0, 0.0, 0.0,
    ...      0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    >>> array_to_image(m, shape=(2, 2, 3))       # doctest: +ELLIPSIS
    <PIL.Image.Image image mode=RGB size=2x2 at ...>
    >>> array_to_image(m, shape=(2, 2, 3), colormap="bone")       # doctest: +ELLIPSIS
    <PIL.Image.Image image mode=RGBA size=2x2 at ...>
    """
    from matplotlib import cm
    array = np.array(array) # let's make sure
    if minmax is None: # auto
        minmax = [array.min(), array.max()]
        if minmax[0] == minmax[1]:
            minmax[0] = minmax[0] - .5
            minmax[1] = minmax[1] + .5
        minmax[0] = math.floor(minmax[0])
        minmax[1] = math.ceil(minmax[1])
    if shape is not None:
        array = array.reshape(shape)
    if len(array.shape) == 3 and array.shape[-1] == 1:
        array = array.reshape((array.shape[0], array.shape[1]))
    elif len(array.shape) == 1:
        array = np.array([array])
    if colormap is not None:
        array = rescale_numpy_array(array, minmax, (0,1), 'float',
                                    truncate=True)
        try:
            cm_hot = cm.get_cmap(colormap)
            array = cm_hot(array)
        except:
            print("WARNING: invalid colormap; ignored", file=sys.stderr)
            ## rescale again:
        array = rescale_numpy_array(array, (0,1), (0,255), 'uint8',
                                    truncate=True)
        image = PIL.Image.fromarray(array, "RGBA")
    else:
        array = rescale_numpy_array(array, minmax, (0,255), 'uint8',
                                    truncate=True)
        image = PIL.Image.fromarray(array)
    if scale != 1.0:
        image = image.resize((int(image.size[0] * scale), int(image.size[1] * scale)))
    if image.mode not in ["RGB", "RGBA"]:
        image = image.convert("RGB")
    return image

def scale_output_for_image(vector, minmax, truncate=False):
    """
    Given an activation name (or something else) and an output
    vector, scale the vector.
    """
    return rescale_numpy_array(vector, minmax, (0,255), 'uint8',
                               truncate=truncate)

def onehot(i, width, values=[0,1]):
    """
    >>> onehot(0, 5)
    [1, 0, 0, 0, 0]

    >>> onehot(3, 5)
    [0, 0, 0, 1, 0]

    >>> onehot(3, 5, values=[False, True])
    [False, False, False, True, False]
    """
    v = [values[0]] * width
    v[i] = values[1]
    return v

def binary(i, width):
    """
    >>> binary(0, 5)
    [0, 0, 0, 0, 0]

    >>> binary(15, 4)
    [1, 1, 1, 1]

    >>> binary(14, 4)
    [1, 1, 1, 0]
    """
    bs = bin(i)[2:]
    bs = ("0" * width + bs)[-width:]
    b = [int(c) for c in bs]
    return b

def binary_to_int(vector):
    """
    Given a binary vector, return the integer value.

    >>> binary_to_int(binary(0, 5))
    0

    >>> binary_to_int(binary(15, 4))
    15

    >>> binary_to_int(binary(14, 4))
    14
    """
    return sum([v * 2 ** (len(vector) - 1 - i) for i,v in enumerate(vector)])

def find_all_paths(net, start_layer, end_layer, path=[]):
    """
    Given a start_layer and an end_layer, return a
    list containing all pathways (does not include end_layer).

    Recursive.
    """
    path = path + [start_layer]
    if start_layer.name == end_layer.name:
        return [path]
    paths = []
    for layer in net[start_layer.name].outgoing_connections:
        if layer not in path:
            newpaths = find_all_paths(net, layer, end_layer, path)
            for newpath in newpaths:
                paths.append(newpath)
    return paths

def find_path(net, start_layer, end_layer):
    """
    Given a conx network, a start layer, and an ending
    layer, find the path between them.
    """
    ## FIXME: doesn't work with merges.
    queue = [start_layer]
    get_to = {} # get to key from value
    found = False
    while queue:
        current = queue.pop(0) # BFS
        if current == end_layer:
            found = True
            break
        else:
            expand = [layer.name for layer in net[current].outgoing_connections]
            for layer_name in expand:
                if layer_name not in get_to:
                    get_to[layer_name] = current
                    queue.append(layer_name)
    if found:
        retval = []
        while current != start_layer:
            retval.append(net[current])
            current = get_to[current]
        return reversed(retval)

def topological_sort(net, layers):
    """
    Given a conx network and list of layers, produce a topological
    sorted list, from input(s) to output(s).
    """
    ## Initilize all:
    for layer in net.layers:
        layer.visited = False
    stack = []
    # Only track and sort these:
    for layer in layers:
        if not layer.visited:
            visit(layer, stack)
    stack.reverse()
    return stack

def visit(layer, stack):
    """
    Utility function for topological_sort.
    """
    layer.visited = True
    for outgoing_layer in layer.outgoing_connections:
        if not outgoing_layer.visited:
            visit(outgoing_layer, stack)
    stack.append(layer)

def autoname(index, sizes):
    """
    Given an index and list of sizes, return a
    name for the layer.

    >>> autoname(0, sizes=4)
    'input'
    >>> autoname(1, sizes=4)
    'hidden1'
    >>> autoname(2, sizes=4)
    'hidden2'
    >>> autoname(3, sizes=4)
    'output'
    """
    if index == 0:
        n = "input"
    elif index == sizes - 1:
        n = "output"
    elif sizes == 3:
        n = "hidden"
    else:
        n = "hidden%d" % index
    return n

def valid_shape(x):
    """
    Is this a valid shape for Keras layers?

    >>> valid_shape(1)
    True
    >>> valid_shape(None)
    True
    >>> valid_shape((1,))
    True
    >>> valid_shape((None, ))
    True
    """
    return ((isinstance(x, numbers.Integral) and (x > 0)) or
            (x is None) or
            (isinstance(x, (tuple, list)) and
             (len(x) > 0) and
             all([((isinstance(n, numbers.Integral) and (n > 0)) or
                   (n is None)) for n in x])))

def valid_vshape(x):
    """
    Is this a valid shape (i.e., size) to display vectors using PIL?
    """
    # vshape must be a single int or a 2- or 3-dimensional tuple
    return valid_shape(x) and (isinstance(x, numbers.Integral) or len(x) in [2,3])

def scale(a, new_range=(0,1), new_dtype="float", truncate=True):
    """
    Given a vector or matrix, scale it to new_range.

    >>> import sys
    >>> results = scale([-1, 0, 1])
    >>> results[0] - 0.0 < sys.float_info.epsilon
    True
    >>> results[1] - 0.5 < sys.float_info.epsilon
    True
    >>> results[2] - 1.0 < sys.float_info.epsilon
    True
    """
    a = np.array(a)
    return rescale_numpy_array(a, (a.min(), a.max()), new_range, new_dtype, truncate).tolist()

def rescale_numpy_array(a, old_range, new_range, new_dtype, truncate=False):
    """
    Given a numpy array, old min/max, a new min/max and a numpy type,
    create a new numpy array that scales the old values into the new_range.

    >>> import numpy as np
    >>> new_array = rescale_numpy_array(np.array([0.1, 0.2, 0.3]), (0, 1), (0.5, 1.), float)
    >>> ", ".join(["%.2f" % v for v in new_array])
    '0.55, 0.60, 0.65'
    """
    assert isinstance(old_range, (tuple, list)) and isinstance(new_range, (tuple, list))
    old_min, old_max = old_range
    if a.min() < old_min or a.max() > old_max:
        if truncate:
            a = np.clip(a, old_min, old_max)
        else:
            raise Exception('array values are outside range %s' % (old_range,))
    new_min, new_max = new_range
    old_delta = float(old_max - old_min)
    new_delta = float(new_max - new_min)
    if old_delta == 0:
        return ((a - old_min) + (new_min + new_max)/2).astype(new_dtype)
    else:
        return (new_min + (a - old_min)*new_delta/old_delta).astype(new_dtype)

def uri_to_image(image_str, width=320, height=240):
    """
    Given an URI, return an image.
    """
    header, image_b64 = image_str.split(",")
    image_binary = base64.b64decode(image_b64)
    image = PIL.Image.open(io.BytesIO(image_binary)).resize((width, height))
    return image

def get_device():
    """
    Returns 'cpu' or 'gpu' indicating which device
    the system will use.

    >>> get_device() in ["gpu", "cpu"]
    True
    """
    import keras.backend as K
    if K._BACKEND == "theano":
        from theano import function, tensor as T, shared, config
        x = shared(np.array([1.0], config.floatX))
        f = function([], T.exp(x))
        if np.any([isinstance(x.op, T.Elemwise) and
                   ('Gpu' not in type(x.op).__name__)
                   for x in f.maker.fgraph.toposort()]):
            return "cpu"
        else:
            return "gpu"
    elif K._BACKEND == "tensorflow":
        from tensorflow.python.client import device_lib
        devices = [dev.name for dev in device_lib.list_local_devices()]
        ## ['/device:CPU:0', '/device:GPU:0']
        return "gpu" if any(["GPU" in dev for dev in devices]) else "cpu"
    else:
        return "unknown"

def import_keras_model(model, network_name, build_propagate_from_models=True):
    """
    Import a keras model into conx.

    """
    from .network import Network
    import inspect
    import conx
    network = Network(network_name, build_propagate_from_models=build_propagate_from_models)
    network.model = model
    conx_layers = {name: layer for (name,layer)
                   in inspect.getmembers(conx.layers, inspect.isclass)}
    # First, make all of the conx layers:
    for layer in model.layers:
        clayer_class = conx_layers[layer.__class__.__name__ + "Layer"]
        if clayer_class.__name__ == "InputLayerLayer":
            clayer = conx.layers.InputLayer(layer.name, None)
            #clayer.make_input_layer_k = lambda layer=layer: layer
            clayer.shape = None
            clayer.params["batch_shape"] = layer.get_config()["batch_input_shape"]
            #clayer.params = layer.get_config()
            clayer.k = clayer.make_input_layer_k()
            clayer.keras_layer = clayer.k
        elif clayer_class.__name__ in ["DenseLayer", "Dense", "Layer"]:
            config = layer.get_config()
            for key in list(config.keys()):
                if isinstance(config[key], dict):
                    del config[key]
            shape = config["units"]
            del config["units"]
            name = config["name"]
            del config["name"]
            clayer = clayer_class(name, shape, **config)
            clayer.k = layer
            clayer.keras_layer = layer
        else:
            config = layer.get_config()
            for key in list(config.keys()):
                if isinstance(config[key], dict):
                    del config[key]
            clayer = clayer_class(**config)
            clayer.k = layer
            clayer.keras_layer = layer
        network.add(clayer)
    # Next, connect them up:
    for layer in model.layers:
        if hasattr(layer, "outbound_nodes"):
            for node in layer.outbound_nodes:
                network.connect(layer.name, node.outbound_layer.name)
        elif hasattr(layer, "_outbound_nodes"):
            for node in layer._outbound_nodes:
                network.connect(layer.name, node.outbound_layer.name)
    for clayer in network.layers:
        clayer.input_names = network.input_bank_order
    # Finally, make the internal models:
    network._build_intermediary_models()
    return network

def movie(function, movie_name="movie.gif", play_range=None,
          loop=0, optimize=True, duration=100, embed=False, mp4=True):
    """
    Make a movie from a function.

    function has signature: function(index) and should return
    a PIL.Image.
    """
    from IPython.display import Image
    frames = []
    for index in range(*play_range):
        frames.append(function(index))
    if frames:
        frames[0].save(movie_name, save_all=True, append_images=frames[1:],
                       optimize=optimize, loop=loop, duration=duration)
        if mp4 is False:
            return Image(url=movie_name, embed=embed)
        else:
            return gif2mp4(movie_name)

def plot_f(f, frange=(-1, 1, .1), symbol="o-", xlabel="", ylabel="", title="",
           format=None):
    """
    Plot a function.

    >>> plot_f(lambda x: x, frange=(-1, 1, .1), format="svg")
    <IPython.core.display.SVG object>
    """
    xs = np.arange(*frange)
    ys = [f(x) for x in xs]
    fig, ax = plt.subplots()
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    if title:
        plt.title(title)
    plt.plot(xs, ys, symbol)
    if format is None:
        plt.show(block=False)
    else:
        from IPython.display import SVG
        bytes = io.BytesIO()
        if format == "svg":
            plt.savefig(bytes, format="svg")
            plt.close(fig)
            img_bytes = bytes.getvalue()
            return SVG(img_bytes.decode())
        elif format == "image":
            plt.savefig(bytes, format="png")
            plt.close(fig)
            bytes.seek(0)
            pil_image = PIL.Image.open(bytes)
            return pil_image
        else:
            raise Exception("format must be None, 'svg', or 'image'")

def plot3D(function, x_range=None, y_range=None, width=4.0, height=4.0, xlabel="",
           ylabel="", zlabel="", title="", label="", symbols=None,
           default_symbol=None, ymin=None, xmin=None, ymax=None,
           xmax=None, format=None, colormap=None,
           linewidth=0, antialiased=False, mode="surface"):
    """
    function is a function(x,y) or list of ["Label", [(x,y,z)]].

    Arguments:
        mode (str) - "surface", "wireframe", "scatter"
        function (list or callable) - function is a list of
            ["Label", [(x,y,z)]], or a function(x,y) that
            returns z

    >>> plot3D([["Test1", [[0, 0, 1], [0, 1, 0]]]], mode="scatter",
    ...        format="svg")
    <IPython.core.display.SVG object>

    >>> plot3D((lambda x,y: x ** 2 + y ** 2),
    ...        (-1,1,.1), (-1,1,.1),
    ...        mode="surface",
    ...        format="svg")
    <IPython.core.display.SVG object>

    >>> plot3D((lambda x,y: x ** 2 + y ** 2),
    ...        (-1,1,.1), (-1,1,.1),
    ...        mode="wireframe",
    ...        format="svg")
    <IPython.core.display.SVG object>
    """
    ## needed to get 3d projection:
    from mpl_toolkits.mplot3d import Axes3D
    if plt is None:
        raise Exception("matplotlib was not loaded")
    fig = plt.figure(figsize=(width, height))
    ax = fig.gca(projection='3d')
    # Plot the surface.
    if mode == "surface" or mode == "wireframe":
        X = frange(*x_range)
        Y = frange(*y_range)
        X, Y  = np.meshgrid(X, Y)
        Z = np.zeros(X.shape)
        for i in range(len(X)):
            for j in range(len(X[0])):
                Z[i][j] = function(X[i][j], Y[i][j])
        if mode == "surface":
            kwargs = {}
            ax.plot_surface(X, Y, Z, cmap=colormap,
                            linewidth=linewidth,
                            antialiased=antialiased, **kwargs)
        elif mode == "wireframe":
            kwargs = {}
            if label:
                kwargs["label"] = label
            ax.plot_wireframe(X, Y, Z, linewidth=linewidth, **kwargs)
            if label:
                ax.legend()
    elif mode == "scatter":
        any_label = False
        for data_label, data in function:
            kwargs = {}
            args = []
            if label:
                kwargs["label"] = label
                any_label = True
            elif data_label:
                kwargs["label"] = data_label
                any_label = True
            symbol = get_symbol(kwargs.get("label", None), symbols, default_symbol)
            if symbol:
                args.append(symbol)
            X = [d[0] for d in data]
            Y = [d[1] for d in data]
            Z = [d[2] for d in data]
            ax.scatter(X, Y, Z, *args, **kwargs)
        if any_label:
            ax.legend()
    else:
        raise Exception("invalid mode")
    if xlabel:
        plt.xlabel(xlabel)
    if zlabel:
        ax.set_zlabel(zlabel)
    if ylabel:
        plt.ylabel(ylabel)
    if title:
        plt.title(title)
    if ymin is not None:
        plt.ylim(ymin=ymin)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    if xmin is not None:
        plt.xlim(xmin=xmin)
    if xmax is not None:
        plt.xlim(xmax=xmax)
    if format is None:
        plt.show(block=False)
        result = None
    else:
        from IPython.display import SVG
        bytes = io.BytesIO()
        if format == "svg":
            plt.savefig(bytes, format="svg")
            plt.close(fig)
            img_bytes = bytes.getvalue()
            result = SVG(img_bytes.decode())
        elif format == "image":
            plt.savefig(bytes, format="png")
            plt.close(fig)
            bytes.seek(0)
            pil_image = PIL.Image.open(bytes)
            result = pil_image
        else:
            raise Exception("format must be None, 'svg', or 'image'")
    return result

def plot(data=[], width=8.0, height=4.0, xlabel="", ylabel="", title="",
         label="", symbols=None, default_symbol=None, ymin=None, xmin=None, ymax=None, xmax=None,
         format='svg', xs=None, xs_rotation=None):
    """
    Create a line or scatter plot given the y-coordinates of a set of
    lines.

    You may provide the x-coordinates if they are not linear starting
    with 0.

    >>> p = plot(["Error", [1, 2, 4, 6, 1, 2, 3]],
    ...           ylabel="error",
    ...           xlabel="hello", format="svg")
    >>> p
    <IPython.core.display.SVG object>
    >>> p = plot([["Error", [1, 2, 4, 6, 1, 2, 3]]],
    ...           ylabel="error",
    ...           xlabel="hello", format="svg")
    >>> p
    <IPython.core.display.SVG object>

    """
    if plt is None:
        raise Exception("matplotlib was not loaded")
    fig, ax = plt.subplots(figsize=(width, height))
    if len(data) == 2 and isinstance(data[0], str):
        data = [data]
    for (data_label, vectors) in data:
        kwargs = {}
        if xs is not None:
            args = [xs, vectors]
        else:
            args = [vectors]
        if label: ## override
            kwargs["label"] = label
        elif data_label:
            kwargs["label"] = data_label
        symbol = get_symbol(kwargs.get("label", None), symbols, default_symbol)
        if symbol:
            args.append(symbol)
        plt.plot(*args, **kwargs)
    if any([line[0] for line in data]):
        plt.legend()
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    if title:
        plt.title(title)
    if ymin is not None:
        plt.ylim(ymin=ymin)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    if xmin is not None:
        plt.xlim(xmin=xmin)
    if xmax is not None:
        plt.xlim(xmax=xmax)
    if xs_rotation is not None:
        plt.setp(ax.get_xticklabels(),
                 rotation=xs_rotation,
                 horizontalalignment='right')
    if format is None:
        plt.show(block=False)
        result = None
    else:
        from IPython.display import SVG
        bytes = io.BytesIO()
        if format == "svg":
            plt.savefig(bytes, format="svg")
            plt.close(fig)
            img_bytes = bytes.getvalue()
            result = SVG(img_bytes.decode())
        elif format == "image":
            plt.savefig(bytes, format="png")
            plt.close(fig)
            bytes.seek(0)
            pil_image = PIL.Image.open(bytes)
            result = pil_image
        else:
            raise Exception("format must be None, 'svg', or 'image'")
    return result

def heatmap(function_or_matrix, in_range=(0,1), width=8.0, height=4.0, xlabel="", ylabel="", title="",
            resolution=None, out_min=None, out_max=None, colormap=None, format=None):
    """
    Create a heatmap plot given a matrix, or a function.

    >>> import math
    >>> def function(x, y):
    ...     return math.sqrt(x ** 2 + y ** 2)
    >>> hm = heatmap(function,
    ...              format="svg")
    >>> hm
    <IPython.core.display.SVG object>
    """
    in_min, in_max = in_range
    if plt is None:
        raise Exception("matplotlib was not loaded")
    fig, ax = plt.subplots(figsize=(width, height))
    if callable(function_or_matrix):
        function = function_or_matrix
        if resolution is None:
            resolution = (in_max - in_min) / 50  # 50x50 pixels by default
        xmin, xmax, xstep = in_min, in_max, resolution
        ymin, ymax, ystep = in_min, in_max, resolution
        xspan = xmax - xmin
        yspan = ymax - ymin
        xpixels = int(xspan/xstep)+1
        ypixels = int(yspan/ystep)+1
        mat = np.zeros((ypixels, xpixels))
        for row in range(ypixels):
            for col in range(xpixels):
                # (x,y) corresponds to lower left corner point of pixel
                x = xmin + xstep * col
                y = ymin + ystep * row
                mat[row,col] = function(x, y)
    else:
        mat = np.array(function_or_matrix)
    if out_min is None:
        out_min = mat.min()
    if out_max is None:
        out_max = mat.max()
    if colormap is None:
        colormap = get_colormap()
    axim = ax.imshow(mat, origin='lower', cmap=colormap, vmin=out_min, vmax=out_max)
    fig.colorbar(axim)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    if title:
        plt.title(title)
    if format is None:
        plt.show(block=False)
        result = None
    else:
        from IPython.display import SVG
        bytes = io.BytesIO()
        if format == "svg":
            plt.savefig(bytes, format="svg")
            plt.close(fig)
            img_bytes = bytes.getvalue()
            result = SVG(img_bytes.decode())
        elif format == "image":
            plt.savefig(bytes, format="png")
            plt.close(fig)
            bytes.seek(0)
            pil_image = PIL.Image.open(bytes)
            result = pil_image
        else:
            raise Exception("format must be None, 'svg', or 'image'")
    return result

CACHE_PARAMS = {}

def scatter(data=[], width=6.0, height=6.0, xlabel="", ylabel="", title="", label="",
            symbols=None, default_symbol="o", ymin=None, xmin=None, ymax=None, xmax=None,
            format='svg'):
    """
    Create a scatter plot with series of (x,y) data.

    >>> scatter(["Test 1", [(0,4), (2,3), (1,2)]], format="svg")
    <IPython.core.display.SVG object>
    """
    if plt is None:
        raise Exception("matplotlib was not loaded")
    fig, ax = plt.subplots(figsize=(width, height))
    if len(data) == 2 and isinstance(data[0], str):
        data = [data]
    for (data_label, vectors) in data:
        kwargs = {}
        args = []
        xs = [vector[0] for vector in vectors]
        ys = [vector[1] for vector in vectors]
        if label: ## override
            kwargs["label"] = label
        elif data_label:
            kwargs["label"] = data_label
        symbol = get_symbol(kwargs.get("label", None), symbols, default_symbol)
        if symbol:
            args.append(symbol)
        plt.plot(xs, ys, *args, **kwargs)
    if any([line[0] for line in data]):
        plt.legend()
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    if ymin is not None:
        plt.ylim(ymin=ymin)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    if xmin is not None:
        plt.xlim(xmin=xmin)
    if xmax is not None:
        plt.xlim(xmax=xmax)
    if title:
        plt.title(title)
    if format is None:
        plt.show(block=False)
        result = None
    else:
        from IPython.display import SVG
        bytes = io.BytesIO()
        if format == "svg":
            plt.savefig(bytes, format="svg")
            plt.close(fig)
            img_bytes = bytes.getvalue()
            result = SVG(img_bytes.decode())
        elif format == "image":
            plt.savefig(bytes, format="png")
            plt.close(fig)
            bytes.seek(0)
            pil_image = PIL.Image.open(bytes)
            result = pil_image
        else:
            raise Exception("format must be None, 'svg', or 'image'")
    return result

def scatter_images(images, xy, size=(800,800), scale=1.0):
    """
    Create a scatter plot of images.

    Takes a list of images, a list of (x,y) coordinates between 0 and
    1. Returns an image the size of size. Make the scale bigger or
    smaller to show more images.

    >>> scatter_images([array_to_image([[1]])], [(0.5, 0.5)]) # doctest: +ELLIPSIS
    <PIL.Image.Image image mode=RGBA size=800x800 at ...>
    """
    def binify(pos, length, chunk):
        """
        Given position, length, and chunk size, return the bin.
        """
        x = int(pos * (length / chunk)) * chunk
        return x

    psize = images[0].resize((int(images[0].size[0] * scale),
                              int(images[0].size[1] * scale))).size
    background = PIL.Image.new('RGBA', size, (255, 255, 255, 255))
    for i in range(len(images)):
        img = images[i].resize((int(images[i].size[0] * scale),
                                int(images[i].size[1] * scale)))
        pos = xy[i]
        background.paste(img, (binify(pos[0], size[0], psize[0]),
                               size[1] - binify(pos[1], size[1], psize[1])))
    return background

def gif2mp4(filename):
    """
    Convert an animated gif into a mp4, to show with controls.
    """
    from IPython.display import HTML
    filename = os.path.expanduser(img)
    if filename.endswith(".gif"):
        filename = filename[:-4]
    if os.path.exists(filename + ".mp4"):
        os.remove(filename + ".mp4")
    retval = os.system("""ffmpeg -i {0}.gif -movflags faststart -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" {0}.mp4""".format(filename))
    if retval == 0:
        return HTML("""<video src='{0}.mp4' controls></video>""".format(filename))
    else:
        print("error running ffmpeg; see console log message")

class PCA():
    """
    Compute the Prinicpal Component Analysis for the points
    in a multi-dimensional space.

    Example:
        >>> data = [
        ...         [0.00, 0.00, 0.00],
        ...         [0.25, 0.25, 0.25],
        ...         [0.50, 0.50, 0.50],
        ...         [0.75, 0.75, 0.75],
        ...         [1.00, 1.00, 1.00],
        ... ]
        >>> pca = PCA(data)
        >>> new_data = pca.transform(data)
        >>> len(new_data)
        5
    """
    def __init__(self, states, dim=2, solver="randomized"):
        from sklearn.decomposition import PCA
        self.dim = dim
        self.solver = solver
        self.pca = PCA(n_components=self.dim, svd_solver=self.solver)
        self.pca.fit(states)
        ## Now, compute and cache stats about this space:
        self.mins = {}
        self.maxs = {}
        states_pca = self.pca.transform(states)
        for i in range(self.dim):
            self.mins[i] = min([state[i] for state in states_pca])
            self.maxs[i] = max([state[i] for state in states_pca])

    def transform_one(self, vector, scale=False):
        """
        Transform a vector into the PCA of the trained states.

        >>> from conx import Network
        >>> net = Network("Example", 2, 2, 1)
        >>> net.compile(error="mse", optimizer="adam")
        >>> net.dataset.load([
        ...        [[0, 0], [0], "0"],
        ...        [[0, 1], [1], "1"],
        ...        [[1, 0], [1], "1"],
        ...        [[1, 1], [0], "0"],
        ... ])
        >>> states = [net.propagate_to("hidden", input) for input in net.dataset.inputs]
        >>> pca = PCA(states)
        >>> new_state = pca.transform_one(states[0])
        >>> len(new_state)
        2
        """
        vector_prime = self.pca.transform([vector])[0]
        if scale:
            return self.scale(vector_prime)
        else:
            return vector_prime

    def transform(self, vectors, scale=False):
        """
        >>> from conx import Network
        >>> net = Network("Example", 2, 2, 1)
        >>> net.compile(error="mse", optimizer="adam")
        >>> net.dataset.load([
        ...        [[0, 0], [0], "0"],
        ...        [[0, 1], [1], "1"],
        ...        [[1, 0], [1], "1"],
        ...        [[1, 1], [0], "0"],
        ... ])
        >>> states = [net.propagate_to("hidden", input) for input in net.dataset.inputs]
        >>> pca = PCA(states)
        >>> new_states = pca.transform(states)
        >>> len(new_states)
        4
        """
        vectors_prime = self.pca.transform(vectors)
        if scale:
            return np.array([self.scale(v) for v in vectors_prime])
        else:
            return vectors_prime

    def transform_network_bank(self, network, bank, label_index=0, tolerance=None,
                               scale=False):
        """
        >>> from conx import Network
        >>> net = Network("Example", 2, 2, 1)
        >>> net.compile(error="mse", optimizer="adam")
        >>> net.dataset.load([
        ...        [[0, 0], [0], "0"],
        ...        [[0, 1], [1], "1"],
        ...        [[1, 0], [1], "1"],
        ...        [[1, 1], [0], "0"],
        ... ])
        >>> states = [net.propagate_to("hidden", input) for input in net.dataset.inputs]
        >>> pca = PCA(states)
        >>> results = pca.transform_network_bank(net, "hidden")
        >>> sum([len(vectors) for (label, vectors) in results["data"]])
        4
        >>> "xmin" in results
        True
        >>> "xmax" in results
        True
        >>> "ymin" in results
        True
        >>> "ymax" in results
        True
        """
        categories = {}
        tolerance = tolerance if tolerance is not None else network.tolerance
        if len(network.dataset.inputs) == 0:
            raise Exception("nothing to test")
        inputs = network.dataset._inputs
        targets = network.dataset._targets
        outputs = network.model.predict(inputs)
        results = network.compute_correct([outputs], targets, tolerance)
        for i in range(len(network.dataset.inputs)):
            label = network.dataset._labels[label_index][i]
            input_vector = network.dataset.inputs[i]
            category = "%s (%s)" % (label, "correct" if results[i] else "wrong")
            hid = network.propagate_to(bank, input_vector)
            hid_prime = self.transform_one(hid, scale)
            if category not in categories:
                categories[category] = []
            categories[category].append(hid_prime)
        return {
            "data": sorted(categories.items()),
            "xmin": self.mins[0],
            "xmax": self.maxs[0],
            "ymin": self.mins[1],
            "ymax": self.maxs[1],
        }

    def scale(self, ovector):
        """
        Scale a transformed vector to (0, 1).
        """
        vector = np.array(ovector)
        for i in range(len(vector)):
            if i in self.maxs:
                span = (self.maxs[i] - self.mins[i])
                vector[i] = (vector[i] - self.mins[i]) / span
        return vector

def get_symbol(label: str, symbols: dict=None, default='o') -> str:
    """
    Get a matplotlib symbol from a label.

    Possible shape symbols:

        * '-'	solid line style
        * '--'	dashed line style
        * '-.'	dash-dot line style
        * ':'	dotted line style
        * '.'	point marker
        * ','	pixel marker
        * 'o'	circle marker
        * 'v'	triangle_down marker
        * '^'	triangle_up marker
        * '<'	triangle_left marker
        * '>'	triangle_right marker
        * '1'	tri_down marker
        * '2'	tri_up marker
        * '3'	tri_left marker
        * '4'	tri_right marker
        * 's'	square marker
        * 'p'	pentagon marker
        * '*'	star marker
        * 'h'	hexagon1 marker
        * 'H'	hexagon2 marker
        * '+'	plus marker
        * 'x'	x marker
        * 'D'	diamond marker
        * 'd'	thin_diamond marker
        * '|'	vline marker
        * '_'	hline marker

    In addition, the shape symbol can be preceded by the following color abbreviations:

        * ‘b’	blue
        * ‘g’	green
        * ‘r’	red
        * ‘c’	cyan
        * ‘m’	magenta
        * ‘y’	yellow
        * ‘k’	black
        * ‘w’	white

    Examples:
        >>> get_symbol("Apple")
        'o'
        >>> get_symbol("Apple", {'Apple': 'x'})
        'x'
        >>> get_symbol("Banana", {'Apple': 'x'})
        'o'
    """
    if symbols is None:
        return default
    else:
        return symbols.get(label, default)

def atype(dtype):
    """
    Given a numpy dtype, return the associated Python type.
    If unable to determine, just return the dtype.kind code.

    >>> atype(np.float64(23).dtype)
    <class 'numbers.Number'>
    """
    if dtype.kind in ["i", "f", "u", "b"]:
        return numbers.Number
    elif dtype.kind in ["U", "S"]:
        return str
    else:
        return dtype.kind

def format_collapse(ttype, dims):
    """
    Given a type and a tuple of dimensions, return a struct of
    [[[ttype, dims[-1]], dims[-2]], ...]

    >>> format_collapse(int, (1, 2, 3))
    [[[<class 'int'>, 3], 2], 1]
    """
    if len(dims) == 1:
        return [ttype, dims[0]]
    else:
        return format_collapse([ttype, dims[-1]], dims[:-1])

def cxtypes(item):
    """
    Get the types of (possibly) nested list(s), and collapse
    if possible.

    >>> cxtypes(0)
    <class 'numbers.Number'>

    >>> cxtypes([0, 1, 2])
    [<class 'numbers.Number'>, 3]
    """
    try:
        length = len(item)
    except:
        return (numbers.Number
                if isinstance(item, (numbers.Number, bool))
                else type(item))
    if isinstance(item, str):
        return str
    elif length == 0:
        return [None, 0]
    array = None
    try:
        array = np.asarray(item)
    except:
        pass
    if array is None or array.dtype == object:
        return [cxtypes(x) for x in item]
    else:
        dtype = array.dtype ## can be many things!
        return format_collapse(atype(dtype), array.shape)

def all_same(iterator):
    """
    Are there more than one item, and all the same?

    >>> all_same([int, int, int])
    True

    >>> all_same([int, float, int])
    False
    """
    iterator = iter(iterator)
    try:
        first = next(iterator)
    except StopIteration:
        return False
    return all([first == rest for rest in iterator])

def is_collapsed(item):
    """
    Is this a collapsed item?

    >>> is_collapsed([int, 3])
    True

    >>> is_collapsed([int, int, int])
    False
    """
    try:
        return (len(item) == 2 and
                isinstance(item[0], (type, np.dtype)) and
                isinstance(item[1], numbers.Number))
    except:
        return False

def collapse(item):
    """
    For any repeated structure, return [struct, count].

    >>> collapse([[int, int, int], [float, float]])
    [[<class 'int'>, 3], [<class 'float'>, 2]]
    """
    if is_collapsed(item):
        return item
    try:
        length = len(item)
    except:
        return item
    items = [collapse(i) for i in item]
    if all_same(items):
        return [items[0], length]
    else:
        return items

def get_form(item):
    """
    First, get the types of all items, and then collapse
    repeated structures.

    >>> get_form([1, [2, 5, 6], 3])
    [<class 'numbers.Number'>, [<class 'numbers.Number'>, 3], <class 'numbers.Number'>]
    """
    return collapse(cxtypes(item))

def get_shape(form):
    """
    Given a form, format it in [type, dimension] format.

    >>> get_shape(get_form([[0.00], [0.00]]))
    (<class 'numbers.Number'>, [2, 1])
    """
    if (isinstance(form, list) and
        len(form) == 2 and
        isinstance(form[1], numbers.Number)):
        ## Is it [type, count]
        if isinstance(form[0], (np.dtype, numbers.Number, type)):
            retval = (form[0], [form[1]])
        else:
            f = get_shape(form[0])
            if isinstance(f, tuple): ## FIXME: and same
                retval = (f[0], [form[1]] + f[1])
            else:
                retval = ([get_shape(f) for f in form], [len(form)])
    elif isinstance(form, list):
        retval = ([get_shape(x) for x in form], [len(form)])
    else:
        retval = (form, [0]) # scalar
    return retval

def get_dim(array, dims):
    """
    Get the values of an array given dimensions, where
    dims is an int or tuple of indicies, where an index can
    be None.. None means the entire dimension.

    >>> test = [
    ...     [[1], [2], [3]],
    ...     [[11], [22], [33]],
    ...     [[111], [222], [333]],
    ...     [[1111], [2222], [3333]],
    ... ]

    >>> get_dim(test, 0)
    [[1], [2], [3]]

    >>> get_dim(test, 1)
    [[11], [22], [33]]

    >>> get_dim(test, (None, 0, 0))
    [1, 11, 111, 1111]

    >>> get_dim(test, (None, None, 0))
    [[1, 2, 3], [11, 22, 33], [111, 222, 333], [1111, 2222, 3333]]

    >>> get_dim(test, (0, None, 0))
    [1, 2, 3]
    """
    if isinstance(dims, int):
        dims = (dims,)
    if len(dims) == 0:
        return array
    elif dims[0] is None:
        return [get_dim(col, dims[1:]) for col in array]
    else:
        return get_dim(array[dims[0]], dims[1:])

def reshape(matrix, new_shape, raw=False):
    """
    Given a list of lists of ... and a new_shape, reformat the
    matrix in the new shape.

    >>> m = [[[1, 2, 3]], [[4, 5, 6]]]
    >>> shape(m)
    (2, 1, 3)
    >>> m1 = reshape(m, 6)
    >>> shape(m1)
    (6,)
    >>> m2 = reshape(m, (3, 2))
    >>> shape(m2)
    (3, 2)
    >>> m2
    [[1, 2], [3, 4], [5, 6]]
    """
    if isinstance(new_shape, int):
        new_shape = (new_shape,)
    matrix = np.array(matrix).reshape(new_shape)
    if not raw:
        matrix = matrix.tolist()
    return matrix

def shape(item, summary=False):
    """
    Given a matrix or vector, return the shape as a tuple
    of dimensions.

    >>> shape([1])
    (1,)
    >>> shape([1, 2])
    (2,)
    >>> shape([[1, 2, 3], [4, 5, 6]])
    (2, 3)

    >>> shape([[1, 2, 3], [4, 5, 6]], summary=True)
    {'shape': (2, 3), 'ranges': [(1, 6)]}
    """
    form = get_form(item)
    s = get_shape(form)
    if (isinstance(s, tuple) and
        len(s) == 2 and
        all([isinstance(v, (np.dtype, numbers.Number, type)) for v in s[1]])):
        retval = tuple(s[1])
    else:
        retval = [tuple(v[1]) for v in s]
    if summary:
        return {
            "shape": retval,
            "ranges": get_ranges(item, form),
        }
    else:
        return retval

def load_data(filename, *args, **kwargs):
    """
    Load a numpy or h5 datafile.
    """
    import h5py
    filename = os.path.expand(filename)
    if filename.endswith("h5"):
        h5 = h5py.File(filename, 'r')
        return np.array(h5["data"])
    else:
        return np.load(filename, *args, **kwargs)

def save_data(filename, data, dtype='uint8', *args, **kwargs):
    """
    Save data to a disk. data can be a generator.

    If the extension is npy, we'll just try to save it.
    If it is h5, then it will be in a particular format:

    The h5 data format is [bank[:length]] which may be:

    * [array(), array() array(), ...
    * [list, list, list, ...]
    """
    import h5py
    filename = os.path.expand(filename)
    if filename.endswith("h5"):
        row_count = 0
        with h5py.File(filename, 'w') as h5:
            # Initialize a resizable dataset to hold the output
            dset = None
            for chunk in data: # list or generator
                if dset is None:
                    chunk_shape = (1,) + shape(chunk)
                    maxshape = (None,) + shape(chunk)
                    dset = h5.create_dataset('data',
                                             maxshape=maxshape,
                                             shape=chunk_shape,
                                             dtype=dtype)
                dset.resize(row_count + 1, axis=0)
                dset[row_count:] = chunk
                row_count += 1 ## could allow bigger chunks!
    else:
        np.save(filename, data, *args, **kwargs)

def get_ranges(items, form, dims=tuple()):
    """

    form - like [[[[numbers.Number, 4], 427], 266], [type, len], ...]

    >>> test = [
    ...     [[1], [2], [3]],
    ...     [[11], [22], [33]],
    ...     [[111], [222], [333]],
    ...     [[1111], [2222], [3333]],
    ... ]

    >>> shape(test)
    (4, 3, 1)

    >>> form = get_form(test)
    >>> get_ranges(test, form)
    [(1, 3333)]

    """
    ### items, form=[[Number, M], N]
    if form == numbers.Number:
        v = get_dim(items, dims)
        return minimum(v), maximum(v)
    elif not isinstance(form, list):
        return None ## something other than Number
    elif (len(form) == 2 and isinstance(form[1], int)):
        if isinstance(form[0], list):
            return get_ranges(items, form[0], dims+(None,))
        else:
            return [(minimum(get_dim(items, dims)),
                     maximum(get_dim(items, dims)))]
    else:
        return [get_ranges(items, form[i], dims+(i,)) for i in range(len(form))]

class Experiment():
    """
    Run a series of experiments.

    function() should take any options, and return a network.

    Arguments:
        * name (str) - name of the experiment. Used in saving/loading

    >>> from conx import Network
    >>> def function(optimizer, activation, **options):
    ...     net = Network("XOR", 2, 2, 1, activation=activation, seed=42)
    ...     net.compile(error="mse", optimizer=optimizer)
    ...     net.dataset.append_by_function(2, (0, 4), "binary", lambda i,v: [int(sum(v) == len(v))])
    ...     net.train(report_rate=100, verbose=0, plot=False, **options)
    ...     category = "%s-%s" % (optimizer, activation)
    ...     return category, net
    >>> exp = Experiment("XOR")
    >>> exp.run(function,
    ...         epochs=5,
    ...         accuracy=[0.8],
    ...         tolerance=0.2,
    ...         optimizer=["adam", "sgd"],
    ...         activation=["sigmoid", "relu"],
    ...         dir="/tmp/")
    >>> len(exp.results)
    4
    >>> exp.plot("loss", format="svg")
    <IPython.core.display.SVG object>
    >>> exp.apply(lambda category, exp_name: (category, exp_name))
    [('adam-sigmoid', '/tmp/XOR-00001-00001'), ('sgd-sigmoid', '/tmp/XOR-00001-00002'), ('adam-relu', '/tmp/XOR-00001-00003'), ('sgd-relu', '/tmp/XOR-00001-00004')]
    """
    def __init__(self, name):
        self.name = name
        self.results = []
        self.cache = {}

    def run(self, function, trials=1, dir="./", save=True, cache=False, **options):
        """Run a set of experiments, varying parameters.

        Arguments:
            * function - callable that takes options, returns category (str) and a `Network`
            * trials (int) - count to run this set of experiments
            * dir (str) - directory to story results
            * save (bool) - if True, then the networks will be saved to disk
            * cache (bool) - if True, then the networks will be saved in memory

        The experiment name is compose of Experiment.name + trial
        number + experiment number.  For example, the first experiment
        in the below example is: "Test1-00001-00001".  The last
        experiment is "Test1-00005-00002".

        Experiment.cache is a dictionary mapping experiment name
        (directory) to network for each experiment.

        Experiment.results is a list of (category, name) for each experiment.

        Example:
            >>> from conx import Network
            >>> net = Network("Sample - empty")
            >>> exp = Experiment("Test1")
            >>> exp.run(lambda var: (var, net),
            ...         trials=5,
            ...         save=False,
            ...         cache=True,
            ...         var=["OPTION1", "OPTION2"])
            >>> len(exp.results) == 10
            True
            >>> len(exp.cache) == 10
            True
            >>> "./Test1-00001-00001" in exp.cache.keys()
            True
            >>> "./Test1-00005-00002" in exp.cache.keys()
            True
            >>> exp.results[0][0] == "OPTION1"
            True
            >>> exp.results[0][1] == "./Test1-00001-00001"
            True
            >>> exp.results[-1][1] == "./Test1-00005-00002"
            True
            >>> exp.results[-1][0] == "OPTION2"
            True
        """
        options = sorted(options.items())
        keys = [option[0] for option in options]
        values = [option[1] if isinstance(option[1], (tuple, list)) else [option[1]]
                  for option in options]
        for trial in range(1, trials + 1):
            count = 1
            for combination in itertools.product(*values):
                opts = dict(zip(keys, combination))
                category, net = function(**opts)
                exp_name = "%s%s-%05d-%05d" % (dir, self.name, trial, count)
                if save:
                    net.save(exp_name)
                if cache:
                    self.cache[exp_name] = net
                self.results.append((category, exp_name))
                count += 1

    def apply(self, function, *args, **kwargs):
        """
        Apply a function to experimental runs.

        Arguments:
            function - takes either: category, network-name, args, and kwargs;
                or category, network, args, kwargs depending on cache, and
                returns some results.
        """
        from conx import Network
        results = []
        for (category, exp_name) in self.results:
            if exp_name in self.cache:
                results.append(function(category, self.cache[exp_name], *args, **kwargs))
            else:
                results.append(function(category, exp_name, *args, **kwargs))
        return results

    def plot(self, metrics='loss', symbols=None, format='svg'):
        """
        Plot all of the results of the experiment on a single plot.
        """
        from conx import Network
        colors = list('bgrcmyk')
        symbols = {}
        count = 0
        for (category, exp_name) in self.results:
            if category not in symbols:
                symbols[category] = colors[count % len(colors)] + '-'
                count += 1
        fig_ax = None
        for (category, exp_name) in self.results:
            if exp_name in self.cache:
                net = self.cache[exp_name]
            else:
                net = Network.load(exp_name)
            fig_ax = net.plot(metrics, return_fig_ax=True, fig_ax=fig_ax, label=category,
                              symbols=symbols, title=self.name)
        fig, ax = fig_ax
        if format is None:
            plt.show(block=False)
        else:
            from IPython.display import SVG
            bytes = io.BytesIO()
            if format == "svg":
                plt.savefig(bytes, format="svg")
                plt.close(fig)
                img_bytes = bytes.getvalue()
                return SVG(img_bytes.decode())
            elif format == "image":
                plt.savefig(bytes, format="png")
                plt.close(fig)
                bytes.seek(0)
                pil_image = PIL.Image.open(bytes)
                return pil_image
            else:
                raise Exception("format must be None, 'svg', or 'image'")

_COMM = None

def dynamic_pictures(value=True, reset=False):
    global _COMM
    try:
        from ipykernel.comm import Comm
    except:
        print("WARNING: ipykernel is not installed; dynamic_pictures ignored",
              file=sys.stderr)
        return False
    if value: ## turn on
        if reset or _COMM is None:
            _COMM = Comm(target_name='conx_svg_control')
            initialize_javascript()
        return True
    else:
        _COMM = None
        return False

def dynamic_pictures_check():
    global _COMM
    return _COMM is not None and _COMM.kernel

def dynamic_pictures_send(package):
    global _COMM
    _COMM.send(package)

def initialize_javascript():
    from IPython.display import Javascript, display
    js = """
require(['base/js/namespace'], function(Jupyter) {
    Jupyter.notebook.kernel.comm_manager.register_target('conx_svg_control', function(comm, msg) {
        comm.on_msg(function(msg) {
            // console.log("received!");
            // console.log(msg);
            var data = msg["content"]["data"];
            var images = document.getElementsByClassName(data["class"]);
            for (var i = 0; i < images.length; i++) {
                if (data["xlink:href"]) {
                    var xlinkns="http://www.w3.org/1999/xlink";
                    images[i].setAttributeNS(xlinkns, "href", data["xlink:href"]);
                }
                if (data["src"]) {
                    images[i].setAttributeNS(null, "src", data["src"]);
                }
            }
        });
    });
});
"""
    if get_ipython():
        display(Javascript(js))
    else:
        print("WARNING: get_ipython() is None; javascript not initialized",
              file=sys.stderr)

def set_random_seed(seed):
    """
    Set the random seed for reproducible results.
    """
    global SEED
    SEED = seed
    np.random.seed(SEED)
    random.seed(SEED)
    ## FIXME: this should do it in the proper backend
    try:
        import tensorflow as tf
        tf.set_random_seed(SEED)
    except:
        pass

## Set to a known seed, so we can replicate if we wish
set_random_seed(np.random.randint(2 ** 31 - 1))
