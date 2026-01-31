# 03 - Workflows & API Analysis

## Overview

The application supports two primary modes of interaction:

1. **Command Line Interface (CLI)**: For quick, scriptable actions (headless).
2. **Graphical User Interface (GUI)**: For interactive dashboarding and management.

Both interfaces sit on top of the same underlying **Logic Layer** (`scripts/*.py`), ensuring consistent behavior.

## Critical Workflows

### 1. Resource Discovery & Dashboarding

**Entry Point**: `aws_infra_gui_v2.py` -> `DashboardTab`

- **Flow**:
    1. App initializes and loads `DashboardTab`.
    2. `QTimer` triggers `refresh_counts()` every 30 seconds.
    3. Manager classes (`EC2Manager`, `S3Manager`, etc.) fetch counts from AWS via `boto3`.
    4. Data is displayed in Summary Labels and Matplotlib Charts (Pie/Bar).
- **Key Feature**: Uses `Worker` threads to prevent UI freezing during API calls.

### 2. EC2 Instance Lifecycle Management

**Entry Point**: `aws_infra_gui_v2.py` -> `EC2Tab`

- **Flow**:
    1. User selects the "EC2 Instances" tab.
    2. `list_instances()` is called to populate the list widget.
    3. User selects an instance -> `display_instance_details()` fetches metadata + CloudWatch metrics.
    4. User clicks Action Button (e.g., "Start Instance").
    5. Action is executed asynchronously; Progress Dialog appears.
    6. UI refreshes to reflect new state (e.g., `stopped` -> `pending` -> `running`).

### 3. Infrastructure Setup (Provisioning)

**Entry Point**: `main.py` -> `setup_aws_resources()`

- **Flow**:
    1. User executes `python main.py setup [component]`.
    2. `setup_directories()` ensures local config paths exist.
    3. The specific manager (e.g., `IAMManager`) is invoked.
    4. Resources are checked for existence to be idempotent.
    5. Missing resources (Roles, Buckets, Instances) are created.
    6. Success/Failure is logged to console and `logs/aws_operations.log`.

## API & External Interactions

The application interacts exclusively with the **AWS Cloud API** using the `boto3` SDK.

### Architecture Pattern

- **Manager Classes**: Each AWS Service has a dedicated Manager class (e.g., `S3Manager`) that encapsulates all `boto3` logic.
- **Client Factory**: `scripts.utils.get_client()` handles `boto3` client creation, session management, and region configuration.
- **Error Handling**: `botocore.exceptions.ClientError` is caught in all managers to provide user-friendly error messages instead of stack traces.
- **Async Handling**: The GUI uses `PyQt5.QtCore.QThread` (Worker Node pattern) to offload blocking network calls to background threads.
