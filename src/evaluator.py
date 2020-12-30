import threading
import time
import psutil
import rostopic
import rospy
from glog import logging
from node_evaluator.msg import Bandwidth as BandwidthMsg


class EvaluatorFactory:

    registry = {}

    @classmethod
    def register(cls, name):
        def inner_wrapper(wrapped_class):
            if name in cls.registry:
                print('Evaluator %s already exists.' % name)
            cls.registry[name] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def create_evaluator(cls, name, **kwargs):
        if name not in cls.registry:
            print('Evaluator %s does not exists.')
            raise NotImplementedError

        eval_class = cls.registry[name]
        evaluator = eval_class(**kwargs)
        return evaluator


class EvaluatorBase(threading.Thread):
    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        self.eval_rate_s = kwargs['eval_rate_s']
        self.eval_stat = {}
        self.eval_stat['time'] = []
        self.stat_update_lock = threading.Lock()
        self.term_event = threading.Event()

    def print_start(self):
        pass

    def run(self):
        self.print_start()

        start_time = time.time()
        while not self.term_event.is_set():
            with self.stat_update_lock:
                if self.eval():
                    self.eval_stat['time'].append(time.time())
            time_to_sleep = start_time + self.eval_rate_s - time.time()
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)
            start_time = time.time()

        print('%s evaluation stopped' % self.eval_mode)

    def eval(self):
        return False

    def get_eval_stat(self):
        with self.stat_update_lock:
            return self.eval_stat

    def stop(self):
        self.term_event.set()


class ProcEvaluatorBase(EvaluatorBase):
    def __init__(self, **kwargs):
        super(ProcEvaluatorBase, self).__init__(**kwargs)
        self.node_name = kwargs['node_name']
        self.node_pid = kwargs['node_pid']
        if self.node_pid is not None:
            self.process = psutil.Process(self.node_pid)
        self.eval_stat[self.node_name] = []

    def print_start(self):
        print('Start %s evaluation on node %s pid %d' %
              (self.eval_mode, self.node_name, self.node_pid))


@EvaluatorFactory.register('cpu')
class CPUEvaluator(ProcEvaluatorBase):
    def __init__(self, **kwargs):
        super(CPUEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'cpu'

    def eval(self):
        self.eval_stat[self.node_name].append(self.process.cpu_percent())
        return True


@EvaluatorFactory.register('mem')
class MemEvaluator(ProcEvaluatorBase):
    def __init__(self, **kwargs):
        super(MemEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'mem'

    def eval(self):
        self.eval_stat[self.node_name].append(self.process.memory_percent())
        return True


@EvaluatorFactory.register('net')
class NetEvaluator(ProcEvaluatorBase):
    def __init__(self, **kwargs):
        super(NetEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'net'

    def eval(self):
        raise NotImplementedError
        print(self.process.connections())


class TopicEvaluatorBase(EvaluatorBase):
    def __init__(self, **kwargs):
        super(TopicEvaluatorBase, self).__init__(**kwargs)
        self.topic = kwargs['topic']
        self.eval_stat[self.topic] = []

    def print_start(self):
        print('Start %s evaluation on topic %s' % (self.eval_mode, self.topic))


@EvaluatorFactory.register('topic_bw')
class TopicBwEvaluator(TopicEvaluatorBase):
    class ROSTopicBandwidth(rostopic.ROSTopicBandwidth):
        def __init__(self, window_size=2):
            super(TopicBwEvaluator.ROSTopicBandwidth,
                  self).__init__(window_size=window_size)
            self.times.append(time.time())
            self.sizes.append(0)

        def get_bw(self):
            if len(self.times) < 2:
                return None
            with self.lock:
                n = len(self.times)
                tn = time.time()
                t0 = self.times[0]

                total = sum(self.sizes)
                bytes_per_s = total / (tn - t0)
                mean = total / n

                # min and max
                max_s = max(self.sizes)
                min_s = min(self.sizes)

                bd_stat = {}
                bd_stat['bytes_per_s'] = bytes_per_s
                bd_stat['mean'] = mean
                bd_stat['min_s'] = min_s
                bd_stat['max_s'] = max_s
                return bd_stat

    def __init__(self, **kwargs):
        super(TopicBwEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'topic_bw'
        self.rt = {}
        self.sub = {}
        self.rt = TopicBwEvaluator.ROSTopicBandwidth(10)
        self.sub = rospy.Subscriber(self.topic, rospy.AnyMsg,
                                    self.rt.callback)

    def eval(self):
        new_bw = self.rt.get_bw()
        if new_bw is not None:
            self.eval_stat[self.topic].append(new_bw['bytes_per_s']/1000000)
            return True
        else:
            return False


@EvaluatorFactory.register('bw_from_msg')
class BwFromMsgEvaluator(EvaluatorBase):
    def __init__(self, **kwargs):
        super(BwFromMsgEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'bw_from_msg'
        self.topic = kwargs['bw_topic']
        self.sub = rospy.Subscriber(
            self.topic, BandwidthMsg, self._bw_callback)

    def _bw_callback(self, data):
        self.eval_stat['time'].append(data.time[0])
        self.eval_stat[data.name].append(data.size/(data.time[1]-data.time[0]))
        self.eval_stat['time'].append(data.time[1])
        self.eval_stat[data.name].append(data.size/(data.time[1]-data.time[0]))

    def eval(self):
        # return false to stop base class to add now() to time list
        return False


@EvaluatorFactory.register('sys_bw')
class SysBwEvaluator(EvaluatorBase):
    def __init__(self, **kwargs):
        super(SysBwEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'sys_bw'
        self.eval_stat['total_recv'] = []
        self.eval_stat['total_sent'] = []
        self.old_recv = 0
        self.old_sent = 0

    def print_start(self):
        print("Start %s evaluation" % self.eval_mode)

    def eval(self):
        result = True
        new_recv = psutil.net_io_counters().bytes_recv
        new_sent = psutil.net_io_counters().bytes_sent
        if self.old_recv == 0 or self.old_sent == 0:
            result = False
        else:
            self.eval_stat['total_recv'].append(
                (new_recv-self.old_recv)/(self.eval_rate_s*1000000))
            self.eval_stat['total_sent'].append(
                (new_sent-self.old_sent)/(self.eval_rate_s*1000000))
            result = True
        self.old_recv = new_recv
        self.old_sent = new_sent
        return result
