##########################################################
# Set up N aws machines and run distributed tensorflow.  #
# WARNING: SHUTS DOWN ALL CURRENTLY RUNNING AWS MACHINES #
# WARNING: DOES NOT SHUT DOWN MACHINES AFTERWARD         #
##########################################################

# Usage: sh run_distributed.sh [machine_tier] [n_instances]

region="us-west-2" # Spot
availability_zone="us-west-2c" # Spot
#region="us-west-1" # On demand
#availability_zone="us-west-1a" # On demand

#image_id=ami-326b2352 # For us-west-1
image_id=ami-7a24fe1a # For us-west-2

spot_price=.2
default_machine_tier='m4.2xlarge'
machine_tier=${1:-$default_machine_tier}
default_n_instances=5
n_instances=${2:-$default_n_instances}
key_name=DistributedSGD

# Cancel all spot instance requests
pending_spot_requests="$(aws ec2 describe-spot-instance-requests --filters "Name=state,Values=open" --query "SpotInstanceRequests[*].SpotInstanceRequestId" --output text)"
active_spot_requests="$(aws ec2 describe-spot-instance-requests --filters "Name=state,Values=active" --query "SpotInstanceRequests[*].SpotInstanceRequestId" --output text)"
echo "Cancelling the following spot requests"
echo ${pending_spot_requests}
echo ${active_spot_requests}
aws ec2 cancel-spot-instance-requests --spot-instance-request-ids ${pending_spot_requests}
aws ec2 cancel-spot-instance-requests --spot-instance-request-ids ${active_spot_requests}

# Check for running instances and shut them down
running_instances=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region ${region} --query "Reservations[*].Instances[*].InstanceId" --output text))

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
	aws ec2 terminate-instances --region ${region} --instance-ids ${running_instance} > /dev/null
    done
    echo "Done. Continuing."
fi

# Check for pending instances and shut them down
pending_instances=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=pending" --region ${region} --query "Reservations[*].Instances[*].InstanceId" --output text))

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
	aws ec2 terminate-instances --region ${region} --instance-ids ${pending_instance} > /dev/null
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

# For on demand launching
#aws ec2 run-instances --region ${region} --image-id "${image_id}" --count "${n_instances}" --instance-type "${machine_tier}" --key-name "${key_name}" > /dev/null

# For spot instance launching
aws ec2 request-spot-instances --spot-price ${spot_price} --instance-count ${n_instances} --launch-specification "{\"KeyName\":\"DistributedSGD\",\"Placement\":{\"AvailabilityZone\":\"${availability_zone}\"},\"ImageId\":\"${image_id}\",\"InstanceType\":\"${machine_tier}\",\"SecurityGroups\":[\"default\"]}"

echo "Launched instances..."
echo "Waiting for launched instances to be ready..."

ips=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region ${region} --query "Reservations[*].Instances[*].PublicIpAddress" --output text))
while [ ${#ips[@]} -ne "${n_instances}" ]; do
    ips=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region ${region} --query "Reservations[*].Instances[*].PublicIpAddress" --output text))
    echo "${#ips[@]} Machines up..."
    sleep 5
done
