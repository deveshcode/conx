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

"""
The network module contains the code for the Network class.
"""

import operator
import importlib
from functools import reduce
import signal
import numbers
import pickle
import base64
import html
import copy
import io
import os
import PIL

import numpy as np
import keras

from .utils import *
from .layers import Layer
from .dataset import Dataset

from typing import Any

try:
    from IPython import get_ipython
except:
    get_ipython = lambda: None

#------------------------------------------------------------------------

class Network():
    """
    The main class for the conx neural network package.

    Arguments:
        name: Required. The name of the network. Should not contain special HTML
           characters.
        sizes: Optional numbers. Defines the sizes of layers of a sequential
           network. These will be created, added, and connected automatically.
        config: Configuration overrides for the network.

    Note:
        To have a complete, operating network, you must do the following items:

        1. create a network
        2. add layers
        3. connect the layers
        4. compile the network

        See also :any:`Layer`, :any:`Network.add`, :any:`Network.connect`,
        and :any:`Network.compile`.

    Examples:
        >>> net = Network("XOR1", 2, 5, 2)
        >>> len(net.layers)
        3

        >>> net = Network("XOR2")
        >>> net.add(Layer("input", 2))
        >>> net.add(Layer("hidden", 5))
        >>> net.add(Layer("output", 2))
        >>> net.connect()
        >>> len(net.layers)
        3

        >>> net = Network("XOR3")
        >>> net.add(Layer("input", 2))
        >>> net.add(Layer("hidden", 5))
        >>> net.add(Layer("output", 2))
        >>> net.connect("input", "hidden")
        >>> net.connect("hidden", "output")
        >>> len(net.layers)
        3

        >>> net = Network("NMIST")
        >>> net.name
        'NMIST'
        >>> len(net.layers)
        0

        >>> net = Network("NMIST", 10, 5, 1)
        >>> len(net.layers)
        3

        >>> net = Network("NMIST", 10, 5, 5, 1, activation="sigmoid")
        >>> net.config["activation"]
        'sigmoid'
        >>> net["output"].activation == "sigmoid"
        True
        >>> net["hidden1"].activation == "sigmoid"
        True
        >>> net["hidden2"].activation == "sigmoid"
        True
        >>> net["input"].activation is None
        True
        >>> net.layers[0].name == "input"
        True
    """
    OPTIMIZERS = ("sgd", "rmsprop", "adagrad", "adadelta", "adam",
                  "adamax", "nadam", "tfoptimizer")
    def __init__(self, name: str, *sizes: int, **config: Any):
        if not isinstance(name, str):
            raise Exception("first argument should be a name for the network")
        self.config = {
            "font_size": 12, # for svg
            "font_family": "monospace", # for svg
            "border_top": 25, # for svg
            "border_bottom": 25, # for svg
            "hspace": 150, # for svg
            "vspace": 30, # for svg, arrows
            "image_maxdim": 200, # for svg
            "image_pixels_per_unit": 50, # for svg
            "activation": "linear", # Dense default, if none specified
            "arrow_color": "blue",
            "arrow_width": "2",
            "border_width": "2",
            "border_color": "blue",
            "show_targets": False,
            "show_errors": False,
            "minmax": None,
            "colormap": None,
            "pixels_per_unit": 1,
            "pp_max_length": 20,
            "pp_precision": 1,
        }
        if not isinstance(name, str):
            raise Exception("conx layers need a name as a first parameter")
        self.config.update(config)
        self.dataset = None
        self.compile_options = {}
        self.train_options = {}
        self.name = name
        self.layers = []
        self.layer_dict = {}
        # If simple feed-forward network:
        for i in range(len(sizes)):
            if i > 0:
                self.add(Layer(autoname(i, len(sizes)), shape=sizes[i],
                               activation=self.config["activation"]))
            else:
                self.add(Layer(autoname(i, len(sizes)), shape=sizes[i]))
        # Connect them together:
        for i in range(len(sizes) - 1):
            self.connect(autoname(i, len(sizes)), autoname(i+1, len(sizes)))
        self.epoch_count = 0
        self.acc_history = []
        self.loss_history = []
        self.val_percent_history = []
        self.visualize = False
        self._comm = None
        self.model = None
        self.prop_from_dict = {}
        self._svg_counter = 1

    def set_dataset(self, dataset):
        if not isinstance(dataset, Dataset):
            dataset = Dataset(pairs=dataset)
        self.dataset = dataset

    def __getitem__(self, layer_name):
        if layer_name not in self.layer_dict:
            return None
        else:
            return self.layer_dict[layer_name]

    def _repr_svg_(self):
        if all([layer.model for layer in self.layers]):
            return self.build_svg()
        else:
            return None

    def __repr__(self):
        return "<Network name='%s' (%s)>" % (
            self.name, ("uncompiled" if not self.model else "compiled"))

    def add(self, layer: Layer):
        """
        Add a layer to the network layer connections. Order is not
        important, unless calling :any:`Network.connect` without any
        arguments.

        Arguments:
            layer: A layer instance.

        Examples:
            >>> net = Network("XOR2")
            >>> net.add(Layer("input", 2))
            >>> len(net.layers)
            1

            >>> net = Network("XOR3")
            >>> net.add(Layer("input", 2))
            >>> net.add(Layer("hidden", 5))
            >>> net.add(Layer("output", 2))
            >>> len(net.layers)
            3

        Note:
            See :any:`Network` for more information.
        """
        if layer.name in self.layer_dict:
            raise Exception("duplicate layer name '%s'" % layer.name)
        self.layers.append(layer)
        self.layer_dict[layer.name] = layer

    def connect(self, from_layer_name:str=None, to_layer_name:str=None):
        """
        Connect two layers together if called with arguments. If
        called with no arguments, then it will make a sequential
        run through the layers in order added.

        Arguments:
            from_layer_name: Name of layer where connect begins.
            to_layer_name: Name of layer where connection ends.

            If both from_layer_name and to_layer_name are None, then
            all of the layers are connected sequentially in the order
            added.

        Examples:
            >>> net = Network("XOR2")
            >>> net.add(Layer("input", 2))
            >>> net.add(Layer("hidden", 5))
            >>> net.add(Layer("output", 2))
            >>> net.connect()
            >>> [layer.name for layer in net["input"].outgoing_connections]
            ['hidden']
        """
        if from_layer_name is None and to_layer_name is None:
            for i in range(len(self.layers) - 1):
                self.connect(self.layers[i].name, self.layers[i+1].name)
        else:
            if from_layer_name not in self.layer_dict:
                raise Exception('unknown layer: %s' % from_layer_name)
            if to_layer_name not in self.layer_dict:
                raise Exception('unknown layer: %s' % to_layer_name)
            from_layer = self.layer_dict[from_layer_name]
            to_layer = self.layer_dict[to_layer_name]
            from_layer.outgoing_connections.append(to_layer)
            to_layer.incoming_connections.append(from_layer)
            input_layers = [layer for layer in self.layers if layer.kind() == "input"]
            self.num_input_layers = len(input_layers)
            target_layers = [layer for layer in self.layers if layer.kind() == "output"]
            self.num_target_layers = len(target_layers)

    def summary(self):
        """
        Print out a summary of the network.
        """
        print("Network Summary")
        print("---------------")
        print("Network name:", self.name)
        for layer in self.layers:
            layer.summary()

    def reset(self):
        """
        Reset all of the weights/biases in a network.
        The magnitude is based on the size of the network.
        """
        self.epoch_count = 0
        self.acc_history = []
        self.loss_history = []
        self.val_percent_history = []
        if self.model:
            # Compile the whole model again:
            self.compile(**self.compile_options)

    def test(self, inputs=None, targets=None, batch_size=32, tolerance=0.1):
        """
        Requires items in proper internal format, if given (for now).
        """
        ## FIXME: allow human format of inputs, if given
        dataset_name = "provided"
        if inputs is None:
            if self.dataset._split == self.dataset._num_inputs:

                inputs = self.dataset._train_inputs
                dataset_name = "training"
            else:
                inputs = self.dataset._test_inputs
                dataset_name = "testing"
        if targets is None:
            if self.dataset._split == self.dataset._num_targets:
                targets = self.dataset._train_targets
            else:
                targets = self.dataset._test_targets
        print("Testing on %s dataset._.." % dataset_name)
        outputs = self.model.predict(inputs, batch_size=batch_size)
        if self.num_input_layers == 1:
            ins = [self.pf(x) for x in inputs.tolist()]
        else:
            ins = [("[" + ", ".join([self.pf(vector) for vector in row]) + "]") for row in np.array(list(zip(*inputs))).tolist()]
        ## targets:
        if self.num_target_layers == 1:
            targs = [self.pf(x) for x in targets.tolist()]
        else:
            targs = [("[" + ", ".join([self.pf(vector) for vector in row]) + "]") for row in np.array(list(zip(*targets))).tolist()]
        ## outputs:
        if self.num_target_layers == 1:
            outs = [self.pf(x) for x in outputs.tolist()]
        else:
            outs = [("[" + ", ".join([self.pf(vector) for vector in row]) + "]") for row in np.array(list(zip(*outputs))).tolist()]
        ## correct?
        if self.num_target_layers == 1:
            correct = [all(x) for x in map(lambda v: v <= tolerance,
                                           np.abs(outputs - targets))]
        else:
            outs = np.array(list(zip(*[out.flatten().tolist() for out in outputs])))
            targs = np.array(list(zip(*[out.flatten().tolist() for out in targets])))
            correct = [all(row) for row in (np.abs(outs - targs) < tolerance)]
        print("# | inputs | targets | outputs | result")
        print("---------------------------------------")
        for i in range(len(outs)):
            print(i, "|", ins[i], "|", targs[i], "|", outs[i], "|", "correct" if correct[i] else "X")
        print("Total count:", len(correct))
        print("Total percentage correct:", list(correct).count(True)/len(correct))

    def train_one(self, inputs, targets, batch_size=32):
        """
        Train on one input/target pair. Requires internal format.

        Examples:

            >>> from conx import Network, Layer, SGD, Dataset
            >>> net = Network("XOR", 2, 2, 1, activation="sigmoid")
            >>> # Method 1:
            >>> ds = [[[0, 0], [0]],
            ...       [[0, 1], [1]],
            ...       [[1, 0], [1]],
            ...       [[1, 1], [0]]]
            >>> dataset = Dataset([2], [1])
            >>> dataset.load(ds)
            >>> net.set_dataset(dataset)
            >>> net.compile(loss='mean_squared_error',
            ...             optimizer=SGD(lr=0.3, momentum=0.9))
            >>> out, err = net.train_one({"input": [0, 0]},
            ...                          {"output": [0]})
            >>> len(out)
            1
            >>> len(err)
            1
            >>> # Method 2:
            >>> net.set_dataset(ds)
            >>> net.dataset._num_target_banks
            1
            >>> net.dataset._num_input_banks
            1

            >>> from conx import Network, Layer, SGD, Dataset
            >>> net = Network("XOR2")
            >>> net.add(Layer("input1", shape=1))
            >>> net.add(Layer("input2", shape=1))
            >>> net.add(Layer("hidden1", shape=2, activation="sigmoid"))
            >>> net.add(Layer("hidden2", shape=2, activation="sigmoid"))
            >>> net.add(Layer("shared-hidden", shape=2, activation="sigmoid"))
            >>> net.add(Layer("output1", shape=1, activation="sigmoid"))
            >>> net.add(Layer("output2", shape=1, activation="sigmoid"))
            >>> net.connect("input1", "hidden1")
            >>> net.connect("input2", "hidden2")
            >>> net.connect("hidden1", "shared-hidden")
            >>> net.connect("hidden2", "shared-hidden")
            >>> net.connect("shared-hidden", "output1")
            >>> net.connect("shared-hidden", "output2")
            >>> net.compile(loss='mean_squared_error',
            ...             optimizer=SGD(lr=0.3, momentum=0.9))
            >>> ds = [([[0],[0]], [[0],[0]]),
            ...       ([[0],[1]], [[1],[1]]),
            ...       ([[1],[0]], [[1],[1]]),
            ...       ([[1],[1]], [[0],[0]])]
            >>> dataset = Dataset([1, 1],
            ...                   [1, 1])
            >>> dataset.load(ds)
            >>> net.set_dataset(dataset)
            >>> net.compile(loss='mean_squared_error',
            ...             optimizer=SGD(lr=0.3, momentum=0.9))
            >>> out, err = net.train_one({"input1": [0], "input2": [0]},
            ...                          {"output1": [0], "output2": [0]})
            >>> len(out)
            2
            >>> len(err)
            2
            >>> net.set_dataset(ds)
            >>> net.dataset._num_input_banks
            2
            >>> net.dataset._num_target_banks
            2
        """
        if isinstance(inputs, dict):
            inputs = [inputs[name] for name in self.input_bank_order]
            if self.num_input_layers == 1:
                inputs = inputs[0]
        if isinstance(targets, dict):
            targets = [targets[name] for name in self.output_bank_order]
            if self.num_target_layers == 1:
                targets = targets[0]
        pairs = [(inputs, targets)]
        if self.num_input_layers == 1:
            ins = np.array([x for (x, y) in pairs], "float32")
        else:
            ins = []
            for i in range(len(pairs[0][0])):
                ins.append(np.array([x[i] for (x,y) in pairs], "float32"))
        if self.num_target_layers == 1:
            targs = np.array([y for (x, y) in pairs], "float32")
        else:
            targs = []
            for i in range(len(pairs[0][1])):
                targs.append(np.array([y[i] for (x,y) in pairs], "float32"))
        history = self.model.fit(ins, targs, epochs=1, verbose=0, batch_size=batch_size)
        ## may need to update history?
        outputs = self.propagate(inputs, batch_size=batch_size)
        errors = (np.array(targets) - np.array(outputs)).tolist() # FIXME: multi outputs?
        if self.visualize:
            if self.config["show_targets"]:
                self.display_component([targets], "targets") # FIXME: use output layers' minmax
            if self.config["show_errors"]:
                self.display_component([errors], "errors", minmax=(-1, 1), colormap="RdGy")
        return (outputs, errors)

    def retrain(self, **overrides):
        """
        Call network.train() again with same options as last call, unless overrides.
        """
        self.train_options.update(overrides)
        self.train(**self.train_options)

    def train(self, epochs=1, accuracy=None, batch_size=None,
              report_rate=1, tolerance=0.1, verbose=1, shuffle=True,
              class_weight=None, sample_weight=None):
        """
        Train the network.
        """
        ## IDEA: train_options could be a history of dicts
        ## to keep track of a schedule of learning over time
        self.train_options = {
            "epochs": epochs,
            "accuracy": accuracy,
            "batch_size": batch_size,
            "report_rate": report_rate,
            "tolerance": tolerance,
            "verbose": verbose,
            "shuffle": shuffle,
            "class_weight": class_weight,
            "sample_weight": sample_weight,
            }
        if batch_size is None:
            if self.num_input_layers == 1:
                batch_size = self.dataset._train_inputs.shape[0]
            else:
                batch_size = self.dataset._train_inputs[0].shape[0]
        if not (isinstance(batch_size, numbers.Integral) or batch_size is None):
            raise Exception("bad batch size: %s" % (batch_size,))
        if accuracy is None and epochs > 1 and report_rate > 1:
            print("Warning: report_rate is ignored when in epoch mode")
        if self.dataset._split == self.dataset._num_inputs:
            validation_inputs = self.dataset._train_inputs
            validation_targets = self.dataset._train_targets
        else:
            validation_inputs = self.dataset._test_inputs
            validation_targets = self.dataset._test_targets
        if verbose: print("Training...")
        with _InterruptHandler() as handler:
            if accuracy is None: # train them all using fit
                result = self.model.fit(self.dataset._train_inputs,
                                        self.dataset._train_targets,
                                        batch_size=batch_size,
                                        epochs=epochs,
                                        verbose=verbose,
                                        shuffle=shuffle,
                                        class_weight=class_weight,
                                        sample_weight=sample_weight)
                outputs = self.model.predict(validation_inputs, batch_size=batch_size)
                if self.num_target_layers == 1:
                    correct = [all(x) for x in map(lambda v: v <= tolerance,
                                                   np.abs(outputs - validation_targets))].count(True)
                else:
                    correct = [all(x) for x in map(lambda v: v <= tolerance,
                                                   np.abs(np.array(outputs) - np.array(validation_targets)))].count(True)
                self.epoch_count += epochs
                acc = 0
                # In multi-outputs, acc is given by output layer name + "_acc"
                for key in result.history:
                    if key.endswith("acc"):
                        acc += result.history[key][0]
                #acc = result.history['acc'][0]
                self.acc_history.append(acc)
                loss = result.history['loss'][0]
                self.loss_history.append(loss)
                val_percent = correct/len(validation_targets)
                self.val_percent_history.append(val_percent)
            else:
                for e in range(1, epochs+1):
                    result = self.model.fit(self.dataset._train_inputs, self.dataset._train_targets,
                                            batch_size=batch_size,
                                            epochs=1,
                                            verbose=0,
                                            shuffle=shuffle,
                                            class_weight=class_weight,
                                            sample_weight=sample_weight)
                    outputs = self.model.predict(validation_inputs, batch_size=batch_size)
                    if self.num_target_layers == 1:
                        correct = [all(x) for x in map(lambda v: v <= tolerance,
                                                       np.abs(outputs - validation_targets))].count(True)
                    else:
                        correct = [all(x) for x in map(lambda v: v <= tolerance,
                                                       np.abs(np.array(outputs) - np.array(validation_targets)))].count(True)
                    self.epoch_count += 1
                    acc = 0
                    # In multi-outputs, acc is given by output layer name + "_acc"
                    for key in result.history:
                        if key.endswith("acc"):
                            acc += result.history[key][0]
                    #acc = result.history['acc'][0]
                    self.acc_history.append(acc)
                    loss = result.history['loss'][0]
                    self.loss_history.append(loss)
                    val_percent = correct/len(validation_targets)
                    self.val_percent_history.append(val_percent)
                    if self.epoch_count % report_rate == 0:
                        if verbose: print("Epoch #%5d | train error %7.5f | train accuracy %7.5f | validate%% %7.5f" %
                                          (self.epoch_count, loss, acc, val_percent))
                    if val_percent >= accuracy or handler.interrupted:
                        break
            if handler.interrupted:
                print("=" * 72)
                print("Epoch #%5d | train error %7.5f | train accuracy %7.5f | validate%% %7.5f" %
                      (self.epoch_count, loss, acc, val_percent))
                raise KeyboardInterrupt
        if verbose:
            print("=" * 72)
            print("Epoch #%5d | train error %7.5f | train accuracy %7.5f | validate%% %7.5f" %
                  (self.epoch_count, loss, acc, val_percent))
        else:
            return (self.epoch_count, loss, acc, val_percent)

        # # evaluate the model
        # print('Evaluating performance...')
        # loss, accuracy = self.model.evaluate(self.test_inputs, self.test_targets, verbose=0)
        # print('Test loss:', loss)
        # print('Test accuracy:', accuracy)
        # #print('Most recent weights saved in model.weights')
        # #self.model.save_weights('model.weights')

    def get_weights(self, layer_name):
        """
        Get the weights from the model in an easy to read format.
        """
        weights = [layer.get_weights() for layer in self.model.layers
                   if layer_name == layer.name][0]
        return [m.tolist() for m in weights]

    def propagate(self, input, batch_size=32):
        """
        Propagate an input (in human API) through the network.
        If visualizing, the network image will be updated.
        """
        import keras.backend as K
        if isinstance(input, dict):
            input = [input[name] for name in self.input_bank_order]
            if self.num_input_layers == 1:
                input = input[0]
        elif isinstance(input, PIL.Image.Image):
            input = np.array(input)
            if len(input.shape) == 2:
                input = input.reshape(input.shape + (1,))
            if K.image_data_format() == 'channels_first':
                input = self.matrix_to_channels_first(input)
        if self.num_input_layers == 1:
            outputs = list(self.model.predict(np.array([input]), batch_size=batch_size)[0])
        else:
            inputs = [np.array(x, "float32") for x in input]
            outputs = [[list(y) for y in x][0] for x in self.model.predict(inputs, batch_size=batch_size)]
        if self.visualize and get_ipython():
            if not self._comm:
                from ipykernel.comm import Comm
                self._comm = Comm(target_name='conx_svg_control')
            if self._comm.kernel:
                for layer in self.layers:
                    image = self.propagate_to_image(layer.name, input, batch_size)
                    data_uri = self._image_to_uri(image)
                    self._comm.send({'class': "%s_%s" % (self.name, layer.name), "href": data_uri})
        return outputs

    def propagate_from(self, layer_name, input, output_layer_names=None, batch_size=32):
        """
        Propagate activations from the given layer name to the output layers.
        """
        if layer_name not in self.layer_dict:
            raise Exception("No such layer '%s'" % layer_name)
        if isinstance(input, dict):
            input = [input[name] for name in self.input_bank_order]
            if self.num_input_layers == 1:
                input = input[0]
        if output_layer_names is None:
            if self.num_target_layers == 1:
                output_layer_names = [layer.name for layer in self.layers if layer.kind() == "output"]
            else:
                output_layer_names = self.output_bank_order
        else:
            if isinstance(output_layer_names, str):
                output_layer_names = [output_layer_names]
        outputs = []
        for output_layer_name in output_layer_names:
            prop_model = self.prop_from_dict.get((layer_name, output_layer_name), None)
            if prop_model is None:
                path = topological_sort(self, self[layer_name].outgoing_connections)
                # Make a new Input to start here:
                k = input_k = keras.layers.Input(self[layer_name].shape, name=self[layer_name].name)
                # So that we can display activations here:
                self.prop_from_dict[(layer_name, layer_name)] = keras.models.Model(inputs=input_k,
                                                                                   outputs=input_k)
                for layer in path:
                    k = self.prop_from_dict.get((layer_name, layer.name), None)
                    if k is None:
                        k = input_k
                        fs = layer.make_keras_functions()
                        for f in fs:
                            k = f(k)
                    self.prop_from_dict[(layer_name, layer.name)] = keras.models.Model(inputs=input_k,
                                                                                       outputs=k)
                # Now we should be able to get the prop_from model:
                prop_model = self.prop_from_dict.get((layer_name, output_layer_name), None)
            inputs = np.array([input])
            outputs.append([list(x) for x in prop_model.predict(inputs)][0])
        if self.visualize and get_ipython():
            if not self._comm:
                from ipykernel.comm import Comm
                self._comm = Comm(target_name='conx_svg_control')
            ## Update from start to rest of graph
            if self._comm.kernel:
                for layer in topological_sort(self, [self[layer_name]]):
                    model = self.prop_from_dict[(layer_name, layer.name)]
                    vector = model.predict(inputs)[0]
                    image = layer.make_image(vector, self.config)
                    data_uri = self._image_to_uri(image)
                    self._comm.send({'class': "%s_%s" % (self.name, layer.name), "href": data_uri})
        if len(output_layer_names) == 1:
            return outputs[0]
        else:
            return outputs

    def display_component(self, vector, component, **opts): #minmax=None, colormap=None):
        """
        vector is a list, one each per output layer. component is "errors" or "targets"
        """
        config = copy.copy(self.config)
        config.update(opts)
        ## FIXME: this doesn't work on multi-targets/outputs
        output_names = self.output_bank_order
        if self._comm.kernel:
            for (target, layer_name) in zip(vector, output_names):
                array = np.array(target)
                image = self[layer_name].make_image(array, config) # minmax=minmax, colormap=colormap)
                data_uri = self._image_to_uri(image)
                self._comm.send({'class': "%s_%s_%s" % (self.name, layer_name, component), "href": data_uri})

    def propagate_to(self, layer_name, inputs, batch_size=32, visualize=True):
        """
        Computes activation at a layer. Side-effect: updates visualized SVG.
        """
        if layer_name not in self.layer_dict:
            raise Exception('unknown layer: %s' % (layer_name,))
        if isinstance(inputs, dict):
            inputs = [inputs[name] for name in self.input_bank_order]
            if self.num_input_layers == 1:
                inputs = inputs[0]
        if self.num_input_layers == 1:
            outputs = self[layer_name].model.predict(np.array([inputs]), batch_size=batch_size)
        else:
            # get just inputs for this layer, in order:
            vector = [np.array(inputs[self.input_bank_order.index(name)]) for name in self[layer_name].input_names]
            outputs = self[layer_name].model.predict(vector, batch_size=batch_size)
        if self.visualize and visualize and get_ipython():
            if not self._comm:
                from ipykernel.comm import Comm
                self._comm = Comm(target_name='conx_svg_control')
            # Update path from input to output
            if self._comm.kernel:
                for layer in self.layers: # FIXME??: update all layers for now
                    out = self.propagate_to(layer.name, inputs, visualize=False)
                    image = self[layer.name].make_image(np.array(out), self.config) # single vector, as an np.array
                    data_uri = self._image_to_uri(image)
                    self._comm.send({'class': "%s_%s" % (self.name, layer.name), "href": data_uri})
        outputs = outputs[0].tolist()
        return outputs

    def propagate_to_image(self, layer_name, input, batch_size=32):
        """
        Gets an image of activations at a layer.
        """
        if isinstance(input, dict):
            input = [input[name] for name in self.input_bank_order]
            if self.num_input_layers == 1:
                input = input[0]
        outputs = self.propagate_to(layer_name, input, batch_size)
        array = np.array(outputs)
        image = self[layer_name].make_image(array, self.config)
        return image

    def compile(self, **kwargs):
        """
        Check and compile the network.

        See https://keras.io/ `Model.compile()` method for more details.
        """
        ## Error checking:
        if len(self.layers) == 0:
            raise Exception("network has no layers")
        for layer in self.layers:
            if layer.kind() == 'unconnected':
                raise Exception("'%s' layer is unconnected" % layer.name)
        if "error" in kwargs: # synonym
            kwargs["loss"] = kwargs["error"]
            del kwargs["error"]
        if "optimizer" in kwargs:
            optimizer = kwargs["optimizer"]
            if (not ((isinstance(optimizer, str) and optimizer in self.OPTIMIZERS) or
                     (isinstance(optimizer, object) and issubclass(optimizer.__class__, keras.optimizers.Optimizer)))):
                raise Exception("invalid optimizer '%s'; use valid function or one of %s" %
                                (optimizer, Network.OPTIMIZERS,))
        input_layers = [layer for layer in self.layers if layer.kind() == "input"]
        self.input_bank_order = [layer.name for layer in input_layers]
        output_layers = [layer for layer in self.layers if layer.kind() == "output"]
        self.output_bank_order = [layer.name for layer in output_layers]
        ## FIXME: redo checks to separate dataset:
        # if len(input_layers) == 1 and len(self.input_layer_order) == 0:
        #     pass # ok!
        # elif len(input_layers) == len(self.dataset._input_layer_order):
        #     # check to make names all match
        #     for layer in input_layers:
        #         if layer.name not in self.dataset._input_layer_order:
        #             raise Exception("layer '%s' is not listed in dataset._input_layer_order" % layer.name)
        # else:
        #     raise Exception("improper dataset._input_layer_order names")
        ## FIXME: add new dataset-based checks:
        # if len(output_layers) == 1 and len(self.output_layer_order) == 0:
        #     pass # ok!
        # elif len(output_layers) == len(self.output_layer_order):
        #     # check to make names all match
        #     for layer in output_layers:
        #         if layer.name not in self.output_layer_order:
        #             raise Exception("layer '%s' is not listed in set_output_layer_order()" % layer.name)
        # else:
        #     raise Exception("improper set_output_layer_order() names")
        self._build_intermediary_models()
        output_k_layers = self._get_output_ks_in_order()
        input_k_layers = self._get_input_ks_in_order(self.input_bank_order)
        self.model = keras.models.Model(inputs=input_k_layers, outputs=output_k_layers)
        kwargs['metrics'] = ['accuracy']
        self.compile_options = copy.copy(kwargs)
        self.model.compile(**kwargs)

    def _delete_intermediary_models(self):
        """
        Remove these, as they don't pickle.
        """
        for layer in self.layers:
            layer.k = None
            layer.input_names = []
            layer.model = None

    def _build_intermediary_models(self):
        """
        Construct the layer.k, layer.input_names, and layer.model's.
        """
        sequence = topological_sort(self, self.layers)
        for layer in sequence:
            if layer.kind() == 'input':
                layer.k = layer.make_input_layer_k()
                layer.input_names = [layer.name]
                layer.model = keras.models.Model(inputs=layer.k, outputs=layer.k) # identity
            else:
                if len(layer.incoming_connections) == 0:
                    raise Exception("non-input layer '%s' with no incoming connections" % layer.name)
                kfuncs = layer.make_keras_functions()
                if len(layer.incoming_connections) == 1:
                    k = layer.incoming_connections[0].k
                    layer.input_names = layer.incoming_connections[0].input_names
                else: # multiple inputs, need to merge
                    k = keras.layers.Concatenate()([incoming.k for incoming in layer.incoming_connections])
                    # flatten:
                    layer.input_names = [item for sublist in
                                         [incoming.input_names for incoming in layer.incoming_connections]
                                         for item in sublist]
                for f in kfuncs:
                    k = f(k)
                layer.k = k
                ## get the inputs to this branch, in order:
                input_ks = self._get_input_ks_in_order(layer.input_names)
                layer.model = keras.models.Model(inputs=input_ks, outputs=layer.k)

    def _get_input_ks_in_order(self, layer_names):
        """
        Get the Keras function for each of a set of layer names.
        [in3, in4] sorted by input bank ordering
        """
        sorted_layer_names = [name for (index, name) in sorted([(self.input_bank_order.index(name), name) for name in layer_names])]
        layer_ks = [self[layer_name].k for layer_name in sorted_layer_names]
        if self.num_target_layers == 1:
            layer_ks = layer_ks[0]
        return layer_ks

    def _get_output_ks_in_order(self):
        """
        Get the Keras function for each output layer, in order.
        """
        layer_ks = [self[layer_name].k for layer_name in self.output_bank_order]
        if self.num_target_layers == 1:
            layer_ks = layer_ks[0]
        return layer_ks

    def _image_to_uri(self, img_src):
        # Convert to binary data:
        b = io.BytesIO()
        img_src.save(b, format='gif')
        data = b.getvalue()
        data = base64.b64encode(data)
        if not isinstance(data, str):
            data = data.decode("latin1")
        return "data:image/gif;base64,%s" % data

    def build_svg(self, opts={}):
        """
        opts - temporary override of config

        includes:
            "font_size": 12,
            "border_top": 25,
            "border_bottom": 25,
            "hspace": 100,
            "vspace": 50,
            "image_maxdim": 200
            "image_pixels_per_unit": 50

        See .config for all options.
        """
        def divide(n):
            return n + 1
            if n == 1:
                return 2
            elif n % 2 == 0:
                return n * 2
            else:
                return (n - 1) * 2
        # defaults:
        config = copy.copy(self.config)
        config.update(opts)
        self.visualize = False # so we don't try to update previously drawn images
        ordering = list(reversed(self._get_level_ordering())) # list of names per level, input to output
        image_svg = """<rect x="{{rx}}" y="{{ry}}" width="{{rw}}" height="{{rh}}" style="fill:none;stroke:{border_color};stroke-width:{border_width}"/><image id="{netname}_{{name}}_{{svg_counter}}" class="{netname}_{{name}}" x="{{x}}" y="{{y}}" height="{{height}}" width="{{width}}" preserveAspectRatio="none" href="{{image}}"><title>{{tooltip}}</title></image>""".format(
            **{
                "netname": self.name,
                "border_color": config["border_color"],
                "border_width": config["border_width"],
            })
        arrow_svg = """<line x1="{{x1}}" y1="{{y1}}" x2="{{x2}}" y2="{{y2}}" stroke="{arrow_color}" stroke-width="{arrow_width}" marker-end="url(#arrow)"><title>{{tooltip}}</title></line>""".format(**self.config)
        arrow_rect = """<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" style="fill:white;stroke:none"><title>{tooltip}</title></rect>"""
        label_svg = """<text x="{x}" y="{y}" font-family="{font_family}" font-size="{font_size}">{label}</text>"""
        max_width = 0
        images = {}
        image_dims = {}
        row_height = []
        # Go through and build images, compute max_width:
        for level_names in ordering:
            # first make all images at this level
            total_width = 0 # for this row
            max_height = 0
            for layer_name in level_names:
                if not self[layer_name].visible:
                    continue
                if self.model: # thus, we can propagate
                    if self.dataset and self.dataset._num_inputs != 0:
                        v = self.dataset.get_input(0)
                    else:
                        if self.num_target_layers > 1:
                            v = []
                            for in_name in self.input_bank_order:
                                v.append(self[in_name].make_dummy_vector())
                        else:
                            in_layer = [layer for layer in self.layers if layer.kind() == "input"][0]
                            v = in_layer.make_dummy_vector()
                    image = self.propagate_to_image(layer_name, v)
                else: # no propagate
                    # get image based on ontputs
                    raise Exception("compile model before building svg")
                (width, height) = image.size
                images[layer_name] = image ## little image
                max_dim = max(width, height)
                ### Layer settings:
                if self[layer_name].image_maxdim:
                    image_maxdim = self[layer_name].image_maxdim
                else:
                    image_maxdim = config["image_maxdim"]
                if self[layer_name].image_pixels_per_unit:
                    image_pixels_per_unit = self[layer_name].image_pixels_per_unit
                else:
                    image_pixels_per_unit = config["image_pixels_per_unit"]
                ## First, try based on shape:
                pwidth, pheight = np.array(image.size) * image_pixels_per_unit
                if max(pwidth, pheight) < image_maxdim:
                    width, height = pwidth, pheight
                else:
                    width, height = (int(width/max_dim * image_maxdim),
                                     int(height/max_dim * image_maxdim))
                # make sure not too small:
                if min(width, height) < 25:
                    width, height = (image_maxdim, 25)
                image_dims[layer_name] = (width, height)
                total_width += width + config["hspace"] # space between
                max_height = max(max_height, height)
            row_height.append(max_height)
            max_width = max(max_width, total_width)
        svg = ""
        cheight = config["border_top"] # top border
        ## Display target?
        if config["show_targets"]:
            # Find the spacing for row:
            for layer_name in ordering[0]:
                if not self[layer_name].visible:
                    continue
                image = images[layer_name]
                (width, height) = image_dims[layer_name]
            spacing = max_width / divide(len(ordering[0]))
            # draw the row of targets:
            cwidth = 0
            for layer_name in ordering[0]:
                image = images[layer_name]
                (width, height) = image_dims[layer_name]
                cwidth += (spacing - width/2)
                svg += image_svg.format(**{"name": layer_name + "_targets",
                                           "svg_counter": self._svg_counter,
                                           "x": cwidth,
                                           "y": cheight,
                                           "image": self._image_to_uri(image),
                                           "width": width,
                                           "height": height,
                                           "tooltip": self[layer_name].tooltip(),
                                           "rx": cwidth - 1, # based on arrow width
                                           "ry": cheight - 1,
                                           "rh": height + 2,
                                           "rw": width + 2})
                ## show a label
                svg += label_svg.format(
                    **{"x": cwidth + width + 5,
                       "y": cheight + height/2 + 2,
                       "label": "targets",
                       "font_size": config["font_size"],
                       "font_family": config["font_family"],
                    })
                cwidth += width/2
            ## Then we need to add height for output layer again, plus a little bit
            cheight += row_height[0] + 10 # max height of row, plus some
        ## Display error?
        if config["show_errors"]:
            # Find the spacing for row:
            for layer_name in ordering[0]:
                if not self[layer_name].visible:
                    continue
                image = images[layer_name]
                (width, height) = image_dims[layer_name]
            spacing = max_width / divide(len(ordering[0]))
            # draw the row of errors:
            cwidth = 0
            for layer_name in ordering[0]:
                image = images[layer_name]
                (width, height) = image_dims[layer_name]
                cwidth += (spacing - (width/2))
                svg += image_svg.format(**{"name": layer_name + "_errors",
                                           "svg_counter": self._svg_counter,
                                           "x": cwidth,
                                           "y": cheight,
                                           "image": self._image_to_uri(image),
                                           "width": width,
                                           "height": height,
                                           "tooltip": self[layer_name].tooltip(),
                                           "rx": cwidth - 1, # based on arrow width
                                           "ry": cheight - 1,
                                           "rh": height + 2,
                                           "rw": width + 2})
                ## show a label
                svg += label_svg.format(
                    **{"x": cwidth + width + 5,
                       "y": cheight + height/2 + 2,
                       "label": "errors",
                       "font_size": config["font_size"],
                       "font_family": config["font_family"],
                    })
                cwidth += width/2
            ## Then we need to add height for output layer again, plus a little bit
            cheight += row_height[0] + 10 # max height of row, plus some
        # Now we go through again and build SVG:
        positioning = {}
        for level_names in ordering:
            # compute width of just pictures for this row:
            for layer_name in level_names:
                if not self[layer_name].visible:
                    continue
                image = images[layer_name]
                (width, height) = image_dims[layer_name]
            spacing = max_width / divide(len(level_names))
            cwidth = 0
            # See if there are any connections up:
            any_connections_up = False
            last_connections_up = False
            for layer_name in level_names:
                if not self[layer_name].visible:
                    continue
                for out in self[layer_name].outgoing_connections:
                    if out.name not in positioning:
                        continue
                    any_connections_up = True
            if any_connections_up:
                cheight += config["vspace"] # for arrows
            else: # give a bit of room:
                if not last_connections_up:
                    cheight += 5
            last_connections_up = any_connections_up
            max_height = 0 # for row of images
            for layer_name in level_names:
                if not self[layer_name].visible:
                    continue
                image = images[layer_name]
                (width, height) = image_dims[layer_name]
                cwidth += (spacing - (width/2))
                positioning[layer_name] = {"name": layer_name,
                                           "svg_counter": self._svg_counter,
                                           "x": cwidth,
                                           "y": cheight,
                                           "image": self._image_to_uri(image),
                                           "width": width,
                                           "height": height,
                                           "tooltip": self[layer_name].tooltip(),
                                           "rx": cwidth - 1, # based on arrow width
                                           "ry": cheight - 1,
                                           "rh": height + 2,
                                           "rw": width + 2}
                x1 = cwidth + width/2
                y1 = cheight - 1
                for out in self[layer_name].outgoing_connections:
                    if out.name not in positioning:
                        continue
                    # draw background to arrows to allow mouseover tooltips:
                    x2 = positioning[out.name]["x"] + positioning[out.name]["width"]/2
                    y2 = positioning[out.name]["y"] + positioning[out.name]["height"]
                    rect_width = abs(x1 - x2)
                    rect_extra = 0
                    if rect_width < 20:
                        rect_extra = 10
                    tooltip = html.escape(self.describe_connection_to(self[layer_name], out))
                    svg += arrow_rect.format(**{"tooltip": tooltip,
                                                "rx": min(x2, x1) - rect_extra,
                                                "ry": min(y2, y1) + 2, # bring down
                                                "rw": rect_width + rect_extra * 2,
                                                "rh": abs(y1 - y2) - 2})
                for out in self[layer_name].outgoing_connections:
                    if out.name not in positioning:
                        continue
                    # draw an arrow between layers:
                    tooltip = html.escape(self.describe_connection_to(self[layer_name], out))
                    x2 = positioning[out.name]["x"] + positioning[out.name]["width"]/2
                    y2 = positioning[out.name]["y"] + positioning[out.name]["height"]
                    svg += arrow_svg.format(
                        **{"x1":x1,
                           "y1":y1,
                           "x2":x2,
                           "y2":y2 + 2,
                           "tooltip": tooltip
                        })
                svg += image_svg.format(**positioning[layer_name])
                svg += label_svg.format(
                    **{"x": positioning[layer_name]["x"] + positioning[layer_name]["width"] + 5,
                       "y": positioning[layer_name]["y"] + positioning[layer_name]["height"]/2 + 2,
                       "label": layer_name,
                       "font_size": config["font_size"],
                       "font_family": config["font_family"],
                    })
                cwidth += width/2
                max_height = max(max_height, height)
                self._svg_counter += 1
            cheight += max_height
        cheight += config["border_bottom"]
        self.visualize = True
        if get_ipython():
            self._initialize_javascript()
        return ("""
        <svg id='{netname}' xmlns='http://www.w3.org/2000/svg' width="{width}" height="{height}" image-rendering="pixelated">
    <defs>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" fill="{arrow_color}" />
        </marker>
    </defs>
""".format(
    **{
        "width": max_width,
        "height": cheight,
        "netname": self.name,
        "arrow_color": config["arrow_color"],
        "arrow_width": config["arrow_width"],
    }) + svg + """</svg>""")

    def _initialize_javascript(self):
        from IPython.display import Javascript, display
        js = """
require(['base/js/namespace'], function(Jupyter) {
    Jupyter.notebook.kernel.comm_manager.register_target('conx_svg_control', function(comm, msg) {
        comm.on_msg(function(msg) {
            var data = msg["content"]["data"];
            var images = document.getElementsByClassName(data["class"]);
            for (var i = 0; i < images.length; i++) {
                images[i].setAttributeNS(null, "href", data["href"]);
            }
        });
    });
});
"""
        display(Javascript(js))

    def _get_level_ordering(self):
        ## First, get a level for all layers:
        levels = {}
        for layer in topological_sort(self, self.layers):
            if not hasattr(layer, "model"):
                continue
            level = max([levels[lay.name] for lay in layer.incoming_connections] + [-1])
            levels[layer.name] = level + 1
        max_level = max(levels.values())
        # Now, sort by input layer indices:
        ordering = []
        for i in range(max_level + 1):
            layer_names = [layer.name for layer in self.layers if levels[layer.name] == i]
            if self.input_bank_order:
                inputs = [([self.input_bank_order.index(name)
                            for name in self[layer_name].input_names], layer_name)
                          for layer_name in layer_names]
            else:
                inputs = [([0 for name in self[layer_name].input_names], layer_name)
                          for layer_name in layer_names]
            level = [row[1] for row in sorted(inputs)]
            ordering.append(level)
        return ordering

    def describe_connection_to(self, layer1, layer2):
        """
        Returns a textual description of the weights for the SVG tooltip.
        """
        retval = "Weights from %s to %s" % (layer1.name, layer2.name)
        for klayer in self.model.layers:
            if klayer.name == layer2.name:
                weights = klayer.get_weights()
                for w in range(len(klayer.weights)):
                    retval += "\n %s has shape %s" % (
                        klayer.weights[w].name, weights[w].shape)
        ## FIXME: how to show merged layer weights?
        return retval

    def save(self, foldername=None, save_all=True):
        """
        Save the network to a folder.
        """
        if foldername is None:
            foldername = "%s.conx" % self.name
        if not os.path.isdir(foldername):
            os.makedirs(foldername)
        if self.model and save_all:
            self.save_model(foldername)
            self.save_weights(foldername)
            self._delete_intermediary_models()
        self.model, tmp_model = None, self.model
        self._comm, tmp_comm = None, self._comm
        self.compile_options, tmp_co = {}, self.compile_options
        try:
            with open("%s/network.pickle" % foldername, "wb") as fp:
                pickle.dump(self, fp)
        except:
            raise
        finally:
            self.model = tmp_model
            self._comm = tmp_comm
            self.compile_options = tmp_co
            if self.model and save_all:
                self._build_intermediary_models()

    ## classmethod or method
    def load(self, foldername=None):
        """
        Load the network from a folder.
        """
        if self is None or isinstance(self, str):
            foldername = self
            if foldername is None:
                raise Exception("foldername is required")
            net = Network("Temp")
            net.load_model(foldername)
            net.load_weights(foldername)
            if os.path.isfile("%s/network.pickle" % foldername):
                with open("%s/network.pickle" % foldername, "rb") as fp:
                    net = pickle.load(fp)
                net._build_intermediary_models()
            return net
        else:
            self.load_model(foldername)
            self.load_weights(foldername)

    def save_weights(self, foldername=None):
        """
        Save the model weights to a folder.
        """
        if self.model:
            if foldername is None:
                foldername = "%s.conx" % self.name
            if not os.path.isdir(foldername):
                os.makedirs(foldername)
            self.model.save_weights("%s/weights.h5" % foldername)
        else:
            raise Exception("need to compile network first")

    def save_model(self, foldername=None):
        """
        Save the model to a folder.
        """
        if self.model:
            if foldername is None:
                foldername = "%s.conx" % self.name
            if not os.path.isdir(foldername):
                os.makedirs(foldername)
            self.model.save("%s/model.h5" % foldername)
        else:
            raise Exception("need to compile network first")

    def load_weights(self, foldername=None):
        """
        Load the model weights from a folder.
        """
        if self.model:
            if foldername is None:
                foldername = "%s.conx" % self.name
            if os.path.isfile("%s/model.h5" % foldername):
                self.model.load_weights("%s/weights.h5" % foldername)

    def load_model(self, foldername=None):
        """
        Load and set the model from a folder.
        """
        if foldername is None:
            foldername = "%s.conx" % self.name
        if os.path.isfile("%s/model.h5" % foldername):
            self.model = keras.models.load_model("%s/model.h5" % foldername)

    def dashboard(self, width="100%", height="550px", iwidth="960px"): ## FIXME: iwidth hack
        """
        Build the dashboard for Jupyter widgets. Requires running
        in a notebook/jupyterlab.
        """
        from ipywidgets import HTML, Button, VBox, HBox, IntSlider, Select, Layout, Tab

        def dataset_move(position):
            if self.dataset is None:
                return
            if control_select.value == "Train":
                length = self.dataset.get_train_inputs_length()
            elif control_select.value == "Test":
                length = self.dataset.get_test_inputs_length()
            #### Position it:
            if position == "begin":
                control_slider.value = 0
            elif position == "end":
                control_slider.value = length - 1
            elif position == "prev":
                if control_slider.value - 1 < 0:
                    control_slider.value = length - 1 # wrap around
                else:
                    control_slider.value = max(control_slider.value - 1, 0)
            elif position == "next":
                if control_slider.value + 1 > length - 1:
                    control_slider.value = 0 # wrap around
                else:
                    control_slider.value = min(control_slider.value + 1, length - 1)

        def update_control_slider(change):
            if self.dataset is None:
                control_slider.disabled = True
                for child in control_buttons.children:
                    child.disabled = True
                return
            if control_select.value == "Test":
                control_slider.value = 0
                control_slider.min = 0
                control_slider.max = max(self.dataset.get_test_inputs_length() - 1, 0)
                if self.dataset.get_test_inputs_length() == 0:
                    disabled = True
                else:
                    disabled = False
            elif control_select.value == "Train":
                control_slider.value = 0
                control_slider.min = 0
                control_slider.max = max(self.dataset.get_train_inputs_length() - 1, 0)
                if self.dataset.get_train_inputs_length() == 0:
                    disabled = True
                else:
                    disabled = False
            control_slider.disabled = disabled
            for child in control_buttons.children:
                child.disabled = disabled

        def update_slider_control(change):
            if self.dataset is None:
                return
            if change["name"] == "value":
                if control_select.value == "Train" and self.dataset.get_train_targets_length() > 0:
                    output = self.propagate(self.dataset.get_train_input(control_slider.value))
                    if self.config["show_targets"]:
                        self.display_component([self.dataset.get_train_target(control_slider.value)], "targets", minmax=(0, 1))
                    if self.config["show_errors"]:
                        errors = np.array(self.dataset.get_train_target(control_slider.value)) - np.array(output)
                        self.display_component([errors.tolist()], "errors", minmax=(-1, 1), colormap="RdGy")
                elif control_select.value == "Test" and self.dataset.get_test_targets_length() > 0:
                    output = self.propagate(self.dataset.get_test_input(control_slider.value))
                    if self.config["show_targets"]:
                        self.display_component([self.dataset.get_test_target(control_slider.value)], "targets", minmax=(0, 1))
                    if self.config["show_errors"]:
                        errors = np.array(self.dataset.get_test_target(control_slider.value)) - np.array(output)
                        self.display_component([errors.tolist()], "errors", minmax=(-1, 1), colormap="RdGy")

        def train_one(button):
            if self.dataset is None:
                return
            if control_select.value == "Train" and self.dataset.get_train_targets_length() > 0:
                outputs = self.train_one(self.dataset.get_train_input(control_slider.value),
                                       self.dataset.get_train_target(control_slider.value))
            elif control_select.value == "Test" and self.dataset.get_test_targets_length() > 0:
                outputs = self.train_one(self.dataset.get_test_input(control_slider.value),
                                       self.dataset.get_test_target(control_slider.value))

        def prop_one(button):
            update_slider_control({"name": "value"})

        net_svg = HTML(value=self.build_svg(), layout=Layout(
            width=width, height=height, overflow_x='auto',
            justify_content="center"))
        button_begin = Button(icon="fast-backward", layout=Layout(width='100%'))
        button_prev = Button(icon="backward", layout=Layout(width='100%'))
        button_next = Button(icon="forward", layout=Layout(width='100%'))
        button_end = Button(icon="fast-forward", layout=Layout(width='100%'))
        #button_prop = Button(description="Propagate", layout=Layout(width='100%'))
        button_train = Button(description="Train", layout=Layout(width='100%'))
        control_buttons = HBox([
            button_begin,
            button_prev,
            button_train,
            button_next,
            button_end,
               ], layout=Layout(width='100%'))
        control_select = Select(
            options=['Test', 'Train'],
            value='Train',
            description='Dataset:',
               )
        length = (self.dataset.get_train_inputs_length() - 1) if self.dataset else 0
        control_slider = IntSlider(description="Dataset index",
                                   continuous_update=False,
                                   min=0,
                                   max=max(length, 0),
                                   value=0,
                                   layout=Layout(width='100%'))

        ## Hook them up:
        button_begin.on_click(lambda button: dataset_move("begin"))
        button_end.on_click(lambda button: dataset_move("end"))
        button_next.on_click(lambda button: dataset_move("next"))
        button_prev.on_click(lambda button: dataset_move("prev"))
        #button_prop.on_click(prop_one)
        button_train.on_click(train_one)
        control_select.observe(update_control_slider)
        control_slider.observe(update_slider_control)

        # Put them together:
        control = VBox([control_select, control_slider, control_buttons], layout=Layout(width='100%'))
        net_page = VBox([net_svg, control], layout=Layout(width='100%', height=height))
        graph_page = VBox(layout=Layout(width='100%', height=height))
        analysis_page = VBox(layout=Layout(width='100%', height=height))
        camera_page = VBox([Button(description="Turn on webcamera")], layout=Layout(width='100%', height=height))
        help_page = HTML('<iframe style="width: %s" src="https://conx.readthedocs.io" width="100%%" height="%s"></frame>' % (iwidth, height),
                         layout=Layout(width="100%", height=height))
        net_page.on_displayed(lambda widget: update_slider_control({"name": "value"}))
        tabs = [("Network", net_page), ("Graphs", graph_page), ("Analysis", analysis_page),
                ("Camera", camera_page), ("Help", help_page)]
        tab = Tab([t[1] for t in tabs])
        for i in range(len(tabs)):
            name, widget = tabs[i]
            tab.set_title(i, name)
        return tab

    def pp(self, *args, **opts):
        """
        Pretty-print a vector.
        """
        if isinstance(args[0], str):
            label = args[0]
            vector = args[1]
        else:
            label = ""
            vector = args[0]
        print(label + self.pf(vector[:20], **opts))

    def pf(self, vector, **opts):
        """
        Pretty-format a vector. Returns string.

        Parameters:
            vector (list): The first parameter.
            pp_max_length (int): Number of decimal places to show for each
                value in vector.

        Returns:
            str: Returns the vector formatted as a short string.

        Examples:
            These examples demonstrate the net.pf formatting function:

            >>> import conx
            >>> net = Network("Test")
            >>> net.pf([1])
            '[1.0]'

            >>> net.pf(range(10), pp_max_length=5)
            '[0.0, 1.0, 2.0, 3.0, 4.0...]'
        """
        config = copy.copy(self.config)
        config.update(opts)
        max_length = config["pp_max_length"]
        precision = config["pp_precision"]
        truncated = len(vector) > max_length
        return "[" + ", ".join([("%." + str(precision) + "f") % v for v in vector[:max_length]]) + ("..." if truncated else "") + "]"

    def to_array(self) -> list:
        """
        Get the weights of a network as a flat, one-dimensional list.

        Example:
            >>> from conx import Network
            >>> net = Network("Deep", 3, 4, 5, 2, 3, 4, 5)
            >>> net.compile(optimizer="adam", error="mse")
            >>> array = net.to_array()
            >>> len(array)
            103

        Returns:
            All of weights and biases of the network in a single, flat list.
        """
        array = []
        for layer in self.model.layers:
            for weight in layer.get_weights():
                array.extend(weight.flatten())
        return array

    def from_array(self, array: list):
        """
        Load the weights from a list.

        Arguments:
            array: a sequence (e.g., list, np.array) of numbers

        Example:
            >>> from conx import Network
            >>> net = Network("Deep", 3, 4, 5, 2, 3, 4, 5)
            >>> net.compile(optimizer="adam", error="mse")
            >>> net.from_array([0] * 103)
            >>> array = net.to_array()
            >>> len(array)
            103
        """
        position = 0
        for layer in self.model.layers:
            weights = layer.get_weights()
            new_weights = []
            for i in range(len(weights)):
                w = weights[i]
                size = reduce(operator.mul, w.shape)
                new_w = np.array(array[position:position + size]).reshape(w.shape)
                new_weights.append(new_w)
                position += size
            layer.set_weights(new_weights)

class _InterruptHandler():
    """
    Class for handling interrupts so that state is not left
    in inconsistant situation.
    """
    def __init__(self, sig=signal.SIGINT):
        self.sig = sig

    def __enter__(self):
        self.interrupted = False
        self.released = False
        self.original_handler = signal.getsignal(self.sig)

        def handler(signum, frame):
            self._release()
            if self.interrupted:
                raise KeyboardInterrupt
            print("\nStopping at end of epoch... (^C again to quit now)...")
            self.interrupted = True

        signal.signal(self.sig, handler)
        return self

    def __exit__(self, type, value, tb):
        self._release()

    def _release(self):
        if self.released:
            return False
        signal.signal(self.sig, self.original_handler)
        self.released = True
        return True
