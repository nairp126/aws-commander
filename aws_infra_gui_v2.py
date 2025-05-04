import sys
print("sys imported")
import time
print("time imported")
import os
print("os imported")
import logging
print("logging imported")
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QStatusBar, QMenuBar, QMenu, QAction, QLabel,
    QListWidget, QFormLayout, QListWidgetItem, QPushButton, QHBoxLayout, QFileDialog, QInputDialog, QMessageBox, QTextEdit, QDialog, QDialogButtonBox, QLineEdit, QComboBox, QSpinBox, QGroupBox, QCheckBox, QPlainTextEdit
)
print("PyQt5 imported")
from PyQt5.QtCore import Qt, QTimer, QEvent, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QKeySequence, QPixmap
from botocore.exceptions import ClientError
from scripts.ec2_manager import EC2Manager
print("EC2Manager imported")
from scripts.lambda_manager import LambdaManager
print("LambdaManager imported")
from scripts.s3_manager import S3Manager
print("S3Manager imported")
from scripts.iam_manager import IAMManager
print("IAMManager imported")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
print("matplotlib FigureCanvas imported")
import matplotlib.pyplot as plt
print("matplotlib.pyplot imported")
import boto3
from botocore.exceptions import ClientError as BotoClientError
from scripts.utils import get_client, get_rds_metrics, get_cloudfront_metrics, get_cost_explorer_data
import json
from datetime import datetime, timedelta
import importlib.util
import glob
import tempfile
from graphviz import Digraph
from cryptography.fernet import Fernet

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# Add at the top, after STYLE_SHEET
LIGHT_STYLE_SHEET = """
QWidget {
    background-color: #f0f0f0;
    font-family: Arial, sans-serif;
}
QLabel {
font-size: 12px;
}
QListWidget::item:selected {
    background-color: #a8d0ff;
}
"""

DARK_STYLE_SHEET = """
QWidget {
    background-color: #232629;
    color: #f0f0f0;
    font-family: Arial, sans-serif;
}
QLabel {
font-size: 12px;
color: #f0f0f0;
}
QListWidget::item:selected {
    background-color: #3a7bd5;
    color: #ffffff;
}
QPushButton {
    background-color: #444a52;
    color: #f0f0f0;
    border: 1px solid #3a7bd5;
    border-radius: 4px;
    padding: 4px 8px;
}
QPushButton:hover {
    background-color: #3a7bd5;
    color: #ffffff;
}
QTabWidget::pane {
    border: 1px solid #3a7bd5;
}
QTabBar::tab {
    background: #232629;
    color: #f0f0f0;
    padding: 6px;
}
QTabBar::tab:selected {
    background: #3a7bd5;
    color: #ffffff;
}
"""

# Global error log for export
ERROR_LOG = []

