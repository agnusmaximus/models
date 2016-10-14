#!/bin/bash

# We assume num PS = 1
# sh ./tools/run_distributed.sh batch_size
default_batch_size=1
batch_size=${1:-$default_batch_size}
key_location=../../DistributedSGD.pem

count_public_private_ips=$(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].[PrivateIpAddress,PublicIpAddress]" --output text)
count=${#count_public_private_ips[@]}
public_private_ips_string="$(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].[PrivateIpAddress,PublicIpAddress]" --output text)"

echo "Private Public Ips"
echo ${public_private_ips_string}

# Run tensorflow on running aws machines.
ips=($(echo ${public_private_ips_string} | awk -F' ' '{ for (i=2;i<=NF;i+=2) print $i }'))
echo "Public Ips"
echo ${ips}
n_hosts=${#ips[@]}

private_ips=$(echo ${public_private_ips_string} | awk -F' ' '{ for (i=1;i<=NF;i+=2) print $i }')
private_ips_string="$(echo ${private_ips})"
echo "Private Ips"
echo ${private_ips}

worker_hosts=$(python ./tools/extract_workers_ps.py workers ${private_ips_string})
ps_hosts=$(python ./tools/extract_workers_ps.py ps ${private_ips_string})
echo ${worker_hosts}
echo ${ps_hosts}

# Create the tensorflow run command.
tf_command=()
for ((i=0; i<n_hosts; i++)); do
    worker_id=$(($i % $((n_hosts-1))));
    if (( $i <= $((n_hosts-2)) ));
    then
	node_type="worker"
    else
	node_type="ps"
    fi

    echo "Machine ${i} has id ${worker_id} and type ${node_type}"
    echo "bazel-bin/inception/imagenet_train --batch_size=${batch_size} --train_dir=/tmp/imagenet_train --data_dir=./data/ --worker_hosts='${worker_hosts}' --ps_hosts='${ps_hosts}' --task_id=${worker_id} --job_name='${node_type}'"
    tf_command[$i]="./bazel-bin/inception/imagenet_distributed_train --input_queue_memory_factor=1 --batch_size=${batch_size} --train_dir=/tmp/imagenet_train --data_dir=./data/ --worker_hosts='${worker_hosts}' --ps_hosts='${ps_hosts}' --task_id=${worker_id} --job_name='${node_type}'"
done

# Loop through, ssh, and run command. Indentation messed up... :(
index=0
for ip in ${ips[@]}; do
    echo $ip
    echo ${tf_command[$index]}
    ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip} "bash -s" <<EOF
pkill python
cd models
cd inception
rm -f out*
git fetch && git reset --hard origin/master
rm -rf /tmp/imagenet_train
${tf_command[$index]} > out${index} 2>&1 &
EOF
    index=$((index+1))
done
