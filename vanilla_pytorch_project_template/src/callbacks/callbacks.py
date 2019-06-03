# -*- coding: utf-8 -*-
"""
Callback implementation (inspired by Keras).
"""

# NOTE(kudkudak): There is no (yet) standalone tensorboard, and I don't think it makes sense to use tensorboardX
import tensorflow

from src.utils import save_weights

import sys
import numpy as np
import os
import pickle
import logging
import time
import datetime
import json

logger = logging.getLogger(__name__)

class Callback(object):
    def __init__(self):
        pass

    def set_config(self, config):
        self.config = config

    def set_meta_data(self, meta_data):
        self.meta_data = meta_data

    def set_save_path(self, save_path):
        self.save_path = save_path

    def set_params(self, params):
        self.params = params

    def set_model(self, model):
        self.model = model

    def on_epoch_begin(self, epoch, logs):
        pass

    def on_epoch_end(self, epoch, logs):
        pass

    def on_batch_begin(self, batch, logs):
        pass

    def on_batch_end(self, batch, logs):
        pass

    def on_backward_end(self, batch):
        pass

    def on_train_begin(self, logs):
        pass

    def on_train_end(self, logs):
        pass


class LRSchedule(Callback):
    def __init__(self, schedule):
        self.schedule = schedule
        super(LRSchedule, self).__init__()

    def on_epoch_begin(self, epoch, logs):
        # Epochs starts from 0
        for e, v in self.schedule:
            if epoch < e:
                break
        for group in self.model.optimizer.param_groups:
            group['lr'] = v
        logger.info("Fix learning rate to {}".format(v))


class History(Callback):
    """
    History callback.

    By default saves history every epoch, can be configured to save also every k examples
    """
    def __init__(self, save_every_k_examples=-1):
        self.examples_seen = 0
        self.save_every_k_examples = save_every_k_examples
        self.examples_seen_since_last_population = 0
        super(History, self).__init__()

    def on_train_begin(self, logs=None):
        # self.epoch = []
        self.history = {}
        self.history_batch = {}

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        # self.epoch.append(epoch)
        for k, v in logs.items():
            self.history.setdefault(k, []).append(v)

        if self.save_path is not None:
            pickle.dump(self.history, open(os.path.join(self.save_path, "history.pkl"), "wb"))
            if self.save_every_k_examples != -1:
                pickle.dump(self.history_batch, open(os.path.join(self.save_path, "history_batch.pkl"), "wb"))

    def on_batch_end(self, epoch, logs=None):
        # Batches starts from 1
        if self.save_every_k_examples != -1:
            if getattr(self.model, "history_batch", None) is None:
                setattr(self.model, "history_batch", self)
            assert "size" in logs
            self.examples_seen += logs['size']
            logs['examples_seen'] = self.examples_seen
            self.examples_seen_since_last_population += logs['size']

            if self.examples_seen_since_last_population > self.save_every_k_examples:
                for k, v in logs.items():
                    self.history_batch.setdefault(k, []).append(v)
                self.examples_seen_since_last_population = 0


class ModelCheckpoint(Callback):
    def __init__(self, filepath, model, optimizer, monitor='val_loss', verbose=0,
                 save_best_only=False,
                 mode='auto', period=1):
        super(ModelCheckpoint, self).__init__()
        self.monitor = monitor
        self.optimizer = optimizer
        self.verbose = verbose
        self.filepath = filepath
        self.model = model
        self.save_best_only = save_best_only
        self.period = period
        self.epochs_since_last_save = 0

        if mode not in ['auto', 'min', 'max']:
            mode = 'auto'

        if mode == 'min':
            self.monitor_op = np.less
            self.best = np.Inf
        elif mode == 'max':
            self.monitor_op = np.greater
            self.best = -np.Inf
        else:
            if 'acc' in self.monitor or self.monitor.startswith('fmeasure'):
                self.monitor_op = np.greater
                self.best = -np.Inf
            else:
                self.monitor_op = np.less
                self.best = np.Inf

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['model']
        del state['optimizer']
        return state

    def __setstate__(self, newstate):
        newstate['model'] = self.model
        newstate['optimizer'] = self.optimizer
        self.__dict__.update(newstate)

    def on_epoch_end(self, epoch, logs=None):
        logs = logs or {}
        self.epochs_since_last_save += 1
        if self.epochs_since_last_save >= self.period:
            self.epochs_since_last_save = 0
            if self.save_best_only:
                current = logs.get(self.monitor)
                if current is None:
                    logging.warning('Can save best model only with %s available, '
                                    'skipping.' % (self.monitor), RuntimeWarning)
                else:
                    if self.monitor_op(current, self.best):
                        if self.verbose > 0:
                            print('Epoch %05d: %s improved from %0.5f to %0.5f,'
                                  ' saving model to %s'
                                  % (epoch, self.monitor, self.best,
                                     current, self.filepath))
                        self.best = current
                        save_weights(self.model.model, self.optimizer, self.filepath)
                    else:
                        if self.verbose > 0:
                            print('Epoch %05d: %s did not improve' %
                                  (epoch, self.monitor))
            else:
                if self.verbose > 0:
                    print('Epoch %05d: saving model to %s' % (epoch, self.filepath))
                    save_weights(self.model.model, self.optimizer, self.filepath)


