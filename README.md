# Remote Runner 

Run python scripts easily on ec2 instances via ssh and scp.

## Habana Gaudi example

```python
from rm_runner import RemoteRunner

runner = RemoteRunner(instance_type="dl1.24xlarge", profile="hf-sm", region="us-east-1")

runner.launch(command="hl-smi")
```