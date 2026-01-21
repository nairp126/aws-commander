# AWS Infrastructure Manager - Project Report

---

## 1. Introduction

The **AWS Infrastructure Manager** is a robust, Python-based application designed to provide a unified, user-friendly interface for managing AWS cloud resources. Built with PyQt5, it offers both a graphical user interface (GUI) and command-line interface (CLI) for seamless management of EC2, S3, Lambda, and IAM resources. The project emphasizes modularity, security, and extensibility, supporting both development and production environments.

---

## 2. Brief Overview of Cloud Computing and AWS

**Cloud computing** enables on-demand access to computing resources over the internet, offering scalability, flexibility, and cost efficiency. **Amazon Web Services (AWS)** is the leading cloud platform, providing a vast array of services such as compute (EC2), storage (S3), serverless (Lambda), and identity management (IAM). AWS empowers organizations to deploy, manage, and scale infrastructure with minimal overhead.

---

## 3. Purpose and Scope of the Project

The purpose of this project is to simplify and centralize the management of AWS resources for developers, DevOps engineers, and cloud administrators. The tool aims to:

- Provide a **single-pane-of-glass** for AWS resource management.
- Support both **GUI** and **CLI** workflows.
- Enable **secure, auditable, and efficient** AWS operations.
- Offer extensibility via a **plugin system** for future AWS services.

---

## 4. Project Goals & Objectives

### Functional Goals

- Manage EC2, S3, Lambda, and IAM resources from a single application.
- Support resource creation, deletion, monitoring, and configuration.
- Provide real-time feedback and error reporting.
- Enable multi-account and credential management.
- Support asynchronous operations for responsiveness.

### Technical Goals

- Use **boto3** for AWS SDK integration.
- Implement a **plugin architecture** for extensibility.
- Ensure robust error handling and logging.
- Support secure credential storage and management.
- Provide a responsive, modern GUI with PyQt5.

### Intended Outcomes

- Streamlined AWS resource management.
- Reduced manual effort and risk of misconfiguration.
- Improved visibility into AWS usage and costs.
- Enhanced security and compliance.

---

## 5. AWS Services Used & Their Configurations

### 5.1 IAM Roles and Permissions Setup

- **IAM Roles** are created for EC2 and Lambda with least-privilege policies.
- **Instance Profiles** are managed for EC2.
- **Policies** attached include:
  - `AmazonEC2ReadOnlyAccess`
  - `AmazonS3ReadOnlyAccess`
  - `AWSLambdaBasicExecutionRole`
- **Role creation** (see `scripts/iam_manager.py`):

```python
def create_ec2_role(self, role_name: Optional[str] = None) -> Optional[str]:
    response = self.iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=self._create_assume_role_policy(["ec2.amazonaws.com"]),
        Description='Role for EC2 instances with minimal required permissions'
    )
    # Attach policies...
```

### 5.2 EC2 Instance Configurations

- **Instance Type**: Configurable (default: `t2.micro`)
- **AMI**: Configurable (default: `ami-0c55b159cbfafe1f0`)
- **Key Pair**: Configurable
- **EBS Volumes**: Encrypted, default 8GB, type `gp2`
- **CloudWatch**: Integrated for CPU monitoring and alarms
- **Security Groups**: Configurable
- **VPC/Subnet**: Supported

```python
def launch_instance(self, ami_id, instance_type, ...):
    instance_params = {
        'ImageId': ami_id,
        'InstanceType': instance_type,
        'KeyName': key_name,
        'BlockDeviceMappings': [{
            'DeviceName': '/dev/xvda',
            'Ebs': {'VolumeSize': 8, 'Encrypted': True}
        }]
    }
    instances = self.ec2_resource.create_instances(**instance_params)
```

### 5.3 S3 Bucket Settings and EBS Attachment

- **Bucket Creation**: Region-aware, versioning enabled, AES256 encryption.
- **Lifecycle Policy**: 30-day retention for backups.
- **CORS and ACL**: Supported.
- **EBS**: Volumes can be created, attached, detached, and deleted via the GUI.

```python
def create_bucket(self, bucket_name, region):
    self.s3_client.create_bucket(Bucket=bucket_name, ...)
    self.s3_resource.BucketVersioning(bucket_name).enable()
    self.s3_client.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}
    )
```

### 5.4 Lambda Function Details

- **Deployment**: ZIP-based, Python 3.9 runtime.
- **IAM Role**: Secure execution with minimal permissions.
- **Event Rules**: CloudWatch Events for scheduled triggers.
- **Environment Variables**: Supported.
- **Update/Deletion**: Supported via GUI and CLI.

