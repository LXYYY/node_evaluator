import evaluator as evaluator
import rostopic
import rospy


@evaluator.EvaluatorFactory.register('topic_bw')
class TopicBwEvaluator(evaluator.EvaluatorBase):
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
        self.topic = kwargs['topic']
        self.rt = {}
        self.sub = {}
        self.rt = TopicBwEvaluator.ROSTopicBandwidth(10)
        self.sub = rospy.Subscriber(self.topic, rospy.AnyMsg,
                                    self.rt.callback)
        self.eval_stat[self.topic] = []

    def print_start(self):
        print('Start %s evaluation on topic %s' % (self.eval_mode, self.topic))

    def eval(self):
        new_bw = self.rt.get_bw()
        if new_bw is not None:
            self.eval_stat[self.topic].append(new_bw['bytes_per_s'])
            return True
        else:
            return False