class LambdaCallback(Callback):
    def __init__(self,
                 on_epoch_begin=None,
                 on_epoch_end=None,
                 on_batch_begin=None,
                 on_batch_end=None,
                 on_train_begin=None,
                 on_train_end=None):
        super(LambdaCallback, self).__init__()
        if on_epoch_begin is not None:
            self.on_epoch_begin = on_epoch_begin
        else:
            self.on_epoch_begin = lambda epoch, logs: None
        if on_epoch_end is not None:
            self.on_epoch_end = on_epoch_end
        else:
            self.on_epoch_end = lambda epoch, logs: None
        if on_batch_begin is not None:
            self.on_batch_begin = on_batch_begin
        else:
            self.on_batch_begin = lambda batch, logs: None
        if on_batch_end is not None:
            self.on_batch_end = on_batch_end
        else:
            self.on_batch_end = lambda batch, logs: None
        if on_train_begin is not None:
            self.on_train_begin = on_train_begin
        else:
            self.on_train_begin = lambda logs: None
        if on_train_end is not None:
            self.on_train_end = on_train_end
        else:
            self.on_train_end = lambda logs: None


class LambdaCallbackPickableEveryKExamples(LambdaCallback):
    """
    Runs lambda every K examples.

    Note: Assumes 'size' key in batch logs denoting size of the current minibatch
    """
    def __init__(self,
                 on_k_examples=None,
                 k=45000,
                 call_after_first_batch=False,
                 **kwargs):
        super(LambdaCallback, self).__init__()
        self.__dict__.update(kwargs)
        self.examples_seen = 0
        self.call_after_first_batch = call_after_first_batch
        self.examples_seen_since_last_call = 0
        self.k = k
        self.on_k_examples = on_k_examples
        self.calls = 0

    def on_batch_end(self, batch, logs=None):
        # Batches starts from 1
        assert "size" in logs
        self.examples_seen += logs['size']
        self.examples_seen_since_last_call += logs['size']

        if (self.call_after_first_batch and batch == 1) \
                or self.examples_seen_since_last_call > self.k:
            logger.info("Batch " + str(batch))
            logger.info("Firing on K examples, ex seen = " + str(self.examples_seen))
            logger.info("Firing on K examples, ex seen last call = " + str(self.examples_seen_since_last_call))
            self.on_k_examples(logs) # self.calls, self.examples_seen,
            self.examples_seen_since_last_call = 0
            self.calls += 1

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['on_k_examples']
        return state


class DumpTensorboardSummaries(Callback):
    def __init__(self):
        super(DumpTensorboardSummaries, self).__init__()

    @property
    def file_writer(self):
        if not hasattr(self, '_file_writer'):
            self._file_writer = tensorflow.summary.FileWriter(
                self.save_path, flush_secs=10.)
        return self._file_writer

    def on_epoch_end(self, epoch, logs=None):
        summary = tensorflow.Summary()
        for key, value in logs.items():
            try:
                float_value = float(value)
                value = summary.value.add()
                value.tag = key
                value.simple_value = float_value
            except:
                pass
        self.file_writer.add_summary(
            summary, epoch)


class MetaSaver(Callback):
    def __init__(self, force_train=False):
        self.force_train = force_train
        super(MetaSaver, self).__init__()

    def on_train_begin(self, logs=None):
        if os.path.exists(os.path.join(self.save_path, "FINISHED")) and not self.force_train:
            logger.info("Finished training. Exiting. Remove FINISHED file if you want to train anyways.")
            exit(0)

        assert os.system("cp {} {}".format(sys.argv[0], self.save_path)) == 0, "Failed to execute cp of source script"

        utc_date = datetime.datetime.utcnow().strftime("%Y_%m_%d")

        time_start = time.time()
        cmd = "python " + " ".join(sys.argv)
        self.meta = {"cmd": cmd,
                     "save_path": self.save_path,
                     "start_utc_date": utc_date,
                     "execution_time": -time_start}

        json.dump(self.config, open(os.path.join(self.save_path, "config.json"), "w"), indent=4)
        json.dump(self.meta, open(os.path.join(self.save_path, "meta.json"), "w"), indent=4)

    def on_train_end(self, logs=None):
        self.meta['execution_time'] += time.time()
        json.dump(self.meta, open(os.path.join(self.save_path, "meta.json"), "w"), indent=4)
        os.system("touch " + os.path.join(self.save_path, "FINISHED"))