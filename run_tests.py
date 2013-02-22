#!/usr/bin/env python
import os, re
from threading import Lock

from ansible.runner import Runner
from ansible.inventory import Inventory
from ansible import callbacks, utils
from ansible.playbook import PlayBook

import xunitparser


utils.VERBOSITY=1


class RunnerCallbacks(callbacks.PlaybookRunnerCallbacks):
    def __init__(self, inventory, stats, verbose):
        super(RunnerCallbacks, self).__init__(stats, verbose=verbose)
        self.inventory = inventory
        self.tests_lock = Lock()
        self.tests_generated = False
    def on_ok(self, host, res):
        module = res['invocation']['module_name']
        if 'git' == module:
            with self.tests_lock:
                if not self.tests_generated:
                    r = Runner(module_name='shell', 
                        module_args='find . -name "Test*java" -exec basename {} \; | sed -e "s/.java//g" | tr "\n" "," chdir=$target_dir',
                        inventory=self.inventory,
                        pattern=host) 
                    res = r.run()
                    self.gen_test_lists(res['contacted'][host]['stdout'].split(','))
                    self.tests_generated = True
        super(RunnerCallbacks, self).on_ok(host, res)
    def gen_test_lists(self, tests):
        hosts = [h.name for h in self.inventory.get_hosts()]
        hosts_cnt = len(hosts)
        tests_per_host = {}
        for i in range(0, len(tests)):
            tests_per_host.setdefault(hosts[i % hosts_cnt], []).append(tests[i]) 
        for host in hosts:
            f = open('tests_' + host, "w")
            f.write(",".join(tests_per_host[host]))
            f.close()

build_num = 0
if 'builds' in os.listdir(os.curdir):
     builds =  map(
      lambda d: int(d), 
      filter(
        lambda d: re.match('\d+', d), 
        os.listdir('builds')))
     if builds:
         build_num = sorted(builds, reverse=True)[0] + 1

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
for report in junit_reports():
    ts, tr = xunitparser.parse(open(report))
    skipped += filter(lambda tc: tc.skipped, ts)
    failed += filter(lambda tc: not tc.good, ts)
    executed += len([tc for tc in ts])

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
