import os
import json
from typing import List, Dict, Optional, Union, Any
from botocore.exceptions import ClientError
from scripts.utils import get_client, get_resource, logger, handle_error, ensure_directory_exists
from config import settings

class S3Manager:
    """A class to manage S3 bucket operations with enhanced functionality."""
    
    def __init__(self):
        """Initialize the S3 manager with client and resource instances."""
        self.s3_client = get_client('s3')
        self.s3_resource = get_resource('s3')
        self.bucket_name = settings.S3_BUCKET_NAME
        
    def create_bucket(self, bucket_name: str = None, region: str = None) -> bool:
        """
        Create an S3 bucket with the specified name and region.
        
        Args:
            bucket_name (str, optional): Name of the bucket to create. If not provided, uses the configured bucket name.
            region (str, optional): AWS region to create the bucket in. If not provided, uses the configured region.
            
        Returns:
            bool: True if bucket was created or already exists, False otherwise
        """
        bucket_name = bucket_name or self.bucket_name
        region = region or settings.AWS_REGION
        
        logger.info(f"Creating S3 bucket: {bucket_name}")
        
        try:
            if region == 'us-east-1':
                self.s3_client.create_bucket(Bucket=bucket_name)
            else:
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': region}
                )
                
            logger.info(f"Bucket '{bucket_name}' created")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'BucketAlreadyOwnedByYou':
                logger.info(f"Bucket '{bucket_name}' already exists and is owned by you")
                return True
            elif error_code == 'BucketAlreadyExists':
                logger.error(f"Bucket name '{bucket_name}' is already taken globally")
                return False
            else:
                handle_error(e, "creating S3 bucket")
                return False
                
    def enable_versioning(self):
        """Enable versioning on the S3 bucket"""
        logger.info(f"Enabling versioning on bucket: {self.bucket_name}")
        
        try:
            self.s3_resource.BucketVersioning(self.bucket_name).enable()
            logger.info(f"Versioning enabled on bucket '{self.bucket_name}'")
            return True
            
        except Exception as e:
            handle_error(e, "enabling bucket versioning")
            return False
            
    def set_lifecycle_policy(self):
        """Set a lifecycle policy to expire objects after 30 days"""
        logger.info(f"Setting lifecycle policy on bucket: {self.bucket_name}")
        
        try:
            lifecycle_configuration = {
                'Rules': [
                    {
                        'ID': 'RetainFor30Days',
                        'Prefix': 'backups/',
                        'Status': 'Enabled',
                        'Expiration': {'Days': 30},
                        'NoncurrentVersionExpiration': {'NoncurrentDays': 30}
                    }
                ]
            }
            
            self.s3_client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket_name,
                LifecycleConfiguration=lifecycle_configuration
            )
            
            logger.info(f"Lifecycle policy applied to bucket '{self.bucket_name}'")
            return True
            
        except Exception as e:
            handle_error(e, "setting lifecycle policy")
            return False
            
    def enable_encryption(self):
        """Enable server-side encryption on the bucket"""
        logger.info(f"Enabling encryption on bucket: {self.bucket_name}")
        
        try:
            self.s3_client.put_bucket_encryption(
                Bucket=self.bucket_name,
                ServerSideEncryptionConfiguration={
                    'Rules': [{
                        'ApplyServerSideEncryptionByDefault': {
                            'SSEAlgorithm': 'AES256'
                        }
                    }]
                }
            )
            
            logger.info(f"Server-side encryption enabled on bucket '{self.bucket_name}'")
            return True
            
        except Exception as e:
            handle_error(e, "enabling bucket encryption")
            return False
            
    def upload_file(self, file_path=settings.LOCAL_UPLOAD_FILE, key=settings.S3_OBJECT_KEY):
        """Upload a file to the S3 bucket"""
        logger.info(f"Uploading file {file_path} to bucket {self.bucket_name} with key {key}")
        
        if not os.path.isfile(file_path):
            logger.error(f"Upload failed: local file '{file_path}' not found")
            return False
            
        try:
            self.s3_client.upload_file(
                Filename=file_path,
                Bucket=self.bucket_name,
                Key=key,
                ExtraArgs={'ServerSideEncryption': 'AES256'}
            )
            
            logger.info(f"Uploaded '{file_path}' to 's3://{self.bucket_name}/{key}'")
            return True
            
        except Exception as e:
            handle_error(e, "uploading file to S3")
            return False
            
    def download_file(self, key=settings.S3_OBJECT_KEY, download_path=None):
        """Download a file from the S3 bucket"""
        if download_path is None:
            download_path = os.path.join(settings.LOCAL_DOWNLOAD_DIR, os.path.basename(key))
            
        logger.info(f"Downloading s3://{self.bucket_name}/{key} to {download_path}")
        
        # Ensure the target directory exists
        target_dir = os.path.dirname(download_path)
        ensure_directory_exists(target_dir)
        
        try:
            self.s3_client.download_file(
                Bucket=self.bucket_name,
                Key=key,
                Filename=download_path
            )
            
            logger.info(f"Downloaded 's3://{self.bucket_name}/{key}' to '{download_path}'")
            return True
            
        except Exception as e:
            handle_error(e, "downloading file from S3")
            return False

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by name. Bucket must be empty."""
        logger.info(f"Attempting to delete bucket: {bucket_name}")

        try:
            # First, check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.info(f"Bucket '{bucket_name}' does not exist.")
                    return True
                else:
                    raise

            # Delete all objects and their versions
            paginator = self.s3_client.get_paginator('list_object_versions')
            for page in paginator.paginate(Bucket=bucket_name):
                if 'Versions' in page:
                    for version in page['Versions']:
                        self.s3_client.delete_object(
                            Bucket=bucket_name,
                            Key=version['Key'],
                            VersionId=version['VersionId']
                        )
                if 'DeleteMarkers' in page:
                    for marker in page['DeleteMarkers']:
                        self.s3_client.delete_object(
                            Bucket=bucket_name,
                            Key=marker['Key'],
                            VersionId=marker['VersionId']
                        )

            # Delete the bucket
            self.s3_client.delete_bucket(Bucket=bucket_name)
            logger.info(f"Bucket '{bucket_name}' deleted successfully")
            return True

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                logger.info(f"Bucket '{bucket_name}' does not exist.")
                return True
            else:
                handle_error(e, f"deleting bucket '{bucket_name}'")
                return False
            
    def delete_object(self, key, bucket_name: str = None):
        """Delete an object from the S3 bucket by key
        
        Args:
            key (str): The key of the object to delete
            bucket_name (str, optional): The name of the bucket. If not provided, uses the configured bucket name.
        """
        bucket_name = bucket_name or self.bucket_name
        logger.info(f"Deleting object 's3://{bucket_name}/{key}'")
        
        try:
            self.s3_client.delete_object(
                Bucket=bucket_name,
                Key=key
            )
            
            logger.info(f"Deleted object 's3://{bucket_name}/{key}'")
            return True
            
        except Exception as e:
            handle_error(e, f"deleting object '{key}' from S3")
            return False
            
    def list_objects(self, prefix=None):
        """List objects in the S3 bucket with optional prefix"""
        logger.info(f"Listing objects in bucket {self.bucket_name}")
        
        try:
            params = {'Bucket': self.bucket_name}
            if prefix:
                params['Prefix'] = prefix
                
            response = self.s3_client.list_objects_v2(**params)
            
            objects = []
            if 'Contents' in response:
                objects = [obj['Key'] for obj in response['Contents']]
                
            logger.info(f"Found {len(objects)} objects in bucket '{self.bucket_name}'")
            return objects
            
        except Exception as e:
            handle_error(e, "listing S3 objects")
            return []

    def set_bucket_policy(self, policy: Dict[str, Any]) -> bool:
        """
        Set a bucket policy.
        
        Args:
            policy (Dict[str, Any]): The bucket policy to set
            
        Returns:
            bool: True if policy was set successfully, False otherwise
        """
        try:
            self.s3_client.put_bucket_policy(
                Bucket=self.bucket_name,
                Policy=json.dumps(policy)
            )
            logger.info(f"Bucket policy set for '{self.bucket_name}'")
            return True
        except Exception as e:
            handle_error(e, "setting bucket policy")
            return False

    def set_cors_configuration(self, cors_rules: List[Dict[str, Any]]) -> bool:
        """
        Set CORS configuration for the bucket.
        
        Args:
            cors_rules (List[Dict[str, Any]]): List of CORS rules
            
        Returns:
            bool: True if CORS was configured successfully, False otherwise
        """
        try:
            self.s3_client.put_bucket_cors(
                Bucket=self.bucket_name,
                CORSConfiguration={'CORSRules': cors_rules}
            )
            logger.info(f"CORS configuration set for '{self.bucket_name}'")
            return True
        except Exception as e:
            handle_error(e, "setting CORS configuration")
            return False

    def set_bucket_acl(self, acl: str) -> bool:
        """
        Set bucket ACL.
        
        Args:
            acl (str): The ACL to set (e.g., 'private', 'public-read', etc.)
            
        Returns:
            bool: True if ACL was set successfully, False otherwise
        """
        try:
            self.s3_client.put_bucket_acl(
                Bucket=self.bucket_name,
                ACL=acl
            )
            logger.info(f"Bucket ACL set to '{acl}' for '{self.bucket_name}'")
            return True
        except Exception as e:
            handle_error(e, "setting bucket ACL")
            return False

    def tag_bucket(self, tags: Dict[str, str]) -> bool:
        """
        Add tags to the bucket.
        
        Args:
            tags (Dict[str, str]): Dictionary of tag key-value pairs
            
        Returns:
            bool: True if tags were set successfully, False otherwise
        """
        try:
            tag_set = [{'Key': k, 'Value': v} for k, v in tags.items()]
            self.s3_client.put_bucket_tagging(
                Bucket=self.bucket_name,
                Tagging={'TagSet': tag_set}
            )
            logger.info(f"Tags set for bucket '{self.bucket_name}'")
            return True
        except Exception as e:
            handle_error(e, "setting bucket tags")
            return False

    def enable_metrics(self, metrics_id: str) -> bool:
        """
        Enable metrics for the bucket.
        
        Args:
            metrics_id (str): The ID for the metrics configuration
            
        Returns:
            bool: True if metrics were enabled successfully, False otherwise
        """
        try:
            self.s3_client.put_bucket_metrics_configuration(
                Bucket=self.bucket_name,
                Id=metrics_id,
                MetricsConfiguration={
                    'Id': metrics_id,
                    'Filter': {}
                }
            )
            logger.info(f"Metrics enabled for bucket '{self.bucket_name}'")
            return True
        except Exception as e:
            handle_error(e, "enabling bucket metrics")
            return False

    def configure_replication(self, destination_bucket: str, role_arn: str) -> bool:
        """
        Configure bucket replication.
        
        Args:
            destination_bucket (str): The destination bucket ARN
            role_arn (str): The IAM role ARN for replication
            
        Returns:
            bool: True if replication was configured successfully, False otherwise
        """
        try:
            replication_config = {
                'Role': role_arn,
                'Rules': [{
                    'ID': 'replication-rule',
                    'Status': 'Enabled',
                    'Priority': 1,
                    'DeleteMarkerReplication': {'Status': 'Enabled'},
                    'Destination': {
                        'Bucket': destination_bucket
                    }
                }]
            }
            
            self.s3_client.put_bucket_replication(
                Bucket=self.bucket_name,
                ReplicationConfiguration=replication_config
            )
            logger.info(f"Replication configured for bucket '{self.bucket_name}'")
            return True
        except Exception as e:
            handle_error(e, "configuring bucket replication")
            return False

    def list_buckets(self):
        """List all S3 buckets in the account."""
        try:
            response = self.s3_client.list_buckets()
            return response.get('Buckets', [])
        except Exception as e:
            handle_error(e, "listing S3 buckets")
            return []

# Function to use the class
def setup_s3_storage() -> Optional[Dict[str, str]]:
    """
    Set up S3 storage infrastructure with enhanced configuration.
    
    Returns:
        Optional[Dict[str, str]]: Dictionary containing bucket details if setup successful, None otherwise
    """
    s3_manager = S3Manager()
    
    # Create and configure bucket
    if s3_manager.create_bucket():
        # Configure bucket settings
        s3_manager.enable_versioning()
        s3_manager.set_lifecycle_policy()
        s3_manager.enable_encryption()
        
        # Set up additional configurations
        s3_manager.set_bucket_acl('private')
        s3_manager.tag_bucket({'Environment': 'Development', 'Project': 'AWSInfraManager'})
        s3_manager.enable_metrics('daily-metrics')
        
        # Create a test file if it doesn't exist
        data_dir = os.path.dirname(settings.LOCAL_UPLOAD_FILE)
        ensure_directory_exists(data_dir)
        
        if not os.path.exists(settings.LOCAL_UPLOAD_FILE):
            with open(settings.LOCAL_UPLOAD_FILE, 'w') as f:
                f.write("This is a test file for S3 upload.")
        
        # Upload and download test file
        s3_manager.upload_file()
        s3_manager.download_file()
        
        return {
            'bucket_name': settings.S3_BUCKET_NAME,
            'object_key': settings.S3_OBJECT_KEY,
            'download_location': os.path.join(settings.LOCAL_DOWNLOAD_DIR, os.path.basename(settings.S3_OBJECT_KEY))
        }
    
    return None