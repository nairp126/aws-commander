# 01 - Architecture & Tech Stack

## Tech Stack

### core

- **Language**: Python 3.x
- **SDK**: `boto3` (AWS SDK for Python)
- **GUI Framework**: `PyQt5` (Desktop Interface)

### utilities

- **Visualization**: `matplotlib`, `graphviz`
- **Configuration**: `python-dotenv`
- **HTTP**: `requests`
- **Security**: `cryptography`

### testing & quality

- **Testing**: `pytest`
- **Linting**: `black`, `flake8`

## System Architecture

```mermaid
graph TD
    User[User] -->|Interacts with| GUI[PyQt5 Interface]
    User -->|Executes| CLI[Command Line Interface]
    
    subgraph "Application Core (d:\aws-commander)"
        GUI -->|Calls| Main[main.py Entry Point]
        CLI -->|Calls| Main
        
        Main -->|Initializes| Managers[Resource Managers]
        
        subgraph "Scripts / Logic"
            Managers --> IAM[IAM Manager]
            Managers --> EC2[EC2 Manager]
            Managers --> S3[S3 Manager]
            Managers --> Lambda[Lambda Manager]
        end
        
        Managers -->|Uses| Utils[Utils & Config]
    end
    
    subgraph "External Systems"
        IAM -->|Boto3 API| AWS[AWS Cloud]
        EC2 -->|Boto3 API| AWS
        S3 -->|Boto3 API| AWS
        Lambda -->|Boto3 API| AWS
    end
```

## Project Goal

The **AWS Infrastructure Manager** is a hybrid Desktop GUI and CLI application designed to simplify the management and visualization of AWS Cloud resources.

It aims to provide a local control plane for:

- **Provisioning**: Setting up IAM roles, EC2 instances, S3 buckets, and Lambda functions.
- **Visualization**: Listing and inspecting existing resources.
- **Operations**: Managing common AWS tasks without navigating the AWS Console.
