from __future__ import print_function
import sys
import threading
import Queue
import paramiko as pm
import boto3
import time

configuration = {
    "key_name": "DistributedSGD",        # Necessary to ssh into created instances

    # Inception topology
    "n_masters" : 1,                     # Should always be 1
    "n_workers" : 5,
    "n_ps" : 1,
    "n_evaluators" : 1,                  # Continually validates the model on the validation data

    # Region speficiation
    "region" : "us-west-2",
    "availability_zone" : "us-west-2a",

    # Machine type - instance type configuration.
    "master_type" : "m4.2xlarge",
    "worker_type" : "m4.2xlarge",
    "ps_type" : "m4.2xlarge",
    "evaluator_type" : "m4.2xlarge",
    "image_id" : "ami-7a24fe1a",         # For us-west-2

    # Launch specifications
    "spot_price" : ".3",                 # Has to be a string

    # SSH configuration
    "ssh_username" : "ubuntu",           # For sshing. E.G: ssh ssh_username@hostname
    "path_to_keyfile" : "/Users/maxlam/Desktop/School/Fall2016/Research/DistributedSGD/DistributedSGD.pem",

    # NFS configuration
    # To set up these values, go to Services > ElasticFileSystem > Create new filesystem, and follow the directions.
    #"nfs_ip_address" : "172.31.3.173",        # This is particular to the availability zone specified above. west-2c
    "nfs_ip_address" : "172.31.35.0",          # us-west-2a
    "nfs_mount_point" : "/home/ubuntu/inception_shared", # Master writes checkpoints to this directory. Outfiles are written to this directory.

    # Dataset one of ("flowers" or "imagenet", since those are the script names)
    # Note that "imagenet" is not supported yet as the AMI does not have the imagenet dataset downloaded/preprocessed.
    "dataset" : "flowers",
    "num_validation_examples" : 500,            # 500 validation examples for flowers dataset.
}

client = boto3.client("ec2", region_name=configuration["region"])
ec2 = boto3.resource("ec2", region_name=configuration["region"])

def sleep_a_bit():
    time.sleep(5)

def summarize_instances(instances):
    instance_type_to_instance_map = {}
    for instance in instances:
        typ = instance.instance_type
        if typ not in instance_type_to_instance_map:
            instance_type_to_instance_map[typ] = []
        instance_type_to_instance_map[typ].append(instance)

    for k,v in instance_type_to_instance_map.items():
        print("%s - %d running" % (k, len(v)))

    return instance_type_to_instance_map

def summarize_idle_instances(argv):
    print("Idle instances: (Idle = not running tensorflow)")
    summarize_instances(get_idle_instances())

def summarize_running_instances(argv):
    print("Running instances: ")
    summarize_instances(ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]))

# Terminate all request.
def terminate_all_requests(method="spot"):
    if method == "spot":
        spot_requests = client.describe_spot_instance_requests()
        spot_request_ids = []
        for spot_request in spot_requests["SpotInstanceRequests"]:
            if spot_request["State"] != "cancelled":
                spot_request_id = spot_request["SpotInstanceRequestId"]
                spot_request_ids.append(spot_request_id)

        if len(spot_request_ids) != 0:
            print("Terminating spot requests: %s" % " ".join([str(x) for x in spot_request_ids]))
            client.cancel_spot_instance_requests(SpotInstanceRequestIds=spot_request_ids)

        # Wait until all are cancelled.
        # TODO: Use waiter class
        done = False
        while not done:
            print("Waiting for all spot requests to be terminated...")
            done = True
            spot_requests = client.describe_spot_instance_requests()
            states = [x["State"] for x in spot_requests["SpotInstanceRequests"]]
            for state in states:
                if state != "cancelled":
                    done = False
            sleep_a_bit()
    else:
        print("Unsupported terminate method: %s" % method)

# Terminate all instances in the configuration
# Note: all_instances = ec2.instances.all() to get all intances
def terminate_all_instances():
    live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    all_instance_ids = [x.id for x in live_instances]
    if len(all_instance_ids) != 0:
        print("Terminating instances: %s" % (" ".join([str(x) for x in all_instance_ids])))
        client.terminate_instances(InstanceIds=all_instance_ids)

        # Wait until all are terminated
        # TODO: Use waiter class
        done = False
        while not done:
            print("Waiting for all instances to be terminated...")
            done = True
            instances = ec2.instances.all()
            for instance in instances:
                if instance.state == "active":
                    done = False
            sleep_a_bit()