class StatusBar(QStatusBar):
    def __init__(self):
        super().__init__()
        self.showMessage("Application Ready", 3000)

    def log_message(self, message):
        self.showMessage(message, 5000)

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
        # Try to get main window for notifications
        self._main_window = self.window() if hasattr(self.window(), 'notify') else None

    def log_message(self, message, error=False):
        """Log a message to the status bar if available."""
        if self._status_bar:
            self._status_bar.log_message(message)
        if hasattr(self, '_main_window') and self._main_window and hasattr(self._main_window, 'notify'):
            self._main_window.notify(message, level="error" if error else "info")
        else:
            print(message)
        if error:
            logger.error(message)
            ERROR_LOG.append(f"{datetime.now()}: {message}")

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
        self.custom_metrics = []  # Store user-defined custom metrics
        self.refresh_interval = 30  # seconds
        self.setup_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_counts)
        self.timer.start(self.refresh_interval * 1000)

    def setup_ui(self) -> None:
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
        # Add matplotlib pie chart
        self.figure, self.ax = plt.subplots(figsize=(4, 3))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        # Add matplotlib bar chart
        self.bar_figure, self.bar_ax = plt.subplots(figsize=(4, 3))
        self.bar_canvas = FigureCanvas(self.bar_figure)
        layout.addWidget(self.bar_canvas)
        self.start_all_ec2_button = QPushButton("Start All EC2 Instances")
        self.start_all_ec2_button.clicked.connect(self.start_all_ec2_instances)
        layout.addWidget(self.start_all_ec2_button)
        # Custom Metrics Section
        custom_group = QGroupBox("Custom CloudWatch Metrics")
        custom_layout = QVBoxLayout()
        form = QFormLayout()
        self.ns_input = QLineEdit(); self.ns_input.setPlaceholderText('AWS/EC2')
        self.metric_input = QLineEdit(); self.metric_input.setPlaceholderText('CPUUtilization')
        self.dim_input = QLineEdit(); self.dim_input.setPlaceholderText('Name=InstanceId,Value=i-xxxx')
        self.period_input = QSpinBox(); self.period_input.setRange(60, 3600); self.period_input.setValue(300)
        self.stat_input = QLineEdit(); self.stat_input.setPlaceholderText('Average')
        form.addRow("Namespace:", self.ns_input)
        form.addRow("Metric Name:", self.metric_input)
        form.addRow("Dimensions:", self.dim_input)
        form.addRow("Period (sec):", self.period_input)
        form.addRow("Statistic:", self.stat_input)
        custom_layout.addLayout(form)
        self.add_metric_btn = QPushButton("Add Custom Metric")
        self.add_metric_btn.clicked.connect(self.add_custom_metric)
        custom_layout.addWidget(self.add_metric_btn)
        self.custom_metrics_list = QListWidget()
        self.custom_metrics_list.itemSelectionChanged.connect(self.display_custom_metric)
        custom_layout.addWidget(self.custom_metrics_list)
        self.custom_figure, self.custom_ax = plt.subplots(figsize=(4, 2))
        self.custom_canvas = FigureCanvas(self.custom_figure)
        custom_layout.addWidget(self.custom_canvas)
        custom_group.setLayout(custom_layout)
        layout.addWidget(custom_group)
        self.setLayout(layout)
        self.refresh_counts()  # Now called after all widgets are created

    def on_interval_changed(self, val):
        self.refresh_interval = val
        self.timer.setInterval(self.refresh_interval * 1000)

    def add_custom_metric(self):
        ns = self.ns_input.text().strip()
        metric = self.metric_input.text().strip()
        dims = self.dim_input.text().strip()
        period = self.period_input.value()
        stat = self.stat_input.text().strip()
        if not ns or not metric or not stat:
            self.show_error_dialog("Validation Error", "Namespace, Metric Name, and Statistic are required.")
            return
        dims_list = []
        if dims:
            for d in dims.split(';'):
                parts = d.split(',')
                dim = {}
                for p in parts:
                    if '=' in p:
                        k, v = p.split('=', 1)
                        dim[k.strip()] = v.strip()
                if dim:
                    dims_list.append(dim)
        query = {
            'namespace': ns,
            'metric_name': metric,
            'dimensions': dims_list,
            'period': period,
            'stat': stat
        }
        self.custom_metrics.append(query)
        self.custom_metrics_list.addItem(f"{ns}/{metric} [{stat}]")
        self.log_message(f"Added custom metric: {ns}/{metric} [{stat}]")
        self.display_custom_metric()

    def display_custom_metric(self):
        idx = self.custom_metrics_list.currentRow()
        if idx < 0 or idx >= len(self.custom_metrics):
            self.custom_ax.clear()
            self.custom_canvas.draw()
            return
        query = self.custom_metrics[idx]
        from scripts.utils import get_custom_cloudwatch_metric
        data = get_custom_cloudwatch_metric(
            query['namespace'], query['metric_name'], query['dimensions'], query['period'], query['stat']
        )
        self.custom_ax.clear()
        if data:
            data = sorted(data, key=lambda x: x['Timestamp'])
            times = [d['Timestamp'] for d in data]
            values = [d.get(query['stat'], 0) for d in data]
            self.custom_ax.plot(times, values, label=f"{query['metric_name']} [{query['stat']}]")
            self.custom_ax.legend()
        self.custom_ax.set_title(f"Custom Metric: {query['namespace']}/{query['metric_name']}")
        self.custom_figure.tight_layout()
        self.custom_canvas.draw()

    def refresh_counts(self) -> None:
        """Refresh the resource counts on the dashboard."""
        if self._is_loading:
            return
        self._is_loading = True
        # Defensive: Only disable button if it exists
        if hasattr(self, 'start_all_ec2_button') and self.start_all_ec2_button:
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
            # Update pie and bar charts
            self.update_pie_chart(ec2_count, s3_count, lambda_count, iam_count)
            self.update_bar_chart(ec2_count, s3_count, lambda_count, iam_count)
        except Exception as e:
            self.log_message(f"Error refreshing counts: {str(e)}", error=True)
            self.ec2_label.setText("Total EC2 Instances: Error")
            self.s3_label.setText("Total S3 Buckets: Error")
            self.lambda_label.setText("Total Lambda Functions: Error")
            self.iam_label.setText("Total IAM Users: Error")
            self.update_pie_chart(0, 0, 0, 0)
            self.update_bar_chart(0, 0, 0, 0)
        finally:
            self._is_loading = False
            if hasattr(self, 'start_all_ec2_button') and self.start_all_ec2_button:
                self.start_all_ec2_button.setEnabled(True)

    def update_pie_chart(self, ec2_count, s3_count, lambda_count, iam_count):
        self.ax.clear()
        labels = ['EC2', 'S3', 'Lambda', 'IAM']
        sizes = [ec2_count, s3_count, lambda_count, iam_count]
        colors_light = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2']
        colors_dark = ['#6baed6', '#fd8d3c', '#fc9272', '#9ecae1']
        parent = self.parentWidget()
        theme = 'light'
        if parent and hasattr(parent, 'window'):
            win = parent.window()
            if hasattr(win, 'current_theme'):
                theme = win.current_theme
        elif hasattr(self, 'window') and hasattr(self.window(), 'current_theme'):
            theme = self.window().current_theme
        colors = colors_dark if theme == 'dark' else colors_light
        if not any(sizes):
            self.ax.pie([1], labels=["No Data"], colors=['#cccccc'])
        else:
            self.ax.pie(
                sizes, labels=labels, autopct='%1.0f', startangle=90, colors=colors, textprops={'color': '#f0f0f0' if theme == 'dark' else '#232629'}
            )
        self.ax.axis('equal')
        self.figure.tight_layout()
        self.canvas.draw()

    def update_bar_chart(self, ec2_count, s3_count, lambda_count, iam_count):
        self.bar_ax.clear()
        labels = ['EC2', 'S3', 'Lambda', 'IAM']
        counts = [ec2_count, s3_count, lambda_count, iam_count]
        colors_light = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2']
        colors_dark = ['#6baed6', '#fd8d3c', '#fc9272', '#9ecae1']
        parent = self.parentWidget()
        theme = 'light'
        if parent and hasattr(parent, 'window'):
            win = parent.window()
            if hasattr(win, 'current_theme'):
                theme = win.current_theme
        elif hasattr(self, 'window') and hasattr(self.window(), 'current_theme'):
            theme = self.window().current_theme
        colors = colors_dark if theme == 'dark' else colors_light
        bar_color = colors
        edge_color = '#f0f0f0' if theme == 'dark' else '#232629'
        if not any(counts):
            self.bar_ax.bar(["No Data"], [1], color='#cccccc', edgecolor=edge_color)
            self.bar_ax.set_ylabel('Resource Count', color=edge_color)
            self.bar_ax.set_title('Resource Counts', color=edge_color)
            self.bar_ax.tick_params(axis='x', colors=edge_color)
            self.bar_ax.tick_params(axis='y', colors=edge_color)
        else:
            bars = self.bar_ax.bar(labels, counts, color=bar_color, edgecolor=edge_color)
            self.bar_ax.set_ylabel('Resource Count', color=edge_color)
            self.bar_ax.set_title('Resource Counts', color=edge_color)
            self.bar_ax.tick_params(axis='x', colors=edge_color)
            self.bar_ax.tick_params(axis='y', colors=edge_color)
            for spine in self.bar_ax.spines.values():
                spine.set_edgecolor(edge_color)
            for bar in bars:
                height = bar.get_height()
                self.bar_ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom', color=edge_color, fontsize=10)
        self.bar_figure.tight_layout()
        self.bar_canvas.draw()

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
        self.worker = None
        self.setup_ui()
        
    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search EC2 Instances...")
        self.search_bar.textChanged.connect(self.filter_instances_list)
        layout.addWidget(self.search_bar)
        # Export/Import buttons
        export_import_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export List")
        self.import_btn = QPushButton("Import List")
        self.export_btn.clicked.connect(self.export_instances)
        self.import_btn.clicked.connect(self.import_instances)
        export_import_layout.addWidget(self.export_btn)
        export_import_layout.addWidget(self.import_btn)
        layout.addLayout(export_import_layout)
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
        
    def filter_instances_list(self):
        text = self.search_bar.text().lower()
        for i in range(self.instances_list.count()):
            item = self.instances_list.item(i)
            item.setHidden(text not in item.text().lower())
        
    def refresh_instances_list(self) -> None:
        if self._is_loading:
            return
        self._is_loading = True
        self._disable_buttons()
        self.instances_list.clear()
        # Show progress dialog
        self.progress_dialog = QMessageBox(self)
        self.progress_dialog.setWindowTitle("Loading EC2 Instances")
        self.progress_dialog.setText("Fetching EC2 instances from AWS...")
        self.progress_dialog.setStandardButtons(QMessageBox.NoButton)
        self.progress_dialog.show()
        # Use Worker thread
        self.worker = Worker(self.ec2_manager.list_instances)
        self.worker.finished.connect(self._on_instances_loaded)
        self.worker.error.connect(self._on_instances_error)
        self.worker.start()

    def _on_instances_loaded(self, instances):
        self.progress_dialog.hide()
        self.instances_list.clear()
        for instance in instances:
            item = QListWidgetItem(f"{instance.id} - {instance.state['Name']}")
            item.setData(Qt.UserRole, instance.id)
            self.instances_list.addItem(item)
        self._is_loading = False
        self._enable_buttons()

    def _on_instances_error(self, e):
        self.progress_dialog.hide()
        self.log_message(f"Error refreshing instances list: {str(e)}", error=True)
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

    def export_instances(self):
        instances = []
        for i in range(self.instances_list.count()):
            item = self.instances_list.item(i)
            if not item.isHidden():
                instances.append(item.text())
        file_path, _ = QFileDialog.getSaveFileName(self, "Export EC2 Instances", "ec2_instances.json", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(instances, f, indent=2)
            self.show_info_dialog("Export", f"Exported {len(instances)} EC2 instances to {file_path}")
    def import_instances(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import EC2 Instances", "", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.show_info_dialog("Import", f"Imported {len(data)} EC2 instances from {file_path}\n(Import does not create resources)")

class S3Tab(BaseTab):
    def __init__(self):
        super().__init__()
        self.worker = None  # Ensure worker is defined before any method uses it
        self.s3_manager = S3Manager()
        self._is_loading = False
        self._selected_bucket = None
        self._selected_object = None
        self.setup_ui()
        self.refresh_buckets_list()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self._selected_bucket:
            self.show_error_dialog("Error", "Please select a bucket before uploading files.")
            return
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path:
                try:
                    if self.s3_manager.upload_file(
                        bucket_name=self._selected_bucket,
                        file_path=file_path
                    ):
                        self.refresh_object_list()
                        self.show_info_dialog("Success", f"File uploaded successfully to '{self._selected_bucket}'")
                    else:
                        self.show_error_dialog("Error", f"Failed to upload file {file_path}")
                except Exception as e:
                    self.show_error_dialog("Error", f"Error uploading file: {str(e)}")
        event.acceptProposedAction()

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        # Search bar for buckets
        self.bucket_search_bar = QLineEdit()
        self.bucket_search_bar.setPlaceholderText("Search Buckets...")
        self.bucket_search_bar.textChanged.connect(self.filter_buckets_list)
        layout.addWidget(self.bucket_search_bar)
        # Export/Import buttons
        export_import_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export Buckets")
        self.import_btn = QPushButton("Import Buckets")
        self.export_btn.clicked.connect(self.export_buckets)
        self.import_btn.clicked.connect(self.import_buckets)
        export_import_layout.addWidget(self.export_btn)
        export_import_layout.addWidget(self.import_btn)
        layout.addLayout(export_import_layout)
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
        
    def filter_buckets_list(self):
        text = self.bucket_search_bar.text().lower()
        for i in range(self.buckets_list.count()):
            item = self.buckets_list.item(i)
            item.setHidden(text not in item.text().lower())
        
    def refresh_buckets_list(self):
        self.log_message("Loading S3 buckets...")
        self._disable_buttons()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self.worker = AsyncWorker(self.s3_manager.list_buckets)
        self.worker.finished.connect(self._on_buckets_loaded)
        self.worker.error.connect(self._on_buckets_error)
        self.worker.start()

    def _on_buckets_loaded(self, buckets):
        self._enable_buttons()
        self.log_message(f"Loaded {len(buckets) if buckets else 0} S3 buckets.")
        self.buckets_list.clear()
        if not buckets or not isinstance(buckets, list):
            return
        for bucket in buckets:
            item = QListWidgetItem(bucket['Name'])
            item.setData(Qt.UserRole, bucket['Name'])
            self.buckets_list.addItem(item)

    def _on_buckets_error(self, e):
        self._enable_buttons()
        self.show_error_dialog("Error loading S3 buckets", str(e))

    def cancel_loading(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log_message("Cancelled S3 bucket loading.")
            
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

    def export_buckets(self):
        buckets = []
        for i in range(self.buckets_list.count()):
            item = self.buckets_list.item(i)
            if not item.isHidden():
                buckets.append(item.text())
        file_path, _ = QFileDialog.getSaveFileName(self, "Export S3 Buckets", "s3_buckets.json", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(buckets, f, indent=2)
            self.show_info_dialog("Export", f"Exported {len(buckets)} S3 buckets to {file_path}")
    def import_buckets(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import S3 Buckets", "", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.show_info_dialog("Import", f"Imported {len(data)} S3 buckets from {file_path}\n(Import does not create resources)")

class LambdaTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.worker = None  # Ensure worker is defined before any method uses it
        self.lambda_manager = LambdaManager()
        self._is_loading = False
        self._selected_function = None
        self.setup_ui()
        self.refresh_functions_list()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        selected_items = self.functions_list.selectedItems()
        if not selected_items:
            self.show_error_dialog("Error", "Please select a Lambda function before deploying.")
            return
        function_name = selected_items[0].data(Qt.UserRole)
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path and (file_path.endswith('.zip') or file_path.endswith('.py')):
                try:
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
        event.acceptProposedAction()

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        # Search bar for functions
        self.function_search_bar = QLineEdit()
        self.function_search_bar.setPlaceholderText("Search Lambda Functions...")
        self.function_search_bar.textChanged.connect(self.filter_functions_list)
        layout.addWidget(self.function_search_bar)
        # Export/Import buttons
        export_import_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export Functions")
        self.import_btn = QPushButton("Import Functions")
        self.export_btn.clicked.connect(self.export_functions)
        self.import_btn.clicked.connect(self.import_functions)
        export_import_layout.addWidget(self.export_btn)
        export_import_layout.addWidget(self.import_btn)
        layout.addLayout(export_import_layout)
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
        
    def filter_functions_list(self):
        text = self.function_search_bar.text().lower()
        for i in range(self.functions_list.count()):
            item = self.functions_list.item(i)
            item.setHidden(text not in item.text().lower())
        
    def refresh_functions_list(self):
        self.log_message("Loading Lambda functions...")
        self._disable_buttons()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self.worker = AsyncWorker(self.lambda_manager.list_functions)
        self.worker.finished.connect(self._on_functions_loaded)
        self.worker.error.connect(self._on_functions_error)
        self.worker.start()

    def _on_functions_loaded(self, functions):
        self._enable_buttons()
        self.log_message(f"Loaded {len(functions)} Lambda functions.")
        self.functions_list.clear()
        for function_name in functions:
            item = QListWidgetItem(function_name)
            item.setData(Qt.UserRole, function_name)
            self.functions_list.addItem(item)

    def _on_functions_error(self, e):
        self._enable_buttons()
        self.show_error_dialog("Error loading Lambda functions", str(e))

    def cancel_loading(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log_message("Cancelled Lambda function loading.")
            
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

    def export_functions(self):
        functions = []
        for i in range(self.functions_list.count()):
            item = self.functions_list.item(i)
            if not item.isHidden():
                functions.append(item.text())
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Lambda Functions", "lambda_functions.json", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(functions, f, indent=2)
            self.show_info_dialog("Export", f"Exported {len(functions)} Lambda functions to {file_path}")
    def import_functions(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Lambda Functions", "", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.show_info_dialog("Import", f"Imported {len(data)} Lambda functions from {file_path}\n(Import does not create resources)")

class IAMTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.worker = None  # Ensure worker is defined before any method uses it
        self.iam_manager = IAMManager()
        self._is_loading = False
        self._selected_role = None
        self._selected_profile = None
        self.setup_ui()
        self.refresh_roles_list()
        
    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        # Search bar for roles
        self.role_search_bar = QLineEdit()
        self.role_search_bar.setPlaceholderText("Search IAM Roles...")
        self.role_search_bar.textChanged.connect(self.filter_roles_list)
        layout.addWidget(self.role_search_bar)
        # Export/Import buttons
        export_import_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export Roles")
        self.import_btn = QPushButton("Import Roles")
        self.export_btn.clicked.connect(self.export_roles)
        self.import_btn.clicked.connect(self.import_roles)
        export_import_layout.addWidget(self.export_btn)
        export_import_layout.addWidget(self.import_btn)
        layout.addLayout(export_import_layout)
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
        
    def filter_roles_list(self):
        text = self.role_search_bar.text().lower()
        for i in range(self.roles_list.count()):
            item = self.roles_list.item(i)
            item.setHidden(text not in item.text().lower())
        
    def refresh_roles_list(self):
        self.log_message("Loading IAM roles...")
        self._disable_buttons()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        self.worker = AsyncWorker(self.iam_manager.list_roles)
        self.worker.finished.connect(self._on_roles_loaded)
        self.worker.error.connect(self._on_roles_error)
        self.worker.start()

    def _on_roles_loaded(self, roles):
        self._enable_buttons()
        self.log_message(f"Loaded {len(roles)} IAM roles.")
        self.roles_list.clear()
        for role in roles:
            item = QListWidgetItem(role['RoleName'])
            item.setData(Qt.UserRole, role['RoleName'])
            self.roles_list.addItem(item)

    def _on_roles_error(self, e):
        self._enable_buttons()
        self.show_error_dialog("Error loading IAM roles", str(e))

    def cancel_loading(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log_message("Cancelled IAM role loading.")
            
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

    def export_roles(self):
        roles = []
        for i in range(self.roles_list.count()):
            item = self.roles_list.item(i)
            if not item.isHidden():
                roles.append(item.text())
        file_path, _ = QFileDialog.getSaveFileName(self, "Export IAM Roles", "iam_roles.json", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(roles, f, indent=2)
            self.show_info_dialog("Export", f"Exported {len(roles)} IAM roles to {file_path}")
    def import_roles(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import IAM Roles", "", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.show_info_dialog("Import", f"Imported {len(data)} IAM roles from {file_path}\n(Import does not create resources)")

class SettingsTab(BaseTab):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.current_profile = None
        self.profiles = self.load_profiles()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<h2>Application Settings</h2>"))

        # --- Theme Selection ---
        theme_group = QGroupBox("Theme")
        theme_layout = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        if self.main_window and hasattr(self.main_window, 'current_theme'):
            self.theme_combo.setCurrentIndex(1 if self.main_window.current_theme == 'dark' else 0)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addWidget(QLabel("Select Theme:"))
        theme_layout.addWidget(self.theme_combo)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # --- AWS Credential Validation ---
        creds_group = QGroupBox("AWS Credentials")
        creds_layout = QHBoxLayout()
        self.validate_btn = QPushButton("Validate AWS Credentials")
        self.validate_btn.clicked.connect(self.validate_aws_credentials)
        self.cred_status_label = QLabel("Status: Not checked")
        creds_layout.addWidget(self.validate_btn)
        creds_layout.addWidget(self.cred_status_label)
        creds_group.setLayout(creds_layout)
        layout.addWidget(creds_group)

        # --- Logging Settings ---
        log_group = QGroupBox("Logging")
        log_layout = QHBoxLayout()
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setCurrentText("INFO")
        self.log_level_combo.currentIndexChanged.connect(self.on_log_level_changed)
        log_layout.addWidget(QLabel("Log Level:"))
        log_layout.addWidget(self.log_level_combo)
        self.log_file_edit = QLineEdit()
        self.log_file_edit.setPlaceholderText("Log file path (e.g. logs/aws_operations.log)")
        log_layout.addWidget(QLabel("Log File:"))
        log_layout.addWidget(self.log_file_edit)
        self.log_file_btn = QPushButton("Browse")
        self.log_file_btn.clicked.connect(self.browse_log_file)
        log_layout.addWidget(self.log_file_btn)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # --- Error Log Export ---
        error_group = QGroupBox("Error Reporting")
        error_layout = QHBoxLayout()
        self.export_error_btn = QPushButton("Export Error Log")
        self.export_error_btn.clicked.connect(self.export_error_log)
        error_layout.addWidget(self.export_error_btn)
        error_group.setLayout(error_layout)
        layout.addWidget(error_group)

        # Credentials Manager UI
        group = QGroupBox("AWS Credentials Manager")
        vbox = QVBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.profiles.keys())
        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        vbox.addWidget(QLabel("Select AWS Profile:"))
        vbox.addWidget(self.profile_combo)
        self.add_profile_btn = QPushButton("Add Profile")
        self.add_profile_btn.clicked.connect(self.add_profile)
        vbox.addWidget(self.add_profile_btn)
        self.edit_profile_btn = QPushButton("Edit Selected Profile")
        self.edit_profile_btn.clicked.connect(self.edit_profile)
        vbox.addWidget(self.edit_profile_btn)
        self.delete_profile_btn = QPushButton("Delete Selected Profile")
        self.delete_profile_btn.clicked.connect(self.delete_profile)
        vbox.addWidget(self.delete_profile_btn)
        group.setLayout(vbox)
        layout.addWidget(group)

        layout.addStretch()
        self.setLayout(layout)

    def load_profiles(self):
        # For now, load from a config file or in-memory dict
        import os, json
        profiles_path = os.path.join(os.path.expanduser('~'), '.aws_infra_profiles.json')
        if os.path.exists(profiles_path):
            with open(profiles_path, 'r') as f:
                return json.load(f)
        return {"default": {"aws_access_key_id": "", "aws_secret_access_key": "", "region": "us-east-1"}}

    def save_profiles(self):
        import os, json
        profiles_path = os.path.join(os.path.expanduser('~'), '.aws_infra_profiles.json')
        with open(profiles_path, 'w') as f:
            json.dump(self.profiles, f, indent=2)

    def on_theme_changed(self, idx):
        if self.main_window:
            theme = 'dark' if idx == 1 else 'light'
            self.main_window.set_theme(theme)

    def validate_aws_credentials(self):
        self.cred_status_label.setText("Status: Checking...")
        self.cred_status_label.repaint()
        try:
            session = boto3.Session()
            sts = session.client('sts')
            identity = sts.get_caller_identity()
            arn = identity.get('Arn', 'Unknown')
            self.cred_status_label.setText(f"Status: Valid (ARN: {arn})")
            self.cred_status_label.setStyleSheet("color: green;")
        except BotoClientError as e:
            self.cred_status_label.setText(f"Status: Invalid ({e.response['Error']['Code']})")
            self.cred_status_label.setStyleSheet("color: red;")
        except Exception as e:
            self.cred_status_label.setText(f"Status: Invalid ({str(e)})")
            self.cred_status_label.setStyleSheet("color: red;")

    def on_log_level_changed(self, idx):
        level = self.log_level_combo.currentText()
        # Optionally, set the log level live
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, level, logging.INFO))
        if self.main_window and hasattr(self.main_window, 'status_bar'):
            self.main_window.status_bar.log_message(f"Log level set to {level}")

    def browse_log_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Select Log File", "logs/aws_operations.log", "Log Files (*.log);;All Files (*)")
        if file_path:
            self.log_file_edit.setText(file_path)
            if self.main_window and hasattr(self.main_window, 'status_bar'):
                self.main_window.status_bar.log_message(f"Log file set to {file_path}")

    def export_error_log(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Error Log", "error_log.txt", "Text Files (*.txt)")
        if file_path:
            with open(file_path, 'w') as f:
                f.write('\n'.join(ERROR_LOG))
            if self.main_window and hasattr(self.main_window, 'status_bar'):
                self.main_window.status_bar.log_message(f"Error log exported to {file_path}")

    def on_profile_changed(self, profile_name):
        self.current_profile = profile_name
        # Switch boto3 session/profile globally
        import boto3
        profile = self.profiles[profile_name]
        secret = profile.get('aws_secret_access_key')
        if profile.get('encrypted'):
            enc_key = self.get_encryption_key()
            f = Fernet(enc_key)
            secret = f.decrypt(secret.encode()).decode()
        elif profile.get('secrets_manager'):
            import boto3
            secrets = boto3.client('secretsmanager')
            resp = secrets.get_secret_value(SecretId=secret)
            secret = resp['SecretString']
        session = boto3.Session(
            aws_access_key_id=profile.get('aws_access_key_id'),
            aws_secret_access_key=secret,
            region_name=profile.get('region', 'us-east-1')
        )
        # Optionally: set as default session for the app
        # boto3.setup_default_session(...)
        self.log_message(f"Switched to profile: {profile_name}")

    def add_profile(self):
        name, ok = QInputDialog.getText(self, "Add Profile", "Profile name:")
        if ok and name:
            key, ok1 = QInputDialog.getText(self, "AWS Access Key ID", "Access Key ID:")
            if not ok1: return
            secret, ok2 = QInputDialog.getText(self, "AWS Secret Access Key", "Secret Access Key:")
            if not ok2: return
            region, ok3 = QInputDialog.getText(self, "AWS Region", "Region:", text="us-east-1")
            if not ok3: return
            # Secure storage
            storage = self.storage_combo.currentText()
            if storage == "Local Encrypted":
                enc_key = self.get_encryption_key()
                f = Fernet(enc_key)
                enc_secret = f.encrypt(secret.encode()).decode()
                self.profiles[name] = {
                    "aws_access_key_id": key,
                    "aws_secret_access_key": enc_secret,
                    "region": region,
                    "encrypted": True
                }
            elif storage == "AWS Secrets Manager":
                # Store in AWS Secrets Manager
                import boto3
                secrets = boto3.client('secretsmanager')
                secret_name = f"aws_infra_{name}"
                secrets.create_secret(Name=secret_name, SecretString=secret)
                self.profiles[name] = {
                    "aws_access_key_id": key,
                    "aws_secret_access_key": secret_name,
                    "region": region,
                    "encrypted": False,
                    "secrets_manager": True
                }
            else:
                self.profiles[name] = {
                    "aws_access_key_id": key,
                    "aws_secret_access_key": secret,
                    "region": region
                }
            self.save_profiles()
            self.profile_combo.addItem(name)
            self.log_message(f"Profile '{name}' added.")

    def edit_profile(self):
        name = self.profile_combo.currentText()
        if not name: return
        profile = self.profiles[name]
        key, ok1 = QInputDialog.getText(self, "Edit Access Key ID", "Access Key ID:", text=profile.get('aws_access_key_id', ''))
        if not ok1: return
        secret, ok2 = QInputDialog.getText(self, "Edit Secret Access Key", "Secret Access Key:", text=profile.get('aws_secret_access_key', ''))
        if not ok2: return
        region, ok3 = QInputDialog.getText(self, "Edit Region", "Region:", text=profile.get('region', 'us-east-1'))
        if not ok3: return
        self.profiles[name] = {
            "aws_access_key_id": key,
            "aws_secret_access_key": secret,
            "region": region
        }
        self.save_profiles()
        self.log_message(f"Profile '{name}' updated.")

    def delete_profile(self):
        name = self.profile_combo.currentText()
        if not name or name == 'default':
            self.show_error_dialog("Cannot delete default profile.", "")
            return
        self.profiles.pop(name, None)
        self.save_profiles()
        idx = self.profile_combo.findText(name)
        self.profile_combo.removeItem(idx)
        self.log_message(f"Profile '{name}' deleted.")

    def get_encryption_key(self):
        import os
        key_path = os.path.join(os.path.expanduser('~'), '.aws_infra_key')
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                return f.read()
        key = Fernet.generate_key()
        with open(key_path, 'wb') as f:
            f.write(key)
        return key

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

        # Theme toggle
        self.theme_action = QAction("Toggle Dark/Light Mode", self)
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(False)
        self.theme_action.triggered.connect(self.toggle_theme)
        settings_menu.addAction(self.theme_action)

        self.addMenu(file_menu)
        self.addMenu(operations_menu)
        self.addMenu(settings_menu)
        self.addMenu(help_menu)

    def show_about(self):
        # Use the status bar's log_message method for About
        if hasattr(self.main_window, 'status_bar') and self.main_window.status_bar:
            self.main_window.status_bar.log_message("AWS Infrastructure Manager version 1.0.0. Built using Python and PyQt5")
        else:
            print("AWS Infrastructure Manager version 1.0.0. Built using Python and PyQt5")

    def toggle_theme(self):
        if self.theme_action.isChecked():
            self.main_window.set_theme('dark')
        else:
            self.main_window.set_theme('light')


# --- RDS Tab ---
class RDSTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.rds_client = get_client('rds')
        self.setup_ui()
        self.refresh_instances()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.instances_list = QListWidget()
        self.instances_list.itemSelectionChanged.connect(self.display_instance_details)
        layout.addWidget(QLabel("RDS DB Instances:"))
        layout.addWidget(self.instances_list)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(QLabel("Instance Details:"))
        layout.addWidget(self.details)
        # Metrics chart
        self.figure, self.ax = plt.subplots(figsize=(4, 2))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(QLabel("Monitoring (CPU, Storage, Connections):"))
        layout.addWidget(self.canvas)
        btns = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_instances)
        self.create_btn = QPushButton("Create")
        self.create_btn.clicked.connect(self.create_instance)
        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self.update_instance)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_instance)
        self.snapshot_btn = QPushButton("Snapshot")
        self.snapshot_btn.clicked.connect(self.snapshot_instance)
        self.restore_btn = QPushButton("Restore from Snapshot")
        self.restore_btn.clicked.connect(self.restore_instance)
        self.backup_btn = QPushButton("Backup Settings")
        self.backup_btn.clicked.connect(self.show_backup_settings)
        self.copy_btn = QPushButton("Copy ARN/ID")
        self.copy_btn.clicked.connect(self.copy_arn_id)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.create_btn)
        btns.addWidget(self.update_btn)
        btns.addWidget(self.delete_btn)
        btns.addWidget(self.snapshot_btn)
        btns.addWidget(self.restore_btn)
        btns.addWidget(self.backup_btn)
        btns.addWidget(self.copy_btn)
        layout.addLayout(btns)
        self.setLayout(layout)

    def refresh_instances(self):
        self.instances_list.clear()
        try:
            resp = self.rds_client.describe_db_instances()
            self.db_instances = resp.get('DBInstances', [])
            for db in self.db_instances:
                item = QListWidgetItem(f"{db['DBInstanceIdentifier']} ({db['DBInstanceStatus']})")
                item.setData(Qt.UserRole, db)
                self.instances_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def display_instance_details(self):
        selected = self.instances_list.selectedItems()
        if not selected:
            self.details.clear()
            self.ax.clear()
            self.canvas.draw()
            return
        db = selected[0].data(Qt.UserRole)
        arn = db.get('DBInstanceArn', 'N/A')
        text = '\n'.join([f"{k}: {v}" for k, v in db.items()])
        self.details.setText(text)
        self._last_arn = arn
        self._last_id = db.get('DBInstanceIdentifier', '')
        # Show metrics
        self.show_metrics(db['DBInstanceIdentifier'])

    def show_metrics(self, db_instance_id):
        metrics = ['CPUUtilization', 'FreeStorageSpace', 'DatabaseConnections']
        self.ax.clear()
        for metric in metrics:
            data = get_rds_metrics(db_instance_id, metric)
            if data:
                data = sorted(data, key=lambda x: x['Timestamp'])
                times = [d['Timestamp'] for d in data]
                values = [d['Average'] for d in data]
                self.ax.plot(times, values, label=metric)
        self.ax.legend()
        self.ax.set_title(f"Metrics for {db_instance_id}")
        self.figure.tight_layout()
        self.canvas.draw()

    def create_instance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create RDS Instance")
        layout = QFormLayout()
        db_id = QLineEdit()
        engine = QComboBox(); engine.addItems(['mysql', 'postgres', 'mariadb', 'oracle-se2', 'sqlserver-ex'])
        instance_class = QLineEdit(); instance_class.setText('db.t3.micro')
        storage = QSpinBox(); storage.setRange(20, 65536); storage.setValue(20)
        username = QLineEdit(); password = QLineEdit(); password.setEchoMode(QLineEdit.Password)
        layout.addRow("DB Identifier:", db_id)
        layout.addRow("Engine:", engine)
        layout.addRow("Instance Class:", instance_class)
        layout.addRow("Allocated Storage (GB):", storage)
        layout.addRow("Master Username:", username)
        layout.addRow("Master Password:", password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.setLayout(layout)
        if dialog.exec_() == QDialog.Accepted:
            try:
                self.rds_client.create_db_instance(
                    DBInstanceIdentifier=db_id.text(),
                    AllocatedStorage=storage.value(),
                    DBInstanceClass=instance_class.text(),
                    Engine=engine.currentText(),
                    MasterUsername=username.text(),
                    MasterUserPassword=password.text(),
                    BackupRetentionPeriod=7
                )
                self.log_message(f"Create requested for {db_id.text()}")
                self.refresh_instances()
            except Exception as e:
                self.log_message(f"Error: {e}", error=True)

    def update_instance(self):
        selected = self.instances_list.selectedItems()
        if not selected:
            return
        db = selected[0].data(Qt.UserRole)
        dialog = QDialog(self)
        dialog.setWindowTitle("Update RDS Instance")
        layout = QFormLayout()
        instance_class = QLineEdit(); instance_class.setText(db['DBInstanceClass'])
        storage = QSpinBox(); storage.setRange(20, 65536); storage.setValue(db['AllocatedStorage'])
        layout.addRow("Instance Class:", instance_class)
        layout.addRow("Allocated Storage (GB):", storage)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.setLayout(layout)
        if dialog.exec_() == QDialog.Accepted:
            try:
                self.rds_client.modify_db_instance(
                    DBInstanceIdentifier=db['DBInstanceIdentifier'],
                    DBInstanceClass=instance_class.text(),
                    AllocatedStorage=storage.value(),
                    ApplyImmediately=True
                )
                self.log_message(f"Update requested for {db['DBInstanceIdentifier']}")
                self.refresh_instances()
            except Exception as e:
                self.log_message(f"Error: {e}", error=True)

    def restore_instance(self):
        # List snapshots, allow restore
        try:
            resp = self.rds_client.describe_db_snapshots(SnapshotType='manual')
            snapshots = resp.get('DBSnapshots', [])
            if not snapshots:
                self.show_info_dialog("Restore", "No manual snapshots found.")
                return
            items = [f"{s['DBSnapshotIdentifier']} ({s['DBInstanceIdentifier']})" for s in snapshots]
            idx, ok = QInputDialog.getItem(self, "Select Snapshot", "Snapshot:", items, 0, False)
            if not ok:
                return
            snap = snapshots[items.index(idx)]
            new_id, ok2 = QInputDialog.getText(self, "Restore As", "New DB Identifier:")
            if not ok2 or not new_id:
                return
            self.rds_client.restore_db_instance_from_db_snapshot(
                DBInstanceIdentifier=new_id,
                DBSnapshotIdentifier=snap['DBSnapshotIdentifier']
            )
            self.log_message(f"Restore requested for {new_id} from {snap['DBSnapshotIdentifier']}")
            self.refresh_instances()
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def show_backup_settings(self):
        selected = self.instances_list.selectedItems()
        if not selected:
            return
        db = selected[0].data(Qt.UserRole)
        dialog = QDialog(self)
        dialog.setWindowTitle("Backup Settings")
        layout = QFormLayout()
        retention = QSpinBox(); retention.setRange(0, 35); retention.setValue(db.get('BackupRetentionPeriod', 7))
        window = QLineEdit(); window.setText(db.get('PreferredBackupWindow', '00:00-02:00'))
        layout.addRow("Backup Retention (days):", retention)
        layout.addRow("Preferred Backup Window:", window)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.setLayout(layout)
        if dialog.exec_() == QDialog.Accepted:
            try:
                self.rds_client.modify_db_instance(
                    DBInstanceIdentifier=db['DBInstanceIdentifier'],
                    BackupRetentionPeriod=retention.value(),
                    PreferredBackupWindow=window.text(),
                    ApplyImmediately=True
                )
                self.log_message(f"Backup settings updated for {db['DBInstanceIdentifier']}")
                self.refresh_instances()
            except Exception as e:
                self.log_message(f"Error: {e}", error=True)

    def delete_instance(self):
        selected = self.instances_list.selectedItems()
        if not selected:
            return
        db = selected[0].data(Qt.UserRole)
        try:
            self.rds_client.delete_db_instance(DBInstanceIdentifier=db['DBInstanceIdentifier'], SkipFinalSnapshot=True)
            self.log_message(f"Delete requested for {db['DBInstanceIdentifier']}")
            self.refresh_instances()
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def snapshot_instance(self):
        selected = self.instances_list.selectedItems()
        if not selected:
            return
        db = selected[0].data(Qt.UserRole)
        try:
            snap_id = db['DBInstanceIdentifier'] + "-snap"
            self.rds_client.create_db_snapshot(DBSnapshotIdentifier=snap_id, DBInstanceIdentifier=db['DBInstanceIdentifier'])
            self.log_message(f"Snapshot requested: {snap_id}")
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def copy_arn_id(self):
        if hasattr(self, '_last_arn') and self._last_arn:
            QApplication.clipboard().setText(self._last_arn)
            self.log_message(f"Copied ARN: {self._last_arn}")
        elif hasattr(self, '_last_id') and self._last_id:
            QApplication.clipboard().setText(self._last_id)
            self.log_message(f"Copied ID: {self._last_id}")

# --- CloudFront Tab ---
class CloudFrontTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.cf_client = get_client('cloudfront')
        self.setup_ui()
        self.refresh_distributions()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.dist_list = QListWidget()
        self.dist_list.itemSelectionChanged.connect(self.display_dist_details)
        layout.addWidget(QLabel("CloudFront Distributions:"))
        layout.addWidget(self.dist_list)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(QLabel("Distribution Details:"))
        layout.addWidget(self.details)
        # Metrics chart
        self.figure, self.ax = plt.subplots(figsize=(4, 2))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(QLabel("Monitoring (Requests, 4xx/5xx Errors, Bandwidth):"))
        layout.addWidget(self.canvas)
        btns = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_distributions)
        self.create_btn = QPushButton("Create")
        self.create_btn.clicked.connect(self.create_dist)
        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self.update_dist)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_dist)
        self.invalidate_btn = QPushButton("Invalidate")
        self.invalidate_btn.clicked.connect(self.invalidate_dist)
        self.show_inv_btn = QPushButton("Show Invalidations")
        self.show_inv_btn.clicked.connect(self.show_invalidations)
        self.copy_btn = QPushButton("Copy ARN/ID")
        self.copy_btn.clicked.connect(self.copy_arn_id)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.create_btn)
        btns.addWidget(self.update_btn)
        btns.addWidget(self.delete_btn)
        btns.addWidget(self.invalidate_btn)
        btns.addWidget(self.show_inv_btn)
        btns.addWidget(self.copy_btn)
        layout.addLayout(btns)
        self.setLayout(layout)

    def refresh_distributions(self):
        self.dist_list.clear()
        try:
            resp = self.cf_client.list_distributions()
            items = resp.get('DistributionList', {}).get('Items', [])
            self.dists = items
            for d in items:
                item = QListWidgetItem(f"{d['Id']} ({d['Status']})")
                item.setData(Qt.UserRole, d)
                self.dist_list.addItem(item)
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def display_dist_details(self):
        selected = self.dist_list.selectedItems()
        if not selected:
            self.details.clear()
            self.ax.clear()
            self.canvas.draw()
            return
        d = selected[0].data(Qt.UserRole)
        arn = d.get('ARN', d.get('Id', 'N/A'))
        text = '\n'.join([f"{k}: {v}" for k, v in d.items()])
        self.details.setText(text)
        self._last_arn = arn
        self._last_id = d.get('Id', '')
        # Show metrics
        self.show_metrics(d['Id'])

    def show_metrics(self, dist_id):
        metrics = ['Requests', '4xxErrorRate', '5xxErrorRate', 'BytesDownloaded', 'BytesUploaded']
        self.ax.clear()
        for metric in metrics:
            data = get_cloudfront_metrics(dist_id, metric)
            if data:
                data = sorted(data, key=lambda x: x['Timestamp'])
                times = [d['Timestamp'] for d in data]
                values = [d['Sum'] for d in data]
                self.ax.plot(times, values, label=metric)
        self.ax.legend()
        self.ax.set_title(f"Metrics for {dist_id}")
        self.figure.tight_layout()
        self.canvas.draw()

    def create_dist(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create CloudFront Distribution")
        layout = QFormLayout()
        origin = QLineEdit(); origin.setPlaceholderText('example-bucket.s3.amazonaws.com')
        comment = QLineEdit(); comment.setText('Created by AWSInfraManager')
        enabled = QCheckBox(); enabled.setChecked(True)
        layout.addRow("Origin Domain Name:", origin)
        layout.addRow("Comment:", comment)
        layout.addRow("Enabled:", enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.setLayout(layout)
        if dialog.exec_() == QDialog.Accepted:
            try:
                resp = self.cf_client.create_distribution(
                    DistributionConfig={
                        'CallerReference': str(time.time()),
                        'Origins': {
                            'Quantity': 1,
                            'Items': [{
                                'Id': origin.text(),
                                'DomainName': origin.text(),
                                'S3OriginConfig': {'OriginAccessIdentity': ''}
                            }]
                        },
                        'DefaultCacheBehavior': {
                            'TargetOriginId': origin.text(),
                            'ViewerProtocolPolicy': 'allow-all',
                            'TrustedSigners': {'Enabled': False, 'Quantity': 0},
                            'ForwardedValues': {'QueryString': False, 'Cookies': {'Forward': 'none'}},
                            'MinTTL': 0
                        },
                        'Comment': comment.text(),
                        'Enabled': enabled.isChecked()
                    }
                )
                self.log_message(f"Create requested for {origin.text()}")
                self.refresh_distributions()
            except Exception as e:
                self.log_message(f"Error: {e}", error=True)

    def update_dist(self):
        selected = self.dist_list.selectedItems()
        if not selected:
            return
        d = selected[0].data(Qt.UserRole)
        dist_id = d['Id']
        try:
            config_resp = self.cf_client.get_distribution_config(Id=dist_id)
            config = config_resp['DistributionConfig']
            etag = config_resp['ETag']
        except Exception as e:
            self.log_message(f"Error fetching config: {e}", error=True)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Update CloudFront Distribution")
        layout = QFormLayout()
        comment = QLineEdit(); comment.setText(config.get('Comment', ''))
        enabled = QCheckBox(); enabled.setChecked(config.get('Enabled', True))
        layout.addRow("Comment:", comment)
        layout.addRow("Enabled:", enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.setLayout(layout)
        if dialog.exec_() == QDialog.Accepted:
            try:
                config['Comment'] = comment.text()
                config['Enabled'] = enabled.isChecked()
                self.cf_client.update_distribution(
                    Id=dist_id,
                    IfMatch=etag,
                    DistributionConfig=config
                )
                self.log_message(f"Update requested for {dist_id}")
                self.refresh_distributions()
            except Exception as e:
                self.log_message(f"Error: {e}", error=True)

    def show_invalidations(self):
        selected = self.dist_list.selectedItems()
        if not selected:
            return
        d = selected[0].data(Qt.UserRole)
        dist_id = d['Id']
        try:
            resp = self.cf_client.list_invalidations(DistributionId=dist_id)
            items = resp.get('InvalidationList', {}).get('Items', [])
            if not items:
                self.show_info_dialog("Invalidations", "No invalidations found.")
                return
            msg = '\n'.join([f"{i['Id']}: {i['Status']} at {i['CreateTime']}" for i in items])
            self.show_info_dialog("Invalidations", msg)
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to list invalidations: {e}")

    def delete_dist(self):
        selected = self.dist_list.selectedItems()
        if not selected:
            return
        d = selected[0].data(Qt.UserRole)
        try:
            self.cf_client.delete_distribution(Id=d['Id'], IfMatch=d.get('ETag', ''))
            self.log_message(f"Delete requested for {d['Id']}")
            self.refresh_distributions()
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def invalidate_dist(self):
        selected = self.dist_list.selectedItems()
        if not selected:
            return
        d = selected[0].data(Qt.UserRole)
        try:
            self.cf_client.create_invalidation(DistributionId=d['Id'], InvalidationBatch={
                'Paths': {'Quantity': 1, 'Items': ['/*']},
                'CallerReference': str(time.time())
            })
            self.log_message(f"Invalidation requested for {d['Id']}")
        except Exception as e:
            self.log_message(f"Error: {e}", error=True)

    def copy_arn_id(self):
        if hasattr(self, '_last_arn') and self._last_arn:
            QApplication.clipboard().setText(self._last_arn)
            self.log_message(f"Copied ARN: {self._last_arn}")
        elif hasattr(self, '_last_id') and self._last_id:
            QApplication.clipboard().setText(self._last_id)
            self.log_message(f"Copied ID: {self._last_id}")

# --- Cost Explorer Tab ---
class CostExplorerTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cost Explorer")
        self.setup_ui()
        self.refresh_costs()

    def setup_ui(self):
        layout = QVBoxLayout()
        title_label = QLabel("<h2>AWS Cost Explorer</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        # Controls for breakdown
        controls_layout = QHBoxLayout()
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems(["Service", "Tag", "Time"])
        controls_layout.addWidget(QLabel("Breakdown by:"))
        controls_layout.addWidget(self.breakdown_combo)
        self.time_range_combo = QComboBox()
        self.time_range_combo.addItems(["Last 7 Days", "Last 30 Days", "This Month", "Last Month"])
        controls_layout.addWidget(QLabel("Time Range:"))
        controls_layout.addWidget(self.time_range_combo)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_costs)
        controls_layout.addWidget(self.refresh_btn)
        layout.addLayout(controls_layout)
        # Chart
        self.figure, self.ax = plt.subplots(figsize=(5, 3))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

    def refresh_costs(self):
        breakdown = self.breakdown_combo.currentText().lower()
        time_range = self.time_range_combo.currentText()
        data = get_cost_explorer_data(breakdown, time_range)
        self.ax.clear()
        if not data:
            self.ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=14)
            self.ax.set_title("No Data")
            self.figure.tight_layout()
            self.canvas.draw()
            return
        if breakdown == "service":
            labels = [d['Service'] for d in data]
            values = [d['Cost'] for d in data]
            if not values or sum(values) == 0:
                self.ax.pie([1], labels=["No Data"], colors=['#cccccc'])
            else:
                self.ax.pie(values, labels=labels, autopct='%1.1f%%')
            self.ax.set_title("Cost by Service")
        elif breakdown == "tag":
            labels = [d['Tag'] for d in data]
            values = [d['Cost'] for d in data]
            if not values or sum(values) == 0:
                self.ax.bar(["No Data"], [1], color='#cccccc')
            else:
                self.ax.bar(labels, values)
            self.ax.set_title("Cost by Tag")
        elif breakdown == "time":
            labels = [d['Date'] for d in data]
            values = [d['Cost'] for d in data]
            if not values or sum(values) == 0:
                self.ax.plot([0], [0], marker='o')
                self.ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=14)
            else:
                self.ax.plot(labels, values, marker='o')
            self.ax.set_title("Cost Over Time")
        self.figure.tight_layout()
        self.canvas.draw()


# --- Add Copy ARN/ID to EC2, S3, Lambda, IAM Tabs ---
# (For brevity, add a copy button to each details panel, similar to RDSTab)
# ... (You would add a QPushButton("Copy ARN/ID") and connect it to a method that copies the relevant value to clipboard in each tab's details UI.)

# --- Keyboard Shortcuts for Tabs and Refresh ---

class HelpTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        help_text = QPlainTextEdit()
        help_text.setReadOnly(True)
        help_text.setPlainText(
            """
AWS Infrastructure Manager - Help

- Use the tabs to manage AWS resources (EC2, S3, Lambda, IAM, etc).
- Use the search bars above each resource list to quickly find resources.
- Right-click or use action buttons for resource operations.
- Scheduled Actions: Use the Scheduled Actions tab to automate AWS tasks.
- Export/Import: Use export/import buttons to backup or restore resource configs.
- Notifications: Important events will appear in the notification area below.
- Keyboard Shortcuts:
    - Ctrl+Tab: Next tab
    - Ctrl+Shift+Tab: Previous tab
    - Ctrl+R: Refresh current tab
- For more help, see the README or documentation.
            """
        )
        layout.addWidget(QLabel("<h2>Help & Documentation</h2>"))
        layout.addWidget(help_text)
        self.setLayout(layout)

# --- IAM Policy Editor Tab ---
class IAMPolicyEditorTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.iam_client = get_client('iam')
        self.setup_ui()
        self.refresh_policies()

    def setup_ui(self):
        layout = QVBoxLayout()
        # Mode toggle
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["JSON Editor", "Visual Builder"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        layout.addWidget(self.mode_combo)
        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search Policies...")
        self.search_bar.textChanged.connect(self.filter_policies)
        layout.addWidget(self.search_bar)
        # Policy list
        self.policy_list = QListWidget()
        self.policy_list.itemSelectionChanged.connect(self.display_policy)
        layout.addWidget(QLabel("Policies:"))
        layout.addWidget(self.policy_list)
        # Policy JSON editor
        self.policy_editor = QPlainTextEdit()
        layout.addWidget(QLabel("Policy JSON:"))
        layout.addWidget(self.policy_editor)
        # Visual builder widgets
        self.visual_group = QGroupBox("Visual Policy Builder")
        vbox = QVBoxLayout()
        self.effect_combo = QComboBox(); self.effect_combo.addItems(["Allow", "Deny"])
        self.action_edit = QLineEdit(); self.action_edit.setPlaceholderText("e.g. s3:*")
        self.resource_edit = QLineEdit(); self.resource_edit.setPlaceholderText("e.g. * or arn:aws:s3:::bucket")
        add_btn = QPushButton("Add Statement")
        add_btn.clicked.connect(self.add_statement)
        vbox.addWidget(QLabel("Effect:")); vbox.addWidget(self.effect_combo)
        vbox.addWidget(QLabel("Action(s):")); vbox.addWidget(self.action_edit)
        vbox.addWidget(QLabel("Resource(s):")); vbox.addWidget(self.resource_edit)
        vbox.addWidget(add_btn)
        self.visual_statements = QListWidget()
        vbox.addWidget(QLabel("Statements:"))
        vbox.addWidget(self.visual_statements)
        self.visual_group.setLayout(vbox)
        layout.addWidget(self.visual_group)
        # Simulate Policy button
        self.simulate_btn = QPushButton("Simulate Policy")
        self.simulate_btn.clicked.connect(self.simulate_policy)
        layout.addWidget(self.simulate_btn)
        # Attached entities
        self.attached_label = QLabel("Attached Entities:")
        self.attached_list = QListWidget()
        layout.addWidget(self.attached_label)
        layout.addWidget(self.attached_list)
        self.setLayout(layout)
        self.visual_group.hide()

    def on_mode_changed(self, idx):
        if idx == 0:
            self.policy_editor.show()
            self.visual_group.hide()
        else:
            self.policy_editor.hide()
            self.visual_group.show()

    def add_statement(self):
        effect = self.effect_combo.currentText()
        action = self.action_edit.text().strip()
        resource = self.resource_edit.text().strip()
        if not action or not resource:
            self.show_error_dialog("Validation Error", "Action and Resource are required.")
            return
        stmt = {"Effect": effect, "Action": action, "Resource": resource}
        self.visual_statements.addItem(str(stmt))
        # Update policy editor JSON
        stmts = []
        for i in range(self.visual_statements.count()):
            stmts.append(eval(self.visual_statements.item(i).text()))
        policy = {"Version": "2012-10-17", "Statement": stmts}
        self.policy_editor.setPlainText(json.dumps(policy, indent=2))

    def simulate_policy(self):
        from botocore.exceptions import ClientError
        try:
            policy_json = self.policy_editor.toPlainText()
            if not policy_json:
                self.show_error_dialog("Error", "No policy to simulate.")
                return
            policy = json.loads(policy_json)
            # Use AWS Policy Simulator API
            sim = get_client('iam')
            actions = []
            for stmt in policy.get('Statement', []):
                if isinstance(stmt['Action'], list):
                    actions.extend(stmt['Action'])
                else:
                    actions.append(stmt['Action'])
            resp = sim.simulate_custom_policy(
                PolicyInputList=[policy_json],
                ActionNames=actions[:10]  # Limit for demo
            )
            results = resp.get('EvaluationResults', [])
            msg = '\n'.join([f"{r['EvalActionName']}: {r['EvalDecision']}" for r in results])
            self.show_info_dialog("Simulation Results", msg or "No results.")
        except ClientError as e:
            self.show_error_dialog("AWS Error", str(e))
        except Exception as e:
            self.show_error_dialog("Error", str(e))

    def refresh_policies(self):
        self.policy_list.clear()
        self.policies = []
        try:
            paginator = self.iam_client.get_paginator('list_policies')
            for page in paginator.paginate(Scope='Local'):
                for pol in page['Policies']:
                    self.policies.append(pol)
                    item = QListWidgetItem(f"{pol['PolicyName']} ({pol['Arn']})")
                    item.setData(Qt.UserRole, pol)
                    self.policy_list.addItem(item)
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to list policies: {e}")

    def filter_policies(self):
        text = self.search_bar.text().lower()
        for i in range(self.policy_list.count()):
            item = self.policy_list.item(i)
            pol = item.data(Qt.UserRole)
            item.setHidden(text not in pol['PolicyName'].lower() and text not in pol['Arn'].lower())

    def display_policy(self):
        selected = self.policy_list.selectedItems()
        if not selected:
            self.policy_editor.clear()
            self.attached_list.clear()
            return
        pol = selected[0].data(Qt.UserRole)
        try:
            v = self.iam_client.get_policy_version(PolicyArn=pol['Arn'], VersionId=pol['DefaultVersionId'])
            doc = v['PolicyVersion']['Document']
            import json
            self.policy_editor.setPlainText(json.dumps(doc, indent=2))
            # Show attached entities
            self.attached_list.clear()
            attached_roles = self.iam_client.list_entities_for_policy(PolicyArn=pol['Arn'])
            for role in attached_roles.get('PolicyRoles', []):
                self.attached_list.addItem(f"Role: {role['RoleName']}")
            for user in attached_roles.get('PolicyUsers', []):
                self.attached_list.addItem(f"User: {user['UserName']}")
            for group in attached_roles.get('PolicyGroups', []):
                self.attached_list.addItem(f"Group: {group['GroupName']}")
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to load policy: {e}")

    def attach_policy(self):
        selected = self.policy_list.selectedItems()
        if not selected:
            self.show_error_dialog("Error", "Select a policy first.")
            return
        pol = selected[0].data(Qt.UserRole)
        entity_type = self.entity_type_combo.currentText()
        entity_id = self.entity_id_input.text().strip()
        if not entity_id:
            self.show_error_dialog("Error", "Enter an entity name.")
            return
        try:
            if entity_type == "Role":
                self.iam_client.attach_role_policy(RoleName=entity_id, PolicyArn=pol['Arn'])
            elif entity_type == "User":
                self.iam_client.attach_user_policy(UserName=entity_id, PolicyArn=pol['Arn'])
            elif entity_type == "Group":
                self.iam_client.attach_group_policy(GroupName=entity_id, PolicyArn=pol['Arn'])
            self.show_info_dialog("Success", f"Policy attached to {entity_type} {entity_id}.")
            self.display_policy()
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to attach policy: {e}")

    def detach_policy(self):
        selected = self.policy_list.selectedItems()
        if not selected:
            self.show_error_dialog("Error", "Select a policy first.")
            return
        pol = selected[0].data(Qt.UserRole)
        entity_type = self.entity_type_combo.currentText()
        entity_id = self.entity_id_input.text().strip()
        if not entity_id:
            self.show_error_dialog("Error", "Enter an entity name.")
            return
        try:
            if entity_type == "Role":
                self.iam_client.detach_role_policy(RoleName=entity_id, PolicyArn=pol['Arn'])
            elif entity_type == "User":
                self.iam_client.detach_user_policy(UserName=entity_id, PolicyArn=pol['Arn'])
            elif entity_type == "Group":
                self.iam_client.detach_group_policy(GroupName=entity_id, PolicyArn=pol['Arn'])
            self.show_info_dialog("Success", f"Policy detached from {entity_type} {entity_id}.")
            self.display_policy()
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to detach policy: {e}")

    def create_policy(self):
        from json import loads, JSONDecodeError
        name, ok = QInputDialog.getText(self, "Create Policy", "Policy Name:")
        if not ok or not name:
            return
        try:
            doc = loads(self.policy_editor.toPlainText())
        except JSONDecodeError as e:
            self.show_error_dialog("Error", f"Invalid JSON: {e}")
            return
        try:
            self.iam_client.create_policy(PolicyName=name, PolicyDocument=json.dumps(doc))
            self.show_info_dialog("Success", f"Policy '{name}' created.")
            self.refresh_policies()
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to create policy: {e}")

    def delete_policy(self):
        selected = self.policy_list.selectedItems()
        if not selected:
            self.show_error_dialog("Error", "Select a policy to delete.")
            return
        pol = selected[0].data(Qt.UserRole)
        if not self.show_confirm_dialog("Confirm Delete", f"Delete policy {pol['PolicyName']}?"):
            return
        try:
            self.iam_client.delete_policy(PolicyArn=pol['Arn'])
            self.show_info_dialog("Success", f"Policy deleted.")
            self.refresh_policies()
        except Exception as e:
            self.show_error_dialog("Error", f"Failed to delete policy: {e}")

# --- Security Audit Tab ---
class SecurityAuditTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.s3_client = get_client('s3')
        self.ec2_client = get_client('ec2')
        self.iam_client = get_client('iam')
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("<h2>Security Audit</h2>"))
        self.run_btn = QPushButton("Run Security Audit")
        self.run_btn.clicked.connect(self.run_audit)
        layout.addWidget(self.run_btn)
        self.export_btn = QPushButton("Export Report")
        self.export_btn.clicked.connect(self.export_report)
        layout.addWidget(self.export_btn)
        self.results_list = QListWidget()
        layout.addWidget(self.results_list)
        self.setLayout(layout)
        self.audit_results = []

    def run_audit(self):
        self.results_list.clear()
        self.audit_results = []
        self.run_btn.setEnabled(False)
        self.results_list.addItem("Running security checks...")
        self.audit_results.append(["Info", "Audit started", "info"])
        try:
            # 1. Public S3 buckets
            buckets = self.s3_client.list_buckets().get('Buckets', [])
            for b in buckets:
                name = b['Name']
                try:
                    acl = self.s3_client.get_bucket_acl(Bucket=name)
                    grants = acl.get('Grants', [])
                    for g in grants:
                        if g['Grantee'].get('URI', '').endswith('AllUsers'):
                            msg = f"S3 bucket {name} is public!"
                            self.results_list.addItem(msg)
                            self.audit_results.append(["High", msg, "S3"])
                except Exception:
                    continue
            # 2. Open EC2 security groups
            sgs = self.ec2_client.describe_security_groups()['SecurityGroups']
            for sg in sgs:
                for perm in sg.get('IpPermissions', []):
                    for ipr in perm.get('IpRanges', []):
                        if ipr.get('CidrIp') == '0.0.0.0/0':
                            port = perm.get('FromPort', 'all')
                            msg = f"Security group {sg['GroupId']} open to the world on port {port}"
                            self.results_list.addItem(msg)
                            self.audit_results.append(["High", msg, "EC2"])
            # 3. Unused IAM users/keys
            users = self.iam_client.list_users()['Users']
            for u in users:
                if 'PasswordLastUsed' not in u:
                    msg = f"IAM user {u['UserName']} has never logged in"
                    self.results_list.addItem(msg)
                    self.audit_results.append(["Medium", msg, "IAM"])
                keys = self.iam_client.list_access_keys(UserName=u['UserName'])['AccessKeyMetadata']
                for k in keys:
                    if k['Status'] == 'Active':
                        last_used = self.iam_client.get_access_key_last_used(AccessKeyId=k['AccessKeyId'])
                        if not last_used['AccessKeyLastUsed'].get('LastUsedDate'):
                            msg = f"Access key {k['AccessKeyId']} for user {u['UserName']} never used"
                            self.results_list.addItem(msg)
                            self.audit_results.append(["Medium", msg, "IAM"])
            # 4. Root account usage
            try:
                summary = self.iam_client.get_account_summary()['SummaryMap']
                if summary.get('AccountMFAEnabled', 0) == 0:
                    msg = "Root account has no MFA enabled!"
                    self.results_list.addItem(msg)
                    self.audit_results.append(["Critical", msg, "Root"])
            except Exception:
                pass
            # 5. Overly permissive policies
            paginator = self.iam_client.get_paginator('list_policies')
            for page in paginator.paginate(Scope='Local'):
                for pol in page['Policies']:
                    arn = pol['Arn']
                    v = self.iam_client.get_policy_version(PolicyArn=arn, VersionId=pol['DefaultVersionId'])
                    doc = v['PolicyVersion']['Document']
                    if any(st.get('Effect') == 'Allow' and st.get('Action') == '*' and st.get('Resource') == '*' for st in doc.get('Statement', [])):
                        msg = f"Policy {pol['PolicyName']} allows *:*"
                        self.results_list.addItem(msg)
                        self.audit_results.append(["High", msg, "IAM Policy"])
            self.results_list.addItem("Audit complete.")
            self.audit_results.append(["Info", "Audit complete", "info"])
        except Exception as e:
            self.results_list.addItem(f"Error: {e}")
            self.audit_results.append(["Error", str(e), "error"])
        self.run_btn.setEnabled(True)

    def export_report(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Audit Report", "security_audit.txt", "Text Files (*.txt)")
        if file_path:
            with open(file_path, 'w') as f:
                for sev, msg, cat in self.audit_results:
                    f.write(f"[{sev}] {cat}: {msg}\n")
            self.show_info_dialog("Export", f"Audit report exported to {file_path}")

class ResourceGraphTab(BaseTab):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Architecture Map")
        self.setup_ui()
        self.refresh_graph()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.refresh_btn = QPushButton("Refresh Diagram")
        self.refresh_btn.clicked.connect(self.refresh_graph)
        layout.addWidget(self.refresh_btn)
        self.graph_label = QLabel()
        self.graph_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.graph_label)
        self.setLayout(layout)

    def refresh_graph(self):
        dot = Digraph(comment='AWS Resource Graph')
        # Example: Fetch resources and relationships (simplified)
        try:
            ec2 = EC2Manager()
            rds = get_client('rds')
            s3 = S3Manager()
            # EC2 Instances
            for inst in ec2.list_instances():
                dot.node(inst.id, f"EC2\n{inst.id}")
                if hasattr(inst, 'vpc_id') and inst.vpc_id:
                    dot.edge(inst.vpc_id, inst.id)
            # RDS Instances
            for db in rds.describe_db_instances().get('DBInstances', []):
                dot.node(db['DBInstanceIdentifier'], f"RDS\n{db['DBInstanceIdentifier']}")
                if db.get('DBSubnetGroup') and db['DBSubnetGroup'].get('VpcId'):
                    dot.edge(db['DBSubnetGroup']['VpcId'], db['DBInstanceIdentifier'])
            # S3 Buckets
            for bucket in s3.list_buckets():
                dot.node(bucket['Name'], f"S3\n{bucket['Name']}")
            # VPCs
            vpcs = get_client('ec2').describe_vpcs().get('Vpcs', [])
            for vpc in vpcs:
                dot.node(vpc['VpcId'], f"VPC\n{vpc['VpcId']}")
            # Render to temporary file (fix for Windows)
            import os
            fd, tmp_path = tempfile.mkstemp(suffix='.png')
            os.close(fd)  # Close the file so Graphviz can write to it
            dot.render(tmp_path, format='png', cleanup=True)
            pixmap = QPixmap(tmp_path + '.png')
            self.graph_label.setPixmap(pixmap.scaled(600, 400, Qt.KeepAspectRatio))
            # Optionally, clean up the file after loading
            try:
                os.remove(tmp_path)
                os.remove(tmp_path + '.png')
            except Exception:
                pass
        except Exception as e:
            self.graph_label.setText(f"Error generating diagram: {e}")

class AWSInfraGUIV2(QMainWindow):
    def __init__(self):
        print("Initializing main window...")
        super().__init__()
        self.setWindowTitle("AWS Infrastructure Manager")
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.current_theme = 'light'  # Add this line
        self.set_theme(self.current_theme)  # Set default theme
        tab_definitions = [
            (DashboardTab, "Dashboard"),
            (EC2Tab, "EC2"),
            (S3Tab, "S3"),
            (LambdaTab, "Lambda"),
            (IAMTab, "IAM"),
            (IAMPolicyEditorTab, "IAM Policy Editor"),
            (SecurityAuditTab, "Security Audit"),
            #(ScheduledActionsTab, "Scheduled Actions"),  # Removed because not defined
            (SettingsTab, "Settings"),
            (CostExplorerTab, "Cost Explorer"),
            (CloudFrontTab, "CloudFront"),
            (RDSTab, "RDS"),
            (HelpTab, "Help"),
            (ResourceGraphTab, "Architecture Map"),
        ]
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        for TabClass, label in tab_definitions:
            if TabClass is SettingsTab:
                tab = TabClass(self)
            else:
                tab = TabClass()
            # Set the status bar for tabs that support it
            if hasattr(tab, 'set_status_bar'):
                tab.set_status_bar(self.status_bar)
            self.tabs.addTab(tab, label)
        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)
        self.file_menu = QMenu("File", self)
        self.menu_bar.addMenu(self.file_menu)
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)
        self.help_menu = QMenu("Help", self)
        self.menu_bar.addMenu(self.help_menu)
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.help_menu.addAction(self.about_action)
        self.show()

    def set_theme(self, theme):
        """Set the application theme (light or dark)."""
        if theme == 'dark':
            self.setStyleSheet(DARK_STYLE_SHEET)
            self.current_theme = 'dark'
        else:
            self.setStyleSheet(LIGHT_STYLE_SHEET)
            self.current_theme = 'light'
        if hasattr(self, 'status_bar') and self.status_bar:
            self.status_bar.log_message(f"Theme set to {theme.capitalize()}")

    def show_about_dialog(self):
        QMessageBox.about(self, "About", "AWS Infrastructure Manager\nVersion 2.0\nBuilt using Python and PyQt5")

# --- Generic Worker for Async Operations ---
class Worker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(Exception)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.exc = None

    def run(self):
        try:
            self.result = self.fn(*self.args, **self.kwargs)
            self.finished.emit(self.result)
        except Exception as e:
            self.exc = e
            self.error.emit(e)

class AsyncWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(Exception)
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def run(self):
        try:
            if self._is_cancelled:
                return
            result = self.fn(*self.args, **self.kwargs)
            if not self._is_cancelled:
                self.finished.emit(result)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(e)

    def cancel(self):
        self._is_cancelled = True

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = AWSInfraGUIV2()
    main_window.show()
    try:
        sys.exit(app.exec_())
    except Exception as e:
        import traceback
        print("Exception occurred:", e)
        traceback.print_exc()
        input("Press Enter to exit...")