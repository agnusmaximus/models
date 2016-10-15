import sys
import glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import re
import numpy as np

host_id_finder = re.compile(".*/out(.*)")
time_finder = re.compile("Time: ([0-9]+)ms \[([0-9]+)\]")

def print_stats(times, name):
    # Maximum and minimum time to compute elapsed time
    max_time = max([max(t) for k,t in times.items()])
    min_time = min([min(t) for k,t in times.items()])
    print("Statistics for %s" % name)
    print("Approximate elapsed time: %fs" % ((max_time-min_time) / float(1000)))

    # Compute mean time by taking the maximum time of the 1st iteration as base_time.
    # Then the elapsed times for the 2nd iteration is the timestamps in the list - base_time.
    for i in range(len(times.items())-1):
        base_time = max(times[i])
        assert(min(times[i+1]) >= base_time)
        elapsed_times = [x-base_time for x in times[i+1]]
        avg_time = sum(elapsed_times)/float(len(elapsed_times))
        min_time = min(elapsed_times)
        max_time = max(elapsed_times)
        percentile_99 = np.percentile(np.array(elapsed_times), 99)
        print("Iteration %d Avg Time: %fms Min Time: %fms Max Time: %fms 99-percentile: %fms" % (i+1, avg_time, min_time, max_time, percentile_99))

def get_arrival_times(f):
    f = open(f, "r")
    times = {}
    for line in f:
        m = time_finder.search(line)
        if m:
            # We expect timestamp, iteration for m.groups
            timestamp_ms, iteration = int(m.groups()[0]), int(m.groups()[1])
            if iteration not in times:
                times[iteration] = []
            times[iteration].append(timestamp_ms)
    print(times)
    return times

def draw_arrival_times_histogram(f, output_name):
    times = get_arrival_times(f)
    plt.clf()
    plt.xlabel('Timestamp(ms)')
    plt.ylabel('Num Occurrences')
    plt.suptitle('Gradient Arrival Times Histogram (measured on PS)')
    for iteration, t in times.items():
        plt.hist(t, label="iteration %d" % iteration)
    plt.legend(loc="upper right")
    plt.savefig("GradientArrivalTimesHistogram_%s.png" % output_name)
    print_stats(times, output_name)

# Looks in ./outfiles/out%d for worker elapsed times.
# Usage: python process_outfiles.py
if __name__=="__main__":
    if len(sys.argv) != 2:
        print("Usage: python process_outfiles.py dir")

    all_files = []
    for filename in glob.glob(sys.argv[1] + "/*"):
        all_files.append(filename)

    print("Files: %s" % ", ".join(all_files))
    print("Only look at last file, since that is the PS's output file.")

    files_with_ids = []
    ps_host_id = 0
    for filename in all_files:
        m = host_id_finder.match(filename)
        hostid = int(m.groups(0)[0])
        ps_host_id = max(ps_host_id, hostid)
        files_with_ids.append((hostid, filename))

    process_files = [x[1] for x in files_with_ids if x[0] == ps_host_id]
    print("Files: %s" % ", ".join(process_files))

    draw_arrival_times_histogram(process_files[0], sys.argv[1])
