# AWS Infrastructure Manager Configuration
from typing import Dict, Optional, Union, List
import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

# Custom Exceptions
class ConfigurationError(Exception):
    """Base exception for configuration errors."""
    pass

class AWSConfigurationError(ConfigurationError):
    """Exception for AWS-specific configuration errors."""
    pass

class ValidationError(ConfigurationError):
    """Exception for validation errors."""
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from the .env file
def load_env_file() -> None:
    """Load environment variables from the .env file."""
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path))
        logger.info(f"Loaded environment variables from {env_path}")
    else:
        logger.warning(f"Environment file not found at {env_path}")
        # Create a default .env file if it doesn't exist
        #create_default_env_file(env_path)

'''
def create_default_env_file(env_path: Path) -> None:
    """Create a default .env file with development settings."""
    default_env_content = """# AWS Credentials (either use access keys or profile)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# AWS Region
AWS_REGION=ap-south-1

# Environment Configuration
ENVIRONMENT=development
CONFIG_PROFILE=default

# VPC Configuration (Optional for development)
VPC_ID=
SUBNET_ID=
SECURITY_GROUP_IDS=

# EC2 Configuration
EC2_AMI_ID=ami-062f0cc54dbfd8ef1
EC2_INSTANCE_TYPE=t2.micro
EC2_KEY_NAME=AutomatedEC2
EC2_MIN_COUNT=1
EC2_MAX_COUNT=1

# EBS Configuration
EBS_VOLUME_SIZE=8
EBS_VOLUME_TYPE=gp2
EBS_ENCRYPTED=true

# S3 Configuration
S3_BUCKET_NAME=my-infra-manager-bucket
S3_OBJECT_KEY=backups/data.txt
LOCAL_UPLOAD_FILE=data/upload_file.txt
LOCAL_DOWNLOAD_DIR=data/downloads
S3_BACKUP_RETENTION_DAYS=30
S3_ENCRYPTION=AES256

# Lambda Configuration
LAMBDA_FUNCTION_NAME=TerminateOldEC2Instances
LAMBDA_ZIP_PATH=lambda_function.zip
LAMBDA_TIMEOUT=60
LAMBDA_MEMORY_SIZE=128
LAMBDA_LOG_LEVEL=INFO

# CloudWatch Configuration
CLOUDWATCH_ALARM_NAME=HighCPUUtilization
CLOUDWATCH_CPU_THRESHOLD=70.0
CLOUDWATCH_EVALUATION_PERIODS=2
CLOUDWATCH_PERIOD=300

# Logging Configuration
LOG_FILE=logs/aws_operations.log
LOG_LEVEL=INFO

# Project Information
PROJECT_NAME=AWSInfraManager
"""
    try:
        with open(env_path, 'w') as f:
            f.write(default_env_content)
        logger.info(f"Created default .env file at {env_path}")
    except Exception as e:
        logger.error(f"Failed to create default .env file: {str(e)}")
'''

load_env_file()

def validate_aws_region(region: str) -> bool:
    """Validate AWS region format."""
    pattern = r'^[a-z]{2}-[a-z]+-\d{1}$'
    return bool(re.match(pattern, region))

def validate_s3_bucket_name(bucket_name: str) -> bool:
    """Validate S3 bucket name format."""
    pattern = r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$'
    return bool(re.match(pattern, bucket_name))

def validate_security_group_id(sg_id: str) -> bool:
    """Validate security group ID format."""
    pattern = r'^sg-[0-9a-f]{8,17}$'
    return bool(re.match(pattern, sg_id))

def get_aws_config() -> Dict[str, str]:
    """
    Determine AWS configuration based on environment variables or profile.
    Prioritize environment variables, then profile, then default.
    """
    config: Dict[str, str] = {}
    
    if 'AWS_ACCESS_KEY_ID' in os.environ and 'AWS_SECRET_ACCESS_KEY' in os.environ:
        config.update({
            'aws_access_key_id': os.environ['AWS_ACCESS_KEY_ID'],
            'aws_secret_access_key': os.environ['AWS_SECRET_ACCESS_KEY'],
        })
        if 'AWS_SESSION_TOKEN' in os.environ:
            config['aws_session_token'] = os.environ['AWS_SESSION_TOKEN']
    elif 'AWS_PROFILE' in os.environ:
        config['profile_name'] = os.environ['AWS_PROFILE']
    
    return config

# AWS Configuration
AWS_CONFIG = get_aws_config()
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-1')
AWS_ROLE_ARN = os.environ.get('AWS_ROLE_ARN', '')
AWS_KMS_KEY_ID = os.environ.get('AWS_KMS_KEY_ID', '')

# Environment Configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
CONFIG_PROFILE = os.environ.get('CONFIG_PROFILE', 'default')

# IAM Settings
IAM_ROLE_NAME = 'AWS_Infrastructure_Role'
IAM_INSTANCE_PROFILE_NAME = 'EC2_Instance_Profile'
IAM_LAMBDA_ROLE_NAME = 'Lambda_Execution_Role'

# EC2 Settings
EC2_AMI_ID = os.environ.get('EC2_AMI_ID', 'ami-0c55b159cbfafe1f0')
EC2_INSTANCE_TYPE = os.environ.get('EC2_INSTANCE_TYPE', 't2.micro')
EC2_KEY_NAME = os.environ.get('EC2_KEY_NAME', 'AutomatedEC2')
EC2_MIN_COUNT = int(os.environ.get('EC2_MIN_COUNT', '1'))
EC2_MAX_COUNT = int(os.environ.get('EC2_MAX_COUNT', '1'))

# VPC Settings
VPC_ID = os.environ.get('VPC_ID', '')
SUBNET_ID = os.environ.get('SUBNET_ID', '')
SECURITY_GROUP_IDS = os.environ.get('SECURITY_GROUP_IDS', '').split(',') if os.environ.get('SECURITY_GROUP_IDS') else []

