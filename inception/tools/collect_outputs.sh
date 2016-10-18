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
cd models/inception
echo ${index}
cat timeline_iter\=* > combined_timeline_${index}
tar -czf combined_timeline.tar.gz combined_timeline_${index}
EOF
    # Collect the outputs
    scp -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip}:~/models/inception/combined_timeline.tar.gz ${outfile_location}/combined_timeline${index}.tar.gz
    cd ${outfile_location}
    tar -xzf combined_timeline${index}.tar.gz
    rm -f combined_timeline${index}.tar.gz
    cd ..
    index=$((index+1))
done
