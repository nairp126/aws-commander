# Templates Directory

## 1. Purpose

**What it does:** Stores the source code templates for resources that are deployed to the cloud. Currently, it holds the Python code for the Lambda function.

**Why it exists:** This implements a basic form of "Infrastructure as Code" (IaC). Instead of embedding long string literals in the manager classes, the code acts as an external resource that is read, zipped, and deployed at runtime.

## 2. Contents & Key Files

- **`lambda_function.py`**: The template code for the AWS Lambda function.
  - **Logic**: It scans for EC2 instances that have been stopped for more than 24 hours and terminates them to save costs.
  - **Handler**: `lambda_handler(event, context)` is the entry point invoked by AWS Lambda.

## 3. Usage & Implementation

### Inputs

- **File System**: The `LambdaManager` reads this file from disk.

### Outputs

- **Deployment Artifact**: The content of this file is written to a `lambda_function.zip` archive by `scripts.lambda_manager.LambdaManager.create_lambda_zip()`.

### Dependencies

- **Runtime**: This code runs in the AWS Lambda Python 3.9 runtime.
- **Libraries**: Depends on `boto3` (available in Lambda runtime) to interact with EC2.