# Launch instances as specified in the configuration.
def launch_instances(method="spot"):
    if method == "spot":
        worker_instance_type, worker_count = configuration["worker_type"], configuration["n_workers"]
        master_instance_type, master_count = configuration["master_type"], configuration["n_masters"]
        ps_instance_type, ps_count = configuration["ps_type"], configuration["n_ps"]
        evaluator_instance_type, evaluator_count = configuration["evaluator_type"], configuration["n_evaluators"]
        specs = [(worker_instance_type, worker_count),
                 (master_instance_type, master_count),
                 (ps_instance_type, ps_count),
                 (evaluator_instance_type, evaluator_count)]
        for (instance_type, count) in specs:
            launch_specs = {"KeyName" : configuration["key_name"],
                            "ImageId" : configuration["image_id"],
                            "InstanceType" : instance_type,
                            "Placement" : {"AvailabilityZone":configuration["availability_zone"]},
                            "SecurityGroups": ["default"]}
            # TODO: EBS optimized? (Will incur extra hourly cost)
            client.request_spot_instances(InstanceCount=count,
                                          LaunchSpecification=launch_specs,
                                          SpotPrice=configuration["spot_price"])
    else:
        print("Unsupported launch method: %s" % method)

# TODO: use waiter class?
def wait_until_running_instances_initialized():
    done = False
    while not done:
        print("Waiting for instances to be initialized...")
        done = True
        live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
        ids = [x.id for x in live_instances]
        resps = client.describe_instance_status(InstanceIds=ids)
        for resp in resps["InstanceStatuses"]:
            if resp["InstanceStatus"]["Status"] != "ok":
                done = False
        if len(ids) <= 0:
            done = False
        sleep_a_bit()

# Waits until status requests are all fulfilled.
# Prints out status of request in between time waits.
# TODO: Use waiter class
def wait_until_instance_request_status_fulfilled(method="spot"):
    if method == "spot":
        requests_fulfilled, at_least_one_open_or_active = False, False
        while not requests_fulfilled or not at_least_one_open_or_active:
            requests_fulfilled = True
            statuses = client.describe_spot_instance_requests()
            print("InstanceRequestId, InstanceType, SpotPrice, State - Status : StatusMessage")
            print("-------------------------------------------")
            for instance_request in statuses["SpotInstanceRequests"]:
                sid = instance_request["SpotInstanceRequestId"]
                machine_type = instance_request["LaunchSpecification"]["InstanceType"]
                price = instance_request["SpotPrice"]
                state = instance_request["State"]
                status, status_string = instance_request["Status"]["Code"], instance_request["Status"]["Message"]
                if state == "active" or state == "open":
                    at_least_one_open_or_active = True
                    print("%s, %s, %s, %s - %s : %s" % (sid, machine_type, price, state, status, status_string))
                    if state != "active":
                        requests_fulfilled = False
            print("-------------------------------------------")
            sleep_a_bit()
    else:
        print("Unsupported instance request method: %s" % method)

# Takes a list of commands (E.G: ["ls", "cd models"]
# and executes command on instance, returning the stdout.
# Executes everything in one session, and returns all output from all the commands.
def run_ssh_commands(instance, commands):
    print("Instance %s, Running ssh commands:\n%s" % (instance.public_ip_address, " ".join(commands)))

    # Always need to exit
    commands.append("exit")

    # Set up ssh client
    client = pm.SSHClient()
    host = instance.public_ip_address
    client.set_missing_host_key_policy(pm.AutoAddPolicy())
    client.connect(host, username=configuration["ssh_username"], key_filename=configuration["path_to_keyfile"])

    # Clear the stdout from ssh'ing in
    # For each command perform command and read stdout
    commandstring = "\n".join(commands)
    stdin, stdout, stderr = client.exec_command(commandstring)
    output = stdout.read()

    # Close down
    stdout.close()
    stdin.close()
    client.close()

    return output

def run_ssh_commands_parallel(instance, commands, q):
    output = run_ssh_commands(instance, commands)
    q.put((instance, output))

# Checks whether instance is idle. Assumed that instance is up and running.
# An instance is idle if it is not running tensorflow...
# Returns a tuple of (instance, is_instance_idle). We return a tuple for multithreading ease.
def is_instance_idle(q, instance):
    python_processes = run_ssh_commands(instance, ["ps aux | grep python"])
    q.put((instance, not "imagenet" in python_processes and not "flowers" in python_processes))

