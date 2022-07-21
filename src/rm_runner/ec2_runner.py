import io
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional, Union

import paramiko
from boto3.session import Session
from scp import SCPClient

from nanoid import generate

from rm_runner.utils import get_price_for_instance_with_seconds


logger = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

# TODO: keyboar InterruptedError


def get_ami_id_for_region_and_instance_type(instance_type: str, ec2_client: Any) -> str:
    if "dl1" in instance_type:
        name = "Deep Learning AMI Habana"
    elif "p" in instance_type or "g" in instance_type:
        name = "Deep Learning AMI GPU"
    else:
        return "Deep Learning AMI GPU"
    return ec2_client.describe_images(
        Owners=["amazon"],
        Filters=[
            {
                "Name": "name",
                "Values": [
                    f"*{name}*Ubuntu 20.04*",
                ],
            },
        ],
    )["Images"][0]["ImageId"]


class EC2RemoteRunner:
    """
    Set up cloud infrastructure and run scripts.
    """

    def __init__(
        self,
        run_name: Optional[str] = f"rm-runner-{generate('abcdefghijklm', 4)}",
        instance_type: str = "t3.micro",
        container: str = "vault.habana.ai/gaudi-docker/1.4.1/ubuntu20.04/habanalabs/pytorch-installer-1.10.2:1.4.1-11",
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> None:
        self.session = Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
            region_name=region,
            profile_name=profile,
        )
        self.region = region
        self.ec2_client = self.session.client("ec2")
        self.ec2_resource = self.session.resource("ec2")
        self.run_name = run_name
        self.instance_type = instance_type
        self.container = container
        self.ami_id = get_ami_id_for_region_and_instance_type(instance_type, self.ec2_client)
        self.runtime_args = self._get_runtime_args_from_instance_type(instance_type)

    def _start(self) -> None:
        key = self._create_ec2_key_pair()
        sg_id = self._create_ec2_security_group_with_ssh_ingress()
        instance_id = self._run_ec2_instance(
            ami_id=self.ami_id, instance_type=self.instance_type, key_name=self.run_name, sg_id=sg_id
        )
        self.instance = self.ec2_resource.Instance(id=instance_id)
        logger.info(f"Waiting for instance to be ready...")
        self.instance.wait_until_running()
        public_dns = self.instance.public_dns_name
        logger.info(f"Instance is ready. Public DNS: {public_dns}")
        self.ssh_client = self._setup_ssh_connection(key=key, instance_dns=public_dns)
        logger.info(f"Pulling container: {self.container}...")
        # TODO: check why it is not loaded with lower tier instance
        stdin, stdout, stderr = self.ssh_client.exec_command(
            f"docker pull {self.container}",
        )
        logger.debug(stdout.read().decode())

    def _exec_command(
        self, command: Optional[str], source_dir: Union[Path, str] = None, runtime_args: Optional[str] = None
    ) -> str:
        # read script and move to remote
        exec_source_dir = source_dir if source_dir else "/home/ubuntu"
        runtime_args = runtime_args if runtime_args else self.runtime_args

        full_command = " ".join(
            [
                "docker run",
                runtime_args,
                "--cap-add=sys_nice --net=host --ipc=host",
                f"-v {exec_source_dir}:/home/ubuntu/rm-runner --workdir=/home/ubuntu/rm-runner",
                f"{self.container}",
                f"{command}",
            ]
        )
        logger.info(f"Executing: {full_command}")

        stdin, stdout, stderr = self.ssh_client.exec_command(
            full_command,
            get_pty=True,
        )
        while True:
            out = stdout.channel.recv(1024)
            if not out:
                break
            sys.stdout.write(out.decode())
            sys.stdout.flush()

    def _upload_data(self, source_dir: Union[Path, str]) -> None:
        if isinstance(source_dir, str):
            source_dir = Path(source_dir)
        remote_path = "/home/ubuntu/test"
        logger.info(f"Uploading from {source_dir}")
        with SCPClient(self.ssh_clientssh.get_transport()) as scp:
            scp.put(source_dir.absolute(), recursive=True, remote_path=remote_path)
        return remote_path

    def _stop(self) -> None:
        # termiante ec2 instances
        logger.info(f"Terminating instance: {self.instance.id}")
        self.instance.terminate()
        # wait for ec2 instances to be terminated
        self.instance.wait_until_terminated()
        # delete sg
        logger.info(f"Deleting security group: {self.run_name}")
        self.ec2_client.delete_security_group(GroupName=self.run_name)
        # delete key
        logger.info(f"Deleting key: {self.run_name}")
        self.ec2_client.delete_key_pair(KeyName=self.run_name)

    def launch(
        self, command: Optional[str], source_dir: Union[Path, str] = None, runtime_args: Optional[str] = None
    ) -> None:
        start_time = time.time()
        # create ec2
        self._start()
        startup_time = round(time.time() - start_time)
        # launch
        try:
            if source_dir:
                source_dir = self._upload_data(source_dir)
            self._exec_command(source_dir=source_dir, command=command, runtime_args=runtime_args)
            exec_time = round(time.time() - startup_time - start_time)
        except Exception as e:
            logger.error(e)
            self._stop()
            raise e

        # stop
        self._stop()
        terminate_time = round(time.time() - exec_time - startup_time - start_time)
        total_time = round(time.time() - start_time)
        estimated_cost = get_price_for_instance_with_seconds(
            duration=total_time - terminate_time,
            region=self.region,
            instance_type=self.instance_type,
            session=self.session,
        )
        logger.info(f"Total time:       {total_time}s")
        logger.info(f"Startup time:     {startup_time}s")
        logger.info(f"Execution time:   {exec_time}s")
        logger.info(f"Termination time: {terminate_time}s")
        logger.info(f"Estimated cost:  ${estimated_cost}")
        return {
            "total_time": total_time,
            "startup_time": startup_time,
            "exec_time": exec_time,
            "terminate_time": terminate_time,
            "estimated_cost": estimated_cost,
        }

    def _create_ec2_key_pair(self) -> str:
        try:
            key = self.ec2_client.create_key_pair(KeyName=self.run_name)["KeyMaterial"]
        except Exception as e:
            if "Duplicate" in str(e):
                self.ec2_client.delete_key_pair(KeyName=self.run_name)
                key = self.ec2_client2.create_key_pair(KeyName=self.run_name)["KeyMaterial"]
            else:
                raise e
        logger.info(f"Created key pair: {self.run_name}")
        return key

    def _create_ec2_security_group_with_ssh_ingress(self) -> str:
        try:
            sg_id = self.ec2_client.create_security_group(
                GroupName=self.run_name, Description="rm-runner only allow SSH traffic"
            )["GroupId"]
        except Exception as e:
            if "Duplicate" in str(e):
                self.ec2_client.delete_security_group(GroupName=self.run_name)
                sg_id = self.ec2_client.create_security_group(
                    GroupName=self.run_name, Description="rm-runner only allow SSH traffic"
                )["GroupId"]
            else:
                raise e
        finally:
            self.ec2_client.authorize_security_group_ingress(
                GroupId=sg_id, IpProtocol="tcp", CidrIp="0.0.0.0/0", FromPort=22, ToPort=22
            )
        logger.info(f"Created security group: {self.run_name}")
        return sg_id

    def _run_ec2_instance(
        self, ami_id="ami-06d20e48ee8d06029", instance_type="t3.micro", sg_id=None, key_name=None, volume_size=150
    ):
        instance = self.ec2_client.run_instances(
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {"DeleteOnTermination": True, "VolumeSize": volume_size, "VolumeType": "gp2"},
                },
            ],
            ImageId=ami_id,
            InstanceType=instance_type,
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[sg_id],
            KeyName=key_name,
            # tag for name
        )
        logger.info(f"Launched instance: {instance['Instances'][0]['InstanceId']}")
        return instance["Instances"][0]["InstanceId"]

    def _setup_ssh_connection(self, key: str, instance_dns: str) -> paramiko.SSHClient:
        #         @staticmethod
        # @contextmanager
        # def _connect_ssh_context(host, username, password, load_host_keys=True):
        #     try:
        #         ssh = paramiko.SSHClient()
        #         if load_host_keys:
        #             ssh.load_host_keys(os.path.expanduser("~/.ssh/known_hosts"))
        #         ssh.connect(host, username=username, password=password)
        #         yield ssh
        #     finally:
        #         ssh.close()

        key = paramiko.RSAKey.from_private_key(io.StringIO(key))
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        t0 = 0
        while t0 < 10:
            try:
                logger.info(f"Setting up ssh connection...")
                ssh.connect(instance_dns, username="ubuntu", pkey=key)
                break
            except Exception:
                t0 += 1
                time.sleep(5)
        return ssh

    def _get_runtime_args_from_instance_type(self, instance_type):
        if "dl1" in instance_type:
            return "--runtime=habana -e HABANA_VISIBLE_DEVICES=all -e OMPI_MCA_btl_vader_single_copy_mechanism=none"
        elif "p" in instance_type or "g" in instance_type:
            return "--gpus all"
        else:
            return ""
