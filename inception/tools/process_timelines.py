from __future__ import print_function
import sys
import glob
import numpy as np
import pickle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import re
import numpy as np
import ujson as json

worker_iter_finder = re.compile("worker=([0-9]+)_timeline_iter=([0-9]+)")

def add_to_dequeue_times(dq_start_time, dq_end_time, fname, dequeue_times):
    m = worker_iter_finder.search(fname)
    worker, iteration = tuple(int(x) for x in m.groups())
    if iteration not in dequeue_times:
        dequeue_times[iteration] = {}
    dequeue_times[iteration][worker] = (dq_start_time, dq_end_time)

def process_timeline(fname, dequeue_times):
    f = open(fname, "r")
    timeline_obj = json.loads(f.read())
    n_dequeues_per_iteration = 0
    dq_start_time, dq_duration = 0, 0
    begin_ts = 1476920659882316**2
    for event in timeline_obj["traceEvents"]:
        # We use QueueDequeue operation as a marker event.
        # Its start time is when the worker is done computing and has sent the gradient to the PS.
        # Its end time is how long the worker waited for the slowest worker of the group.
        if event["name"] == "QueueDequeue":
            # Note that time is in microseconds
            dq_start_time = event["ts"]
            dq_duration = event["dur"]
            n_dequeues_per_iteration += 1
        else:
            if "ts" in event:
                begin_ts = min(begin_ts, event["ts"])

    # Only 1 dequeue per iteration
    assert(n_dequeues_per_iteration == 1)

    start_time = (dq_start_time - begin_ts) / 1000000.0
    end_time = start_time + dq_duration / 1000000.0
    add_to_dequeue_times(start_time, end_time, fname, dequeue_times)
    print("Dequeue start time: %f, end time: %f" % (start_time, end_time))

    f.close()

def mean_min_max_stdev(vals):
    return sum(vals)/float(len(vals)), min(vals), max(vals), np.std(vals), np.percentile(np.array(vals), 99)

def create_runtime_histogram_per_iter(dequeue_times):
    for iteration in dequeue_times.keys():
        # 0'th index = start dequeue time = time worker spent computing gradient
        gradient_compute_times = [dequeue_times[iteration][worker][0] for worker in dequeue_times[iteration].keys()]
        dequeue_end_time =  [dequeue_times[iteration][worker][1] for worker in dequeue_times[iteration].keys()]
        mean, mini, maxi, stdev, perc_99 = mean_min_max_stdev(gradient_compute_times)
        print("Iteration: %d, mean: %fs, min: %fs, max: %fs, perc_99: %fs, stdev: %f, max_dequeue_end_time: %fs" % (iteration, mean, mini, maxi, perc_99, stdev, max(dequeue_end_time)))

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python process_timelines.py dirname should_use_cached_dequeue_times")
        sys.exit(0)

    dir_name = sys.argv[1]
    if dir_name[-1] != "/":
        dir_name += "/"

    # [iteration][worker] in ms
    dequeue_times = {}
    if int(sys.argv[2]) == 0:

        # Process all timelines for all iterations
        for filename in glob.glob(dir_name + "*"):
            print(filename)
            process_timeline(filename, dequeue_times)

        f_cached_dequeue = open("cached_dequeue_times.json", "w")
        pickle.dump(dequeue_times, f_cached_dequeue)
        f_cached_dequeue.close()
    else:
        f_cached_dequeue = open("cached_dequeue_times.json", "r")
        dequeue_times = pickle.load(f_cached_dequeue)
        f_cached_dequeue.close()

    # Create histograms of runtimes for all timelines and all iterations
    create_runtime_histogram_per_iter(dequeue_times)