# Idle instances are running instances that are not running the inception model.
# We check whether an instance is running the inception model by ssh'ing into a running machine,
# and checking whether python is running.
def get_idle_instances():
    live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    threads = []
    q = Queue.Queue()

    # Run commands in parallel, writing to the queue
    for instance in live_instances:
        t = threading.Thread(target=is_instance_idle, args=(q, instance))
        t.daemon = True
        t.start()
        threads.append(t)

    # Wait for threads to finish
    for thread in threads:
        thread.join()

    # Collect idle instances
    idle_instances = []
    while not q.empty():
        instance, is_idle = q.get()
        if is_idle:
            idle_instances.append(instance)

    return idle_instances

def get_instance_requirements():
    # Get the requirements given the specification of worker/master/etc machine types
    worker_instance_type, worker_count = configuration["worker_type"], configuration["n_workers"]
    master_instance_type, master_count = configuration["master_type"], configuration["n_masters"]
    ps_instance_type, ps_count = configuration["ps_type"], configuration["n_ps"]
    evaluator_instance_type, evaluator_count = configuration["evaluator_type"], configuration["n_evaluators"]
    specs = [(worker_instance_type, worker_count),
             (master_instance_type, master_count),
             (ps_instance_type, ps_count),
             (evaluator_instance_type, evaluator_count)]
    reqs = {}
    for (type_needed, count_needed) in specs:
        if type_needed not in reqs:
            reqs[type_needed] = 0
        reqs[type_needed] += count_needed
    return reqs

# Returns whether the idle instances satisfy the specs of the configuration.
def check_idle_instances_satisfy_configuration():
    # Create a map of instance types to instances of that type
    idle_instances = get_idle_instances()
    instance_type_to_instance_map = summarize_instances(idle_instances)

    # Get instance requirements
    reqs = get_instance_requirements()

    # Check the requirements are satisfied.
    print("Checking whether # of running instances satisfies the configuration...")
    for k,v in instance_type_to_instance_map.items():
        print("%s - %d running vs %d required" % (k,len(v),reqs[k]))
        if len(v) < reqs[k]:
            print("Error, running instances failed to satisfy configuration requirements")
            sys.exit(0)
    print("Success, running instances satisfy configuration requirement")

def shut_everything_down(argv):
    terminate_all_requests()
    terminate_all_instances()