```python
def deploy_lambda(self, role_arn):
    with open(self.zip_path, 'rb') as f:
        zipped_code = f.read()
    response = self.lambda_client.create_function(
        FunctionName=self.function_name,
        Runtime='python3.9',
        Role=role_arn,
        Handler='lambda_function.lambda_handler',
        Code={'ZipFile': zipped_code},
        ...
    )
```

### 5.5 Other Services Used

- **CloudWatch**: For metrics, alarms, and logging.
- **Cost Explorer, RDS, CloudFront**: Supported via plugins and additional tabs in the GUI.

---

## 6. Implementation Details & Code Snippets

### 6.1 Development Process

1. **Project Setup**: Virtual environment, requirements, and directory structure.
2. **Core Modules**: Implemented for EC2, S3, Lambda, IAM in `scripts/`.
3. **GUI Development**: PyQt5-based, modular tabs for each AWS service.
4. **Plugin System**: Drop-in Python modules for new AWS services.
5. **Async Operations**: QThread/asyncio for non-blocking UI.
6. **Credential Management**: Multi-profile support, secure storage.
7. **Logging & Error Handling**: Centralized, with exportable logs.

### 6.2 Code Samples

**EC2 Instance Launch (with EBS and IAM):**
```python
instance = self.ec2_resource.create_instances(
    ImageId=ami_id,
    InstanceType=instance_type,
    KeyName=key_name,
    IamInstanceProfile={'Name': profile_name},
    BlockDeviceMappings=[{
        'DeviceName': '/dev/xvda',
        'Ebs': {'VolumeSize': 8, 'Encrypted': True}
    }]
)
```

**S3 Bucket Creation with Encryption:**
```python
self.s3_client.create_bucket(Bucket=bucket_name, ...)
self.s3_resource.BucketVersioning(bucket_name).enable()
self.s3_client.put_bucket_encryption(
    Bucket=bucket_name,
    ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}
)
```

**Lambda Deployment:**
```python
response = self.lambda_client.create_function(
    FunctionName=self.function_name,
    Runtime='python3.9',
    Role=role_arn,
    Handler='lambda_function.lambda_handler',
    Code={'ZipFile': zipped_code},
    ...
)
```

**IAM Role Creation:**
```python
response = self.iam_client.create_role(
    RoleName=role_name,
    AssumeRolePolicyDocument=self._create_assume_role_policy(["ec2.amazonaws.com"]),
    Description='Role for EC2 instances with minimal required permissions'
)
```

**CloudWatch Metric Logging:**
```python
self.cloudwatch_client.put_metric_data(
    Namespace='AWS/EC2Manager',
    MetricData=[{
        'MetricName': metric_name,
        'Dimensions': [{'Name': k, 'Value': v} for k, v in dimensions.items()],
        'Value': duration,
        'Unit': 'Seconds',
        'Timestamp': datetime.utcnow()
    }]
)
```

### 6.3 Integration and Automation

- All AWS operations are performed via **boto3**.
- The GUI and CLI both use the same backend logic for consistency.
- Asynchronous operations ensure the GUI remains responsive.
- Plugins can be added for new AWS services without modifying core code.

---

## 7. Challenges Faced & Solutions Implemented

### 7.1 Technical/Configuration Issues

- **AWS Credential Management**: Secure handling via environment variables and profile switching.
- **Resource Cleanup**: Comprehensive cleanup methods for all AWS resources.
- **Error Handling**: Centralized, robust error handling with user feedback.
- **Performance**: Caching and async operations for large resource sets.

### 7.2 Debugging and Resolution

- Extensive logging for all operations.
- Exportable error logs for troubleshooting.
- GUI dialogs for error/info reporting.

---

## 8. Future Improvements

### 8.1 Potential Enhancements

- **Enhanced Monitoring**: Real-time dashboards, custom metrics, cost tracking.
- **Additional AWS Services**: RDS, CloudFront, Route 53, ECS/EKS.
- **UI/UX**: More themes, mobile support, advanced visualizations.
- **Scalability**: Multi-region, auto-scaling, batch operations.
- **Integration**: API Gateway, webhooks, third-party plugins.

---

## 9. Conclusion

The AWS Infrastructure Manager project delivers a powerful, extensible, and user-friendly solution for AWS resource management. By combining a modern GUI, robust backend, and secure practices, it streamlines cloud operations and lays a strong foundation for future growth and integration.

---

**For screenshots:**  
- Open the application (`python main.py --gui`) and capture the main dashboard, EC2/S3/Lambda/IAM tabs, and settings/profile management screens to include in your documentation.

---

**References:**  
- See `README.md` for setup and usage.
- See `AWS_Infrastructure_Manager_Report.md` for additional code and architecture details.
- Explore the `scripts/` directory for all AWS integration logic.

---