# EBS Settings
EBS_VOLUME_SIZE = int(os.environ.get('EBS_VOLUME_SIZE', '8'))
EBS_VOLUME_TYPE = os.environ.get('EBS_VOLUME_TYPE', 'gp2')
EBS_ENCRYPTED = os.environ.get('EBS_ENCRYPTED', 'true').lower() == 'true'
EBS_KMS_KEY_ID = os.environ.get('EBS_KMS_KEY_ID', AWS_KMS_KEY_ID)

# S3 Settings
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'my-infra-manager-bucket')
S3_OBJECT_KEY = os.environ.get('S3_OBJECT_KEY', 'backups/data.txt')
LOCAL_UPLOAD_FILE = os.environ.get('LOCAL_UPLOAD_FILE', 'data/upload_file.txt')
LOCAL_DOWNLOAD_DIR = os.environ.get('LOCAL_DOWNLOAD_DIR', 'data/downloads')
S3_BACKUP_RETENTION_DAYS = int(os.environ.get('S3_BACKUP_RETENTION_DAYS', '30'))
S3_ENCRYPTION = os.environ.get('S3_ENCRYPTION', 'AES256')
S3_KMS_KEY_ID = os.environ.get('S3_KMS_KEY_ID', AWS_KMS_KEY_ID)

# Lambda Settings
LAMBDA_FUNCTION_NAME = os.environ.get('LAMBDA_FUNCTION_NAME', 'TerminateOldEC2Instances')
LAMBDA_ZIP_PATH = os.environ.get('LAMBDA_ZIP_PATH', 'lambda_function.zip')
LAMBDA_TIMEOUT = int(os.environ.get('LAMBDA_TIMEOUT', '60'))
LAMBDA_MEMORY_SIZE = int(os.environ.get('LAMBDA_MEMORY_SIZE', '128'))
LAMBDA_ENVIRONMENT_VARS = {
    'LOG_LEVEL': os.environ.get('LAMBDA_LOG_LEVEL', 'INFO'),
    'REGION': AWS_REGION,
    'ENVIRONMENT': ENVIRONMENT
}

# CloudWatch Settings
CLOUDWATCH_ALARM_NAME = os.environ.get('CLOUDWATCH_ALARM_NAME', 'HighCPUUtilization')
CLOUDWATCH_CPU_THRESHOLD = float(os.environ.get('CLOUDWATCH_CPU_THRESHOLD', '70.0'))
CLOUDWATCH_EVALUATION_PERIODS = int(os.environ.get('CLOUDWATCH_EVALUATION_PERIODS', '2'))
CLOUDWATCH_PERIOD = int(os.environ.get('CLOUDWATCH_PERIOD', '300'))

# Logging Settings
LOG_FILE = os.environ.get('LOG_FILE', 'logs/aws_operations.log')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Tags
DEFAULT_TAGS = {
    'Environment': ENVIRONMENT,
    'Project': os.environ.get('PROJECT_NAME', 'AWSInfraManager'),
    'ManagedBy': 'AWSInfraManager',
    'ConfigProfile': CONFIG_PROFILE
}

def validate_config() -> None:
    """Validate that required configuration values are present and valid."""
    try:
        # Validate AWS Region
        if not validate_aws_region(AWS_REGION):
            raise ValidationError(f"Invalid AWS region format: {AWS_REGION}")

        # Validate S3 Bucket Name
        if not validate_s3_bucket_name(S3_BUCKET_NAME):
            raise ValidationError(f"Invalid S3 bucket name format: {S3_BUCKET_NAME}")

        # Validate Security Group IDs if provided
        for sg_id in SECURITY_GROUP_IDS:
            if sg_id and not validate_security_group_id(sg_id):
                raise ValidationError(f"Invalid security group ID format: {sg_id}")

        # Validate required settings based on environment
        required_settings = {
            'AWS_REGION': AWS_REGION,
            'S3_BUCKET_NAME': S3_BUCKET_NAME
        }
        
        # Add VPC settings as required only for non-development environments
        if ENVIRONMENT.lower() != 'development':
            required_settings.update({
                'VPC_ID': VPC_ID,
                'SUBNET_ID': SUBNET_ID
            })
        
        for setting, value in required_settings.items():
            if not value:
                raise ValidationError(f"{setting} must be set in environment variables")
        
        # Validate AWS credentials
        if not AWS_CONFIG:
            raise AWSConfigurationError("AWS credentials must be configured via environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) or profile (AWS_PROFILE)")
        
        if 'aws_access_key_id' not in AWS_CONFIG and 'profile_name' not in AWS_CONFIG:
            raise AWSConfigurationError("AWS credentials must be configured via environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) or profile (AWS_PROFILE)")
        
        # Validate numeric values
        numeric_settings = {
            'EBS_VOLUME_SIZE': EBS_VOLUME_SIZE,
            'LAMBDA_TIMEOUT': LAMBDA_TIMEOUT,
            'LAMBDA_MEMORY_SIZE': LAMBDA_MEMORY_SIZE,
            'S3_BACKUP_RETENTION_DAYS': S3_BACKUP_RETENTION_DAYS
        }
        
        for setting, value in numeric_settings.items():
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValidationError(f"{setting} must be a positive number")

        # Create required directories
        directories = [
            Path(LOCAL_UPLOAD_FILE).parent,
            Path(LOCAL_DOWNLOAD_DIR),
            Path(LOG_FILE).parent
        ]
        
        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {directory}")

        logger.info("Configuration validation successful")
        
    except Exception as e:
        logger.error(f"Configuration validation failed: {str(e)}")
        raise

validate_config()