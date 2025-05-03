import os
import zipfile
import time
import shutil
import boto3
import json
from typing import Optional, Dict, List, Union
from botocore.exceptions import ClientError
from botocore.config import Config
from scripts.utils import get_client, logger, handle_error, wait_with_progress, ensure_directory_exists
from config import settings

class LambdaManager:
    """Manages AWS Lambda functions and their associated resources."""
    
    def __init__(self):
        """Initialize Lambda manager with AWS Lambda client and configuration."""
        self.lambda_client = get_client('lambda')
        self.function_name = settings.LAMBDA_FUNCTION_NAME
        self.zip_path = settings.LAMBDA_ZIP_PATH
        self.role_name = settings.IAM_LAMBDA_ROLE_NAME
        
        # Configure retry mechanism
        self.config = Config(
            retries = dict(
                max_attempts = 3
            )
        )
        
    def _validate_function_name(self, function_name: str) -> bool:
        """Validate Lambda function name according to AWS requirements.
        
        Args:
            function_name: Name of the Lambda function to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not function_name:
            return False
        if len(function_name) > 64:
            return False
        if not function_name[0].isalpha():
            return False
        if not all(c.isalnum() or c in ['_', '-'] for c in function_name):
            return False
        return True
        
    def create_lambda_zip(self, source_file: str) -> bool:
        """Create a ZIP file for Lambda deployment.
        
        Args:
            source_file: Path to the source Python file
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Creating Lambda ZIP package from {source_file}")
        
        if not os.path.exists(source_file):
            logger.error(f"Source file '{source_file}' not found")
            return False
            
        try:
            with zipfile.ZipFile(self.zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
                z.write(source_file, arcname='lambda_function.py')
                
            logger.info(f"Created ZIP file: {self.zip_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create Lambda ZIP: {str(e)}")
            return False
            
    def deploy_lambda(self, role_arn: str) -> Optional[str]:
        """Deploy Lambda function from ZIP file.
        
        Args:
            role_arn: ARN of the IAM role for the Lambda function
            
        Returns:
            Optional[str]: Function ARN if successful, None otherwise
        """
        logger.info(f"Deploying Lambda function: {self.function_name}")
        
        if not self._validate_function_name(self.function_name):
            logger.error(f"Invalid function name: {self.function_name}")
            return None
            
        # Check if ZIP file exists
        if not os.path.isfile(self.zip_path) or os.path.getsize(self.zip_path) == 0:
            logger.error(f"ZIP file '{self.zip_path}' not found or empty")
            return None
            
        try:
            # Read ZIP package
            with open(self.zip_path, 'rb') as f:
                zipped_code = f.read()
                
            # Create Lambda function
            response = self.lambda_client.create_function(
                FunctionName=self.function_name,
                Runtime='python3.9',
                Role=role_arn,
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': zipped_code},
                Timeout=settings.LAMBDA_TIMEOUT,
                MemorySize=settings.LAMBDA_MEMORY_SIZE,
                Publish=True,
                Environment={
                    'Variables': {
                        'LOG_LEVEL': settings.LOG_LEVEL
                    }
                }
            )
            
            logger.info(f"Lambda function '{self.function_name}' created: {response['FunctionArn']}")
            return response['FunctionArn']
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceConflictException':
                logger.info(f"Lambda function '{self.function_name}' already exists")
                
                # Get function info
                function = self.lambda_client.get_function(FunctionName=self.function_name)
                return function['Configuration']['FunctionArn']
            else:
                handle_error(e, "deploying Lambda function")
                return None
                
    def update_lambda(self) -> bool:
        """Update existing Lambda function code.
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Updating Lambda function: {self.function_name}")
        
        # Check if ZIP file exists
        if not os.path.isfile(self.zip_path) or os.path.getsize(self.zip_path) == 0:
            logger.error(f"ZIP file '{self.zip_path}' not found or empty")
            return False
            
        try:
            # Read ZIP package
            with open(self.zip_path, 'rb') as f:
                zipped_code = f.read()
                
            # Update function code
            response = self.lambda_client.update_function_code(
                FunctionName=self.function_name,
                ZipFile=zipped_code,
                Publish=True
            )
            
            logger.info(f"Lambda function '{self.function_name}' updated: {response['FunctionArn']}")
            return True
            
        except Exception as e:
            handle_error(e, "updating Lambda function")
            return False
            
    def create_event_rule(self, schedule_expression: str = "rate(1 day)") -> Optional[str]:
        """Create CloudWatch event rule to trigger Lambda on a schedule.
        
        Args:
            schedule_expression: Schedule expression for the rule (default: "rate(1 day)")
            
        Returns:
            Optional[str]: Rule ARN if successful, None otherwise
        """
        logger.info(f"Creating event rule for Lambda function: {self.function_name}")
        
        events_client = get_client('events')
        rule_name = f"{self.function_name}-ScheduleRule"
        
        try:
            # Get AWS account ID
            sts_client = boto3.client('sts')
            account_id = sts_client.get_caller_identity()['Account']
            
            # Create rule
            response = events_client.put_rule(
                Name=rule_name,
                ScheduleExpression=schedule_expression,
                State='ENABLED',
                Description=f"Trigger {self.function_name} on a schedule"
            )
            
            rule_arn = response['RuleArn']
            logger.info(f"Created event rule: {rule_name}")
            
            # Add permission to Lambda
            try:
                self.lambda_client.add_permission(
                    FunctionName=self.function_name,
                    StatementId=f"{rule_name}-Permission",
                    Action="lambda:InvokeFunction",
                    Principal="events.amazonaws.com",
                    SourceArn=rule_arn
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceConflictException':
                    logger.info(f"Permission already exists for {rule_name}")
                else:
                    raise e
            
            # Set Lambda as target
            events_client.put_targets(
                Rule=rule_name,
                Targets=[
                    {
                        'Id': '1',
                        'Arn': f"arn:aws:lambda:{settings.AWS_REGION}:{account_id}:function:{self.function_name}"
                    }
                ]
            )
            
            logger.info(f"Lambda function set as target for event rule")
            return rule_arn
            
        except Exception as e:
            handle_error(e, "creating event rule")
            return None
            
    def delete_event_rule(self, rule_name: str) -> bool:
        """Delete a CloudWatch event rule by name.
        
        Args:
            rule_name: Name of the event rule to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Deleting event rule: {rule_name}")

        events_client = get_client('events')

        try:
            # Get targets before deleting the rule
            targets = events_client.list_targets_by_rule(Rule=rule_name)['Targets']

            if targets:
                target_ids = [target['Id'] for target in targets]
                events_client.remove_targets(Rule=rule_name, Ids=target_ids)
                logger.info(f"Removed targets from rule: {rule_name}")

            events_client.delete_rule(Name=rule_name)
            logger.info(f"Event rule '{rule_name}' deleted")
            return True

        except Exception as e:
            handle_error(e, f"deleting event rule {rule_name}")
            return False

    def list_functions(self) -> List[str]:
        """List Lambda functions.
        
        Returns:
            List[str]: List of function names
        """
        logger.info("Listing Lambda functions")
        
        try:
            response = self.lambda_client.list_functions()
            functions = response.get('Functions', [])
            
            function_names = [f['FunctionName'] for f in functions]
            logger.info(f"Found {len(function_names)} Lambda functions")
            return function_names
            
        except Exception as e:
            handle_error(e, "listing Lambda functions")
            return []

    def delete_function(self, function_name: str) -> bool:
        """Delete a Lambda function by name.
        
        Args:
            function_name: Name of the Lambda function to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Deleting Lambda function: {function_name}")

        try:
            self.lambda_client.delete_function(
                FunctionName=function_name
            )
            logger.info(f"Lambda function '{function_name}' deleted")
            return True

        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.info(f"Lambda function '{function_name}' not found")
                return True  # Consider it successful if it's already gone
            else:
                handle_error(e, f"deleting Lambda function {function_name}")
                return False

    def cleanup(self) -> bool:
        """Clean up all Lambda resources.
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Cleaning up Lambda resources")
        
        try:
            # Delete event rule
            rule_name = f"{self.function_name}-ScheduleRule"
            self.delete_event_rule(rule_name)
            
            # Delete Lambda function
            self.delete_function(self.function_name)
            
            # Delete ZIP file if it exists
            if os.path.exists(self.zip_path):
                os.remove(self.zip_path)
                logger.info(f"Deleted ZIP file: {self.zip_path}")
                
            logger.info("Lambda resources cleaned up successfully")
            return True
            
        except Exception as e:
            handle_error(e, "cleaning up Lambda resources")
            return False

    def _create_assume_role_policy(self, services: List[str]) -> str:
        """Create a trust policy document for the specified AWS services.
        
        Args:
            services: List of AWS services that can assume the role
            
        Returns:
            JSON string containing the trust policy document
        """
        return json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": services
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        })

    def get_function(self, function_name: str) -> Optional[Dict]:
        """Get details of a Lambda function.
        
        Args:
            function_name: Name of the Lambda function
            
        Returns:
            Optional[Dict]: Function details if successful, None otherwise
        """
        try:
            response = self.lambda_client.get_function(FunctionName=function_name)
            return response
        except ClientError as e:
            handle_error(e, f"getting function {function_name}")
            return None

    def get_event_rule(self, rule_name: str) -> Optional[Dict]:
        """Get details of an event rule.
        
        Args:
            rule_name: Name of the event rule
            
        Returns:
            Optional[Dict]: Rule details if successful, None otherwise
        """
        try:
            response = self.lambda_client.get_event_rule(RuleName=rule_name)
            return response
        except ClientError as e:
            handle_error(e, f"getting event rule {rule_name}")
            return None

    def list_event_rules(self, function_name: str) -> List[Dict]:
        """List event rules for a Lambda function.
        
        Args:
            function_name: Name of the Lambda function
            
        Returns:
            List[Dict]: List of event rules
        """
        try:
            response = self.lambda_client.list_event_rules(FunctionName=function_name)
            return response.get('Rules', [])
        except ClientError as e:
            handle_error(e, f"listing event rules for {function_name}")
            return []

