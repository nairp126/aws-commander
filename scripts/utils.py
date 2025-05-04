import boto3
import logging
import os
import time
from botocore.exceptions import ClientError
import sys
import json
from typing import Optional, Any, Union
from functools import lru_cache
from config import settings
from datetime import datetime, timedelta

# Singleton logger instance
_logger = None

def setup_logging() -> logging.Logger:
    """
    Configure logging for the application.
    
    Returns:
        logging.Logger: Configured logger instance
    
    Raises:
        OSError: If log directory cannot be created
        ValueError: If log level is invalid
    """
    global _logger
    if _logger is not None:
        return _logger
        
    log_dir = os.path.dirname(settings.LOG_FILE)
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
    except OSError as e:
        raise OSError(f"Failed to create log directory {log_dir}: {str(e)}")
    
    try:
        log_level = getattr(logging, settings.LOG_LEVEL)
    except AttributeError:
        raise ValueError(f"Invalid log level: {settings.LOG_LEVEL}")
        
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(settings.LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    _logger = logging.getLogger('aws_infra_manager')
    return _logger

logger = setup_logging()

@lru_cache(maxsize=32)
def create_session(region: str = settings.AWS_REGION) -> boto3.Session:
    """
    Create and return a cached boto3 session.
    
    Args:
        region (str): AWS region name
        
    Returns:
        boto3.Session: AWS session object
        
    Raises:
        ValueError: If region is invalid
        Exception: For other AWS session creation errors
    """
    try:
        if not region:
            raise ValueError("AWS region cannot be empty")
        session = boto3.Session(region_name=region)
        return session
    except Exception as e:
        logger.error(f"Failed to create AWS session: {str(e)}")
        raise

def get_client(service: str, region: str = settings.AWS_REGION) -> Any:
    """
    Get a boto3 client for the specified service.
    
    Args:
        service (str): AWS service name (e.g., 'ec2', 's3')
        region (str): AWS region name
        
    Returns:
        Any: AWS service client
        
    Raises:
        ValueError: If service name is invalid
        Exception: For other AWS client creation errors
    """
    try:
        if not service:
            raise ValueError("Service name cannot be empty")
        session = create_session(region)
        return session.client(service)
    except Exception as e:
        logger.error(f"Failed to create {service} client: {str(e)}")
        raise

def get_resource(service: str, region: str = settings.AWS_REGION) -> Any:
    """
    Get a boto3 resource for the specified service.
    
    Args:
        service (str): AWS service name (e.g., 'ec2', 's3')
        region (str): AWS region name
        
    Returns:
        Any: AWS service resource
        
    Raises:
        ValueError: If service name is invalid
        Exception: For other AWS resource creation errors
    """
    try:
        if not service:
            raise ValueError("Service name cannot be empty")
        session = create_session(region)
        return session.resource(service)
    except Exception as e:
        logger.error(f"Failed to create {service} resource: {str(e)}")
        raise

def wait_with_progress(seconds: int, message: str = "Waiting") -> None:
    """
    Display a progress bar for waiting periods.
    
    Args:
        seconds (int): Number of seconds to wait
        message (str): Message to display during wait
        
    Raises:
        ValueError: If seconds is negative
        KeyboardInterrupt: If user interrupts the wait
    """
    if seconds < 0:
        raise ValueError("Seconds cannot be negative")
        
    try:
        print(f"{message}... ", end="", flush=True)
        for _ in range(seconds):
            print(".", end="", flush=True)
            time.sleep(1)
        print(" Done!")
    except KeyboardInterrupt:
        print("\nWait interrupted by user")
        raise

def handle_error(e: Exception, operation: str) -> str:
    """
    Handle AWS errors in a consistent way.
    
    Args:
        e (Exception): The exception to handle
        operation (str): Description of the operation that failed
        
    Returns:
        str: Formatted error message
    """
    error_message = ""
    if isinstance(e, ClientError):
        error_code = e.response['Error']['Code']
        error_message_detail = e.response['Error']['Message']
        error_message = f"AWS Error during {operation}: {error_code} - {error_message_detail}"
        logger.error(error_message)
    else:
        error_message = f"Error during {operation}: {str(e)}"
        logger.error(error_message)
    return error_message

def ensure_directory_exists(directory: str) -> None:
    """
    Ensure that the specified directory exists.
    
    Args:
        directory (str): Path to the directory
        
    Raises:
        OSError: If directory cannot be created
        PermissionError: If insufficient permissions
    """
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to create directory {directory}: {str(e)}")
        raise

def get_rds_metrics(db_instance_id, metric_name, period=300, start_time=None, end_time=None):
    """Fetch CloudWatch metrics for an RDS instance."""
    cloudwatch = get_client('cloudwatch')
    if not start_time:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
    if not end_time:
        end_time = datetime.utcnow()
    try:
        resp = cloudwatch.get_metric_statistics(
            Namespace='AWS/RDS',
            MetricName=metric_name,
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=['Average']
        )
        return resp.get('Datapoints', [])
    except Exception as e:
        logger.error(f"Error fetching RDS metric {metric_name}: {e}")
        return []

def get_cloudfront_metrics(distribution_id, metric_name, period=300, start_time=None, end_time=None):
    """Fetch CloudWatch metrics for a CloudFront distribution."""
    cloudwatch = get_client('cloudwatch', region='us-east-1')  # CloudFront metrics are always in us-east-1
    if not start_time:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
    if not end_time:
        end_time = datetime.utcnow()
    try:
        resp = cloudwatch.get_metric_statistics(
            Namespace='AWS/CloudFront',
            MetricName=metric_name,
            Dimensions=[{'Name': 'DistributionId', 'Value': distribution_id}, {'Name': 'Region', 'Value': 'Global'}],
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=['Sum']
        )
        return resp.get('Datapoints', [])
    except Exception as e:
        logger.error(f"Error fetching CloudFront metric {metric_name}: {e}")
        return []

def get_custom_cloudwatch_metric(namespace, metric_name, dimensions, period=300, stat='Average', start_time=None, end_time=None):
    """Fetch arbitrary CloudWatch metric data."""
    cloudwatch = get_client('cloudwatch')
    if not start_time:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
    if not end_time:
        end_time = datetime.utcnow()
    try:
        resp = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=[{'Name': k, 'Value': v} for d in dimensions for k, v in d.items()],
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=[stat]
        )
        return resp.get('Datapoints', [])
    except Exception as e:
        logger.error(f"Error fetching custom metric {namespace}/{metric_name}: {e}")
        return []

