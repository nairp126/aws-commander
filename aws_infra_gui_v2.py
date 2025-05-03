import sys
import time
import os
import logging
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QStatusBar, QMenuBar, QMenu, QAction, QLabel,
    QListWidget, QFormLayout, QListWidgetItem, QPushButton, QHBoxLayout, QFileDialog, QInputDialog, QMessageBox, QTextEdit, QDialog, QDialogButtonBox, QLineEdit, QComboBox, QSpinBox, QGroupBox, QCheckBox
)
from PyQt5.QtCore import Qt, QTimer
from botocore.exceptions import ClientError
from scripts.ec2_manager import EC2Manager
from scripts.lambda_manager import LambdaManager
from scripts.s3_manager import S3Manager
from scripts.iam_manager import IAMManager

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

class StatusBar(QStatusBar):
    def __init__(self):
        super().__init__()
        self.showMessage("Application Ready", 3000)

    def log_message(self, message):
        self.showMessage(message, 5000)

STYLE_SHEET = """
QWidget {
    background-color: #f0f0f0;
    font-family: Arial, sans-serif;
}
QLabel {
 font-size: 12px;
}
QListWidget::item:selected {
    background-color: #a8d0ff; /* Light blue selection color */
}
"""

class BaseTab(QWidget):
    """Base class for all tabs to provide common functionality."""
    def __init__(self):
        super().__init__()
        self._status_bar = None
        self._cache = {}
        self._cache_timeout = 300  # 5 minutes
        self._last_cache_update = {}

    def set_status_bar(self, status_bar):
        """Set the status bar reference."""
        self._status_bar = status_bar

    def log_message(self, message, error=False):
        """Log a message to the status bar if available."""
        if self._status_bar:
            self._status_bar.log_message(message)
        else:
            print(message)  # Fallback to print if status bar not available
        if error:
            logger.error(message)

    def get_cached_data(self, key, fetch_func, force_refresh=False):
        """Get data from cache or fetch if not available or expired."""
        current_time = time.time()
        
        if (not force_refresh and 
            key in self._cache and 
            key in self._last_cache_update and
            current_time - self._last_cache_update[key] < self._cache_timeout):
            return self._cache[key]
            
        try:
            data = fetch_func()
            self._cache[key] = data
            self._last_cache_update[key] = current_time
            return data
        except Exception as e:
            self.log_message(f"Error fetching data for {key}: {str(e)}", error=True)
            if key in self._cache:
                return self._cache[key]  # Return stale data if available
            raise

    def clear_cache(self, key=None):
        """Clear cached data for a specific key or all keys."""
        if key:
            self._cache.pop(key, None)
            self._last_cache_update.pop(key, None)
        else:
            self._cache.clear()
            self._last_cache_update.clear()

    def validate_input(self, value, field_name, custom_validator=None):
        """Validate user input with optional custom validation."""
        if not value:
            self.show_error_dialog("Validation Error", f"{field_name} cannot be empty.")
            return False
            
        if custom_validator and not custom_validator(value):
            self.show_error_dialog("Validation Error", f"Invalid {field_name}.")
            return False
            
        return True

    def show_error_dialog(self, title, message):
        """Show an error dialog to the user."""
        QMessageBox.critical(self, title, message)
        self.log_message(f"Error: {message}", error=True)

    def show_info_dialog(self, title, message):
        """Show an information dialog to the user."""
        QMessageBox.information(self, title, message)
        self.log_message(message)

    def show_confirm_dialog(self, title, message):
        """Show a confirmation dialog to the user."""
        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes

class DashboardTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dashboard")
        self._is_loading = False

        self.ec2_manager = EC2Manager()
        self.s3_manager = S3Manager()
        self.lambda_manager = LambdaManager()
        self.iam_manager = IAMManager()

        self.setup_ui()
        self.refresh_counts()

    def setup_ui(self) -> None:
        """Setup the dashboard UI components."""
        layout = QVBoxLayout()

        title_label = QLabel("<h2>Resource Overview</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        self.ec2_label = QLabel("Total EC2 Instances: Loading...")
        self.s3_label = QLabel("Total S3 Buckets: Loading...")
        self.lambda_label = QLabel("Total Lambda Functions: Loading...")
        self.iam_label = QLabel("Total IAM Users: Loading...")

        layout.addWidget(self.ec2_label)
        layout.addWidget(self.s3_label)
        layout.addWidget(self.lambda_label)
        layout.addWidget(self.iam_label)

        self.start_all_ec2_button = QPushButton("Start All EC2 Instances")
        self.start_all_ec2_button.clicked.connect(self.start_all_ec2_instances)
        layout.addWidget(self.start_all_ec2_button)

        self.setLayout(layout)

    def refresh_counts(self) -> None:
        """Refresh the resource counts on the dashboard."""
        if self._is_loading:
            return

        self._is_loading = True
        self.start_all_ec2_button.setEnabled(False)
        
        try:
            ec2_count = len(self.ec2_manager.list_instances())
            s3_count = len(self.s3_manager.s3_client.list_buckets().get('Buckets', []))
            lambda_count = len(self.lambda_manager.list_functions())
            iam_count = len(self.iam_manager.iam_client.list_users().get('Users', []))

            self.ec2_label.setText(f"Total EC2 Instances: {ec2_count}")
            self.s3_label.setText(f"Total S3 Buckets: {s3_count}")
            self.lambda_label.setText(f"Total Lambda Functions: {lambda_count}")
            self.iam_label.setText(f"Total IAM Users: {iam_count}")
        except Exception as e:
            self.log_message(f"Error refreshing counts: {str(e)}", error=True)
            self.ec2_label.setText("Total EC2 Instances: Error")
            self.s3_label.setText("Total S3 Buckets: Error")
            self.lambda_label.setText("Total Lambda Functions: Error")
            self.iam_label.setText("Total IAM Users: Error")
        finally:
            self._is_loading = False
            self.start_all_ec2_button.setEnabled(True)

    def start_all_ec2_instances(self) -> None:
        """Start all stopped EC2 instances."""
        if self._is_loading:
            return

        self._is_loading = True
        self.start_all_ec2_button.setEnabled(False)
        
        try:
            instances = self.ec2_manager.list_instances()
            stopped_instances = [instance.id for instance in instances if instance.state['Name'] == 'stopped']
            
            if stopped_instances:
                success = self.ec2_manager.start_instance(stopped_instances)
                if success:
                    self.log_message("All stopped EC2 instances started successfully.")
                    self.refresh_counts()
                else:
                    self.log_message("Failed to start some EC2 instances.", error=True)
            else:
                self.log_message("No stopped EC2 instances found.")
        except Exception as e:
            self.log_message(f"Error starting EC2 instances: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self.start_all_ec2_button.setEnabled(True)

    def __del__(self) -> None:
        """Cleanup resources when the tab is destroyed."""
        try:
            self.ec2_manager = None
            self.s3_manager = None
            self.lambda_manager = None
            self.iam_manager = None
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

class EC2Tab(BaseTab):
    def __init__(self):
        super().__init__()
        self.ec2_manager = EC2Manager()
        self._is_loading = False
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """Setup the EC2 tab UI components."""
        layout = QVBoxLayout()
        
        # Instance list
        self.instances_list = QListWidget()
        self.instances_list.itemSelectionChanged.connect(self.display_instance_details)
        layout.addWidget(QLabel("EC2 Instances:"))
        layout.addWidget(self.instances_list)
        
        # Instance details
        self.instance_details = QTextEdit()
        self.instance_details.setReadOnly(True)
        layout.addWidget(QLabel("Instance Details:"))
        layout.addWidget(self.instance_details)
        
        # CloudWatch metrics
        self.metrics_display = QTextEdit()
        self.metrics_display.setReadOnly(True)
        layout.addWidget(QLabel("CloudWatch Metrics:"))
        layout.addWidget(self.metrics_display)
        
        # Performance metrics
        self.performance_display = QTextEdit()
        self.performance_display.setReadOnly(True)
        layout.addWidget(QLabel("Performance Metrics:"))
        layout.addWidget(self.performance_display)
        
        # Volume management
        volume_group = QGroupBox("Volume Management")
        volume_layout = QVBoxLayout()
        
        self.volumes_list = QListWidget()
        self.volumes_list.itemSelectionChanged.connect(self.display_volume_details)
        volume_layout.addWidget(QLabel("Attached Volumes:"))
        volume_layout.addWidget(self.volumes_list)
        
        self.volume_details = QTextEdit()
        self.volume_details.setReadOnly(True)
        volume_layout.addWidget(QLabel("Volume Details:"))
        volume_layout.addWidget(self.volume_details)
        
        volume_buttons = QHBoxLayout()
        self.create_volume_button = QPushButton("Create Volume")
        self.attach_volume_button = QPushButton("Attach Volume")
        self.detach_volume_button = QPushButton("Detach Volume")
        self.delete_volume_button = QPushButton("Delete Volume")
        
        self.create_volume_button.clicked.connect(self.create_volume)
        self.attach_volume_button.clicked.connect(self.attach_volume)
        self.detach_volume_button.clicked.connect(self.detach_volume)
        self.delete_volume_button.clicked.connect(self.delete_volume)
        
        volume_buttons.addWidget(self.create_volume_button)
        volume_buttons.addWidget(self.attach_volume_button)
        volume_buttons.addWidget(self.detach_volume_button)
        volume_buttons.addWidget(self.delete_volume_button)
        
        volume_layout.addLayout(volume_buttons)
        volume_group.setLayout(volume_layout)
        layout.addWidget(volume_group)
        
        # Action buttons
        action_buttons = QHBoxLayout()
        self.create_instance_button = QPushButton("Create Instance")
        self.start_instance_button = QPushButton("Start Instance")
        self.stop_instance_button = QPushButton("Stop Instance")
        self.reboot_instance_button = QPushButton("Reboot Instance")
        self.terminate_instance_button = QPushButton("Terminate Instance")
        
        self.create_instance_button.clicked.connect(self.create_ec2_instance)
        self.start_instance_button.clicked.connect(self.start_selected_instance)
        self.stop_instance_button.clicked.connect(self.stop_selected_instance)
        self.reboot_instance_button.clicked.connect(self.reboot_selected_instance)
        self.terminate_instance_button.clicked.connect(self.terminate_selected_instance)
        
        action_buttons.addWidget(self.create_instance_button)
        action_buttons.addWidget(self.start_instance_button)
        action_buttons.addWidget(self.stop_instance_button)
        action_buttons.addWidget(self.reboot_instance_button)
        action_buttons.addWidget(self.terminate_instance_button)
        
        layout.addLayout(action_buttons)
        self.setLayout(layout)
        
        # Initial refresh
        self.refresh_instances_list()
        
    def refresh_instances_list(self) -> None:
        """Refresh the list of EC2 instances."""
        if self._is_loading:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            instances = self.ec2_manager.list_instances()
            self.instances_list.clear()
            
            for instance in instances:
                item = QListWidgetItem(f"{instance.id} - {instance.state['Name']}")
                item.setData(Qt.UserRole, instance.id)
                self.instances_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing instances list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def _disable_buttons(self) -> None:
        """Disable all action buttons."""
        self.create_instance_button.setEnabled(False)
        self.start_instance_button.setEnabled(False)
        self.stop_instance_button.setEnabled(False)
        self.reboot_instance_button.setEnabled(False)
        self.terminate_instance_button.setEnabled(False)
        self.create_volume_button.setEnabled(False)
        self.attach_volume_button.setEnabled(False)
        self.detach_volume_button.setEnabled(False)
        self.delete_volume_button.setEnabled(False)
        
    def _enable_buttons(self) -> None:
        """Enable all action buttons."""
        self.create_instance_button.setEnabled(True)
        self.start_instance_button.setEnabled(True)
        self.stop_instance_button.setEnabled(True)
        self.reboot_instance_button.setEnabled(True)
        self.terminate_instance_button.setEnabled(True)
        self.create_volume_button.setEnabled(True)
        self.attach_volume_button.setEnabled(True)
        self.detach_volume_button.setEnabled(True)
        self.delete_volume_button.setEnabled(True)
        
    def __del__(self) -> None:
        """Cleanup resources when the tab is destroyed."""
        try:
            self.ec2_manager = None
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def display_instance_details(self):
        """Display details of the selected EC2 instance."""
        selected_items = self.instances_list.selectedItems()
        if not selected_items:
            self.clear_instance_details()
            return
            
        instance_id = selected_items[0].data(Qt.UserRole)
        try:
            details = self.get_cached_data(
                f'ec2_instance_{instance_id}',
                lambda: self.ec2_manager.describe_instance(instance_id)
            )
            
            if details:
                # Display basic instance details
                self.instance_details.setText(
                    f"Instance ID: {details['InstanceId']}\n"
                    f"State: {details['State']['Name']}\n"
                    f"Type: {details['InstanceType']}\n"
                    f"Public IP: {details.get('PublicIpAddress', 'N/A')}\n"
                    f"Private IP: {details.get('PrivateIpAddress', 'N/A')}\n"
                    f"Launch Time: {details['LaunchTime']}\n"
                    f"VPC ID: {details.get('VpcId', 'N/A')}\n"
                    f"Subnet ID: {details.get('SubnetId', 'N/A')}"
                )
                
                # Display CloudWatch metrics
                metrics = self.ec2_manager.get_cloudwatch_metrics(instance_id)
                metrics_text = "CloudWatch Metrics:\n"
                for metric in metrics:
                    metrics_text += f"{metric['MetricName']}: {metric['Value']} {metric['Unit']}\n"
                self.metrics_display.setText(metrics_text)
                
                # Display performance metrics
                performance = self.ec2_manager.get_performance_metrics(instance_id)
                performance_text = "Performance Metrics:\n"
                for metric, value in performance.items():
                    performance_text += f"{metric}: {value}\n"
                self.performance_display.setText(performance_text)
                
                # Refresh volumes list
                self.refresh_volumes_list(instance_id)
            else:
                self.clear_instance_details()
                
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to get instance details: {str(e)}")
            self.clear_instance_details()
            
    def refresh_volumes_list(self, instance_id: str):
        """Refresh the list of volumes attached to the instance."""
        try:
            volumes = self.ec2_manager.list_volumes(instance_id)
            self.volumes_list.clear()
            for volume in volumes:
                item = QListWidgetItem(f"{volume['VolumeId']} - {volume['State']}")
                item.setData(Qt.UserRole, volume)
                self.volumes_list.addItem(item)
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to refresh volumes list: {str(e)}")
            
    def display_volume_details(self):
        """Display details of the selected volume."""
        selected_items = self.volumes_list.selectedItems()
        if not selected_items:
            self.volume_details.clear()
            return
            
        volume = selected_items[0].data(Qt.UserRole)
        try:
            details = self.ec2_manager.describe_volume(volume['VolumeId'])
            if details:
                self.volume_details.setText(
                    f"Volume ID: {details['VolumeId']}\n"
                    f"State: {details['State']}\n"
                    f"Size: {details['Size']} GB\n"
                    f"Type: {details['VolumeType']}\n"
                    f"IOPS: {details.get('Iops', 'N/A')}\n"
                    f"Encrypted: {details['Encrypted']}\n"
                    f"Attached to: {details.get('Attachments', [{}])[0].get('InstanceId', 'N/A')}"
                )
            else:
                self.volume_details.clear()
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to get volume details: {str(e)}")
            self.volume_details.clear()
            
    def create_volume(self):
        """Create a new EBS volume."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create EBS Volume")
        layout = QFormLayout()
        
        size = QSpinBox()
        size.setRange(1, 16384)
        size.setValue(8)
        
        volume_type = QComboBox()
        volume_type.addItems(['gp2', 'gp3', 'io1', 'io2', 'st1', 'sc1'])
        
        iops = QSpinBox()
        iops.setRange(100, 64000)
        iops.setValue(3000)
        
        layout.addRow("Size (GB):", size)
        layout.addRow("Volume Type:", volume_type)
        layout.addRow("IOPS:", iops)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            try:
                volume = self.ec2_manager.create_volume(
                    size=size.value(),
                    volume_type=volume_type.currentText(),
                    iops=iops.value()
                )
                if volume:
                    self.show_info_dialog("Success", f"Volume {volume.id} created successfully")
                    self.refresh_volumes_list(self.get_selected_instance_id())
                else:
                    self.show_error_dialog("Error", "Failed to create volume")
            except Exception as e:
                self.show_error_dialog("Error", f"Error creating volume: {str(e)}")
                
    def attach_volume(self):
        """Attach a volume to the selected instance."""
        selected_items = self.volumes_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a volume to attach")
            return
            
        volume = selected_items[0].data(Qt.UserRole)
        instance_id = self.get_selected_instance_id()
        
        if not instance_id:
            self.show_error_dialog("Error", "Please select an instance first")
            return
            
        try:
            if self.ec2_manager.attach_volume(volume['VolumeId'], instance_id):
                self.show_info_dialog("Success", f"Volume {volume['VolumeId']} attached successfully")
                self.refresh_volumes_list(instance_id)
            else:
                self.show_error_dialog("Error", f"Failed to attach volume {volume['VolumeId']}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error attaching volume: {str(e)}")
            
    def detach_volume(self):
        """Detach a volume from the selected instance."""
        selected_items = self.volumes_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a volume to detach")
            return
            
        volume = selected_items[0].data(Qt.UserRole)
        instance_id = self.get_selected_instance_id()
        
        if not instance_id:
            self.show_error_dialog("Error", "Please select an instance first")
            return
            
        try:
            if self.ec2_manager.detach_volume(volume['VolumeId']):
                self.show_info_dialog("Success", f"Volume {volume['VolumeId']} detached successfully")
                self.refresh_volumes_list(instance_id)
            else:
                self.show_error_dialog("Error", f"Failed to detach volume {volume['VolumeId']}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error detaching volume: {str(e)}")
            
    def delete_volume(self):
        """Delete the selected volume."""
        selected_items = self.volumes_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a volume to delete")
            return
            
        volume = selected_items[0].data(Qt.UserRole)
        
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"Delete volume {volume['VolumeId']}?"):
            return
            
        try:
            if self.ec2_manager.delete_volume(volume['VolumeId']):
                self.show_info_dialog("Success", f"Volume {volume['VolumeId']} deleted successfully")
                self.refresh_volumes_list(self.get_selected_instance_id())
            else:
                self.show_error_dialog("Error", f"Failed to delete volume {volume['VolumeId']}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting volume: {str(e)}")
            
    def get_selected_instance_id(self) -> Optional[str]:
        """Get the ID of the currently selected instance."""
        selected_items = self.instances_list.selectedItems()
        if not selected_items:
            return None
        return selected_items[0].data(Qt.UserRole)
        
    def create_ec2_instance(self):
        """Create a new EC2 instance."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create EC2 Instance")
        layout = QFormLayout()
        
        ami_id = QLineEdit()
        instance_type = QLineEdit()
        key_name = QLineEdit()
        
        # Add instance type validation
        instance_type.textChanged.connect(lambda: self.validate_instance_type(instance_type))
        
        layout.addRow("AMI ID:", ami_id)
        layout.addRow("Instance Type:", instance_type)
        layout.addRow("Key Name:", key_name)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            if not self.validate_input(ami_id.text(), "AMI ID"):
                return
            if not self.validate_input(instance_type.text(), "Instance Type"):
                return
            if not self.validate_input(key_name.text(), "Key Name"):
                return
                
            try:
                instance = self.ec2_manager.launch_instance(
                    ami_id=ami_id.text(),
                    instance_type=instance_type.text(),
                    key_name=key_name.text()
                )
                
                if instance:
                    self.clear_cache('ec2_instances')
                    self.refresh_instances_list()
                    self.show_info_dialog("Success", f"Instance {instance.id} created successfully.")
                else:
                    self.show_error_dialog("Error", "Failed to create instance.")
            except Exception as e:
                self.show_error_dialog("Error", f"Error creating instance: {str(e)}")
                
    def validate_instance_type(self, instance_type_input: QLineEdit):
        """Validate the instance type and provide feedback."""
        instance_type = instance_type_input.text()
        if not instance_type:
            return
            
        is_valid = self.ec2_manager.validate_instance_type(instance_type)
        if is_valid:
            instance_type_input.setStyleSheet("color: green;")
        else:
            instance_type_input.setStyleSheet("color: red;")
            
    def clear_instance_details(self):
        """Clear all instance-related displays."""
        self.instance_details.clear()
        self.metrics_display.clear()
        self.performance_display.clear()
        self.volumes_list.clear()
        self.volume_details.clear()
        
    def start_selected_instance(self):
        """Start the selected EC2 instance."""
        selected_items = self.instances_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select an instance to start.")
            return
            
        instance_id = selected_items[0].data(Qt.UserRole)
        instance = self.ec2_manager.describe_instance(instance_id)
        if not instance:
            self.show_error_dialog("Error", f"Failed to get details for instance {instance_id}")
            return
            
        if instance['State']['Name'] != 'stopped':
            self.show_error_dialog("Error", "Instance must be in stopped state to start.")
            return
            
        if not self.show_confirm_dialog("Confirm Start", f"Start instance {instance_id}?"):
            return
            
        try:
            if self.ec2_manager.start_instance(instance_id):
                self.clear_cache('ec2_instances')
                self.clear_cache(f'ec2_instance_{instance_id}')
                self.refresh_instances_list()
                self.show_info_dialog("Success", f"Instance {instance_id} started successfully.")
            else:
                self.show_error_dialog("Error", f"Failed to start instance {instance_id}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error starting instance: {str(e)}")
            
    def stop_selected_instance(self):
        """Stop the selected EC2 instance."""
        selected_items = self.instances_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select an instance to stop.")
            return
            
        instance_id = selected_items[0].data(Qt.UserRole)
        instance = self.ec2_manager.describe_instance(instance_id)
        if not instance:
            self.show_error_dialog("Error", f"Failed to get details for instance {instance_id}")
            return
            
        if instance['State']['Name'] != 'running':
            self.show_error_dialog("Error", "Instance must be in running state to stop.")
            return
            
        if not self.show_confirm_dialog("Confirm Stop", f"Stop instance {instance_id}?"):
            return
            
        try:
            if self.ec2_manager.stop_instance(instance_id):
                self.clear_cache('ec2_instances')
                self.clear_cache(f'ec2_instance_{instance_id}')
                self.refresh_instances_list()
                self.show_info_dialog("Success", f"Instance {instance_id} stopped successfully.")
            else:
                self.show_error_dialog("Error", f"Failed to stop instance {instance_id}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error stopping instance: {str(e)}")
            
    def reboot_selected_instance(self):
        """Reboot the selected EC2 instance."""
        selected_items = self.instances_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select an instance to reboot.")
            return
            
        instance_id = selected_items[0].data(Qt.UserRole)
        instance = self.ec2_manager.describe_instance(instance_id)
        if not instance:
            self.show_error_dialog("Error", f"Failed to get details for instance {instance_id}")
            return
            
        if instance['State']['Name'] != 'running':
            self.show_error_dialog("Error", "Instance must be in running state to reboot.")
            return
            
        if not self.show_confirm_dialog("Confirm Reboot", f"Reboot instance {instance_id}?"):
            return
            
        try:
            if self.ec2_manager.reboot_instance(instance_id):
                self.clear_cache('ec2_instances')
                self.clear_cache(f'ec2_instance_{instance_id}')
                self.refresh_instances_list()
                self.show_info_dialog("Success", f"Instance {instance_id} rebooted successfully.")
            else:
                self.show_error_dialog("Error", f"Failed to reboot instance {instance_id}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error rebooting instance: {str(e)}")
            
    def terminate_selected_instance(self):
        """Terminate the selected EC2 instance."""
        selected_items = self.instances_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select an instance to terminate.")
            return
            
        instance_id = selected_items[0].data(Qt.UserRole)
        instance = self.ec2_manager.describe_instance(instance_id)
        if not instance:
            self.show_error_dialog("Error", f"Failed to get details for instance {instance_id}")
            return
            
        if not self.show_confirm_dialog("Confirm Termination", 
                                      f"WARNING: This will permanently delete instance {instance_id}. Continue?"):
            return
            
        try:
            if self.ec2_manager.terminate_instance(instance_id):
                self.clear_cache('ec2_instances')
                self.clear_cache(f'ec2_instance_{instance_id}')
                self.refresh_instances_list()
                self.show_info_dialog("Success", f"Instance {instance_id} terminated successfully.")
            else:
                self.show_error_dialog("Error", f"Failed to terminate instance {instance_id}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error terminating instance: {str(e)}")

class S3Tab(BaseTab):
    def __init__(self):
        super().__init__()
        self.s3_manager = S3Manager()
        self._is_loading = False
        self._selected_bucket = None
        self._selected_object = None
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """Setup the S3 tab UI components."""
        layout = QVBoxLayout()
        
        # Bucket management
        bucket_group = QGroupBox("Bucket Management")
        bucket_layout = QVBoxLayout()
        
        self.buckets_list = QListWidget()
        self.buckets_list.itemSelectionChanged.connect(self.on_bucket_selected)
        bucket_layout.addWidget(QLabel("S3 Buckets:"))
        bucket_layout.addWidget(self.buckets_list)
        
        bucket_buttons = QHBoxLayout()
        self.create_bucket_button = QPushButton("Create Bucket")
        self.delete_bucket_button = QPushButton("Delete Bucket")
        
        self.create_bucket_button.clicked.connect(self.create_bucket)
        self.delete_bucket_button.clicked.connect(self.delete_bucket)
        
        bucket_buttons.addWidget(self.create_bucket_button)
        bucket_buttons.addWidget(self.delete_bucket_button)
        
        bucket_layout.addLayout(bucket_buttons)
        bucket_group.setLayout(bucket_layout)
        layout.addWidget(bucket_group)
        
        # Object management
        object_group = QGroupBox("Object Management")
        object_layout = QVBoxLayout()
        
        self.objects_list = QListWidget()
        self.objects_list.itemSelectionChanged.connect(self.on_object_selected)
        object_layout.addWidget(QLabel("Bucket Objects:"))
        object_layout.addWidget(self.objects_list)
        
        object_buttons = QHBoxLayout()
        self.upload_button = QPushButton("Upload File")
        self.download_button = QPushButton("Download File")
        self.delete_object_button = QPushButton("Delete Object")
        
        self.upload_button.clicked.connect(self.upload_selected_file)
        self.download_button.clicked.connect(self.download_selected_file)
        self.delete_object_button.clicked.connect(self.delete_selected_object)
        
        object_buttons.addWidget(self.upload_button)
        object_buttons.addWidget(self.download_button)
        object_buttons.addWidget(self.delete_object_button)
        
        object_layout.addLayout(object_buttons)
        object_group.setLayout(object_layout)
        layout.addWidget(object_group)
        
        self.setLayout(layout)
        
        # Initial refresh
        self.refresh_buckets_list()
        
    def refresh_buckets_list(self) -> None:
        """Refresh the list of S3 buckets."""
        if self._is_loading:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            buckets = self.s3_manager.s3_client.list_buckets().get('Buckets', [])
            self.buckets_list.clear()
            
            for bucket in buckets:
                item = QListWidgetItem(bucket['Name'])
                item.setData(Qt.UserRole, bucket['Name'])
                self.buckets_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing buckets list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def refresh_object_list(self) -> None:
        """Refresh the list of objects in the selected bucket."""
        if self._is_loading or not self._selected_bucket:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            objects = self.s3_manager.s3_client.list_objects_v2(
                Bucket=self._selected_bucket
            ).get('Contents', [])
            
            self.objects_list.clear()
            
            for obj in objects:
                item = QListWidgetItem(obj['Key'])
                item.setData(Qt.UserRole, obj['Key'])
                self.objects_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing objects list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def _disable_buttons(self) -> None:
        """Disable all action buttons."""
        self.create_bucket_button.setEnabled(False)
        self.delete_bucket_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.delete_object_button.setEnabled(False)
        
    def _enable_buttons(self) -> None:
        """Enable all action buttons."""
        self.create_bucket_button.setEnabled(True)
        self.delete_bucket_button.setEnabled(True)
        self.upload_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.delete_object_button.setEnabled(True)
        
    def __del__(self) -> None:
        """Cleanup resources when the tab is destroyed."""
        try:
            self.s3_manager = None
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def on_bucket_selected(self):
        """Handle bucket selection and update UI accordingly."""
        selected_items = self.buckets_list.selectedItems()
        if not selected_items:
            self._selected_bucket = None
            self.objects_list.clear()
            return
            
        self._selected_bucket = selected_items[0].text()
        self.refresh_object_list()
        
    def on_object_selected(self):
        """Handle object selection and update UI accordingly."""
        selected_items = self.objects_list.selectedItems()
        if not selected_items:
            return
            
        self._selected_object = selected_items[0].text()
        
    def create_bucket(self):
        """Create a new S3 bucket."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create S3 Bucket")
        layout = QFormLayout()
        
        bucket_name = QLineEdit()
        region = QComboBox()
        region.addItems(['us-east-1', 'us-west-2', 'ap-south-1', 'ap-southeast-1'])
        
        layout.addRow("Bucket Name:", bucket_name)
        layout.addRow("Region:", region)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            if not self.validate_input(bucket_name.text(), "Bucket Name"):
                return
                
            try:
                if self.s3_manager.create_bucket(
                    bucket_name=bucket_name.text(),
                    region=region.currentText()
                ):
                    self.clear_cache('s3_buckets')
                    self.refresh_buckets_list()
                    self.show_info_dialog("Success", f"Bucket '{bucket_name.text()}' created successfully")
                else:
                    self.show_error_dialog("Error", f"Failed to create bucket '{bucket_name.text()}'")
            except Exception as e:
                self.show_error_dialog("Error", f"Error creating bucket: {str(e)}")
                
    def delete_bucket(self):
        """Delete the selected S3 bucket."""
        if not self._selected_bucket:
            self.show_error_dialog("Error", "Please select a bucket to delete")
            return
            
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"Delete bucket '{self._selected_bucket}'?"):
            return
            
        try:
            if self.s3_manager.delete_bucket(self._selected_bucket):
                self.clear_cache('s3_buckets')
                self.refresh_buckets_list()
                self.show_info_dialog("Success", f"Bucket '{self._selected_bucket}' deleted successfully")
            else:
                self.show_error_dialog("Error", f"Failed to delete bucket '{self._selected_bucket}'")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting bucket: {str(e)}")
            
    def upload_selected_file(self):
        """Upload a file to the selected bucket."""
        if not self._selected_bucket:
            self.show_error_dialog("Error", "Please select a bucket first")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select File to Upload",
            "",
            "All Files (*.*)"
        )
        
        if file_path:
            try:
                if self.s3_manager.upload_file(
                    bucket_name=self._selected_bucket,
                    file_path=file_path
                ):
                    self.refresh_object_list()
                    self.show_info_dialog("Success", f"File uploaded successfully to '{self._selected_bucket}'")
                else:
                    self.show_error_dialog("Error", "Failed to upload file")
            except Exception as e:
                self.show_error_dialog("Error", f"Error uploading file: {str(e)}")
                
    def download_selected_file(self):
        """Download the selected object from the bucket."""
        if not self._selected_object:
            self.show_error_dialog("Error", "Please select an object to download")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            self._selected_object,
            "All Files (*.*)"
        )
        
        if file_path:
            try:
                if self.s3_manager.download_file(
                    bucket_name=self._selected_bucket,
                    object_key=self._selected_object,
                    file_path=file_path
                ):
                    self.show_info_dialog("Success", f"File downloaded successfully to {file_path}")
                else:
                    self.show_error_dialog("Error", "Failed to download file")
            except Exception as e:
                self.show_error_dialog("Error", f"Error downloading file: {str(e)}")
                
    def delete_selected_object(self):
        """Delete the selected object from the bucket."""
        if not self._selected_object:
            self.show_error_dialog("Error", "Please select an object to delete")
            return
            
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"Delete object '{self._selected_object}'?"):
            return
            
        try:
            if self.s3_manager.delete_object(
                bucket_name=self._selected_bucket,
                key=self._selected_object
            ):
                self.refresh_object_list()
                self.show_info_dialog("Success", f"Object '{self._selected_object}' deleted successfully")
            else:
                self.show_error_dialog("Error", f"Failed to delete object '{self._selected_object}'")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting object: {str(e)}")

class LambdaTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.lambda_manager = LambdaManager()
        self._is_loading = False
        self._selected_function = None
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """Setup the Lambda tab UI components."""
        layout = QVBoxLayout()
        
        # Function management
        function_group = QGroupBox("Function Management")
        function_layout = QVBoxLayout()
        
        self.functions_list = QListWidget()
        self.functions_list.itemSelectionChanged.connect(self.display_function_details)
        function_layout.addWidget(QLabel("Lambda Functions:"))
        function_layout.addWidget(self.functions_list)
        
        function_buttons = QHBoxLayout()
        self.create_function_button = QPushButton("Create Function")
        self.update_function_button = QPushButton("Update Function")
        self.delete_function_button = QPushButton("Delete Function")
        
        self.create_function_button.clicked.connect(self.deploy_function)
        self.update_function_button.clicked.connect(self.update_function)
        self.delete_function_button.clicked.connect(self.delete_function)
        
        function_buttons.addWidget(self.create_function_button)
        function_buttons.addWidget(self.update_function_button)
        function_buttons.addWidget(self.delete_function_button)
        
        function_layout.addLayout(function_buttons)
        function_group.setLayout(function_layout)
        layout.addWidget(function_group)
        
        # Function details
        details_group = QGroupBox("Function Details")
        details_layout = QVBoxLayout()
        
        self.function_details = QTextEdit()
        self.function_details.setReadOnly(True)
        details_layout.addWidget(QLabel("Function Details:"))
        details_layout.addWidget(self.function_details)
        
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        # Event rules
        rules_group = QGroupBox("Event Rules")
        rules_layout = QVBoxLayout()
        
        self.rules_list = QListWidget()
        self.rules_list.itemSelectionChanged.connect(self.display_rule_details)
        rules_layout.addWidget(QLabel("Event Rules:"))
        rules_layout.addWidget(self.rules_list)
        
        rules_buttons = QHBoxLayout()
        self.create_rule_button = QPushButton("Create Rule")
        self.delete_rule_button = QPushButton("Delete Rule")
        
        self.create_rule_button.clicked.connect(self.create_event_rule)
        self.delete_rule_button.clicked.connect(self.delete_event_rule)
        
        rules_buttons.addWidget(self.create_rule_button)
        rules_buttons.addWidget(self.delete_rule_button)
        
        rules_layout.addLayout(rules_buttons)
        rules_group.setLayout(rules_layout)
        layout.addWidget(rules_group)
        
        self.setLayout(layout)
        
        # Initial refresh
        self.refresh_functions_list()
        
    def refresh_functions_list(self) -> None:
        """Refresh the list of Lambda functions."""
        if self._is_loading:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            functions = self.lambda_manager.list_functions()
            self.functions_list.clear()
            
            for function_name in functions:
                item = QListWidgetItem(function_name)
                item.setData(Qt.UserRole, function_name)
                self.functions_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing functions list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def refresh_rules_list(self, function_name: str) -> None:
        """Refresh the list of event rules for a function."""
        if self._is_loading or not function_name:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            rules = self.lambda_manager.list_event_rules(function_name)
            self.rules_list.clear()
            
            for rule in rules:
                item = QListWidgetItem(rule['Name'])
                item.setData(Qt.UserRole, rule['Name'])
                self.rules_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing rules list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def _disable_buttons(self) -> None:
        """Disable all action buttons."""
        self.create_function_button.setEnabled(False)
        self.update_function_button.setEnabled(False)
        self.delete_function_button.setEnabled(False)
        self.create_rule_button.setEnabled(False)
        self.delete_rule_button.setEnabled(False)
        
    def _enable_buttons(self) -> None:
        """Enable all action buttons."""
        self.create_function_button.setEnabled(True)
        self.update_function_button.setEnabled(True)
        self.delete_function_button.setEnabled(True)
        self.create_rule_button.setEnabled(True)
        self.delete_rule_button.setEnabled(True)
        
    def __del__(self) -> None:
        """Cleanup resources when the tab is destroyed."""
        try:
            self.lambda_manager = None
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def display_function_details(self):
        """Display details of the selected Lambda function."""
        selected_items = self.functions_list.selectedItems()
        if not selected_items:
            self.clear_function_details()
            return
            
        function_name = selected_items[0].data(Qt.UserRole)
        try:
            details = self.get_cached_data(
                f'lambda_function_{function_name}',
                lambda: self.lambda_manager.get_function(function_name)
            )
            
            if details and 'Configuration' in details:
                config = details['Configuration']
                self.function_details.setText(
                    f"Function Name: {config['FunctionName']}\n"
                    f"Runtime: {config['Runtime']}\n"
                    f"Handler: {config['Handler']}\n"
                    f"Memory Size: {config['MemorySize']} MB\n"
                    f"Timeout: {config['Timeout']} seconds\n"
                    f"Last Modified: {config['LastModified']}\n"
                    f"Role: {config['Role']}\n"
                    f"Description: {config.get('Description', 'N/A')}"
                )
                
                # Refresh event rules
                self.refresh_rules_list(function_name)
            else:
                self.clear_function_details()
                
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to get function details: {str(e)}")
            self.clear_function_details()
            
    def display_rule_details(self):
        """Display details of the selected event rule."""
        selected_items = self.rules_list.selectedItems()
        if not selected_items:
            self.function_details.clear()
            return
            
        rule_name = selected_items[0].data(Qt.UserRole)
        try:
            details = self.lambda_manager.get_event_rule(rule_name)
            if details:
                self.function_details.setText(
                    f"Rule Name: {details['Name']}\n"
                    f"Schedule: {details['ScheduleExpression']}\n"
                    f"State: {details['State']}\n"
                    f"Description: {details.get('Description', 'N/A')}\n"
                    f"Targets: {len(details.get('Targets', []))}"
                )
            else:
                self.function_details.clear()
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to get rule details: {str(e)}")
            self.function_details.clear()
            
    def create_event_rule(self):
        """Create a new event rule for the selected function."""
        selected_items = self.functions_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a function first")
            return
            
        function_name = selected_items[0].data(Qt.UserRole)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Event Rule")
        layout = QFormLayout()
        
        schedule = QLineEdit()
        schedule.setText("rate(1 day)")
        
        layout.addRow("Schedule Expression:", schedule)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            if not self.validate_input(schedule.text(), "Schedule Expression"):
                return
                
            try:
                rule_arn = self.lambda_manager.create_event_rule(
                    function_name=function_name,
                    schedule_expression=schedule.text()
                )
                if rule_arn:
                    self.show_info_dialog("Success", f"Event rule created successfully: {rule_arn}")
                    self.refresh_rules_list(function_name)
                else:
                    self.show_error_dialog("Error", "Failed to create event rule")
            except Exception as e:
                self.show_error_dialog("Error", f"Error creating event rule: {str(e)}")
                
    def delete_event_rule(self):
        """Delete the selected event rule."""
        selected_items = self.rules_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a rule to delete")
            return
            
        rule_name = selected_items[0].data(Qt.UserRole)
        
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"Delete event rule {rule_name}?"):
            return
            
        try:
            if self.lambda_manager.delete_event_rule(rule_name):
                self.show_info_dialog("Success", f"Event rule {rule_name} deleted successfully")
                self.refresh_rules_list(self.get_selected_function_name())
            else:
                self.show_error_dialog("Error", f"Failed to delete event rule {rule_name}")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting event rule: {str(e)}")
            
    def get_selected_function_name(self) -> Optional[str]:
        """Get the name of the currently selected function."""
        selected_items = self.functions_list.selectedItems()
        if not selected_items:
            return None
        return selected_items[0].data(Qt.UserRole)
        
    def deploy_function(self):
        """Deploy a new Lambda function."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Deploy Lambda Function")
        layout = QFormLayout()
        
        function_name = QLineEdit()
        runtime = QComboBox()
        runtime.addItems(['python3.9', 'python3.8', 'python3.7'])
        handler = QLineEdit()
        handler.setText('lambda_function.lambda_handler')
        memory_size = QSpinBox()
        memory_size.setRange(128, 10240)
        memory_size.setSingleStep(64)
        memory_size.setValue(128)
        timeout = QSpinBox()
        timeout.setRange(1, 900)
        timeout.setValue(3)
        
        # Add function name validation
        function_name.textChanged.connect(lambda: self.validate_function_name(function_name))
        
        layout.addRow("Function Name:", function_name)
        layout.addRow("Runtime:", runtime)
        layout.addRow("Handler:", handler)
        layout.addRow("Memory Size (MB):", memory_size)
        layout.addRow("Timeout (seconds):", timeout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            if not self.validate_input(function_name.text(), "Function Name"):
                return
            if not self.validate_input(handler.text(), "Handler"):
                return
                
            try:
                file_path, _ = QFileDialog.getOpenFileName(
                    self, 
                    "Select Python File",
                    "",
                    "Python Files (*.py)"
                )
                
                if file_path:
                    # Create ZIP package
                    if not self.lambda_manager.create_lambda_zip(file_path):
                        self.show_error_dialog("Error", "Failed to create ZIP package")
                        return
                        
                    success = self.lambda_manager.deploy_lambda(
                        function_name=function_name.text(),
                        runtime=runtime.currentText(),
                        handler=handler.text(),
                        memory_size=memory_size.value(),
                        timeout=timeout.value(),
                        code_file=file_path
                    )
                    
                    if success:
                        self.clear_cache('lambda_functions')
                        self.refresh_functions_list()
                        self.show_info_dialog("Success", f"Lambda function '{function_name.text()}' deployed successfully.")
                    else:
                        self.show_error_dialog("Error", f"Failed to deploy Lambda function '{function_name.text()}'.")
            except Exception as e:
                self.show_error_dialog("Error", f"Error deploying Lambda function: {str(e)}")
                
    def validate_function_name(self, function_name_input: QLineEdit):
        """Validate the function name and provide feedback."""
        function_name = function_name_input.text()
        if not function_name:
            return
            
        is_valid = self.lambda_manager._validate_function_name(function_name)
        if is_valid:
            function_name_input.setStyleSheet("color: green;")
        else:
            function_name_input.setStyleSheet("color: red;")
            
    def clear_function_details(self):
        """Clear all function-related displays."""
        self.function_details.clear()
        self.rules_list.clear()
        
    def update_function(self):
        """Update an existing Lambda function."""
        selected_items = self.functions_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a function to update.")
            return
            
        function_name = selected_items[0].data(Qt.UserRole)
        
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Select Python File",
                "",
                "Python Files (*.py)"
            )
            
            if file_path:
                if self.lambda_manager.update_function(
                    function_name=function_name,
                    code_file=file_path
                ):
                    self.clear_cache('lambda_functions')
                    self.clear_cache(f'lambda_function_{function_name}')
                    self.refresh_functions_list()
                    self.show_info_dialog("Success", f"Lambda function '{function_name}' updated successfully.")
                else:
                    self.show_error_dialog("Error", f"Failed to update Lambda function '{function_name}'.")
        except Exception as e:
            self.show_error_dialog("Error", f"Error updating Lambda function: {str(e)}")
            
    def delete_function(self):
        """Delete the selected Lambda function."""
        selected_items = self.functions_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a function to delete.")
            return
            
        function_name = selected_items[0].data(Qt.UserRole)
        
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"WARNING: This will permanently delete function '{function_name}'. Continue?"):
            return
            
        try:
            if self.lambda_manager.delete_function(function_name):
                self.clear_cache('lambda_functions')
                self.clear_cache(f'lambda_function_{function_name}')
                self.refresh_functions_list()
                self.show_info_dialog("Success", f"Lambda function '{function_name}' deleted successfully.")
            else:
                self.show_error_dialog("Error", f"Failed to delete Lambda function '{function_name}'.")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting Lambda function: {str(e)}")

class IAMTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.iam_manager = IAMManager()
        self._is_loading = False
        self._selected_role = None
        self._selected_profile = None
        self.setup_ui()
        
    def setup_ui(self) -> None:
        """Setup the IAM tab UI components."""
        layout = QVBoxLayout()
        
        # Role management
        role_group = QGroupBox("Role Management")
        role_layout = QVBoxLayout()
        
        self.roles_list = QListWidget()
        self.roles_list.itemSelectionChanged.connect(self.display_role_details)
        role_layout.addWidget(QLabel("IAM Roles:"))
        role_layout.addWidget(self.roles_list)
        
        role_buttons = QHBoxLayout()
        self.create_role_button = QPushButton("Create Role")
        self.delete_role_button = QPushButton("Delete Role")
        
        self.create_role_button.clicked.connect(self.create_role)
        self.delete_role_button.clicked.connect(self.delete_role)
        
        role_buttons.addWidget(self.create_role_button)
        role_buttons.addWidget(self.delete_role_button)
        
        role_layout.addLayout(role_buttons)
        role_group.setLayout(role_layout)
        layout.addWidget(role_group)
        
        # Role details
        role_details_group = QGroupBox("Role Details")
        role_details_layout = QVBoxLayout()
        
        self.role_details = QTextEdit()
        self.role_details.setReadOnly(True)
        role_details_layout.addWidget(QLabel("Role Details:"))
        role_details_layout.addWidget(self.role_details)
        
        role_details_group.setLayout(role_details_layout)
        layout.addWidget(role_details_group)
        
        # Instance profile management
        profile_group = QGroupBox("Instance Profile Management")
        profile_layout = QVBoxLayout()
        
        self.profiles_list = QListWidget()
        self.profiles_list.itemSelectionChanged.connect(self.display_profile_details)
        profile_layout.addWidget(QLabel("Instance Profiles:"))
        profile_layout.addWidget(self.profiles_list)
        
        profile_buttons = QHBoxLayout()
        self.create_profile_button = QPushButton("Create Profile")
        self.delete_profile_button = QPushButton("Delete Profile")
        self.add_role_button = QPushButton("Add Role")
        self.remove_role_button = QPushButton("Remove Role")
        
        self.create_profile_button.clicked.connect(self.create_instance_profile)
        self.delete_profile_button.clicked.connect(self.delete_instance_profile)
        self.add_role_button.clicked.connect(self.add_role_to_profile)
        self.remove_role_button.clicked.connect(self.remove_role_from_profile)
        
        profile_buttons.addWidget(self.create_profile_button)
        profile_buttons.addWidget(self.delete_profile_button)
        profile_buttons.addWidget(self.add_role_button)
        profile_buttons.addWidget(self.remove_role_button)
        
        profile_layout.addLayout(profile_buttons)
        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)
        
        # Profile details
        profile_details_group = QGroupBox("Profile Details")
        profile_details_layout = QVBoxLayout()
        
        self.profile_details = QTextEdit()
        self.profile_details.setReadOnly(True)
        profile_details_layout.addWidget(QLabel("Profile Details:"))
        profile_details_layout.addWidget(self.profile_details)
        
        profile_details_group.setLayout(profile_details_layout)
        layout.addWidget(profile_details_group)
        
        self.setLayout(layout)
        
        # Initial refresh
        self.refresh_roles_list()
        self.refresh_profiles_list()
        
    def refresh_roles_list(self) -> None:
        """Refresh the list of IAM roles."""
        if self._is_loading:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            roles = self.iam_manager.iam_client.list_roles().get('Roles', [])
            self.roles_list.clear()
            
            for role in roles:
                item = QListWidgetItem(role['RoleName'])
                item.setData(Qt.UserRole, role['RoleName'])
                self.roles_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing roles list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def refresh_profiles_list(self) -> None:
        """Refresh the list of instance profiles."""
        if self._is_loading:
            return
            
        self._is_loading = True
        self._disable_buttons()
        
        try:
            profiles = self.iam_manager.iam_client.list_instance_profiles().get('InstanceProfiles', [])
            self.profiles_list.clear()
            
            for profile in profiles:
                item = QListWidgetItem(profile['InstanceProfileName'])
                item.setData(Qt.UserRole, profile['InstanceProfileName'])
                self.profiles_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error refreshing profiles list: {str(e)}", error=True)
        finally:
            self._is_loading = False
            self._enable_buttons()
            
    def _disable_buttons(self) -> None:
        """Disable all action buttons."""
        self.create_role_button.setEnabled(False)
        self.delete_role_button.setEnabled(False)
        self.create_profile_button.setEnabled(False)
        self.delete_profile_button.setEnabled(False)
        self.add_role_button.setEnabled(False)
        self.remove_role_button.setEnabled(False)
        
    def _enable_buttons(self) -> None:
        """Enable all action buttons."""
        self.create_role_button.setEnabled(True)
        self.delete_role_button.setEnabled(True)
        self.create_profile_button.setEnabled(True)
        self.delete_profile_button.setEnabled(True)
        self.add_role_button.setEnabled(True)
        self.remove_role_button.setEnabled(True)
        
    def __del__(self) -> None:
        """Cleanup resources when the tab is destroyed."""
        try:
            self.iam_manager = None
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    def display_role_details(self):
        """Display details of the selected IAM role."""
        selected_items = self.roles_list.selectedItems()
        if not selected_items:
            self.role_details.clear()
            return
            
        role_name = selected_items[0].data(Qt.UserRole)
        try:
            details = self.get_cached_data(
                f'iam_role_{role_name}',
                lambda: self.iam_manager.get_role(role_name)
            )
            
            if details:
                self.role_details.setText(
                    f"Role Name: {details['RoleName']}\n"
                    f"ARN: {details['Arn']}\n"
                    f"Create Date: {details['CreateDate']}\n"
                    f"Description: {details.get('Description', 'N/A')}\n"
                    f"Max Session Duration: {details.get('MaxSessionDuration', 'N/A')}\n"
                    f"Path: {details.get('Path', '/')}\n"
                    f"Last Used: {details.get('RoleLastUsed', {}).get('LastUsedDate', 'Never')}\n"
                    f"Attached Policies: {len(details.get('AttachedPolicies', []))}"
                )
            else:
                self.role_details.clear()
                
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to get role details: {str(e)}")
            self.role_details.clear()
            
    def display_profile_details(self):
        """Display details of the selected instance profile."""
        selected_items = self.profiles_list.selectedItems()
        if not selected_items:
            self.profile_details.clear()
            return
            
        profile_name = selected_items[0].data(Qt.UserRole)
        try:
            details = self.get_cached_data(
                f'iam_profile_{profile_name}',
                lambda: self.iam_manager.get_instance_profile(profile_name)
            )
            
            if details:
                self.profile_details.setText(
                    f"Profile Name: {details['InstanceProfileName']}\n"
                    f"ARN: {details['Arn']}\n"
                    f"Create Date: {details['CreateDate']}\n"
                    f"Path: {details.get('Path', '/')}\n"
                    f"Roles: {', '.join([role['RoleName'] for role in details.get('Roles', [])])}"
                )
            else:
                self.profile_details.clear()
                
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to get profile details: {str(e)}")
            self.profile_details.clear()
            
    def create_role(self):
        """Create a new IAM role."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create IAM Role")
        layout = QFormLayout()
        
        role_name = QLineEdit()
        description = QLineEdit()
        role_type = QComboBox()
        role_type.addItems(['EC2', 'Lambda'])
        
        # Add role name validation
        role_name.textChanged.connect(lambda: self.validate_role_name(role_name))
        
        layout.addRow("Role Name:", role_name)
        layout.addRow("Description:", description)
        layout.addRow("Role Type:", role_type)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            if not self.validate_input(role_name.text(), "Role Name"):
                return
                
            try:
                if self.iam_manager.create_role(
                    role_name=role_name.text(),
                    description=description.text(),
                    role_type=role_type.currentText()
                ):
                    self.clear_cache('iam_roles')
                    self.refresh_roles_list()
                    self.show_info_dialog("Success", f"Role '{role_name.text()}' created successfully")
                else:
                    self.show_error_dialog("Error", f"Failed to create role '{role_name.text()}'")
            except Exception as e:
                self.show_error_dialog("Error", f"Error creating role: {str(e)}")
                
    def validate_role_name(self, role_name_input: QLineEdit):
        """Validate the role name and provide feedback."""
        role_name = role_name_input.text()
        if not role_name:
            return
            
        is_valid = self.iam_manager._validate_role_name(role_name)
        if is_valid:
            role_name_input.setStyleSheet("color: green;")
        else:
            role_name_input.setStyleSheet("color: red;")
            
    def delete_role(self):
        """Delete the selected IAM role."""
        selected_items = self.roles_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a role to delete")
            return
            
        role_name = selected_items[0].data(Qt.UserRole)
        
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"Delete role '{role_name}'?"):
            return
            
        try:
            if self.iam_manager.delete_role(role_name):
                self.clear_cache('iam_roles')
                self.clear_cache(f'iam_role_{role_name}')
                self.refresh_roles_list()
                self.show_info_dialog("Success", f"Role '{role_name}' deleted successfully")
            else:
                self.show_error_dialog("Error", f"Failed to delete role '{role_name}'")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting role: {str(e)}")
            
    def create_instance_profile(self):
        """Create a new instance profile."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Instance Profile")
        layout = QFormLayout()
        
        profile_name = QLineEdit()
        path = QLineEdit()
        path.setText('/')
        
        layout.addRow("Profile Name:", profile_name)
        layout.addRow("Path:", path)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addRow(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            if not self.validate_input(profile_name.text(), "Profile Name"):
                return
                
            try:
                if self.iam_manager.create_instance_profile(
                    profile_name=profile_name.text(),
                    path=path.text()
                ):
                    self.clear_cache('iam_profiles')
                    self.refresh_profiles_list()
                    self.show_info_dialog("Success", f"Instance profile '{profile_name.text()}' created successfully")
                else:
                    self.show_error_dialog("Error", f"Failed to create instance profile '{profile_name.text()}'")
            except Exception as e:
                self.show_error_dialog("Error", f"Error creating instance profile: {str(e)}")
                
    def delete_instance_profile(self):
        """Delete the selected instance profile."""
        selected_items = self.profiles_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a profile to delete")
            return
            
        profile_name = selected_items[0].data(Qt.UserRole)
        
        if not self.show_confirm_dialog("Confirm Delete", 
                                      f"Delete instance profile '{profile_name}'?"):
            return
            
        try:
            if self.iam_manager.delete_instance_profile(profile_name):
                self.clear_cache('iam_profiles')
                self.clear_cache(f'iam_profile_{profile_name}')
                self.refresh_profiles_list()
                self.show_info_dialog("Success", f"Instance profile '{profile_name}' deleted successfully")
            else:
                self.show_error_dialog("Error", f"Failed to delete instance profile '{profile_name}'")
        except Exception as e:
            self.show_error_dialog("Error", f"Error deleting instance profile: {str(e)}")
            
    def add_role_to_profile(self):
        """Add a role to the selected instance profile."""
        selected_items = self.profiles_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a profile first")
            return
            
        profile_name = selected_items[0].data(Qt.UserRole)
        
        try:
            roles = self.iam_manager.list_roles()
            if not roles:
                self.show_error_dialog("Error", "No roles available")
                return
                
            role_name, ok = QInputDialog.getItem(
                self,
                "Add Role to Profile",
                "Select role to add:",
                [role['RoleName'] for role in roles],
                0,
                False
            )
            
            if not ok or not role_name:
                return
                
            if self.iam_manager.add_role_to_instance_profile(
                profile_name=profile_name,
                role_name=role_name
            ):
                self.clear_cache(f'iam_profile_{profile_name}')
                self.display_profile_details()
                self.show_info_dialog("Success", f"Role '{role_name}' added to profile successfully")
            else:
                self.show_error_dialog("Error", f"Failed to add role '{role_name}' to profile")
        except Exception as e:
            self.show_error_dialog("Error", f"Error adding role to profile: {str(e)}")
            
    def remove_role_from_profile(self):
        """Remove a role from the selected instance profile."""
        selected_items = self.profiles_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a profile first")
            return
            
        profile_name = selected_items[0].data(Qt.UserRole)
        
        try:
            profile_details = self.iam_manager.get_instance_profile(profile_name)
            if not profile_details or not profile_details.get('Roles'):
                self.show_error_dialog("Error", "No roles attached to this profile")
                return
                
            role_name, ok = QInputDialog.getItem(
                self,
                "Remove Role from Profile",
                "Select role to remove:",
                [role['RoleName'] for role in profile_details['Roles']],
                0,
                False
            )
            
            if not ok or not role_name:
                return
                
            if self.iam_manager.remove_role_from_instance_profile(
                profile_name=profile_details['InstanceProfileName'],
                role_name=role_name
            ):
                self.clear_cache(f'iam_profile_{profile_details["InstanceProfileName"]}')
                self.display_profile_details()
                self.show_info_dialog("Success", f"Role '{role_name}' removed from profile successfully")
            else:
                self.show_error_dialog("Error", f"Failed to remove role '{role_name}' from profile")
        except Exception as e:
            self.show_error_dialog("Error", f"Error removing role from profile: {str(e)}")
            
    def cleanup_resources(self):
        """Clean up unused IAM resources."""
        if not self.show_confirm_dialog("Confirm Cleanup", 
                                      "This will remove all unused IAM resources. Continue?"):
            return
            
        try:
            cleanup_results = self.iam_manager.cleanup_resources()
            if cleanup_results:
                self.clear_cache('iam_roles')
                self.clear_cache('iam_profiles')
                self.refresh_roles_list()
                self.refresh_profiles_list()
                
                result_text = "Cleanup Results:\n"
                for resource_type, count in cleanup_results.items():
                    result_text += f"{resource_type}: {count} removed\n"
                    
                self.show_info_dialog("Success", result_text)
            else:
                self.show_error_dialog("Error", "Failed to cleanup resources")
        except Exception as e:
            self.show_error_dialog("Error", f"Error during cleanup: {str(e)}")

class SettingsTab(BaseTab):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Settings Content"))
        self.setLayout(layout)

class MenuBar(QMenuBar):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        file_menu = QMenu("File", self)
        operations_menu = QMenu("Operations", self)
        settings_menu = QMenu("Settings", self)
        help_menu = QMenu("Help", self)
        about_menu = QMenu("About", self)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.main_window.close)
        file_menu.addAction(exit_action)
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        self.addMenu(file_menu)
        self.addMenu(operations_menu)
        self.addMenu(settings_menu)
        self.addMenu(help_menu)

    def show_about(self):
        self.main_window.log_message("AWS Infrastructure Manager version 1.0.0. Built using Python and PyQt5")


