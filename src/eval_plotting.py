import csv
import datetime
import os
import re
import sys
import numpy as np
import rospy
import shutil
from matplotlib import pyplot as plt


class PlottingFactory(object):

    registry = {}

    @classmethod
    def register(cls, name):
        def inner_wrapper(wrapped_class):
            if name in cls.registry:
                print('Plotting %s already exists.' % name)
            cls.registry[name] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def create_evaluator(cls, name, **kwargs):
        if name not in cls.registry:
            print('Plotting %s does not exists.')
            raise NotImplementedError

        eval_class = cls.registry[name]
        evaluator = eval_class(**kwargs)
        return evaluator

    def __init__(self):
        pass


class PlottingBase(object):
    def __init__(self):
        pass
