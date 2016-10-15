region="us-west-2"
key_location=../../../DistributedSGD.pem
default_outfile_location="./outfiles"
outfile_location=${1:-$default_outfile_location}

echo ${outfile_location}
rm -rf ${outfile_location}
mkdir ${outfile_location}

ips=($(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region ${region} --query "Reservations[*].Instances[*].PublicIpAddress" --output text))
ips_string=$(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --region ${region} --query "Reservations[*].Instances[*].PublicIpAddress" --output text)
n_hosts=${#ips[@]}
start=0
echo "Running machines: ${ips_string}"

index=0
for ip in ${ips[@]}; do
    echo $ip

    # Terminate python
    ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip} "bash -s" <<EOF
pkill python
EOF
    # Collect the outputs
    scp -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip}:~/models/inception/out* ${outfile_location}
    index=$((index+1))
done
