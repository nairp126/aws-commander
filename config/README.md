# Config Directory

## 1. Purpose

**What it does:** Centralizes the application's configuration settings, environment variable management, and validation logic.

**Why it exists:** It creates a single source of truth for runtime behavior, decoupling configuration from code and ensuring that the application fails fast if required settings (like AWS region) are missing.

## 2. Contents & Key Files

- **`settings.py`**: The primary configuration module. It performs several key roles:
  - **Environment Loading**: Uses `python-dotenv` to load variables from a `.env` file.
  - **Variable Mapping**: Maps environment variables (e.g., `AWS_REGION`) to Python constants.
  - **Validation**: Includes `validate_config()` to check for required fields and correct formats (e.g., Regex for S3 buckets and Security Groups).
  - **Defaults**: Defines sensible default values for optional settings.

## 3. Usage & Implementation

### Inputs

This module reads primarily from:

- **Environment Variables**: `os.environ` (populated via `.env`).
- **File System**: Checks for the existence of directories (logs, data).

### Outputs

- **Module Constants**: Exports typed constants like `AWS_REGION`, `EC2_INSTANCE_TYPE`, `S3_BUCKET_NAME`.
- **Validation Exceptions**: Raises `ValidationError` or `AWSConfigurationError` if the configuration is invalid.

### Dependencies

- **External**: `python-dotenv` (for `.env` parsing).
- **Internal**: `logging` (to report validation status).

### Example Usage

```python
from config import settings

print(settings.AWS_REGION)
# Output: 'us-east-1' (or value from .env)
```