# Function to use the class
def setup_lambda() -> Optional[Dict[str, str]]:
    """Set up Lambda infrastructure.
    
    Returns:
        Optional[Dict[str, str]]: Dictionary containing function details if successful, None otherwise
    """
    # Copy lambda template to project directory
    lambda_manager = LambdaManager()
    
    # Ensure templates directory exists
    template_dir = 'templates'
    ensure_directory_exists(template_dir)
    
    # Path to template file
    template_path = os.path.join(template_dir, 'lambda_function.py')
    
    # Create lambda code from template if it doesn't exist
    if not os.path.exists(template_path):
        # Create lambda function code
        template_code = '''# lambda_function.py
import boto3
import logging
from datetime import datetime, timezone, timedelta

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Terminate EC2 instances that have been stopped for more than 24 hours."""
    ec2 = boto3.client('ec2')
    
    try:
        response = ec2.describe_instances(Filters=[
            {'Name': 'instance-state-name', 'Values': ['stopped']}
        ])
        
        stopped_instances = []
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                state_transition_time = instance.get('StateTransitionReason', '')
                
                if 'User initiated' in state_transition_time:
                    try:
                        timestamp_str = state_transition_time.split('(')[1].replace(' GMT)', '')
                        stopped_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        stopped_time = stopped_time.replace(tzinfo=timezone.utc)
                        now = datetime.now(timezone.utc)
                        
                        if (now - stopped_time) > timedelta(hours=24):
                            stopped_instances.append(instance_id)
                            logger.info(f"Instance {instance_id} has been stopped for more than 24 hours")
                            
                    except Exception as e:
                        logger.error(f"Date parse error for {instance_id}: {e}")
        
        if stopped_instances:
            logger.info(f"Terminating instances: {stopped_instances}")
            ec2.terminate_instances(InstanceIds=stopped_instances)
            return {
                "statusCode": 200,
                "body": {
                    "terminated": stopped_instances,
                    "message": f"Successfully terminated {len(stopped_instances)} instances"
                }
            }
        else:
            return {
                "statusCode": 200,
                "body": {
                    "message": "No stale instances found"
                }
            }
            
    except Exception as e:
        logger.error(f"Error in Lambda function: {str(e)}")
        return {
            "statusCode": 500,
            "body": {
                "error": str(e)
            }
        }
'''
        with open(template_path, 'w') as f:
            f.write(template_code)
    
    # Create Lambda zip package
    if not lambda_manager.create_lambda_zip(template_path):
        logger.error("Failed to create Lambda ZIP package")
        return None
    
    # Import IAM manager for role creation
    from scripts.iam_manager import IAMManager
    iam_manager = IAMManager()
    lambda_role_arn = iam_manager.create_lambda_role()
    
    # Deploy Lambda function
    if lambda_role_arn:
        # Wait for IAM role propagation with proper handling
        wait_time = 10  # Increased from 5 to 10 seconds for better propagation
        logger.info(f"Waiting {wait_time} seconds for IAM role propagation")
        wait_with_progress(wait_time, "Waiting for IAM role propagation")
        
        # Try up to 3 times with increased delay if needed
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            function_arn = lambda_manager.deploy_lambda(lambda_role_arn)
            
            if function_arn:
                # Set up scheduled event
                rule_arn = lambda_manager.create_event_rule()
                
                return {
                    'function_name': settings.LAMBDA_FUNCTION_NAME,
                    'function_arn': function_arn,
                    'role_arn': lambda_role_arn,
                    'rule_arn': rule_arn
                }
            elif attempt < max_attempts:
                wait_time = 10 * attempt
                logger.warning(f"Lambda deployment failed, waiting {wait_time}s before retry {attempt+1}/{max_attempts}")
                wait_with_progress(wait_time, f"Retry {attempt+1}/{max_attempts}")
    
    logger.error("Failed to set up Lambda function")
    return None