import json
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from scripts.utils import get_client, logger, handle_error
from config import settings
import boto3
from botocore.config import Config

class IAMManager:
    def __init__(self):
        """Initialize IAM manager with AWS IAM client and configuration."""
        self.iam_client = get_client('iam')
        self.role_name = settings.IAM_ROLE_NAME
        self.instance_profile_name = settings.IAM_INSTANCE_PROFILE_NAME
        self.lambda_role_name = settings.IAM_LAMBDA_ROLE_NAME
        
        # Configure retry mechanism
        self.config = Config(
            retries = dict(
                max_attempts = 3
            )
        )

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

    def _validate_role_name(self, role_name: str) -> bool:
        """Validate IAM role name according to AWS requirements.
        
        Args:
            role_name: Name of the IAM role to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not role_name:
            return False
        if len(role_name) > 64:
            return False
        if not role_name[0].isalpha():
            return False
        if not all(c.isalnum() or c in ['_', '-', '@'] for c in role_name):
            return False
        return True

    def create_ec2_role(self, role_name: Optional[str] = None) -> Optional[str]:
        """Create IAM role for EC2 instances with minimal required permissions.
        
        Args:
            role_name: Optional name of the IAM role. If not provided, uses self.role_name
            
        Returns:
            str: ARN of the created role or None if creation failed
        """
        role_name = role_name or self.role_name
        if not self._validate_role_name(role_name):
            logger.error(f"Invalid role name: {role_name}")
            return None

        logger.info(f"Creating IAM role: {role_name}")
        
        try:
            # Create role with minimal trust policy
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=self._create_assume_role_policy(["ec2.amazonaws.com"]),
                Description='Role for EC2 instances with minimal required permissions'
            )
            logger.info(f"Role created: {response['Role']['Arn']}")
            
            # Attach minimal required policies
            policies = [
                'arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess',  # Basic EC2 access
                'arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess',   # Read-only S3 access
                'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'  # Basic Lambda execution
            ]
            
            for policy_arn in policies:
                try:
                    self.iam_client.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy_arn
                    )
                    logger.info(f"Attached policy: {policy_arn}")
                except ClientError as e:
                    logger.error(f"Failed to attach policy {policy_arn}: {str(e)}")
                    # Continue with other policies even if one fails
                    continue
                
            return response['Role']['Arn']
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                logger.info(f"Role {role_name} already exists")
                try:
                    role = self.iam_client.get_role(RoleName=role_name)
                    return role['Role']['Arn']
                except ClientError as get_error:
                    handle_error(get_error, "getting existing role")
                    return None
            else:
                handle_error(e, "creating IAM role")
                return None

    def create_instance_profile(self, profile_name: Optional[str] = None) -> Optional[str]:
        """Create IAM instance profile and attach role with proper error handling.
        
        Args:
            profile_name: Optional name of the instance profile. If not provided, uses self.instance_profile_name
            
        Returns:
            str: Name of the instance profile or None if creation failed
        """
        profile_name = profile_name or self.instance_profile_name
        logger.info(f"Creating IAM instance profile: {profile_name}")
        
        try:
            # Check if the instance profile exists
            self.iam_client.get_instance_profile(InstanceProfileName=profile_name)
            logger.info(f"Instance profile {profile_name} already exists")
            
            # Ensure the role exists
            role_arn = self.create_ec2_role()
            if not role_arn:
                logger.error("Failed to create EC2 role for instance profile")
                return None
            
            return profile_name
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                try:
                    # Create the instance profile
                    self.iam_client.create_instance_profile(
                        InstanceProfileName=profile_name
                    )
                    logger.info(f"Instance profile {profile_name} created")
                    
                    # Ensure the role exists
                    role_arn = self.create_ec2_role()
                    if not role_arn:
                        logger.error("Failed to create EC2 role for instance profile")
                        return None
                    
                    # Add the role to the instance profile
                    self.iam_client.add_role_to_instance_profile(
                        InstanceProfileName=profile_name,
                        RoleName=self.role_name
                    )
                    logger.info(f"Role {self.role_name} added to instance profile {profile_name}")
                    
                    return profile_name
                    
                except ClientError as inner_e:
                    handle_error(inner_e, "creating instance profile")
                    return None
            else:
                handle_error(e, "checking instance profile")
                return None

    def create_lambda_role(self, role_name: Optional[str] = None) -> Optional[str]:
        """Create IAM role for Lambda function with minimal required permissions.
        
        Args:
            role_name: Optional name of the Lambda role. If not provided, uses self.lambda_role_name
            
        Returns:
            str: ARN of the created Lambda role or None if creation failed
        """
        role_name = role_name or self.lambda_role_name
        if not self._validate_role_name(role_name):
            logger.error(f"Invalid Lambda role name: {role_name}")
            return None

        logger.info(f"Creating Lambda IAM role: {role_name}")
        
        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=self._create_assume_role_policy(["lambda.amazonaws.com"]),
                Description='Role for Lambda functions with minimal required permissions'
            )
            logger.info(f"Lambda role created: {response['Role']['Arn']}")
            
            # Attach minimal required policies
            policies = [
                'arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess',  # Read-only EC2 access
                'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'  # Basic Lambda execution
            ]
            
            for policy_arn in policies:
                try:
                    self.iam_client.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy_arn
                    )
                    logger.info(f"Attached policy to Lambda role: {policy_arn}")
                except ClientError as e:
                    logger.error(f"Failed to attach policy {policy_arn} to Lambda role: {str(e)}")
                    continue
                
            return response['Role']['Arn']
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                logger.info(f"Lambda role {role_name} already exists")
                try:
                    role = self.iam_client.get_role(RoleName=role_name)
                    return role['Role']['Arn']
                except ClientError as get_error:
                    handle_error(get_error, "getting existing Lambda role")
                    return None
            else:
                handle_error(e, "creating Lambda IAM role")
                return None

    def cleanup_resources(self) -> Dict[str, bool]:
        """Clean up all created IAM resources.
        
        Returns:
            Dict[str, bool]: Dictionary indicating success/failure of cleanup operations
        """
        results = {
            'role_deleted': False,
            'instance_profile_deleted': False,
            'lambda_role_deleted': False
        }
        
        try:
            # Delete Lambda role
            self.iam_client.delete_role(RoleName=self.lambda_role_name)
            results['lambda_role_deleted'] = True
            logger.info(f"Deleted Lambda role: {self.lambda_role_name}")
        except ClientError as e:
            logger.error(f"Failed to delete Lambda role: {str(e)}")
        
        try:
            # Remove role from instance profile
            self.iam_client.remove_role_from_instance_profile(
                InstanceProfileName=self.instance_profile_name,
                RoleName=self.role_name
            )
            logger.info(f"Removed role from instance profile: {self.role_name}")
        except ClientError as e:
            logger.error(f"Failed to remove role from instance profile: {str(e)}")
        
        try:
            # Delete instance profile
            self.iam_client.delete_instance_profile(
                InstanceProfileName=self.instance_profile_name
            )
            results['instance_profile_deleted'] = True
            logger.info(f"Deleted instance profile: {self.instance_profile_name}")
        except ClientError as e:
            logger.error(f"Failed to delete instance profile: {str(e)}")
        
        try:
            # Delete EC2 role
            self.iam_client.delete_role(RoleName=self.role_name)
            results['role_deleted'] = True
            logger.info(f"Deleted role: {self.role_name}")
        except ClientError as e:
            logger.error(f"Failed to delete role: {str(e)}")
        
        return results

    def get_role(self, role_name: str) -> Optional[Dict]:
        """Get details of an IAM role.
        
        Args:
            role_name: Name of the IAM role
            
        Returns:
            Optional[Dict]: Role details if successful, None otherwise
        """
        try:
            response = self.iam_client.get_role(RoleName=role_name)
            return response['Role']
        except ClientError as e:
            handle_error(e, f"getting role {role_name}")
            return None

    def get_instance_profile(self, profile_name: str) -> Optional[Dict]:
        """Get details of an instance profile.
        
        Args:
            profile_name: Name of the instance profile
            
        Returns:
            Optional[Dict]: Profile details if successful, None otherwise
        """
        try:
            response = self.iam_client.get_instance_profile(InstanceProfileName=profile_name)
            return response['InstanceProfile']
        except ClientError as e:
            handle_error(e, f"getting instance profile {profile_name}")
            return None

    def list_roles(self) -> List[Dict]:
        """List all IAM roles.
        
        Returns:
            List[Dict]: List of IAM roles
        """
        try:
            response = self.iam_client.list_roles()
            return response.get('Roles', [])
        except ClientError as e:
            handle_error(e, "listing IAM roles")
            return []

    def list_instance_profiles(self) -> List[Dict]:
        """List all instance profiles.
        
        Returns:
            List[Dict]: List of instance profiles
        """
        try:
            response = self.iam_client.list_instance_profiles()
            return response.get('InstanceProfiles', [])
        except ClientError as e:
            handle_error(e, "listing instance profiles")
            return []

    def add_role_to_instance_profile(self, profile_name: str, role_name: str) -> bool:
        """Add a role to an instance profile.
        
        Args:
            profile_name: Name of the instance profile
            role_name: Name of the IAM role
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.iam_client.add_role_to_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=role_name
            )
            return True
        except ClientError as e:
            handle_error(e, f"adding role {role_name} to profile {profile_name}")
            return False

    def remove_role_from_instance_profile(self, profile_name: str, role_name: str) -> bool:
        """Remove a role from an instance profile.
        
        Args:
            profile_name: Name of the instance profile
            role_name: Name of the IAM role
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.iam_client.remove_role_from_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=role_name
            )
            return True
        except ClientError as e:
            handle_error(e, f"removing role {role_name} from profile {profile_name}")
            return False

    def delete_role(self, role_name: str) -> bool:
        """Delete an IAM role.
        
        Args:
            role_name: Name of the IAM role to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # First, detach all policies from the role
            try:
                policies = self.iam_client.list_attached_role_policies(RoleName=role_name)
                for policy in policies.get('AttachedPolicies', []):
                    self.iam_client.detach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy['PolicyArn']
                    )
            except ClientError as e:
                logger.error(f"Failed to detach policies from role {role_name}: {str(e)}")
                return False

            # Delete the role
            self.iam_client.delete_role(RoleName=role_name)
            logger.info(f"Deleted IAM role: {role_name}")
            return True
        except ClientError as e:
            handle_error(e, f"deleting role {role_name}")
            return False

    def delete_instance_profile(self, profile_name: str) -> bool:
        """Delete an instance profile.
        
        Args:
            profile_name: Name of the instance profile to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # First, remove any roles from the instance profile
            try:
                profile = self.iam_client.get_instance_profile(InstanceProfileName=profile_name)
                for role in profile['InstanceProfile']['Roles']:
                    self.iam_client.remove_role_from_instance_profile(
                        InstanceProfileName=profile_name,
                        RoleName=role['RoleName']
                    )
            except ClientError as e:
                logger.error(f"Failed to remove roles from profile {profile_name}: {str(e)}")
                return False

            # Delete the instance profile
            self.iam_client.delete_instance_profile(InstanceProfileName=profile_name)
            logger.info(f"Deleted instance profile: {profile_name}")
            return True
        except ClientError as e:
            handle_error(e, f"deleting instance profile {profile_name}")
            return False

    def detach_role_policy(self, role_name: str, policy_arn: str) -> bool:
        """Detach a policy from a role.
        
        Args:
            role_name: Name of the IAM role
            policy_arn: ARN of the policy to detach
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.iam_client.detach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            logger.info(f"Detached policy {policy_arn} from role {role_name}")
            return True
        except ClientError as e:
            handle_error(e, f"detaching policy {policy_arn} from role {role_name}")
            return False

    def list_attached_role_policies(self, role_name: str) -> List[Dict]:
        """List all policies attached to a role.
        
        Args:
            role_name: Name of the IAM role
            
        Returns:
            List[Dict]: List of attached policies
        """
        try:
            response = self.iam_client.list_attached_role_policies(RoleName=role_name)
            return response.get('AttachedPolicies', [])
        except ClientError as e:
            handle_error(e, f"listing attached policies for role {role_name}")
            return []

def setup_iam() -> Dict[str, Optional[str]]:
    """Set up all required IAM resources with proper error handling.
    
    Returns:
        Dict[str, Optional[str]]: Dictionary containing ARNs of created resources
    """
    iam_manager = IAMManager()
    
    try:
        # Create role and instance profile
        role_arn = iam_manager.create_ec2_role()
        instance_profile = iam_manager.create_instance_profile()
        lambda_role_arn = iam_manager.create_lambda_role()
        
        return {
            'role_arn': role_arn,
            'instance_profile': instance_profile,
            'lambda_role_arn': lambda_role_arn
        }
    except Exception as e:
        logger.error(f"Failed to set up IAM resources: {str(e)}")
        # Attempt cleanup in case of partial creation
        iam_manager.cleanup_resources()
        return {
            'role_arn': None,
            'instance_profile': None,
            'lambda_role_arn': None
        }