class AWSInfraGUIV2(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AWS Infrastructure Manager")
        self.setStyleSheet(STYLE_SHEET)
        self.setGeometry(100, 100, 1200, 800)

        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)

        self.menu_bar = MenuBar(self)
        self.setMenuBar(self.menu_bar)

        self.tab_widget = QTabWidget()
        
        # Create tabs and set their status bar
        dashboard_tab = DashboardTab()
        dashboard_tab.set_status_bar(self.status_bar)
        self.tab_widget.addTab(dashboard_tab, "Dashboard")
        
        ec2_tab = EC2Tab()
        ec2_tab.set_status_bar(self.status_bar)
        self.tab_widget.addTab(ec2_tab, "EC2")
        
        s3_tab = S3Tab()
        s3_tab.set_status_bar(self.status_bar)
        self.tab_widget.addTab(s3_tab, "S3")
        
        lambda_tab = LambdaTab()
        lambda_tab.set_status_bar(self.status_bar)
        self.tab_widget.addTab(lambda_tab, "Lambda")
        
        iam_tab = IAMTab()
        iam_tab.set_status_bar(self.status_bar)
        self.tab_widget.addTab(iam_tab, "IAM")
        
        settings_tab = SettingsTab()
        settings_tab.set_status_bar(self.status_bar)
        self.tab_widget.addTab(settings_tab, "Settings")

        self.setCentralWidget(self.tab_widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = AWSInfraGUIV2()
    main_window.show()
    sys.exit(app.exec_())