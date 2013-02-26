#!/usr/bin/env python
import os, re
from datetime import datetime
import argparse

from ansible.runner import Runner
from ansible.inventory import Inventory
from ansible import callbacks, utils
from ansible.playbook import PlayBook

import xunitparser

from balancer import new_balancer


def gen_test_lists(build_dir, inventory, tests):
    hosts = [h.name for h in inventory.get_hosts()]
    balancer = new_balancer()
    splits = balancer.calc_splits(len(hosts), tests) 
    for i in range(0, len(hosts)):
        f = open(build_dir + '/tests_' + hosts[i], "w")
        f.write(",".join(splits[i]))
        f.close()

def junit_reports(build_dir):
    for dirname, dirnames, filenames in os.walk(build_dir):
        for fn in filenames:
            if fn.startswith('TEST-') and fn.endswith('.xml'):
                yield os.path.join(dirname, fn)


class RunnerCallbacks(callbacks.PlaybookRunnerCallbacks):
    def __init__(self, build_dir, inventory, stats, verbose, module):
        super(RunnerCallbacks, self).__init__(stats, verbose=verbose)
        self.build_dir = build_dir
        self.inventory = inventory
        self.module = module
    def on_ok(self, host, res):
        module = res['invocation']['module_name']
        print "%s ok:[%s]" % (str(datetime.now()), host)
        if 'git' == module and host == self.inventory.get_hosts()[0].name:
            r = Runner(module_name='shell', 
                module_args='find . -name "Test*java" -exec basename {} \; | sed -e "s/.java//g" | tr "\n" "," chdir=$target_dir/%s' % self.module,
                inventory=self.inventory,
                pattern=host) 
            res = r.run()
            gen_test_lists(self.build_dir, self.inventory, res['contacted'][host]['stdout'].split(','))

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("-v", "--verbose", 
  help="increase output verbosity",
  action="store_true")
arg_parser.add_argument("-m", "--module",
  help="module to test (e.g. hadoop-common-project/hadoop-common)",
  default=".")
args = arg_parser.parse_args()
if args.verbose:
    utils.VERBOSITY=1

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
runner_cb = RunnerCallbacks(build_dir, inv, stats, 
  utils.VERBOSITY, args.module)
extra_vars = {'build_dir': build_dir}
if args.module:
    extra_vars['module'] = args.module
pb = PlayBook(playbook='run_tests.yml', inventory=inv, 
  stats=stats, runner_callbacks=runner_cb, callbacks=playbook_cb, 
  extra_vars=extra_vars)
pb.run()


os.system('find %s -name *tar.gz -exec tar -C %s -xzf {} \;' % (build_dir, build_dir))

failed = []
skipped = []
executed = 0
tests_durations = {}
for report in junit_reports(build_dir):
    ts, tr = xunitparser.parse(open(report))
    skipped += filter(lambda tc: tc.skipped, ts)
    failed += filter(lambda tc: not tc.good, ts)
    executed += len([tc for tc in ts])
    name = ts.name[ts.name.rindex('.') + 1:]
    tests_durations[name] = tr.time.total_seconds()

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
