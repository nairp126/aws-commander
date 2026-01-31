<div align="center">

# AWS Infrastructure Manager

### Your Local Control Plane for AWS Cloud

![Python](https://img.shields.io/badge/Language-Python_3.x-blue?style=for-the-badge&logo=python)
![Framework](https://img.shields.io/badge/GUI-PyQt5-green?style=for-the-badge&logo=qt)
![AWS](https://img.shields.io/badge/Cloud-AWS_Boto3-orange?style=for-the-badge&logo=amazon-aws)
![License](https://img.shields.io/badge/License-MIT-lightgrey?style=for-the-badge)

</div>

---

## 🚀 About The Project

**AWS Infrastructure Manager** is a powerful, hybrid Desktop GUI and CLI tool designed to simplify cloud resource operations. It bridges the gap between complex AWS Console navigation and raw script execution, offering a unified control plane for developers and sysadmins.

**Key Capabilities:**

- **Visual Dashboard**: Monitor EC2, S3, IAM, and Lambda resources in real-time.
- **One-Click Provisioning**: Deploy standardized infrastructure components instantly.
- **Automated Lifecycle**: Manage instance states, volume snapshots, and cleanup tasks.
- **Extensible Plugin System**: Add custom modules without altering the core codebase.

## 🏗️ Architecture

The system follows a modular architecture, separating the Presentation Layer (GUI/CLI) from the Logic Layer (Managers).

```mermaid
graph TD
    User[User] -->|Interacts with| GUI[PyQt5 Interface]
    User -->|Executes| CLI[Command Line Interface]
    
    subgraph "Application Core"
        GUI -->|Calls| Main[main.py Entry Point]
        CLI -->|Calls| Main
        
        Main -->|Initializes| Managers[Resource Managers]
        
        subgraph "Logic Layer (scripts/)"
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

## 📂 Project Structure

```text
d:\aws-commander
├── config/                 # ⚙️ Configuration & Environment Settings
├── docs/                   # 📚 Detailed System Documentation (Phase 1)
├── plugins/                # 🧩 Extensible Plugin Modules
├── scripts/                # 🧠 Core Business Logic & Resource Managers
├── templates/              # 📝 IaC Templates (e.g., Lambda Functions)
├── aws_infra_gui_v2.py     # 🖥️ Main GUI Application Entry Point
└── main.py                 # ⌨️ CLI Entry Point & Orchestrator
```

## 📦 Module Guide

| Module | Description | Documentation |
|:---|:---|:---|
| **`scripts/`** | The "Brain" of the app. Contains `EC2Manager`, `S3Manager`, etc. | [Read the Guide](scripts/README.md) |
| **`config/`** | Centralized settings, `.env` loading, and validation logic. | [Read the Guide](config/README.md) |
| **`templates/`** | Source code for cloud-deployed resources (Infrastructure as Code). | [Read the Guide](templates/README.md) |
| **`plugins/`** | Drop-in folder for extending GUI functionality. | [Read the Guide](plugins/README.md) |

## 🏁 Getting Started

### Prerequisites

- Python 3.8+
- AWS Credentials configured (via `aws configure` or `.env`)

### Installation & Run

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/aws-commander.git

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure Environment
# Copy example.env to .env and fill in your details

# 4. Run the GUI
python main.py --gui

# OR Run via CLI
python main.py setup all
```

## 📚 Documentation

For a deep dive into the system design, please refer to the **Documentation Series**:

1. [**Architecture & Tech Stack**](docs/01_ARCHITECTURE.md): Deep dive into the system design and dependencies.
2. [**Data Model & ERD**](docs/02_DATA_MODEL.md): Visualizing the relationships between EC2, S3, IAM, and Lambda.
3. [**Key Workflows**](docs/03_WORKFLOWS.md): Step-by-step breakdown of critical user journeys.
