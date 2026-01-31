# Scripts Directory

## 1. Purpose

**What it does:** Contains the core logic and operational code for the application. It houses the "Model" and "Controller" logic that interacts directly with AWS services.

**Why it exists:** This folder separates the business logic (AWS interactions) from the Presentation Layer (GUI in `aws_infra_gui_v2.py` / CLI in `main.py`). It ensures code reusability across both interfaces.

## 2. Contents & Key Files

### Resource Managers

- **`ec2_manager.py`**: Manages EC2 instance lifecycle (launch, start, stop, terminate) and EBS volumes.
- **`s3_manager.py`**: Handles S3 bucket creation, configuration (versioning, encryption), and object operations (upload/download).
- **`iam_manager.py`**: Manages Identity and Access Management (Roles, Instance Profiles, Policies).
- **`lambda_manager.py`**: orchestrates Lambda function deployment, updates, and CloudWatch Event triggers.

### Utilities

- **`utils.py`**: Provides shared helper functions for the application, including:
  - **Session Factory**: `create_session()`, `get_client()`, `get_resource()` for Boto3.
  - **Logging**: Singleton logger configuration.
  - **Metrics**: fetching CloudWatch data for RDS and CloudFront.

## 3. Usage & Implementation

### Inputs

Most manager methods accept specific identifiers or configuration parameters:

- **`EC2Manager.launch_instance`**: Accepts `ami_id`, `instance_type`, `key_name`, etc.
- **`S3Manager.create_bucket`**: Accepts `bucket_name` and `region`.

### Outputs

Methods generally return:

- **Success/Failure**: Boolean values (`True`/`False`) or created resource objects (`boto3.resources.factory.ec2.Instance`).
- **Data Structures**: Lists of dictionaries for resource listings (e.g., `list_instances()` returns a list of Instance objects).

### Dependencies

- **External**: `boto3`, `botocore` (AWS SDK).
- **Internal**: `config.settings` for global configuration values.
