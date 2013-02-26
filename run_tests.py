#!/usr/bin/env python
import os, re
from datetime import datetime
from contextlib import contextmanager

from ansible.runner import Runner
from ansible.inventory import Inventory
from ansible import callbacks, utils
from ansible.playbook import PlayBook

import xunitparser

from balancer import new_balancer


utils.VERBOSITY=0

def gen_test_lists(inventory, tests):
    hosts = [h.name for h in inventory.get_hosts()]
    balancer = new_balancer()
    splits = balancer.calc_splits(len(hosts), tests) 
    for i in range(0, len(hosts)):
        f = open('tests_' + hosts[i], "w")
        f.write(",".join(splits[i]))
        f.close()


class RunnerCallbacks(callbacks.PlaybookRunnerCallbacks):
    def __init__(self, inventory, stats, verbose):
        super(RunnerCallbacks, self).__init__(stats, verbose=verbose)
        self.inventory = inventory
        self.host_ts = {}
        for h in inventory.get_hosts():
            self.host_ts[h.name] = datetime.now()
    def on_ok(self, host, res):
        module = res['invocation']['module_name']
        delta = datetime.now() - self.host_ts[host]
        print "done in %s on %s" % (str(delta), host)
        if 'git' == module and host == self.inventory.get_hosts()[0]:
            r = Runner(module_name='shell', 
                module_args='find . -name "Test*java" -exec basename {} \; | sed -e "s/.java//g" | tr "\n" "," chdir=$target_dir',
                inventory=self.inventory,
                pattern=host) 
            res = r.run()
            gen_test_lists(self.inventory, res['contacted'][host]['stdout'].split(','))
        super(RunnerCallbacks, self).on_ok(host, res)
        self.host_ts[host] = datetime.now()


build_num = 0
prev_build_num = None
if 'builds' in os.listdir(os.curdir):
     builds =  map(
      lambda d: int(d), 
      filter(
        lambda d: re.match('\d+', d), 
        os.listdir('builds')))
     if builds:
         prev_build_num = sorted(builds, reverse=True)[0]
         build_num = prev_build_num + 1

print "Build", build_num

build_dir = "builds/%s" % build_num
os.makedirs(build_dir)

inv = Inventory('hosts')

stats = callbacks.AggregateStats()
playbook_cb = callbacks.PlaybookCallbacks(verbose=utils.VERBOSITY)
runner_cb = RunnerCallbacks(inv, stats, verbose=utils.VERBOSITY)
pb = PlayBook(playbook='run_tests.yml', inventory=inv, 
  stats=stats, runner_callbacks=runner_cb, callbacks=playbook_cb, 
  extra_vars={'build_dir': build_dir})
pb.run()


def junit_reports():
    for dirname, dirnames, filenames in os.walk(build_dir):
        for fn in filenames:
            if fn.startswith('TEST-') and fn.endswith('.xml'):
                yield os.path.join(dirname, fn)

os.system('find %s -name *tar.gz -exec tar -C %s -xzf {} \;' % (build_dir, build_dir))

failed = []
skipped = []
executed = 0
tests_durations = {}
for report in junit_reports():
    ts, tr = xunitparser.parse(open(report))
    skipped += filter(lambda tc: tc.skipped, ts)
    failed += filter(lambda tc: not tc.good, ts)
    executed += len([tc for tc in ts])
    tests_durations[ts.name] = tr.time.total_seconds()

balancer = new_balancer()
balancer.update_stats(tests_durations)

print "Tests run: %s\tFailures: %s\tSkipped: %s" % (executed, len(failed), len(skipped))

if failed:
    print "\nFailed tests:"
    for tc in failed:
        print "  " + tc.methodname + "(" + tc.classname + ")"

if skipped:
    print "\nSkipped tests:"
    for tc in skipped:
        if tc.methodname == tc.classname:
            print "  " + tc.classname
        else: 
            print "  " + tc.methodname + "(" + tc.classname + ")"
