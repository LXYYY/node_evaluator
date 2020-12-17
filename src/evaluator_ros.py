#!/usr/bin/env python

import rospy, rosnode, rosgraph, rostopic
import re, time, glog, threading
import evaluator

ID = '/rosnode'


@evaluator.EvaluatorFactory.register('topic_bw')
class TopicBwEvaluator(evaluator.EvaluatorBase):
    class ROSTopicBandwidth(rostopic.ROSTopicBandwidth):
        def __init__(self, window_size=100):
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
        self.topics = kwargs['topics']
        self.rt = {}
        self.sub = {}
        for topic in self.topics:
            rt = TopicBwEvaluator.ROSTopicBandwidth(10)
            self.sub[topic] = rospy.Subscriber(topic, rospy.AnyMsg,
                                               rt.callback)
            self.rt[topic] = rt
            self.eval_stat[topic] = []
            print('Start %s evaluation on topic %s' % (self.eval_mode, topic))

    def eval(self):
        for topic in self.topics:
            self.eval_stat[topic].append(self.rt[topic].get_bw())
            print(self.rt[topic].get_bw())


class Evaluator:
    def __init__(self):
        self.eval_rate_s = rospy.get_param('~eval_rate_s', default=0.5)

        self.node_names = rospy.get_param('~node_names')
        for i in range(0, len(self.node_names)):
            self.node_names[i] = rosgraph.names.script_resolve_name(
                '/', self.node_names[i])
        node_eval_mode = rospy.get_param('~node_eval_mode')
        if self.node_names is not None or node_eval_mode is not None:
            glog.check_eq(len(self.node_names), len(node_eval_mode))
            self.eval_mode = {}
            for name, mode in zip(self.node_names, node_eval_mode):
                self.eval_mode[name] = mode

        self.ext_eval = rospy.get_param('~ext_eval')
        if 'topic_bw' in self.ext_eval:
            self.topics = rospy.get_param('~topics')

        self.master = rosgraph.Master(ID)
        self.node_pid = {}
        self.node_eval_threads = {}
        self.ext_eval_threads = {}
        for node_name in self.node_names:
            self.node_eval_threads[node_name] = {}

        self.start_eval()

    def start_eval(self):
        rate = rospy.Rate(2)
        while self.node_names is not None and not rospy.is_shutdown():
            rate.sleep()
            all_node_names = rosnode.get_node_names()
            for node_name in self.node_names:

                # check if node is running
                if node_name not in all_node_names:
                    rospy.logwarn('Node %s is not running' % node_name)
                    continue

                if node_name in self.node_pid:
                    continue

                rospy.loginfo('Looking for pid of node %s' % node_name)
                node_api = rosnode.get_api_uri(self.master, node_name)
                node_con_info = rosnode.get_node_connection_info_description(
                    node_api, self.master)
                pid_match = re.search('Pid: (\d+)', node_con_info)
                if pid_match is None:
                    rospy.logwarn('Not found pid in description of node %s' %
                                  node_name)
                    continue
                self.node_pid[node_name] = int(pid_match.group(1))
                rospy.loginfo('Pid: %d' % self.node_pid[node_name])

            if len(self.node_pid) == len(self.node_names):
                break

        rospy.loginfo('Catched pid of every node, start evaluating')

        self._start_eval_threads()

        rospy.on_shutdown(self.stop_threads)

    def _start_eval_threads(self):
        for node_name in self.node_names:
            for eval_mode in self.eval_mode[node_name]:
                eval_thread = evaluator.EvaluatorFactory.create_evaluator(
                    eval_mode,
                    node_name=node_name,
                    node_pid=self.node_pid[node_name],
                    eval_rate_s=self.eval_rate_s)
                eval_thread.start()
                self.node_eval_threads[node_name][eval_mode] = eval_thread

        for ext_eval_name in self.ext_eval:
            ext_eval_thread = evaluator.EvaluatorFactory.create_evaluator(
                ext_eval_name,
                topics=self.topics,
                eval_rate_s=self.eval_rate_s)
            ext_eval_thread.start()
            self.ext_eval_threads[ext_eval_name] = ext_eval_thread

    def stop_threads(self):
        for node_name in self.node_names:
            for eval_mode in self.eval_mode[node_name]:
                self.node_eval_threads[node_name][eval_mode].stop()

        for thread in self.ext_eval_threads:
            self.ext_eval_threads[thread].stop()


if __name__ == "__main__":
    rospy.init_node('evaluator', anonymous=True)
    evaluator = Evaluator()
    rospy.spin()
