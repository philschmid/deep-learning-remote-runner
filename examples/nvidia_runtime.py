from rm_runner import EC2RemoteRunner


runner = EC2RemoteRunner(
    container="nvcr.io/nvidia/pytorch:22.06-py3", instance_type="p3.8xlarge", profile="hf-sm", region="us-east-1"
)

runner.launch(command="nvidia-smi")
