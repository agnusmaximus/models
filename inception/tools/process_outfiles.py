import sys
import glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import re
import numpy as np

host_id_finder = re.compile("./outfiles/out(.*)")
time_finder = re.compile("Time: ([0-9]+)ms")

def print_stats(nums, name):
    mean = sum(nums)/float(len(nums))
    med = sorted(nums)[len(nums)/2]
    stddev = np.std(nums)
    print("%s - mean: %f med: %f stddev: %f" % (name, mean, med, stddev))

def get_set_of_elapsed_times(f):
    f = open(f, "r")
    times = []
    for line in f:
        m = time_finder.search(line)
        if m:
            for g in m.groups():
                times.append(int(g))

    elapsed = [times[i]-times[i-1] for i in range(1, len(times))]
    f.close()
    return elapsed

def draw_individual_worker_times_histogram(f, name):
    elapsed = get_set_of_elapsed_times(f)
    print_stats(elapsed, name)
    plt.clf()
    plt.xlabel('Time(ms)')
    plt.ylabel('Num Occurrences')
    plt.suptitle('%s Histogram' % name)
    plt.hist(elapsed,bins=100,fc=(0, 0, 1, 0.5))
    plt.savefig("%s.png" % name)

def draw_combined_worker_times_histogram(fs, name):
    elapsed = []
    for f in fs:
        elapsed += get_set_of_elapsed_times(f)
    print_stats(elapsed, name)
    plt.clf()
    plt.xlabel('Time(ms)')
    plt.ylabel('Num Occurrences')
    plt.suptitle('%s Histogram' % name)
    plt.hist(elapsed,bins=100,fc=(0, 0, 1, 0.5))
    plt.savefig("%s.png" % name)

# Looks in ./outfiles/out%d for worker elapsed times.
# Usage: python process_outfiles.py
if __name__=="__main__":
    all_files = []
    for filename in glob.glob("./outfiles/*"):
        all_files.append(filename)

    print("Files: %s" % ", ".join(all_files))
    print("Excluding last file since the last host is the PS")

    files_with_ids = []
    ps_host_id = 0
    for filename in all_files:
        m = host_id_finder.match(filename)
        hostid = int(m.groups(0)[0])
        ps_host_id = max(ps_host_id, hostid)
        files_with_ids.append((hostid, filename))

    process_files = [x[1] for x in files_with_ids if x[0] != ps_host_id]
    print("Files: %s" % ", ".join(process_files))

    for i, f in enumerate(process_files):
        draw_individual_worker_times_histogram(f, "Worker %d" % i)
    draw_combined_worker_times_histogram(process_files, "All")
