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

for ip in ${ips[@]}; do
    echo $ip

    # Terminate python and zip the timelines
    ssh -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip} "bash -s" <<EOF
pkill python
cd models/inception
tar -czf timelines.tar.gz timelines
EOF
    # Collect the outputs
    scp -oStrictHostKeyChecking=no -oUserKnownHostsFile=/dev/null -i ${key_location} ubuntu@${ip}:~/models/inception/timelines.tar.gz ${outfile_location}/timelines.tar.gz
    cd ${outfile_location}
    tar -xzf timelines.tar.gz
    mv timelines/* .
    rm -f timelines.tar.gz
    rm -rf timelines
    cd ..
done