# Main method to run inception on a set of idle instances.
def run_inception(argv, batch_size=128, port=1234):

    assert(configuration["n_masters"] == 1)

    # Check idle instances satisfy configs
    check_idle_instances_satisfy_configuration()

    # Get idle instances
    idle_instances = get_idle_instances()

    # Clear the nfs
    instances_string = ",".join([x.instance_id for x in idle_instances])
    clear_nfs_argv = ["python", "inception_ec2.py", instances_string, "rm -rf %s/*" % configuration["nfs_mount_point"]]
    run_command(clear_nfs_argv, quiet=True)

    # Assign instances for worker/ps/etc
    instance_type_to_instance_map = summarize_instances(idle_instances)
    specs = {
        "master" : {"instance_type" : configuration["master_type"],
                    "n_required" : configuration["n_masters"]},
        "worker" : {"instance_type" : configuration["worker_type"],
                    "n_required" : configuration["n_workers"]},
        "ps" : {"instance_type" : configuration["ps_type"],
                "n_required" : configuration["n_ps"]},
        "evaluator" : {"instance_type" : configuration["evaluator_type"],
                       "n_required" : configuration["n_evaluators"]}
    }
    machine_assignments = {
        "master" : [],
        "worker" : [],
        "ps" : [],
        "evaluator" : []
    }
    for role, requirement in specs.items():
        instance_type_for_role = requirement["instance_type"]
        n_instances_needed = requirement["n_required"]
        instances_to_assign, rest = instance_type_to_instance_map[instance_type_for_role][:n_instances_needed], instance_type_to_instance_map[instance_type_for_role][n_instances_needed:]
        instance_type_to_instance_map[instance_type_for_role] = rest
        machine_assignments[role] = instances_to_assign

    # Construct the host strings necessary for running the inception command.
    # Note we use private ip addresses to avoid EC2 transfer costs.
    worker_host_string = ",".join([x.private_ip_address+":"+str(port) for x in machine_assignments["master"] + machine_assignments["worker"]])
    ps_host_string = ",".join([x.private_ip_address+":"+str(port) for x in machine_assignments["ps"]])

    # Create a map of command&machine assignments
    command_machine_assignments = {}

    # TODO: Make all the commands much easier to parse / modify (refactor it).
    # Construct the inception command
    run_inception_command = "./bazel-bin/inception/%s_distributed_train  --batch_size=%s --train_dir=%s/train_dir --data_dir=./data/ --worker_hosts='%s' --ps_hosts='%s' --task_id=%s --job_name='%s' > %s/out_%s 2>&1 &"
    params = (configuration["dataset"], batch_size, configuration["nfs_mount_point"], worker_host_string, ps_host_string, 0, "worker", configuration["nfs_mount_point"], "master")
    command_machine_assignments["master"] = {"instance" : machine_assignments["master"][0], "command" : run_inception_command % params}
    for worker_id, instance in enumerate(machine_assignments["worker"]):
        name = "worker_%d" % worker_id
        params = (configuration["dataset"], batch_size, configuration["nfs_mount_point"], worker_host_string, ps_host_string, worker_id+1, "worker", configuration["nfs_mount_point"], name)
        command_machine_assignments[name] = {"instance" : instance, "command" : run_inception_command % params}
    for ps_id, instance in enumerate(machine_assignments["ps"]):
        name = "ps_%d" % ps_id
        params = (configuration["dataset"], batch_size, configuration["nfs_mount_point"], worker_host_string, ps_host_string, ps_id, "ps", configuration["nfs_mount_point"], name)
        command_machine_assignments[name] = {"instance" : instance, "command" : run_inception_command % params}

    # The evaluator requires a special command to continually evaluate accuracy on validation data.
    # We also launch the tensorboard on it.
    assert(len(machine_assignments["evaluator"]) == 1)
    evaluator_run_command = "{ bazel-bin/inception/%s_eval --num_examples=%d --data_dir=./data/  --checkpoint_dir=%s/train_dir --eval_dir=%s/%s_eval > %s/out_%s 2>&1 & }"
    evaluator_run_command = evaluator_run_command % (configuration["dataset"], configuration["num_validation_examples"], configuration["nfs_mount_point"], configuration["nfs_mount_point"], configuration["dataset"], configuration["nfs_mount_point"], "evaluator")
    evaluator_board_command = "{ python /usr/local/lib/python2.7/dist-packages/tensorflow/tensorboard/tensorboard.py --logdir=%s/%s_eval/ > %s/out_%s 2>&1 & }"
    evaluator_board_command = evaluator_board_command % (configuration["nfs_mount_point"], configuration["dataset"], configuration["nfs_mount_point"], "evaluator_tensorboard")
    evaluator_command = " && ".join([evaluator_run_command, evaluator_board_command])
    command_machine_assignments["evaluator"] = {"instance" : machine_assignments["evaluator"][0],
                                                "command" : evaluator_command}

    # Other useful commands such as pulling from the github directory, etc
    base_commands = ["cd models",
                     "cd inception",
                     "git fetch && git reset --hard origin/master",
                     "bazel build //...",
                     "rm -rf timeline*",
                     "rm -rf out*",
                     "mkdir timelines"]

    # Run the commands via ssh in parallel
    threads = []
    q = Queue.Queue()
    for name, command_and_machine in command_machine_assignments.items():
        instance = command_and_machine["instance"]
        commands = base_commands + [command_and_machine["command"]]
        print("-----------------------")
        print("Command: %s\n" % " ".join(commands))
        t = threading.Thread(target=run_ssh_commands_parallel, args=(instance, commands, q))
        t.start()
        threads.append(t)

    # Wait until commands are all finished
    for t in threads:
        t.join()

    # Print the output
    while not q.empty():
        instance, output = q.get()
        print(instance.public_ip_address)
        print(output)

    # Debug print
    instances = []
    print("\n--------------------------------------------------\n")
    print("Machine assignments:")
    print("------------------------")
    for name, command_and_machine in command_machine_assignments.items():
        instance = command_and_machine["instance"]
        instances.append(instance)
        commands = base_commands + [command_and_machine["command"]]
        ssh_command = "ssh -i %s %s@%s" % (configuration["path_to_keyfile"], configuration["ssh_username"], instance.public_ip_address)
        print("%s - %s" % (name, instance.instance_id))
        print("To ssh: %s" % ssh_command)
        print("------------------------")

    # Print out list of instance ids (which will be useful in selctively stopping inception
    # for given instances.
    instance_cluster_string = ",".join([x.instance_id for x in instances])
    print("\nInstances cluster string: %s" % instance_cluster_string)

