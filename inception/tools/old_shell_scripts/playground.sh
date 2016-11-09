#!/bin/bash

# We assume num PS = 1
# sh ./tools/run_distributed.sh batch_size
region="us-west-2"
default_batch_size=1
batch_size=${1:-$default_batch_size}
key_location=../../DistributedSGD.pem

public_private_ips_string="$(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region ${region} --query "Reservations[*].Instances[*].[PrivateIpAddress,PublicIpAddress]" --output text)"

echo "Private Public Ips"
echo ${public_private_ips_string}

# Run tensorflow on running aws machines.
ips=($(echo ${public_private_ips_string} | awk -F' ' '{ for (i=2;i<=NF;i+=2) print $i }'))
echo "Public Ips"
echo ${ips}
n_hosts=${#ips[@]}

for ip in ${ips[@]}; do
    echo $ip
    ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip} "bash -s" <<EOF
cd models
cd inception
more out* | grep "stragg" | wc -l
EOF
done
