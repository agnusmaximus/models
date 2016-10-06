# We assume num PS = 1
# sh ./tools/run_distributed.sh

key_location=../../DistributedSGD.pem

# Run tensorflow on running aws machines.
ips=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].PublicIpAddress" --output text))
ips_string=$(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].PublicIpAddress" --output text)
n_hosts=${#ips[@]}
start=0
echo "Running machines: ${ips_string}"

private_ips_string=$(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region us-west-1 --query "Reservations[*].Instances[*].PrivateIpAddress" --output text)
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
    echo "bazel-bin/inception/imagenet_train --batch_size=1 --train_dir=/tmp/imagenet_train --data_dir=./data/ --worker_hosts='${worker_hosts}' --ps_hosts='${ps_hosts}' --task_id=${worker_id} --job_name='${node_type}'"
    tf_command[$i]="./bazel-bin/inception/imagenet_distributed_train --batch_size=1 --train_dir=/tmp/imagenet_train --data_dir=./data/ --worker_hosts='${worker_hosts}' --ps_hosts='${ps_hosts}' --task_id=${worker_id} --job_name='${node_type}'"
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
