from rm_runner import EC2RemoteRunner


runner = EC2RemoteRunner(instance_type="dl1.24xlarge", profile="hf-sm", region="us-east-1")

runner.launch(command="hl-smi")
