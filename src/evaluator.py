import threading, time
import psutil


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
                self.eval_stat['time'].append(time.time())
                self.eval()
            time.sleep(start_time + self.eval_rate_s - time.time())
            start_time = time.time()

        print('Evaluation stopped')

    def eval(self):
        pass

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


@EvaluatorFactory.register('mem')
class MemEvaluator(ProcEvaluatorBase):
    def __init__(self, **kwargs):
        super(MemEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'mem'

    def eval(self):
        self.eval_stat[self.node_name].append(self.process.memory_percent())


@EvaluatorFactory.register('net')
class NetEvaluator(ProcEvaluatorBase):
    def __init__(self, **kwargs):
        super(NetEvaluator, self).__init__(**kwargs)
        self.eval_mode = 'net'

    def eval(self):
        raise NotImplementedError
        print(self.process.connections())
