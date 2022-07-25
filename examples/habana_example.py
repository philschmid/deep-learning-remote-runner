from rm_runner import EC2RemoteRunner
from huggingface_hub import HfFolder

# hyperparameters
hyperparameters = {
    "model_id": "distilbert-base-uncased",
    "dataset_id": "imdb",
    "save_repository_id": "distilbert-imdb-habana-remote-runner",
    "hf_hub_token": HfFolder.get_token(),  # need to be login in with `huggingface-cli login`
    "num_train_epochs": 3,
    "per_device_train_batch_size": 48,
    "per_device_eval_batch_size": 16,
}
hyperparameters_string = " ".join(f"--{key} {value}" for key, value in hyperparameters.items())

# create ec2 remote runner
runner = EC2RemoteRunner(instance_type="dl1.24xlarge", profile="hf-sm", region="us-east-1")

# launch my script with gaudi_spawn for distributed training
runner.launch(
    command=f"python3 gaudi_spawn.py --use_mpi --world_size=8  habana_text_classification.py {hyperparameters_string}",
    source_dir="scripts",
)
