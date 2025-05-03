# lambda_function.py
import boto3
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
STALE_INSTANCE_THRESHOLD_HOURS = 24
MAX_BATCH_SIZE = 100  # AWS limit for terminate_instances

def get_stopped_instances(ec2_client: boto3.client) -> List[Dict[str, Any]]:
    """Retrieve all stopped EC2 instances with pagination."""
    stopped_instances = []
    paginator = ec2_client.get_paginator('describe_instances')
    
    try:
        for page in paginator.paginate(Filters=[
            {'Name': 'instance-state-name', 'Values': ['stopped']}
        ]):
            for reservation in page['Reservations']:
                for instance in reservation['Instances']:
                    stopped_instances.append(instance)
    except ClientError as e:
        logger.error(f"Error describing instances: {e}")
        raise
    
    return stopped_instances

def parse_stopped_time(instance: Dict[str, Any]) -> Optional[datetime]:
    """Parse the stopped time from instance state transition reason."""
    state_transition_time = instance.get('StateTransitionReason', '')
    if 'User initiated' not in state_transition_time:
        return None
        
    try:
        timestamp_str = state_transition_time.split('(')[1].replace(' GMT)', '')
        stopped_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        return stopped_time.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.warning(f"Failed to parse stopped time for instance {instance['InstanceId']}: {e}")
        return None

def terminate_instances_batch(ec2_client: boto3.client, instance_ids: List[str]) -> Dict[str, Any]:
    """Terminate instances in batches to respect AWS limits."""
    results = {"terminated": [], "failed": []}
    
    for i in range(0, len(instance_ids), MAX_BATCH_SIZE):
        batch = instance_ids[i:i + MAX_BATCH_SIZE]
        try:
            ec2_client.terminate_instances(InstanceIds=batch)
            results["terminated"].extend(batch)
            logger.info(f"Successfully terminated instances: {batch}")
        except ClientError as e:
            logger.error(f"Failed to terminate instances {batch}: {e}")
            results["failed"].extend(batch)
    
    return results

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Terminate EC2 instances that have been stopped for more than configured threshold.
    
    Args:
        event: Lambda event object
        context: Lambda context object
    
    Returns:
        Dict containing information about terminated instances
    """
    try:
        ec2 = boto3.client('ec2')
        stopped_instances = get_stopped_instances(ec2)
        
        stale_instances = []
        now = datetime.now(timezone.utc)
        
        for instance in stopped_instances:
            stopped_time = parse_stopped_time(instance)
            if stopped_time and (now - stopped_time) > timedelta(hours=STALE_INSTANCE_THRESHOLD_HOURS):
                stale_instances.append(instance['InstanceId'])
        
        if stale_instances:
            logger.info(f"Found {len(stale_instances)} stale instances to terminate")
            result = terminate_instances_batch(ec2, stale_instances)
            return {
                "status": "success",
                "terminated_instances": result["terminated"],
                "failed_instances": result["failed"]
            }
        else:
            logger.info("No stale instances found")
            return {
                "status": "success",
                "message": "No stale instances found"
            }
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }