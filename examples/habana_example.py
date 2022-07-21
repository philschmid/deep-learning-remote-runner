from rm_runner import EC2RemoteRunner

# create runner
runner = EC2RemoteRunner(instance_type="dl1.24xlarge", profile="hf-sm", region="us-east-1")

# launch my script
runner.launch(command="python3 habana.py", source_dir="scripts")
