"""
AWS Infrastructure Manager

A tool to manage AWS infrastructure components including EC2, S3,
Lambda, and IAM resources, providing both a graphical user interface
and command-line options.

This module provides the main entry point for the AWS Infrastructure Manager,
handling both GUI and CLI operations for managing AWS resources.
"""

import os
import sys
import argparse
from typing import Dict, Tuple, Type, Optional, Any
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from scripts.utils import logger, ensure_directory_exists
from config import settings
from aws_infra_gui_v2 import AWSInfraGUIV2


class AWSInfraManagerError(Exception):
    """Base exception class for AWS Infrastructure Manager."""
    pass


def setup_directories() -> None:
    """
    Create necessary directories for the project.
    
    Raises:
        AWSInfraManagerError: If directory creation fails
    """
    directories = [
        os.path.dirname(settings.LOG_FILE),
        os.path.dirname(settings.LOCAL_UPLOAD_FILE),
        settings.LOCAL_DOWNLOAD_DIR,
        "templates",
    ]

    try:
        for directory in directories:
            ensure_directory_exists(directory)
    except Exception as e:
        raise AWSInfraManagerError(f"Failed to create directories: {e}")


def setup_aws_resources(component: str = "all") -> None:
    """
    Set up AWS resources based on the specified component.
    
    Args:
        component: The AWS component to set up (default: "all")
        
    Raises:
        AWSInfraManagerError: If setup fails
        ValueError: If invalid component is specified
    """
    from scripts.iam_manager import setup_iam
    from scripts.ec2_manager import setup_ec2_infrastructure
    from scripts.s3_manager import setup_s3_storage
    from scripts.lambda_manager import setup_lambda

    resource_functions: Dict[str, Tuple[Any, str]] = {
        "iam": (setup_iam, "IAM"),
        "ec2": (setup_ec2_infrastructure, "EC2"),
        "s3": (setup_s3_storage, "S3"),
        "lambda": (setup_lambda, "Lambda"),
    }

    try:
        if component == "all":
            for comp, (func, name) in resource_functions.items():
                logger.info(f"Setting up {name} resources")
                try:
                    func()
                except Exception as e:
                    logger.error(f"Error setting up {name} resources: {e}")
                    raise AWSInfraManagerError(f"Failed to set up {name} resources: {e}")
        elif component in resource_functions:
            func, name = resource_functions[component]
            logger.info(f"Setting up {name} resources")
            try:
                func()
            except Exception as e:
                logger.error(f"Error setting up {name} resources: {e}")
                raise AWSInfraManagerError(f"Failed to set up {name} resources: {e}")
        else:
            raise ValueError(f"Invalid component: {component}")
        
        logger.info("AWS Resources setup completed successfully")
        print("AWS Resources setup completed successfully.")
    except Exception as e:
        logger.error(f"Failed to set up AWS resources: {e}")
        raise AWSInfraManagerError(f"Failed to set up AWS resources: {e}")


def list_aws_resources(resource: str) -> None:
    """
    List AWS resources based on the specified type.
    
    Args:
        resource: The type of resource to list
        
    Raises:
        AWSInfraManagerError: If listing fails
        ValueError: If invalid resource type is specified
    """
    from scripts.ec2_manager import EC2Manager
    from scripts.s3_manager import S3Manager
    from scripts.lambda_manager import LambdaManager

    resource_managers: Dict[str, Tuple[Type[Any], str]] = {
        "ec2": (EC2Manager, "EC2 Instances"),
        "s3": (S3Manager, "S3 Objects"),
        "lambda": (LambdaManager, "Lambda Functions"),
    }

    try:
        if resource in resource_managers:
            manager_class, resource_name = resource_managers[resource]
            manager = manager_class()
            try:
                resources = manager.list_resources()
                print(f"\n{resource_name}:")
                if not resources:
                    print("  No resources found")
                else:
                    for resource in resources:
                        print(f"  - {resource}")
            except Exception as e:
                logger.error(f"Error listing {resource_name}: {e}")
                raise AWSInfraManagerError(f"Failed to list {resource_name}: {e}")
        else:
            raise ValueError(f"Invalid resource type: {resource}")
    except Exception as e:
        logger.error(f"Failed to list AWS resources: {e}")
        raise AWSInfraManagerError(f"Failed to list AWS resources: {e}")


def start_gui() -> None:
    """
    Start the GUI application.
    
    Raises:
        AWSInfraManagerError: If GUI initialization fails
    """
    try:
        app = QApplication(sys.argv)
        window = AWSInfraGUIV2()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(f"Failed to start GUI: {e}")
        raise AWSInfraManagerError(f"Failed to start GUI: {e}")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed command line arguments
        
    Raises:
        SystemExit: If invalid arguments are provided
    """
    parser = argparse.ArgumentParser(
        description="AWS Infrastructure Manager - A tool to manage AWS resources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --gui                - Start the GUI
  python main.py setup all            - Set up all AWS infrastructure components
  python main.py setup iam            - Set up only IAM resources
  python main.py setup ec2            - Set up only EC2 resources
  python main.py setup s3             - Set up only S3 resources
  python main.py setup lambda         - Set up only Lambda resources
  python main.py list ec2             - List EC2 instances
  python main.py list s3              - List S3 objects
  python main.py list lambda          - List Lambda functions
        """
    )
    
    parser.add_argument(
        "--gui", 
        action="store_true", 
        help="Start the graphical user interface"
    )

    subparsers = parser.add_subparsers(
        dest="command", 
        help="Command to execute", 
        required=False
    )

    # Setup commands
    setup_parser = subparsers.add_parser(
        "setup", 
        help="Set up AWS infrastructure"
    )
    setup_parser.add_argument(
        "component",
        nargs="?",
        choices=["all", "iam", "ec2", "s3", "lambda"],
        default="all",
        help="Component to set up (default: all)",
    )

    # List commands
    list_parser = subparsers.add_parser(
        "list", 
        help="List AWS resources"
    )
    list_parser.add_argument(
        "resource",
        choices=["ec2", "s3", "lambda"],
        help="Resource type to list",
    )

    return parser.parse_args()


def main() -> None:
    """
    Main entry point for the AWS Infrastructure Manager.
    
    Handles command line arguments and executes the appropriate actions.
    """
    try:
        setup_directories()
        args = parse_arguments()

        if args.gui:
            start_gui()
        elif args.command == "setup":
            setup_aws_resources(args.component)
        elif args.command == "list":
            list_aws_resources(args.resource)
        else:
            print("AWS Infrastructure Manager")
            print("\nUsage examples:")
            print("  python main.py --gui                - Start the GUI")
            print("  python main.py setup all            - Set up all AWS infrastructure components")
            print("  python main.py setup iam            - Set up only IAM resources")
            print("  python main.py setup ec2            - Set up only EC2 resources")
            print("  python main.py setup s3             - Set up only S3 resources")
            print("  python main.py setup lambda         - Set up only Lambda resources")
            print("  python main.py list ec2             - List EC2 instances")
            print("  python main.py list s3              - List S3 objects")
            print("  python main.py list lambda          - List Lambda functions")
    except AWSInfraManagerError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
