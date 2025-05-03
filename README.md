# AWS Commander - Simple and direct, emphasizing control over AWS resources

A powerful GUI-based tool for managing AWS infrastructure components including EC2, S3, Lambda, and IAM resources.

## Features

- Graphical User Interface (GUI) for easy AWS resource management
- Support for multiple AWS services:
  - EC2 instances
  - S3 buckets
  - Lambda functions
  - IAM resources
- Resource monitoring and management
- Local file management capabilities
- Comprehensive logging system

## Prerequisites

- Python 3.7 or higher
- AWS CLI configured with appropriate credentials
- Required Python packages (see requirements.txt)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/aws_infra_manager.git
cd aws_infra_manager
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Configuration

1. Ensure your AWS credentials are properly configured:
   - Using AWS CLI: `aws configure`
   - Or set environment variables:
     - AWS_ACCESS_KEY_ID
     - AWS_SECRET_ACCESS_KEY
     - AWS_DEFAULT_REGION

2. The application will create necessary directories automatically:
   - logs/
   - templates/
   - config/
   - data/

## Usage

### GUI Mode
Run the application with GUI:
```bash
python main.py --gui
```

### Command Line Mode
List AWS resources:
```bash
python main.py --list ec2
```

Setup AWS resources:
```bash
python main.py --setup all
```

## Project Structure

```
aws_infra_manager/
├── main.py                 # Main application entry point
├── aws_infra_gui.py        # GUI implementation
├── aws_infra_gui_v2.py     # Enhanced GUI implementation
├── requirements.txt        # Python dependencies
├── config/                 # Configuration files
├── scripts/                # Utility scripts
├── templates/             # Template files
├── logs/                  # Application logs
└── data/                  # Data storage
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- AWS SDK for Python (boto3)
- PyQt5 for GUI implementation
- Matplotlib for data visualization

## Support

For support, please open an issue in the GitHub repository or contact the maintainers. 