import sqlite3 as lite
import random

class Balancer(object):
    def calc_splits(self, split_factor, test_names):
        raise "Not implemented"
    def update_stats(self, junit_reports):
        raise "Not implemented"

class RoundRobinBalancer(object):
    def calc_splits(self, split_factor, test_names):
        splits = {}
        for i in range(0, len(test_names)):
            tests = splits.setdefault(i % split_factor, [])
            tests.append(test_names[i]) 
        return splits
    def update_stats(self, junit_reports):
        pass

class EvenDurationBalancer(RoundRobinBalancer):
    def __init__(self):
        con = lite.connect('test_stats.db')
        try:
            cursor = con.cursor()
            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='test_stat'")
            self.no_stats = 0 == cursor.fetchone()[0]
            if self.no_stats:
                cursor.execute("create table test_stat(test_name varchar(512), duration float)")
        finally:
            con.close()
    def calc_splits(self, split_factor, test_names):
        if self.no_stats:
            print "Use round robin test balancing as there are no stats collected"
            return super(EvenDurationBalancer, self).calc_splits(split_factor, test_names)
        #[ LOAD TEST STATISTICS
        con = lite.connect('test_stats.db')
        try:
            cursor = con.cursor()
            cursor.execute("SELECT test_name, duration FROM test_stat")
            test_statistics_data = cursor.fetchall()
            test_statistics = dict(test_statistics_data)
            print "Loaded statistics for %d tests" % len(test_statistics)
        finally:
            con.close()
        #]
 
        #[ PREPARE SPLITS, GREEDY ALGORITHM
        test_splits = [ [] for i in range(split_factor) ]
        test_times = [0] * split_factor
        unknown_tests = [0] * split_factor
        for test in sorted(test_names, key=lambda test : -test_statistics.get(test, 0)):
            split_index = test_times.index(min(test_times))
            test_duration = test_statistics.get(test, 0)
            print "Process test %s, duration %f" % (test, test_duration)
            if not test_duration:
                split_index = random.randint(0, split_factor - 1)
                unknown_tests[split_index] += 1
            test_splits[split_index].append(test)
            test_times[split_index] += test_duration
        for split, total_time, unknown in zip(test_splits, test_times, unknown_tests):
            print 'Split size %3d, known duration %7.2f, unknown tests %3d' % (len(split), total_time, unknown)
        #]

        return test_splits

    def update_stats(self, tests_durations):
        #[ UPDATE TEST STATISTICS
        con = lite.connect("test_stats.db")
        try:
            cursor = con.cursor()
            for test in tests_durations: 
                duration = tests_durations[test]
                print "Process test %s, duration %s" % (test, duration)
                cursor.execute("REPLACE INTO test_stat(test_name, duration) VALUES(?,?) ", (test, float(duration)))
            con.commit()
        finally:
            con.close()
        print "Test statistics updated"
        self.no_stats = False
        #]

def new_balancer():
    return EvenDurationBalancer()
    #return RoundRobinBalancer()