def kill_inception(argv):
    if len(argv) != 3:
        print("Usage: python inception_ec2.py kill_inception instance_id1,instance_id2,id3...")
        sys.exit(0)
    cluster_instance_string = argv[2]
    instance_ids_to_shutdown = cluster_instance_string.split(",")

    live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    threads = []
    q = Queue.Queue()
    for instance in live_instances:
        if instance.instance_id in instance_ids_to_shutdown:
            commands = ["pkill -9 python"]
            t = threading.Thread(target=run_ssh_commands_parallel, args=(instance, commands, q))
            t.start()
            threads.append(t)
    for thread in threads:
        thread.join()
    summarize_idle_instances(None)

def kill_all_inception(argv):
    live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    threads = []
    q = Queue.Queue()
    for instance in live_instances:
        commands = ["pkill -9 python"]
        t = threading.Thread(target=run_ssh_commands_parallel, args=(instance, commands, q))
        t.start()
        threads.append(t)
    for thread in threads:
        thread.join()
    summarize_idle_instances(None)

def run_command(argv, quiet=False):
    if len(argv) != 4:
        print("Usage: python inception_ec2.py run_command instance_id1,instance_id2,id3... command")
        sys.exit(0)
    cluster_instance_string = argv[2]
    command = argv[3]
    instance_ids_to_run_command = cluster_instance_string.split(",")

    live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    threads = []
    q = Queue.Queue()
    for instance in live_instances:
        if instance.instance_id in instance_ids_to_run_command:
            commands = [command]
            t = threading.Thread(target=run_ssh_commands_parallel, args=(instance, commands, q))
            t.start()
            threads.append(t)
    for thread in threads:
        thread.join()

    while not q.empty():
        instance, output = q.get()
        if not quiet:
            print(instance, output)

# Setup nfs on all instances
def setup_nfs():
    print("Installing nfs on all running instances...")
    live_instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    live_instances_string = ",".join([x.instance_id for x in live_instances])
    update_command = "sudo apt-get -y update"
    install_nfs_command = "sudo apt-get -y install nfs-common"
    create_mount_command = "mkdir %s" % configuration["nfs_mount_point"]
    setup_nfs_command = "sudo mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 %s:/ %s" % (configuration["nfs_ip_address"], configuration["nfs_mount_point"])
    reduce_permissions_command = "sudo chmod 777 %s " % configuration["nfs_mount_point"]
    command = update_command + " && " + install_nfs_command + " && " + create_mount_command + " && " + setup_nfs_command + " && " + reduce_permissions_command

    # pretty hackish
    argv = ["python", "inception_ec2.py", live_instances_string, command]
    run_command(argv, quiet=True)

# Launch instances as specified by the configuration.
# We also want a shared filesystem to write model checkpoints.
# For simplicity we will have the user specify the filesystem via the config.
def launch(argv):
    launch_instances()
    wait_until_instance_request_status_fulfilled()
    wait_until_running_instances_initialized()
    setup_nfs()

def clean_launch_and_run(argv):
    # 1. Kills all instances in region
    # 2. Kills all requests in region
    # 3. Launches requests
    # 5. Waits until launch requests have all been satisfied,
    #    printing status outputs in the meanwhile
    # 4. Checks that configuration has been satisfied
    # 5. Runs inception
    shut_everything_down(None)
    launch(None)
    run_inception(None)

def help(hmap):
    print("Usage: python inception_ec2.py [command]")
    print("Commands:")
    for k,v in hmap.items():
        print("%s - %s" % (k,v))

if __name__ == "__main__":
    command_map = {
        "launch" : launch,
        "clean_launch_and_run" : clean_launch_and_run,
        "shutdown" : shut_everything_down,
        "run_inception" : run_inception,
        "kill_all_inception" : kill_all_inception,
        "list_idle_instances" : summarize_idle_instances,
        "list_running_instances" : summarize_running_instances,
        "kill_inception" : kill_inception,
        "run_command" : run_command,
    }
    help_map = {
        "launch" : "Launch instances",
        "clean_launch_and_run" : "Shut everything down, launch instances, wait until requests fulfilled, check that configuration is fulfilled, and launch and run inception.",
        "shutdown" : "Shut everything down by cancelling all instance requests, and terminating all instances.",
        "list_idle_instances" : "Lists all idle instances. Idle instances are running instances not running tensorflow.",
        "list_running_instances" : "Lists all running instances.",
        "run_inception" : "Runs inception on idle instances.",
        "kill_all_inception" : "Kills python running inception training on ALL instances.",
        "kill_inception" : "Kills python running inception on instances indicated by instance id string separated by ',' (no spaces).",
        "run_command" : "Runs given command on instances selcted by instance id string, separated by ','.",
    }

    if len(sys.argv) < 2:
        help(help_map)
        sys.exit(0)

    command = sys.argv[1]
    command_map[command](sys.argv)
