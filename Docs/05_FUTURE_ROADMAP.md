# 05 - Future Roadmap

## 🔍 Gap Analysis

Comparing the current **AWS Infrastructure Manager** against industry best practices reveals the following key areas for improvement:

- **Quality Assurance**: `pytest` is included in dependencies, but there is no dedicated `tests/` directory or CI/CD integration.
- **Portability**: The application runs locally but lacks containerization (Docker), making dependency management on different OSs fragile.
- **Security**: Basic IAM roles are created, but there is no support for MFA, assume-role with external accounts, or secret rotation.
- **User Experience**: The GUI is functional but lacks modern touches like Dark Mode toggling (detected but not setting-controllable) or resource filtering/search for S3/Lambda.

---

## 1. Horizon 1: Immediate Improvements

**Focus**: Stability, Hygiene, and "Quick Wins" (Next 1-2 Weeks)

### 1.1 Establish Test Suite

- **Why**: Prevent regression bugs when modifying manager logic.
- **Plan**: Create a `tests/` directory and add unit tests for `scripts/utils.py` and `scripts/ec2_manager.py` using `pytest`.
- **Implementation Hint**: Mock `boto3` calls using `moto`.
  - *Ref*: `scripts/utils.py` (Focus on `get_client` handling).

### 1.2 Input Validation Hardening

- **Why**: Prevent API errors from bad user input.
- **Plan**: Add strict type checking and regex validation to all input fields in the GUI before calling managers.
- **Implementation Hint**: Enhance `BaseTab.validate_input` in `aws_infra_gui_v2.py` to support specific AWS formats (e.g., S3 bucket naming rules).
  - *Ref*: `aws_infra_gui_v2.py`: `BaseTab` class.

### 1.3 Add `.env.example` Template

- **Why**: Security best practice to not commit secrets, but developers need to know what keys to set.
- **Plan**: Create `config/env.example` with dummy values for `AWS_ACCESS_KEY_ID`, `AWS_REGION`, etc.
- **Implementation Hint**: Extract keys from `config/settings.py`.

---

## 2. Horizon 2: Short-Term Goals

**Focus**: Feature Completeness and DevOps Maturity (Next 1-3 Months)

### 2.1 Containerization (Docker Support)

- **Why**: Eliminate "works on my machine" issues.
- **Plan**: Create a `Dockerfile` to package the app. Since it uses PyQt5, this will require X11 forwarding or a switch to a web-based frontend (see Long-Term).
- **Implementation Hint**: Use `python:3.9-slim`, install `requirements.txt`.

### 2.2 CI/CD Pipeline

- **Why**: Automate linting and testing.
- **Plan**: Add `.github/workflows/ci.yml` to run `flake8` and `pytest` on every push.
- **Implementation Hint**: Use `black` check for formatting.
  - *Ref*: `requirements.txt` (Contains `flake8`, `black`).

### 2.3 Enhanced GUI Features

- **Why**: Improve usability.
- **Plan**:
  - Add **Dark/Light Mode Toggle** in the menu bar.
  - Implement **Multi-threading** for all API calls (currently only some use Workers).
  - Add **Search/Filter** bars to S3 and Lambda tabs.
- **Implementation Hint**: `aws_infra_gui_v2.py`: `DashboardTab.update_pie_chart` has theme logic; expose this as a user setting.

---

## 3. Horizon 3: Long-Term Vision

**Focus**: Innovation and Market Differentiation (Blue Sky)

### 3.1 Migration to Web-Based Interface

- **Idea**: Replace PyQt5 with a modern web stack (FastAPI Backend + React Frontend).
- **Benefit**: True cross-platform support, remote access, and easier containerization.
- **Tech**: Reuse `scripts/*` logic as the FastAPI service layer.

### 3.2 AI-Powered Cost Optimization

- **Idea**: Integrate an LLM (like Gemini or GPT) to analyze CloudWatch metrics and Billing data.
- **Benefit**: Proactive suggestions like "Instance i-123 is underutilized; switch to t3.micro to save $20/month."
- **Tech**: new `scripts/ai_advisor.py` module consuming `boto3` Cost Explorer API.

### 3.3 Multi-Account & Cross-Region Control Plane

- **Idea**: Allow managing resources across multiple AWS accounts and regions simultaneously.
- **Benefit**: Enterprise-grade capability.
- **Tech**: Update `utils.create_session` to handle assume-role STS logic for varying profiles.
