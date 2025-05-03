import time
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, WaiterError
from scripts.utils import get_client, get_resource, logger, handle_error, wait_with_progress
from config import settings

class EC2Manager:
    def __init__(self):
        self.ec2_client = get_client('ec2')
        self.ec2_resource = get_resource('ec2')
        self.cloudwatch_client = get_client('cloudwatch')
        self.operation_metrics = {
            'launch_instance': 'EC2InstanceLaunch',
            'start_instance': 'EC2InstanceStart',
            'stop_instance': 'EC2InstanceStop',
            'reboot_instance': 'EC2InstanceReboot',
            'create_volume': 'EBSVolumeCreate',
            'attach_volume': 'EBSVolumeAttach',
            'create_snapshot': 'EBSSnapshotCreate'
        }
        
    def _log_operation_metric(self, operation: str, success: bool, duration: float, 
                            dimensions: Optional[Dict[str, str]] = None) -> None:
        """
        Log operation metrics to CloudWatch
        
        Args:
            operation: The operation being performed
            success: Whether the operation was successful
            duration: Duration of the operation in seconds
            dimensions: Additional dimensions for the metric
        """
        try:
            metric_name = self.operation_metrics.get(operation, operation)
            dimensions = dimensions or {}
            
            # Add common dimensions
            dimensions.update({
                'Operation': operation,
                'Success': str(success).lower()
            })
            
            # Put metric data
            self.cloudwatch_client.put_metric_data(
                Namespace='AWS/EC2Manager',
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Dimensions': [{'Name': k, 'Value': v} for k, v in dimensions.items()],
                        'Value': duration,
                        'Unit': 'Seconds',
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Failed to log CloudWatch metric: {str(e)}")
            
    def _log_performance_metrics(self, operation: str, start_time: float, 
                               additional_info: Optional[Dict[str, Any]] = None) -> None:
        """
        Log performance metrics for an operation
        
        Args:
            operation: The operation being performed
            start_time: Start time of the operation
            additional_info: Additional information to log
        """
        duration = time.time() - start_time
        logger.info(f"Operation {operation} completed in {duration:.2f} seconds")
        
        if additional_info:
            logger.info(f"Additional metrics for {operation}: {additional_info}")
            
        # Log to CloudWatch
        self._log_operation_metric(operation, True, duration, additional_info)
        
    def validate_instance_type(self, instance_type: str) -> bool:
        """Validate if the instance type is supported"""
        try:
            response = self.ec2_client.describe_instance_types(
                InstanceTypes=[instance_type]
            )
            return len(response['InstanceTypes']) > 0
        except ClientError:
            return False

    def launch_instance(self, 
                       ami_id: str = settings.EC2_AMI_ID, 
                       instance_type: str = settings.EC2_INSTANCE_TYPE,
                       key_name: str = settings.EC2_KEY_NAME,
                       profile_name: str = settings.IAM_INSTANCE_PROFILE_NAME,
                       security_group_ids: Optional[List[str]] = None,
                       subnet_id: Optional[str] = None) -> Optional[Any]:
        """
        Launch a new EC2 instance with encrypted root volume
        
        Args:
            ami_id: The AMI ID to use for the instance
            instance_type: The instance type (e.g., t2.micro)
            key_name: The name of the key pair
            profile_name: The IAM instance profile name
            security_group_ids: List of security group IDs
            subnet_id: The subnet ID to launch the instance in
            
        Returns:
            The created instance object or None if failed
        """
        start_time = time.time()
        operation = 'launch_instance'
        logger.info(f"Starting {operation} with AMI: {ami_id}, Type: {instance_type}")
        
        if not self.validate_instance_type(instance_type):
            logger.error(f"Invalid instance type: {instance_type}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
            
        try:
            instance_params = {
                'ImageId': ami_id,
                'MinCount': 1,
                'MaxCount': 1,
                'InstanceType': instance_type,
                'KeyName': key_name,
                'IamInstanceProfile': {'Name': profile_name},
                'BlockDeviceMappings': [
                    {
                        'DeviceName': '/dev/xvda',
                        'Ebs': {
                            'VolumeSize': settings.EBS_VOLUME_SIZE,
                            'DeleteOnTermination': True,
                            'VolumeType': settings.EBS_VOLUME_TYPE,
                            'Encrypted': True
                        }
                    }
                ]
            }
            
            if security_group_ids:
                instance_params['SecurityGroupIds'] = security_group_ids
            if subnet_id:
                instance_params['SubnetId'] = subnet_id
            
            instances = self.ec2_resource.create_instances(**instance_params)
            instance = instances[0]
            
            logger.info(f"Instance {instance.id} created. Waiting for running state...")
            instance.wait_until_running()
            instance.reload()
            
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'InstanceId': instance.id,
                    'InstanceType': instance_type,
                    'AMI': ami_id
                }
            )
            
            logger.info(f"Instance {instance.id} is running with public IP: {instance.public_ip_address}")
            return instance
            
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to launch instance: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
        except Exception as e:
            logger.error(f"Unexpected error launching instance: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
            
    def create_and_attach_volume(self, instance: Any) -> Optional[Any]:
        """
        Create an EBS volume and attach it to the instance
        
        Args:
            instance: The EC2 instance object to attach the volume to
            
        Returns:
            The created volume object or None if failed
        """
        start_time = time.time()
        operation = 'create_and_attach_volume'
        
        if not instance:
            logger.error("No instance provided to attach volume to")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
            
        if not hasattr(instance, 'id'):
            logger.error("Invalid instance object provided")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
            
        logger.info(f"Starting {operation} for instance {instance.id}")
        
        try:
            # Validate instance state
            instance.reload()
            if instance.state['Name'] != 'running':
                logger.error(f"Instance {instance.id} is not in running state")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return None
            
            # Create volume in the same AZ as the instance
            volume = self.ec2_resource.create_volume(
                AvailabilityZone=instance.placement['AvailabilityZone'],
                Size=settings.EBS_VOLUME_SIZE,
                VolumeType=settings.EBS_VOLUME_TYPE,
                Encrypted=True,
                TagSpecifications=[
                    {
                        'ResourceType': 'volume',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': f'Volume for {instance.id}'
                            }
                        ]
                    }
                ]
            )
            
            logger.info(f"Volume {volume.id} created. Waiting for it to become available...")
            
            # Wait for volume to be available with timeout
            try:
                self.ec2_client.get_waiter('volume_available').wait(
                    VolumeIds=[volume.id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}  # 1 minute timeout
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for volume {volume.id} to become available")
                # Clean up the volume
                self.delete_volume(volume.id)
                self._log_operation_metric(operation, False, time.time() - start_time)
                return None
            
            # Attach the volume
            logger.info(f"Attaching volume {volume.id} to instance {instance.id}")
            attachment = volume.attach_to_instance(
                InstanceId=instance.id,
                Device='/dev/sdf'
            )
            
            # Wait for attachment to complete
            time.sleep(5)  # Give some time for the attachment to complete
            
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'InstanceId': instance.id,
                    'VolumeId': volume.id,
                    'VolumeSize': settings.EBS_VOLUME_SIZE,
                    'VolumeType': settings.EBS_VOLUME_TYPE
                }
            )
            
            logger.info(f"Volume attached: {attachment}")
            return volume
            
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to create/attach volume: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating/attaching volume: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None

    def create_snapshot(self, volume: Any) -> Optional[Any]:
        """
        Create a snapshot of the volume
        """
        start_time = time.time()
        operation = 'create_snapshot'
        
        if not volume:
            logger.error("No volume provided to create snapshot from")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
            
        if not hasattr(volume, 'id'):
            logger.error("Invalid volume object provided")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
            
        logger.info(f"Starting {operation} for volume {volume.id}")
        
        try:
            volume.reload()
            if volume.state != 'in-use':
                logger.error(f"Volume {volume.id} is not in use")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return None
            
            snapshot = volume.create_snapshot(
                Description=f"Backup snapshot for volume {volume.id}",
                TagSpecifications=[
                    {
                        'ResourceType': 'snapshot',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': f'Snapshot of {volume.id}'
                            }
                        ]
                    }
                ]
            )
            
            # Wait for snapshot to complete
            try:
                self.ec2_client.get_waiter('snapshot_completed').wait(
                    SnapshotIds=[snapshot.id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for snapshot {snapshot.id} to complete")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return None
                
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'VolumeId': volume.id,
                    'SnapshotId': snapshot.id,
                    'VolumeSize': volume.size,
                    'VolumeType': volume.volume_type
                }
            )
            
            return snapshot
            
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to create snapshot: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating snapshot: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None

    def start_instance(self, instance_id: str) -> bool:
        """
        Start an EC2 instance
        """
        start_time = time.time()
        operation = 'start_instance'
        logger.info(f"Starting {operation} for instance {instance_id}")

        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.reload()
            
            if instance.state['Name'] not in ['stopped', 'stopping']:
                logger.error(f"Instance {instance_id} is not in a stoppable state")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False

            response = self.ec2_client.start_instances(
                InstanceIds=[instance_id]
            )
            
            try:
                self.ec2_client.get_waiter('instance_running').wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for instance {instance_id} to start")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False
                
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'InstanceId': instance_id,
                    'InstanceType': instance.instance_type,
                    'PreviousState': instance.state['Name']
                }
            )
            
            return True

        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to start instance: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting instance: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False

    def stop_instance(self, instance_id: str) -> bool:
        """
        Stop an EC2 instance
        """
        start_time = time.time()
        operation = 'stop_instance'
        logger.info(f"Starting {operation} for instance {instance_id}")

        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.reload()
            
            if instance.state['Name'] not in ['running', 'pending']:
                logger.error(f"Instance {instance_id} is not in a stoppable state")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False

            response = self.ec2_client.stop_instances(
                InstanceIds=[instance_id]
            )

            try:
                self.ec2_client.get_waiter('instance_stopped').wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for instance {instance_id} to stop")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False
                
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'InstanceId': instance_id,
                    'InstanceType': instance.instance_type,
                    'PreviousState': instance.state['Name']
                }
            )
            
            return True

        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to stop instance: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error stopping instance: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False

    def reboot_instance(self, instance_id: str) -> bool:
        """
        Reboot an EC2 instance
        """
        start_time = time.time()
        operation = 'reboot_instance'
        logger.info(f"Starting {operation} for instance {instance_id}")

        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.reload()
            
            if instance.state['Name'] not in ['running']:
                logger.error(f"Instance {instance_id} is not in a rebootable state")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False

            response = self.ec2_client.reboot_instances(
                InstanceIds=[instance_id]
            )

            try:
                self.ec2_client.get_waiter('instance_running').wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for instance {instance_id} to reboot")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False
                
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'InstanceId': instance_id,
                    'InstanceType': instance.instance_type,
                    'PreviousState': instance.state['Name']
                }
            )
            
            return True

        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to reboot instance: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error rebooting instance: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False

    def describe_instance(self, instance_id):
        """Describe an EC2 instance"""
        logger.info(f"Describing EC2 instance {instance_id}")

        try:
            response = self.ec2_client.describe_instances(
                InstanceIds=[instance_id]
            )

            if response['Reservations'] and response['Reservations'][0]['Instances']:
                instance_details = response['Reservations'][0]['Instances'][0]
                logger.info(f"Instance {instance_id} details retrieved")
                return instance_details
            return None
        except Exception as e:
            handle_error(e, f"describing instance {instance_id}")
            return None

    def get_cloudwatch_metrics(self, instance_id: str) -> List[Dict[str, Any]]:
        """
        Get CloudWatch metrics for an EC2 instance
        
        Args:
            instance_id: The ID of the EC2 instance
            
        Returns:
            List of metric data points
        """
        try:
            # Get metrics for the last hour
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            
            response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5 minutes
                Statistics=['Average']
            )
            
            metrics = []
            for datapoint in response.get('Datapoints', []):
                metrics.append({
                    'MetricName': 'CPUUtilization',
                    'Value': datapoint['Average'],
                    'Unit': 'Percent',
                    'Timestamp': datapoint['Timestamp']
                })
                
            return metrics
            
        except Exception as e:
            handle_error(e, f"getting CloudWatch metrics for instance {instance_id}")
            return []

    def get_performance_metrics(self, instance_id: str) -> Dict[str, Any]:
        """
        Get performance metrics for an EC2 instance
        
        Args:
            instance_id: The ID of the EC2 instance
            
        Returns:
            Dictionary of performance metrics
        """
        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.reload()
            
            metrics = {
                'InstanceType': instance.instance_type,
                'State': instance.state['Name'],
                'LaunchTime': instance.launch_time,
                'PublicIP': instance.public_ip_address or 'N/A',
                'PrivateIP': instance.private_ip_address or 'N/A',
                'VPC': instance.vpc_id or 'N/A',
                'Subnet': instance.subnet_id or 'N/A',
                'SecurityGroups': ', '.join([sg['GroupName'] for sg in instance.security_groups])
            }
            
            return metrics
            
        except Exception as e:
            handle_error(e, f"getting performance metrics for instance {instance_id}")
            return {}

    def setup_cloudwatch_alarm(self, instance):
        """Set up a CloudWatch alarm for high CPU utilization"""
        if not instance:
            logger.error("No instance provided to set up CloudWatch alarm for")
            return False
            
        logger.info(f"Setting up CloudWatch alarm for instance {instance.id}")
        
        try:
            alarm_response = self.cloudwatch_client.put_metric_alarm(
                AlarmName=f"{settings.CLOUDWATCH_ALARM_NAME}-{instance.id}",
                ComparisonOperator='GreaterThanThreshold',
                EvaluationPeriods=1,
                MetricName='CPUUtilization',
                Namespace='AWS/EC2',
                Period=300,
                Statistic='Average',
                Threshold=settings.CLOUDWATCH_CPU_THRESHOLD,
                ActionsEnabled=False,
                AlarmDescription=f'Alarm when server CPU exceeds {settings.CLOUDWATCH_CPU_THRESHOLD}%',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': instance.id
                    },
                ]
            )
            
            logger.info(f"CloudWatch alarm created for instance {instance.id}")
            return True
            
        except Exception as e:
            handle_error(e, "setting up CloudWatch alarm")
            return False
            
    def list_instances(self, state=None):
        """List EC2 instances with optional state filter"""
        logger.info("Listing EC2 instances")
        
        filters = []
        if state:
            filters.append({'Name': 'instance-state-name', 'Values': [state]})
            
        try:
            instances = list(self.ec2_resource.instances.filter(Filters=filters))
            
            logger.info(f"Found {len(instances)} instances")
            return instances
            
        except Exception as e:
            handle_error(e, "listing EC2 instances")
            return []
            
    def list_volumes(self, instance_id: str) -> List[Dict[str, Any]]:
        """
        List volumes attached to an EC2 instance
        
        Args:
            instance_id: The ID of the EC2 instance
            
        Returns:
            List of volume information dictionaries
        """
        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.reload()
            
            volumes = []
            for block_device in instance.block_device_mappings:
                volume_id = block_device['Ebs']['VolumeId']
                volume = self.ec2_resource.Volume(volume_id)
                volume.reload()
                
                volumes.append({
                    'VolumeId': volume.id,
                    'State': volume.state,
                    'Size': volume.size,
                    'VolumeType': volume.volume_type,
                    'AvailabilityZone': volume.availability_zone,
                    'Device': block_device['DeviceName'],
                    'DeleteOnTermination': block_device['Ebs']['DeleteOnTermination']
                })
            
            logger.info(f"Found {len(volumes)} volumes attached to instance {instance_id}")
            return volumes
            
        except Exception as e:
            handle_error(e, f"listing volumes for instance {instance_id}")
            return []

    def describe_volume(self, volume_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a volume
        
        Args:
            volume_id: The ID of the volume
            
        Returns:
            Dictionary containing volume details or None if not found
        """
        try:
            volume = self.ec2_resource.Volume(volume_id)
            volume.reload()
            
            details = {
                'VolumeId': volume.id,
                'State': volume.state,
                'Size': volume.size,
                'VolumeType': volume.volume_type,
                'AvailabilityZone': volume.availability_zone,
                'Encrypted': volume.encrypted,
                'Iops': volume.iops,
                'Throughput': volume.throughput,
                'Tags': volume.tags,
                'Attachments': [
                    {
                        'InstanceId': attachment['InstanceId'],
                        'Device': attachment['Device'],
                        'State': attachment['State'],
                        'DeleteOnTermination': attachment['DeleteOnTermination']
                    }
                    for attachment in volume.attachments
                ]
            }
            
            logger.info(f"Retrieved details for volume {volume_id}")
            return details
            
        except Exception as e:
            handle_error(e, f"describing volume {volume_id}")
            return None

    def create_volume(self, size: int, volume_type: str, availability_zone: str, 
                     encrypted: bool = True, iops: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Create a new EBS volume
        
        Args:
            size: Size of the volume in GiB
            volume_type: Type of the volume (e.g., gp2, io1, etc.)
            availability_zone: The AZ to create the volume in
            encrypted: Whether to encrypt the volume
            iops: IOPS for io1/io2 volumes
            
        Returns:
            Dictionary containing volume details or None if failed
        """
        start_time = time.time()
        operation = 'create_volume'
        logger.info(f"Starting {operation} with size {size}GB, type {volume_type} in {availability_zone}")

        try:
            # Prepare volume parameters
            volume_params = {
                'AvailabilityZone': availability_zone,
                'Size': size,
                'VolumeType': volume_type,
                'Encrypted': encrypted,
                'TagSpecifications': [
                    {
                        'ResourceType': 'volume',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': f'Volume-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}'
                            }
                        ]
                    }
                ]
            }
            
            # Add IOPS if specified and volume type supports it
            if iops and volume_type in ['io1', 'io2']:
                volume_params['Iops'] = iops
                
            # Create the volume
            response = self.ec2_client.create_volume(**volume_params)
            volume_id = response['VolumeId']
            
            # Wait for volume to be available
            try:
                self.ec2_client.get_waiter('volume_available').wait(
                    VolumeIds=[volume_id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}  # 1 minute timeout
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for volume {volume_id} to become available")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return None
                
            # Get volume details
            volume = self.ec2_resource.Volume(volume_id)
            volume.reload()
            
            details = {
                'VolumeId': volume.id,
                'State': volume.state,
                'Size': volume.size,
                'VolumeType': volume.volume_type,
                'AvailabilityZone': volume.availability_zone,
                'Encrypted': volume.encrypted,
                'Iops': volume.iops,
                'Throughput': volume.throughput
            }
            
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'VolumeId': volume.id,
                    'VolumeSize': volume.size,
                    'VolumeType': volume.volume_type,
                    'AvailabilityZone': volume.availability_zone
                }
            )
            
            logger.info(f"Volume {volume_id} created successfully")
            return details
            
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to create volume: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating volume: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return None

    def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate an EC2 instance
        
        Args:
            instance_id: The ID of the instance to terminate
            
        Returns:
            bool: True if successful, False otherwise
        """
        start_time = time.time()
        operation = 'terminate_instance'
        logger.info(f"Starting {operation} for instance {instance_id}")

        try:
            instance = self.ec2_resource.Instance(instance_id)
            instance.reload()
            
            if instance.state['Name'] not in ['running', 'stopped']:
                logger.error(f"Instance {instance_id} is not in a terminable state")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False

            response = self.ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )
            
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'InstanceId': instance_id,
                    'InstanceType': instance.instance_type,
                    'PreviousState': instance.state['Name']
                }
            )
            
            logger.info(f"Instance {instance_id} termination initiated")
            return True
            
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to terminate instance: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error terminating instance: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False

    def delete_volume(self, volume_id: str) -> bool:
        """
        Delete an EBS volume
        """
        start_time = time.time()
        operation = 'delete_volume'
        logger.info(f"Starting {operation} for volume {volume_id}")

        try:
            volume = self.ec2_resource.Volume(volume_id)
            volume.reload()
            
            if volume.state != 'available':
                logger.error(f"Volume {volume_id} is not in available state")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False

            response = self.ec2_client.delete_volume(
                VolumeId=volume_id
            )

            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'VolumeId': volume_id,
                    'VolumeSize': volume.size,
                    'VolumeType': volume.volume_type
                }
            )

            return True

        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to delete volume: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting volume: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False

    def detach_volume(self, volume_id: str) -> bool:
        """
        Detach a volume from its instance
        
        Args:
            volume_id: The ID of the volume to detach
            
        Returns:
            bool: True if successful, False otherwise
        """
        start_time = time.time()
        operation = 'detach_volume'
        logger.info(f"Starting {operation} for volume {volume_id}")

        try:
            volume = self.ec2_resource.Volume(volume_id)
            volume.reload()
            
            if not volume.attachments:
                logger.error(f"Volume {volume_id} is not attached to any instance")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False
                
            attachment = volume.attachments[0]
            instance_id = attachment['InstanceId']
            
            # Detach the volume
            response = self.ec2_client.detach_volume(
                VolumeId=volume_id,
                InstanceId=instance_id,
                Device=attachment['Device']
            )
            
            # Wait for volume to be available
            try:
                self.ec2_client.get_waiter('volume_available').wait(
                    VolumeIds=[volume_id],
                    WaiterConfig={'Delay': 5, 'MaxAttempts': 12}  # 1 minute timeout
                )
            except WaiterError as e:
                logger.error(f"Timeout waiting for volume {volume_id} to become available")
                self._log_operation_metric(operation, False, time.time() - start_time)
                return False
                
            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'VolumeId': volume_id,
                    'InstanceId': instance_id,
                    'VolumeSize': volume.size,
                    'VolumeType': volume.volume_type
                }
            )
            
            logger.info(f"Volume {volume_id} detached from instance {instance_id}")
            return True
            
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to detach volume: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error detaching volume: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        Delete an EBS snapshot
        """
        start_time = time.time()
        operation = 'delete_snapshot'
        logger.info(f"Starting {operation} for snapshot {snapshot_id}")

        try:
            snapshot = self.ec2_resource.Snapshot(snapshot_id)
            snapshot.reload()

            response = self.ec2_client.delete_snapshot(
                SnapshotId=snapshot_id
            )

            # Log performance metrics
            self._log_performance_metrics(
                operation,
                start_time,
                {
                    'SnapshotId': snapshot_id,
                    'VolumeSize': snapshot.volume_size,
                    'VolumeId': snapshot.volume_id
                }
            )

            return True

        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Failed to delete snapshot: {error_msg}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting snapshot: {str(e)}")
            self._log_operation_metric(operation, False, time.time() - start_time)
            return False

# Function to use the class
def setup_ec2_infrastructure():
    """Set up EC2 infrastructure"""
    ec2_manager = EC2Manager()
    
    # Launch an instance
    instance = ec2_manager.launch_instance()
    
    if instance:
        # Create and attach a volume
        volume = ec2_manager.create_and_attach_volume(instance)
        
        # Create a snapshot
        if volume:
            snapshot = ec2_manager.create_snapshot(volume)
        
        # Set up CloudWatch alarm
        ec2_manager.setup_cloudwatch_alarm(instance)
        
        return {
            'instance_id': instance.id,
            'public_ip': instance.public_ip_address,
            'volume_id': volume.id if volume else None
        }
    
    return None