def get_cost_explorer_data(breakdown, time_range):
    """Fetch cost data from AWS Cost Explorer API."""
    ce = get_client('ce')
    today = datetime.utcnow().date()
    if time_range == 'Last 7 Days':
        start = today - timedelta(days=7)
        end = today
    elif time_range == 'Last 30 Days':
        start = today - timedelta(days=30)
        end = today
    elif time_range == 'This Month':
        start = today.replace(day=1)
        end = today
    elif time_range == 'Last Month':
        first = today.replace(day=1)
        last_month_end = first - timedelta(days=1)
        start = last_month_end.replace(day=1)
        end = last_month_end
    else:
        start = today - timedelta(days=7)
        end = today
    start_str = str(start)
    end_str = str(end)
    try:
        if breakdown == 'service':
            resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start_str, 'End': end_str},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            results = []
            for group in resp['ResultsByTime'][0]['Groups']:
                results.append({'Service': group['Keys'][0], 'Cost': float(group['Metrics']['UnblendedCost']['Amount'])})
            return results
        elif breakdown == 'tag':
            resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start_str, 'End': end_str},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'TAG', 'Key': 'Name'}]
            )
            results = []
            for group in resp['ResultsByTime'][0]['Groups']:
                tag = group['Keys'][0] if group['Keys'] else 'Untagged'
                results.append({'Tag': tag, 'Cost': float(group['Metrics']['UnblendedCost']['Amount'])})
            return results
        elif breakdown == 'time':
            resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start_str, 'End': end_str},
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            results = []
            for result in resp['ResultsByTime']:
                date = result['TimePeriod']['Start']
                cost = float(result['Total']['UnblendedCost']['Amount'])
                results.append({'Date': date, 'Cost': cost})
            return results
    except Exception as e:
        logger.error(f"Error fetching cost explorer data: {e}")
        return []