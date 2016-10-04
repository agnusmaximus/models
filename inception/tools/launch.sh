##########################################################
# Set up N aws machines and run distributed tensorflow.  #
# WARNING: SHUTS DOWN ALL CURRENTLY RUNNING AWS MACHINES #
# WARNING: DOES NOT SHUT DOWN MACHINES AFTERWARD         #
##########################################################

# Usage: sh run_distributed.sh [machine_tier] [n_instances]

image_id=ami-57470e37
default_machine_tier='t2.small'
machine_tier=${1:-$default_machine_tier}
default_n_instances=5
n_instances=${2:-$default_n_instances}
key_name=DistributedSGD

# Check for running instances
running_instances=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].InstanceId" --output text))

if [ ${#running_instances[@]} == 0 ]; then
    echo "No running ec2 instances... continuing"
else
    echo "Currently running ${#running_instances[@]} instances... Need to shut them down"

    # Should we continue to launch even though there are existing instances?
    read -r -p "Are you sure? [y/N] " response
    if [[ ! $response =~ ^[yY]$ ]]
    then
	exit 1
    fi

    for running_instance in ${running_instances[@]}; do
	echo "Terminating ${running_instance}..."
	aws ec2 terminate-instances --region us-west-1 --instance-ids ${running_instance} > /dev/null
    done
    echo "Done. Continuing."
fi

# Check for pending instances
pending_instances=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=pending" --region us-west-1 --query "Reservations[*].Instances[*].InstanceId" --output text))

if [ ${#pending_instances[@]} == 0 ]; then
    echo "No pending ec2 instances... continuing"
else
    echo "Currently pending ${#pending_instances[@]} instances... Need to shut them down"

    # Should we continue to launch even though there are existing instances?
    read -r -p "Are you sure? [y/N] " response
    if [[ ! $response =~ ^[yY]$ ]]
    then
	exit 1
    fi

    for pending_instance in ${pending_instances[@]}; do
	echo "Terminating ${pending_instance}..."
	aws ec2 terminate-instances --region us-west-1 --instance-ids ${pending_instance} > /dev/null
    done
    echo "Done. Continuing."
fi

echo
echo "Starting AWS cluster..."
echo "-----------------------"
echo "image_id=${image_id}"
echo "machine_tier=${machine_tier}"
echo "n_instances=${n_instances}"
echo

# Prompt correctness
read -r -p "Are you sure? [y/N] " response
if [[ ! $response =~ ^[Yy]$ ]]
then
    exit 1
fi

# Launch machines and wait for them to be ready
aws ec2 run-instances --region us-west-1 --image-id "${image_id}" --count "${n_instances}" --instance-type "${machine_tier}" --key-name "${key_name}" > /dev/null
echo "Launched instances..."
echo "Waiting for launched instances to be ready..."

ips=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].PublicIpAddress" --output text))
while [ ${#ips[@]} -ne "${n_instances}" ]; do
    ips=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].PublicIpAddress" --output text))
    echo "${#ips[@]} Machines up..."
    sleep 5
done
