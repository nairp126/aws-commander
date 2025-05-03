"""
AWS Infrastructure Manager GUI

A graphical user interface for the AWS Infrastructure Manager tool.

Prerequisites:
    - tkinter (should be included with standard Python installation)
    - PIL/Pillow (for icons): pip install pillow
"""

import os
import sys
import json
import threading
import tkinter as tk, os
from tkinter import ttk, messagebox, filedialog, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import importlib.util
from PIL import Image, ImageTk

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the project root directory to sys.path
sys.path.append(current_dir)

# Import project modules
from config import settings
from scripts.utils import logger, ensure_directory_exists
from scripts.utils import get_client, get_resource

# Conditional imports for GUI functionality
try:
    # Import project modules for AWS operations
    from scripts.iam_manager import IAMManager, setup_iam
    from scripts.ec2_manager import EC2Manager, setup_ec2_infrastructure
    from scripts.s3_manager import S3Manager, setup_s3_storage
    from scripts.lambda_manager import LambdaManager, setup_lambda
except Exception as e:
    print(f"Error importing project modules: {e}")
    # We'll show an error in the GUI

class RedirectText:
    """Class to redirect stdout/stderr to the GUI text widget"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""
        
    def write(self, string):
        self.buffer += string
        self.text_widget.configure(state=tk.NORMAL)
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.configure(state=tk.DISABLED)
        
    def flush(self):
        pass

class AWSInfraGUI:
    """Main GUI class for AWS Infrastructure Manager"""
    
    def __init__(self, root):
        """Initialize the GUI"""
        self.root = root
        self.root.title("AWS Infrastructure Manager")
        self.root.geometry("900x650")
        self.root.minsize(800, 600)
        
        # Set icon
        try:
            # Use a cloud icon if available
            self.root.iconphoto(True, tk.PhotoImage(file="assets/icon.png"))
        except:
            pass
            
        # Main frame for the GUI
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create menu
        self.create_menu()
        
        # Create top status bar
        self.create_status_bar()
        
        # Create notebook for tabbed interface
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.create_dashboard_tab()
        self.create_ec2_tab()
        self.create_s3_tab()
        self.create_lambda_tab()
        self.create_iam_tab()
        self.create_settings_tab()
        
        # Create console output area
        self.create_console_output()
        
        # Initialize status
        self.update_status("Ready")
        
        # AWS clients and resources
        self.aws_clients = {}
        self.aws_resources = {}
        
        # Configuration
        self.config = self.load_config()
        
        # AWS Managers
        self.ec2_manager = EC2Manager()
        
        # EC2 Frame and its contents are now part of __init__
        self.create_ec2_frame()
        
        # Status variables
        self.task_running = False
        
        # Check AWS credentials
    def load_config_dialog(self):
        """Load configuration from user-selected file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                self.load_config(filename)
                self.update_status(f"Configuration loaded and re-applied from {filename}")
            except Exception as e:
                self.update_status(f"Error loading config: {str(e)}", error=True)

    def save_config(self, filename):
        """Save the current configuration to a file"""
        try:
            config = self.get_current_config()
            ensure_directory_exists(os.path.dirname(filename))
            with open(filename, 'w') as f:
                json.dump(config, f, indent=4)
            self.update_status(f"Configuration saved to {filename}")
        except Exception as e:
            self.update_status(f"Error saving config: {str(e)}", error=True)

    def save_config_dialog(self):
        """Save configuration to user-selected file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.save_config(filename)
    def create_menu(self):
        """Create the application menu"""
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Configuration", command=self.save_config_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Operations menu
        ops_menu = tk.Menu(menubar, tearoff=0)
        ops_menu.add_command(label="Setup All", command=lambda: self.run_in_thread(self.setup_all))
        ops_menu.add_separator()
        ops_menu.add_command(label="Setup IAM", command=lambda: self.run_in_thread(self.setup_iam))
        ops_menu.add_command(label="Setup EC2", command=lambda: self.run_in_thread(self.setup_ec2))
        ops_menu.add_command(label="Setup S3", command=lambda: self.run_in_thread(self.setup_s3))
        ops_menu.add_command(label="Setup Lambda", command=lambda: self.run_in_thread(self.setup_lambda))
        menubar.add_cascade(label="Operations", menu=ops_menu)
        
        # List menu
        list_menu = tk.Menu(menubar, tearoff=0)
        list_menu.add_command(label="List EC2 Instances", command=lambda: self.run_in_thread(self.list_ec2))
        list_menu.add_command(label="List S3 Objects", command=lambda: self.run_in_thread(self.list_s3))
        list_menu.add_command(label="List Lambda Functions", command=lambda: self.run_in_thread(self.list_lambda))
        menubar.add_cascade(label="List", menu=list_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help", command=lambda: self.show_help())
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        # Configure root to use this menu
        self.root.config(menu=menubar)

    def show_help(self):
        """Display a help message box."""
        help_text = (
            "Welcome to the AWS Infrastructure Manager!\n\n"
            "Use the tabs to manage different AWS services: EC2, S3, Lambda, and IAM.\n"
            "The Operations menu provides quick setup and listing options.\n"
            "The Settings tab allows you to configure AWS credentials, region, and application preferences.\n"
            "Console output at the bottom shows real-time operation logs.\n\n"
            "Ensure your AWS credentials are set up correctly (via profile or explicitly in settings)."
        )
        messagebox.showinfo("Help", help_text)
    
    def show_about(self):
        """Display the about message box."""
        about_text = (
            "AWS Infrastructure Manager\n"
            "Version: 1.0\n"
            "Developer: [Your Name]\n\n" # Replace with your name
            "A tool for managing AWS infrastructure components."
        )
        messagebox.showinfo("About", about_text)
    
    def create_status_bar(self):
        """Create status bar at the top"""
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.aws_region_label = ttk.Label(self.status_frame, text=f"AWS Region: {settings.AWS_REGION}")
        self.aws_region_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # AWS Status indicator
        self.aws_status_var = tk.StringVar(value="AWS: Checking...")
        self.aws_status_label = ttk.Label(self.status_frame, textvariable=self.aws_status_var)
        self.aws_status_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Status message
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.RIGHT, padx=5)

        # Progress bar
        self.progress_bar = ttk.Progressbar(self.status_frame, orient="horizontal", length=200, mode="determinate")
        self.progress_bar.pack(side=tk.RIGHT, padx=5)

    
    def create_dashboard_tab(self):
        """Create the dashboard tab"""
        self.dashboard_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.dashboard_frame, text="Dashboard")
        
        # Welcome message
        welcome_label = ttk.Label(
            self.dashboard_frame, 
            text="AWS Infrastructure Manager", 
            font=("Helvetica", 16)
        )
        welcome_label.pack(pady=20)
        
        # Description
        desc_text = (
            "This tool helps you manage your AWS infrastructure components including "
            "EC2, S3, Lambda, and IAM resources. Use the tabs above to access "
            "different AWS services or use the Operations menu for setup commands."
        )
        desc_label = ttk.Label(
            self.dashboard_frame, 
            text=desc_text, 
            wraplength=600, 
            justify=tk.CENTER
        )
        desc_label.pack(pady=10, padx=20)
        
        # Quick action buttons frame
        action_frame = ttk.LabelFrame(self.dashboard_frame, text="Quick Actions")
        action_frame.pack(pady=20, padx=20, fill=tk.X)
        
        # Create a 2x2 grid of buttons
        setup_all_btn = ttk.Button(
            action_frame, 
            text="Setup All Infrastructure", 
            command=lambda: self.run_in_thread(self.setup_all)
        )
        setup_all_btn.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W+tk.E)
        
        list_resources_btn = ttk.Button(
            action_frame, 
            text="List All Resources", 
            command=lambda: self.run_in_thread(self.list_all_resources)
        )
        list_resources_btn.grid(row=0, column=1, padx=10, pady=10, sticky=tk.W+tk.E)
        
        config_btn = ttk.Button(
            action_frame, 
            text="Edit Configuration", 
            command=lambda: self.notebook.select(5)  # Switch to settings tab
        )
        config_btn.grid(row=1, column=0, padx=10, pady=10, sticky=tk.W+tk.E)
        
        check_status_btn = ttk.Button(
            action_frame, 
            text="Check AWS Status", 
            command=lambda: self.run_in_thread(self.check_aws_status)
        )
        check_status_btn.grid(row=1, column=1, padx=10, pady=10, sticky=tk.W+tk.E)
        
        # Configure grid columns
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        
        # Status summary frame
        status_frame = ttk.LabelFrame(self.dashboard_frame, text="Resource Status")
        status_frame.pack(pady=20, padx=20, fill=tk.BOTH, expand=True)
        
        # Create treeview for resources
        self.resource_tree = ttk.Treeview(status_frame, columns=("Type", "Count", "Status"))
        self.resource_tree.heading("#0", text="Service")
        self.resource_tree.heading("Type", text="Resource Type")
        self.resource_tree.heading("Count", text="Count")
        self.resource_tree.heading("Status", text="Status")
        
        self.resource_tree.column("#0", width=100, stretch=tk.YES)
        self.resource_tree.column("Type", width=150, stretch=tk.YES)
        self.resource_tree.column("Count", width=80, stretch=tk.YES)
        self.resource_tree.column("Status", width=150, stretch=tk.YES)
        
        self.resource_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add refresh button
        refresh_btn = ttk.Button(
            status_frame, 
            text="Refresh Status", 
            command=lambda: self.run_in_thread(self.refresh_resource_status)
        )
        refresh_btn.pack(pady=5)
        
      
    
    def create_ec2_tab(self):
        """Create the EC2 tab"""
        self.ec2_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ec2_frame, text="EC2")
        
        # EC2 Actions frame
        ec2_actions = ttk.LabelFrame(self.ec2_frame, text="EC2 Actions")
        ec2_actions.pack(fill=tk.X, padx=10, pady=10)
        
        # EC2 Buttons
        setup_ec2_btn = ttk.Button(
            ec2_actions, 
            text="Setup EC2 Infrastructure", 
            command=lambda: self.run_in_thread(self.setup_ec2)
        )
        setup_ec2_btn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W+tk.E)
        
        list_ec2_btn = ttk.Button(
            ec2_actions, 
            text="List EC2 Instances", 
            command=lambda: self.run_in_thread(self.list_ec2)
        )
        list_ec2_btn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        terminate_ec2_btn = ttk.Button(
            ec2_actions, 
            text="Terminate Selected", 
            command=self.terminate_selected_ec2
        )
        terminate_ec2_btn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Configure grid
        ec2_actions.columnconfigure(0, weight=1)
        ec2_actions.columnconfigure(1, weight=1)
        ec2_actions.columnconfigure(2, weight=1)
        
        # EC2 Configuration frame
        ec2_config = ttk.LabelFrame(self.ec2_frame, text="EC2 Configuration")
        ec2_config.pack(fill=tk.X, padx=10, pady=10)
        
        # AMI ID
        ttk.Label(ec2_config, text="AMI ID:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.ami_id_var = tk.StringVar(value=settings.EC2_AMI_ID)
        ttk.Entry(ec2_config, textvariable=self.ami_id_var).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Instance Type
        ttk.Label(ec2_config, text="Instance Type:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.instance_type_var = tk.StringVar(value=settings.EC2_INSTANCE_TYPE)
        instance_types = ["t2.micro", "t2.small", "t2.medium", "t3.micro", "t3.small", "t3.medium"]
        ttk.Combobox(ec2_config, textvariable=self.instance_type_var, values=instance_types).grid(
            row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E
        )
        
        # Key Pair
        ttk.Label(ec2_config, text="Key Pair:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.key_pair_var = tk.StringVar(value=settings.EC2_KEY_NAME)
        ttk.Entry(ec2_config, textvariable=self.key_pair_var).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Configure grid
        ec2_config.columnconfigure(1, weight=1)
        
        # EC2 Instances frame
        ec2_instances = ttk.LabelFrame(self.ec2_frame, text="EC2 Instances")
        ec2_instances.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create treeview for instances
        self.ec2_tree = ttk.Treeview(
            ec2_instances, 
            columns=("ID", "Type", "State", "Public IP", "Launch Time")
        )
        
        # EC2 Treeview Headings and Columns
        self.ec2_tree.heading("#0", text="")
        self.ec2_tree.heading("ID", text="Instance ID")
        self.ec2_tree.heading("Type", text="Type")
        self.ec2_tree.heading("State", text="State")
        self.ec2_tree.heading("Public IP", text="Public IP")
        self.ec2_tree.heading("Launch Time", text="Launch Time")
    
        # Context Menu for EC2
        self.ec2_context_menu = tk.Menu(self.ec2_tree, tearoff=0)
        self.ec2_context_menu.add_command(label="Start Instance", command=self.start_selected_ec2)
        self.ec2_context_menu.add_command(label="Stop Instance", command=self.stop_selected_ec2)
        self.ec2_context_menu.add_command(label="Reboot Instance", command=self.reboot_selected_ec2)
        self.ec2_context_menu.add_command(label="View Details", command=self.view_ec2_details)
        self.ec2_tree.bind("<Button-3>", self.show_ec2_context_menu)

    def start_selected_ec2(self):        
        """Start selected EC2 instance"""
        selected_items = self.ec2_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select an EC2 instance to start.")
            return
        instance_id = self.ec2_tree.item(selected_items[0])['values'][0]
        self.run_in_thread(self._start_ec2_instance, instance_id)

    def _start_ec2_instance(self, instance_id):
        """Internal method to start an EC2 instance"""
        try:
            self.update_status(f"Starting EC2 instance {instance_id}...")
            ec2_client = get_client('ec2')
            ec2_client.start_instances(InstanceIds=[instance_id])
            self.update_status(f"EC2 instance {instance_id} started successfully")
            self.list_ec2()
        except Exception as e:
            self.update_status(f"Error starting EC2 instance {instance_id}: {str(e)}", error=True)

    def stop_selected_ec2(self):
        """Stop selected EC2 instance"""
        selected_items = self.ec2_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select an EC2 instance to stop.")
            return
        instance_id = self.ec2_tree.item(selected_items[0])['values'][0]
        confirm = messagebox.askyesno(
            "Confirm Stop",
            f"Are you sure you want to stop instance {instance_id}? This may cause data loss."
        )
        if confirm:
            self.run_in_thread(self._stop_ec2_instance, instance_id)

    def _stop_ec2_instance(self, instance_id):
        """Internal method to stop an EC2 instance"""
        try:
            self.update_status(f"Stopping EC2 instance {instance_id}...")
            ec2_client = get_client('ec2')
            ec2_client.stop_instances(InstanceIds=[instance_id])
            self.update_status(f"EC2 instance {instance_id} stopped successfully")
            self.list_ec2()
        except Exception as e:
            self.update_status(f"Error stopping EC2 instance {instance_id}: {str(e)}", error=True)

    def reboot_selected_ec2(self):        
        """Reboot selected EC2 instance"""
        selected_items = self.ec2_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select an EC2 instance to reboot.")
            return
        instance_id = self.ec2_tree.item(selected_items[0])['values'][0]
        confirm = messagebox.askyesno(
            "Confirm Reboot",
            f"Are you sure you want to reboot instance {instance_id}?"
        )
        if confirm:
            self.run_in_thread(self._reboot_ec2_instance, instance_id)

    def _reboot_ec2_instance(self, instance_id):
        """Internal method to reboot an EC2 instance"""
        try:
            self.update_status(f"Rebooting EC2 instance {instance_id}...")
            ec2_client = get_client('ec2')
            ec2_client.reboot_instances(InstanceIds=[instance_id])
            self.update_status(f"EC2 instance {instance_id} reboot initiated")
            self.list_ec2()
        except Exception as e:
            self.update_status(f"Error rebooting EC2 instance {instance_id}: {str(e)}", error=True)

    def view_ec2_details(self):
        """View details of selected EC2 instance"""
        selected_items = self.ec2_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select an EC2 instance to view details.")
            return
        instance_id = self.ec2_tree.item(selected_items[0])['values'][0]
        self.run_in_thread(self._get_ec2_instance_details, instance_id)

    def _get_ec2_instance_details(self, instance_id):
        """Internal method to retrieve and display EC2 instance details"""
        try:
            ec2_client = get_client('ec2')
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            instance_data = response['Reservations'][0]['Instances'][0]
            messagebox.showinfo(f"EC2 Instance Details: {instance_id}", json.dumps(instance_data, indent=4, default=str))
        except Exception as e:
            self.update_status(f"Error retrieving details for EC2 instance {instance_id}: {str(e)}", error=True)

    def create_s3_tab(self):
        """Create the S3 tab"""
        self.s3_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.s3_frame, text="S3")
        
        # S3 Actions frame
        s3_actions = ttk.LabelFrame(self.s3_frame, text="S3 Actions")
        s3_actions.pack(fill=tk.X, padx=10, pady=10)
        
        # S3 Buttons
        setup_s3_btn = ttk.Button(
            s3_actions, 
            text="Setup S3 Storage", 
            command=lambda: self.run_in_thread(self.setup_s3)
        )
        setup_s3_btn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W+tk.E)
        
        list_s3_btn = ttk.Button(
            s3_actions, 
            text="List S3 Objects", 
            command=lambda: self.run_in_thread(self.list_s3)
        )
        list_s3_btn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        upload_btn = ttk.Button(
            s3_actions, 
            text="Upload File", 
            command=self.upload_to_s3
        )
        upload_btn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W+tk.E)
        
        download_btn = ttk.Button(
            s3_actions, 
            text="Download Selected", 
            command=self.download_from_s3
        )
        download_btn.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W+tk.E)
        
        delete_obj_btn = ttk.Button(
            s3_actions, 
            text="Delete Selected", 
            command=self.delete_s3_object
        )
        delete_obj_btn.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        refresh_s3_btn = ttk.Button(
            s3_actions, 
            text="Refresh", 
            command=lambda: self.run_in_thread(self.list_s3)
        )
        refresh_s3_btn.grid(row=1, column=2, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Configure grid
        s3_actions.columnconfigure(0, weight=1)
        s3_actions.columnconfigure(1, weight=1)
        s3_actions.columnconfigure(2, weight=1)
        
        # S3 Configuration frame
        s3_config = ttk.LabelFrame(self.s3_frame, text="S3 Configuration")
        s3_config.pack(fill=tk.X, padx=10, pady=10)
        
        # Bucket Name
        ttk.Label(s3_config, text="Bucket Name:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.bucket_name_var = tk.StringVar(value=settings.S3_BUCKET_NAME)
        ttk.Entry(s3_config, textvariable=self.bucket_name_var).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Upload Path
        ttk.Label(s3_config, text="Local Upload File:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.upload_path_var = tk.StringVar(value=settings.LOCAL_UPLOAD_FILE)
        upload_path_entry = ttk.Entry(s3_config, textvariable=self.upload_path_var)
        upload_path_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        browse_upload_btn = ttk.Button(
            s3_config, 
            text="Browse", 
            command=lambda: self.browse_file(self.upload_path_var)
        )
        browse_upload_btn.grid(row=1, column=2, padx=5, pady=5)
        
        # Download Directory
        ttk.Label(s3_config, text="Download Directory:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.download_dir_var = tk.StringVar(value=settings.LOCAL_DOWNLOAD_DIR)
        download_dir_entry = ttk.Entry(s3_config, textvariable=self.download_dir_var)
        download_dir_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        browse_download_btn = ttk.Button(
            s3_config, 
            text="Browse", 
            command=lambda: self.browse_directory(self.download_dir_var)
        )
        browse_download_btn.grid(row=2, column=2, padx=5, pady=5)
        
        # Configure grid
        s3_config.columnconfigure(1, weight=1)
        
        # S3 Objects frame
        s3_objects = ttk.LabelFrame(self.s3_frame, text="S3 Objects")
        s3_objects.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create treeview for objects
        self.s3_tree = ttk.Treeview(s3_objects, columns=("Key", "Size", "Last Modified"))
        self.s3_tree.heading("#0", text="")
        self.s3_tree.heading("Key", text="Object Key")
        self.s3_tree.heading("Size", text="Size")
        self.s3_tree.heading("Last Modified", text="Last Modified")
        
        self.s3_tree.column("#0", width=20, stretch=tk.NO)
        self.s3_tree.column("Key", width=300, stretch=tk.YES)
        self.s3_tree.column("Size", width=100, stretch=tk.YES)
        self.s3_tree.column("Last Modified", width=180, stretch=tk.YES)
        
        # Add scrollbar
        s3_scroll = ttk.Scrollbar(s3_objects, orient="vertical", command=self.s3_tree.yview)
        self.s3_tree.configure(yscrollcommand=s3_scroll.set)
        
        s3_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.s3_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    def upload_to_s3(self):
        """Upload a file to S3"""
        bucket_name = self.bucket_name_var.get()
        file_path = self.upload_path_var.get()
        if not bucket_name or not file_path:
            messagebox.showinfo("Incomplete Information", "Please specify both the bucket name and the local file path.")
            return
        if not os.path.exists(file_path):
            messagebox.showinfo("File Not Found", "The specified file does not exist.")
            return
        self.run_in_thread(self._upload_file, bucket_name, file_path)

    def _upload_file(self, bucket_name, file_path):
        """Internal method to upload file to S3"""
        try:
            self.update_status(f"Uploading {file_path} to S3 bucket {bucket_name}...")
            s3_client = get_client('s3')
            file_name = os.path.basename(file_path)
            s3_client.upload_file(file_path, bucket_name, file_name)
            self.update_status(f"Successfully uploaded {file_name} to S3 bucket {bucket_name}")
            self.list_s3()
        except Exception as e:
            self.update_status(f"Error uploading file to S3: {str(e)}", error=True)

    def download_from_s3(self):
        """Download selected object from S3"""
        selected_items = self.s3_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select an object to download.")
            return
        bucket_name = self.bucket_name_var.get()
        object_key = self.s3_tree.item(selected_items[0])['values'][0]
        download_dir = self.download_dir_var.get()
        self.run_in_thread(self._download_file, bucket_name, object_key, download_dir)

    def _download_file(self, bucket_name, object_key, download_dir):
        """Internal method to download object from S3"""
        try:
            self.update_status(f"Downloading {object_key} from S3 bucket {bucket_name}...")
            s3_client = get_client('s3')
            local_path = os.path.join(download_dir, os.path.basename(object_key))
            s3_client.download_file(bucket_name, object_key, local_path)
            self.update_status(f"Successfully downloaded {object_key} to {local_path}")
            messagebox.showinfo("Download Complete", f"File downloaded to: {local_path}")
        except Exception as e:
            self.update_status(f"Error downloading file from S3: {str(e)}", error=True)

    def delete_s3_object(self):
        """Delete selected object from S3"""
        selected_items = self.s3_tree.selection()
        if not selected_items:
            messagebox.showinfo("No Selection", "Please select an object to delete.")
            return
        
        bucket_name = self.bucket_name_var.get()
        object_key = self.s3_tree.item(selected_items[0])['values'][0]
        
        confirm = messagebox.askyesno(
            "Confirm Deletion", 
            f"Are you sure you want to delete object '{object_key}' from bucket '{bucket_name}'?"
        )
        if confirm:
            self.run_in_thread(self._delete_object, bucket_name, object_key)

    def create_lambda_tab(self):
        """Create the Lambda tab"""
        self.lambda_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.lambda_frame, text="Lambda")
        
        # Lambda Actions frame
        lambda_actions = ttk.LabelFrame(self.lambda_frame, text="Lambda Actions")
        lambda_actions.pack(fill=tk.X, padx=10, pady=10)
        
        # Lambda Buttons
        setup_lambda_btn = ttk.Button(
            lambda_actions, 
            text="Setup Lambda Function", 
            command=lambda: self.run_in_thread(self.setup_lambda)
        )
        setup_lambda_btn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W+tk.E)
        
        list_lambda_btn = ttk.Button(
            lambda_actions, 
            text="List Lambda Functions", 
            command=lambda: self.run_in_thread(self.list_lambda)
        )
        list_lambda_btn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        update_lambda_btn = ttk.Button(
            lambda_actions, 
            text="Update Lambda Code", 
            command=self.update_lambda_code
        )
        update_lambda_btn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Configure grid
        lambda_actions.columnconfigure(0, weight=1)
        lambda_actions.columnconfigure(1, weight=1)
        lambda_actions.columnconfigure(2, weight=1)
        
        # Lambda Configuration frame
        lambda_config = ttk.LabelFrame(self.lambda_frame, text="Lambda Configuration")
        lambda_config.pack(fill=tk.X, padx=10, pady=10)
        
        # Function Name
        ttk.Label(lambda_config, text="Function Name:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.lambda_name_var = tk.StringVar(value=settings.LAMBDA_FUNCTION_NAME)
        ttk.Entry(lambda_config, textvariable=self.lambda_name_var).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # ZIP Path
        ttk.Label(lambda_config, text="ZIP File Path:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.lambda_zip_var = tk.StringVar(value=settings.LAMBDA_ZIP_PATH)
        zip_path_entry = ttk.Entry(lambda_config, textvariable=self.lambda_zip_var)
        zip_path_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        browse_zip_btn = ttk.Button(
            lambda_config, 
            text="Browse", 
            command=lambda: self.browse_file(self.lambda_zip_var)
        )
        browse_zip_btn.grid(row=1, column=2, padx=5, pady=5)
        
        # Memory and Timeout
        memory_frame = ttk.Frame(lambda_config)
        memory_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        
        ttk.Label(memory_frame, text="Memory (MB):").pack(side=tk.LEFT, padx=(0, 5))
        self.lambda_memory_var = tk.StringVar(value=str(settings.LAMBDA_MEMORY_SIZE))
        ttk.Spinbox(memory_frame, from_=128, to=3008, increment=64, textvariable=self.lambda_memory_var, width=6).pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Label(memory_frame, text="Timeout (sec):").pack(side=tk.LEFT, padx=(0, 5))
        self.lambda_timeout_var = tk.StringVar(value=str(settings.LAMBDA_TIMEOUT))
        ttk.Spinbox(memory_frame, from_=1, to=900, increment=10, textvariable=self.lambda_timeout_var, width=5).pack(side=tk.LEFT)
        
        # Configure grid
        lambda_config.columnconfigure(1, weight=1)
        
        # Lambda Code Editor
        lambda_code = ttk.LabelFrame(self.lambda_frame, text="Lambda Function Code")
        lambda_code.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create code editor with line numbers
        self.lambda_code_editor = scrolledtext.ScrolledText(lambda_code, wrap=tk.NONE, font=("Courier", 10))
        self.lambda_code_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
    def update_lambda_code(self):
        """Update Lambda function code"""
        function_name = self.lambda_name_var.get()
        zip_file_path = self.lambda_zip_var.get()
        if not function_name or not zip_file_path:
            messagebox.showinfo("Incomplete Information", "Please specify both the function name and the ZIP file path.")
            return
        if not os.path.exists(zip_file_path):
            messagebox.showinfo("File Not Found", "The specified ZIP file does not exist.")
            return
        self.run_in_thread(self._update_lambda_code, function_name, zip_file_path)

    def _update_lambda_code(self, function_name, zip_file_path):
        """Internal method to update Lambda code"""
        try:
            self.update_status(f"Updating Lambda function {function_name} with code from {zip_file_path}...")
            lambda_client = get_client('lambda')
            with open(zip_file_path, 'rb') as f:
                lambda_client.update_function_code(FunctionName=function_name, ZipFile=f.read())
            self.update_status(f"Successfully updated Lambda function {function_name}")
        except Exception as e:
            self.update_status(f"Error updating Lambda function: {str(e)}", error=True)

"""
Continuation of AWS Infrastructure Manager GUI implementation
"""

def create_iam_tab(self):
    """Create the IAM tab"""
    self.iam_frame = ttk.Frame(self.notebook)
    self.notebook.add(self.iam_frame, text="IAM")
    
    # IAM Actions frame
    iam_actions = ttk.LabelFrame(self.iam_frame, text="IAM Actions")
    iam_actions.pack(fill=tk.X, padx=10, pady=10)
    
    # IAM Buttons
    setup_iam_btn = ttk.Button(
        iam_actions, 
        text="Setup IAM Roles", 
        command=lambda: self.run_in_thread(self.setup_iam)
    )
    setup_iam_btn.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W+tk.E)
    
    list_roles_btn = ttk.Button(
        iam_actions, 
        text="List IAM Roles", 
        command=lambda: self.run_in_thread(self.list_iam_roles)
    )
    list_roles_btn.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    delete_role_btn = ttk.Button(
        iam_actions, 
        text="Delete Selected", 
        command=self.delete_selected_role
    )
    delete_role_btn.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W+tk.E)
    
    # Configure grid
    iam_actions.columnconfigure(0, weight=1)
    iam_actions.columnconfigure(1, weight=1)
    iam_actions.columnconfigure(2, weight=1)
    
    # IAM Configuration frame
    iam_config = ttk.LabelFrame(self.iam_frame, text="IAM Configuration")
    iam_config.pack(fill=tk.X, padx=10, pady=10)
    
    # Role Name
    ttk.Label(iam_config, text="Role Name:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    self.role_name_var = tk.StringVar(value=settings.IAM_ROLE_NAME)
    ttk.Entry(iam_config, textvariable=self.role_name_var).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    # Policy Name
    ttk.Label(iam_config, text="Policy Name:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
    self.policy_name_var = tk.StringVar(value=settings.IAM_POLICY_NAME)
    ttk.Entry(iam_config, textvariable=self.policy_name_var).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    # Configure grid
    iam_config.columnconfigure(1, weight=1)
    
    # IAM Roles frame
    iam_roles = ttk.LabelFrame(self.iam_frame, text="IAM Roles")
    iam_roles.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # Create treeview for roles
    self.iam_tree = ttk.Treeview(iam_roles, columns=("Role Name", "ARN", "Creation Date"))
    self.iam_tree.heading("#0", text="")
    self.iam_tree.heading("Role Name", text="Role Name")
    self.iam_tree.heading("ARN", text="ARN")
    self.iam_tree.heading("Creation Date", text="Creation Date")
    
    self.iam_tree.column("#0", width=20, stretch=tk.NO)
    self.iam_tree.column("Role Name", width=150, stretch=tk.YES)
    self.iam_tree.column("ARN", width=300, stretch=tk.YES)
    self.iam_tree.column("Creation Date", width=150, stretch=tk.YES)
    
    # Add scrollbar
    iam_scroll = ttk.Scrollbar(iam_roles, orient="vertical", command=self.iam_tree.yview)
    self.iam_tree.configure(yscrollcommand=iam_scroll.set)
    
    iam_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    self.iam_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

def create_settings_tab(self):
    """Create the settings tab"""
    self.settings_frame = ttk.Frame(self.notebook)
    self.notebook.add(self.settings_frame, text="Settings")
    
    # AWS Settings frame
    aws_settings = ttk.LabelFrame(self.settings_frame, text="AWS Settings")
    aws_settings.pack(fill=tk.X, padx=10, pady=10)
    
    # Region
    ttk.Label(aws_settings, text="AWS Region:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    self.region_var = tk.StringVar(value=settings.AWS_REGION)
    regions = [
        "us-east-1", "us-east-2", "us-west-1", "us-west-2", 
        "eu-west-1", "eu-west-2", "eu-central-1", 
        "ap-northeast-1", "ap-northeast-2", "ap-southeast-1", "ap-southeast-2", 
        "sa-east-1", "ca-central-1"
    ]
    region_combo = ttk.Combobox(aws_settings, textvariable=self.region_var, values=regions)
    region_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    # AWS Profile Management
    profile_frame = ttk.LabelFrame(aws_settings, text="AWS Profile Management")
    profile_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W + tk.E)

    # Profile Selection
    ttk.Label(profile_frame, text="Select Profile:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    self.profile_var = tk.StringVar()
    self.profile_combo = ttk.Combobox(profile_frame, textvariable=self.profile_var, state="readonly")
    self.profile_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W + tk.E)
    self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_select)

    # New Profile Name
    ttk.Label(profile_frame, text="New Profile Name:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
    ttk.Entry(profile_frame, textvariable=self.profile_var).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W + tk.E)
    
    # Credentials
    creds_frame = ttk.LabelFrame(aws_settings, text="Credentials (Alternative to Profile)")
    creds_frame.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W+tk.E)
    
    ttk.Label(creds_frame, text="Access Key:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    self.access_key_var = tk.StringVar(value=settings.AWS_ACCESS_KEY if hasattr(settings, 'AWS_ACCESS_KEY') else "")
    ttk.Entry(creds_frame, textvariable=self.access_key_var, show="*").grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    ttk.Label(creds_frame, text="Secret Key:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
    self.secret_key_var = tk.StringVar(value=settings.AWS_SECRET_KEY if hasattr(settings, 'AWS_SECRET_KEY') else "")
    ttk.Entry(creds_frame, textvariable=self.secret_key_var, show="*").grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    creds_frame.columnconfigure(1, weight=1)
    
    # Configure grid
    aws_settings.columnconfigure(1, weight=1)
    
    # App Settings frame
    app_settings = ttk.LabelFrame(self.settings_frame, text="Application Settings")
    app_settings.pack(fill=tk.X, padx=10, pady=10)
    
    # Log Level
    ttk.Label(app_settings, text="Log Level:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    self.log_level_var = tk.StringVar(value=settings.LOG_LEVEL)
    log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    log_level_combo = ttk.Combobox(app_settings, textvariable=self.log_level_var, values=log_levels)
    log_level_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    # Log File
    ttk.Label(app_settings, text="Log File:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
    self.log_file_var = tk.StringVar(value=settings.LOG_FILE)
    log_file_entry = ttk.Entry(app_settings, textvariable=self.log_file_var)
    log_file_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
    
    browse_log_btn = ttk.Button(
        app_settings, 
        text="Browse", 
        command=lambda: self.browse_file_save(self.log_file_var)
    )
    browse_log_btn.grid(row=1, column=2, padx=5, pady=5)
    
    # Configure grid
    app_settings.columnconfigure(1, weight=1)
    
    # Actions frame
    actions_frame = ttk.Frame(self.settings_frame)
    actions_frame.pack(fill=tk.X, padx=10, pady=20)
    
    # Button to save settings
    save_settings_btn = ttk.Button(
        actions_frame, 
        text="Save Settings", 
        command=self.save_settings
    )
    save_settings_btn.pack(side=tk.RIGHT, padx=5)
    
    # Button to reload settings
    reload_settings_btn = ttk.Button(
        actions_frame, 
        text="Reload Settings", 
        command=self.reload_settings
    )
    reload_settings_btn.pack(side=tk.RIGHT, padx=5)

def create_console_output(self):
    """Create console output area at the bottom"""
    self.console_frame = ttk.LabelFrame(self.main_frame, text="Console Output")
    self.console_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=10)
    
    # Create text widget for output with scrollbar
    self.console_text = scrolledtext.ScrolledText(self.console_frame, height=10, wrap=tk.WORD)
    self.console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    self.console_text.configure(state=tk.DISABLED)
    
    # Redirect stdout and stderr to the console
    self.stdout_redirect = RedirectText(self.console_text)
    self.old_stdout = sys.stdout
    self.old_stderr = sys.stderr
    sys.stdout = self.stdout_redirect
    sys.stderr = self.stdout_redirect
    
    # Button to clear console
    clear_btn = ttk.Button(
        self.console_frame, 
        text="Clear Console", 
        command=self.clear_console
    )
    clear_btn.pack(side=tk.RIGHT, padx=5, pady=5)

# --------------- Utility Methods ---------------

def update_status(self, message, error=False):
    """Update status bar with message"""
    self.status_var.set(message)
    if error:
        print(f"ERROR: {message}")
    else:
        print(message)

def check_aws_credentials(self):
    """Check if AWS credentials are valid"""
    self.run_in_thread(self.check_aws_status)

def check_aws_status(self):
    """Check AWS connection status"""
    try:
        self.update_status("Checking AWS credentials...")
        client = get_client('sts')
        identity = client.get_caller_identity()
        account_id = identity['Account']
        self.aws_status_var.set(f"AWS: Connected (Account: {account_id})")
        self.update_status("AWS credentials verified successfully")
        return True
    except Exception as e:
        self.aws_status_var.set("AWS: Not Connected")
        self.update_status(f"AWS credentials error: {str(e)}", error=True)
        return False

def run_in_thread(self, func, *args, **kwargs):
    """Run a function in a separate thread to avoid UI freezing"""
    if self.task_running:
        messagebox.showinfo("Task Running", "Please wait for the current task to complete.")
        return
    
    self.task_running = True
    threading.Thread(target=self._run_task, args=(func, args, kwargs)).start()

def _run_task(self, func, args, kwargs):
    """Execute a task and handle exceptions"""
    try:
        self.update_progress(0)
        func(*args, **kwargs)
        self.update_progress(100)
    except Exception as e:
        self.update_status(f"Error: {str(e)}", error=True)
        logger.error(f"Error in task: {str(e)}", exc_info=True)
    finally:
        self.task_running = False

def update_progress(self, value, message=None):
    """Update progress bar and status label."""
    # Safely update UI elements from any thread
    if 0 <= value <= 100:
        self.root.after(0, self._update_progress_ui, value, message)

def _update_progress_ui(self, value, message):
    """Helper method to update the progress bar and status label."""
    if value == 0:
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
    elif value == 100:
        self.progress_bar.stop()
        self.progress_bar['value'] = 0
        self.progress_bar.configure(mode="determinate")
    else:
        self.progress_bar.configure(mode="determinate")
        self.progress_bar['value'] = value
    if message:
        self.status_var.set(message)

def clear_console(self):
    """Clear the console output""" 
    self.console_text.configure(state=tk.NORMAL)
    self.console_text.delete(1.0, tk.END)
    self.console_text.configure(state=tk.DISABLED)

def browse_file(self, var):
    """Open file browser dialog"""
    filename = filedialog.askopenfilename()
    if filename:
        var.set(filename)

def browse_file_save(self, var):
    """Open file save dialog"""
    filename = filedialog.asksaveasfilename()
    if filename:
        var.set(filename)

def browse_directory(self, var):
    """Open directory browser dialog"""
    directory = filedialog.askdirectory()
    if directory:
        var.set(directory)

def load_config(self):
    """Load configuration from file"""
    try:
        config_path = os.path.join(current_dir, 'config', 'app_config.json')
        if not os.path.exists(config_path):
            config = {}
            self.update_status("No existing configuration file found, starting with a blank configuration.")
            return config

        with open(config_path, 'r') as f:
            config_data = json.load(f)

        # Check if the config file is structured for multiple profiles
        if isinstance(config_data, dict) and any(isinstance(v, dict) for v in config_data.values()):
            config = config_data
            self.profile_combo['values'] = list(config.keys())
            
            # Select a default profile
            default_profile = 'default' if 'default' in config else list(config.keys())[0] if config else None
            if default_profile:
                self.profile_var.set(default_profile)
                self.apply_config(config)
                self.update_status(f"Configuration loaded and profile '{default_profile}' selected")
            else:
                self.update_status("Configuration loaded, but no profiles found.")
            
            return config

        

        else:
            # If the file is in the old format, wrap it under a "default" profile
            return {"default": config_data}

    except Exception as e:
        self.update_status(f"Error loading config: {str(e)}", error=True)
        return {}

def on_profile_select(self, event):
    """Handle profile selection from Combobox."""
    selected_profile = self.profile_combo.get()
    if selected_profile in self.config:
        try:
            self.apply_config(self.config)
        except Exception as e:
            self.update_status(f"Error saving config: {str(e)}", error=True)

def apply_config(self, config):
    """Apply loaded configuration to the UI focd ..r the current profile."""
    current_profile = self.profile_var.get()
    if current_profile and current_profile in config:
        profile_config = config[current_profile]

        # AWS settings
        if 'aws_region' in profile_config:
            self.region_var.set(profile_config['aws_region'])
        if 'aws_access_key' in profile_config:
            self.access_key_var.set(profile_config['aws_access_key'])
        if 'aws_secret_key' in profile_config:
            self.secret_key_var.set(profile_config['aws_secret_key'])

        # EC2 settings
        if 'ec2_ami_id' in profile_config:
            self.ami_id_var.set(profile_config['ec2_ami_id'])
        if 'ec2_instance_type' in profile_config:
            self.instance_type_var.set(profile_config['ec2_instance_type'])
        if 'ec2_key_name' in profile_config:
            self.key_pair_var.set(profile_config['ec2_key_name'])

        # S3 settings
        if 's3_bucket_name' in profile_config:
            self.bucket_name_var.set(profile_config['s3_bucket_name'])
        if 'local_upload_file' in profile_config:
            self.upload_path_var.set(profile_config['local_upload_file'])
        if 'local_download_dir' in profile_config:
            self.download_dir_var.set(profile_config['local_download_dir'])

        # Lambda settings
        if 'lambda_function_name' in profile_config:
            self.lambda_name_var.set(profile_config['lambda_function_name'])
        if 'lambda_zip_path' in profile_config:
            self.lambda_zip_var.set(profile_config['lambda_zip_path'])
        if 'lambda_memory_size' in profile_config:
            self.lambda_memory_var.set(str(profile_config['lambda_memory_size']))
        if 'lambda_timeout' in profile_config:
            self.lambda_timeout_var.set(str(profile_config['lambda_timeout']))

        # IAM settings
        if 'iam_role_name' in profile_config:
            self.role_name_var.set(profile_config['iam_role_name'])
        if 'iam_policy_name' in profile_config:
            self.policy_name_var.set(profile_config['iam_policy_name'])

        # App settings
        if 'log_level' in profile_config:
            self.log_level_var.set(profile_config['log_level'])
        if 'log_file' in profile_config:
            self.log_file_var.set(profile_config['log_file'])


def get_current_config(self):
    """Get the current configuration for the selected profile from UI"""
    current_profile = self.profile_var.get()
    if not current_profile:
        return {}
    profile_config = {
        # AWS settings
        'aws_region': self.region_var.get(),
        'aws_access_key': self.access_key_var.get(),
        'aws_secret_key': self.secret_key_var.get(),

        # EC2 settings
        'ec2_ami_id': self.ami_id_var.get(),
        'ec2_instance_type': self.instance_type_var.get(),
        'ec2_key_name': self.key_pair_var.get(),

        # S3 settings
        's3_bucket_name': self.bucket_name_var.get(),
        'local_upload_file': self.upload_path_var.get(),
        'local_download_dir': self.download_dir_var.get(),

        # Lambda settings
        'lambda_function_name': self.lambda_name_var.get(),
        'lambda_zip_path': self.lambda_zip_var.get(),
        'lambda_memory_size': int(self.lambda_memory_var.get()),
        'lambda_timeout': int(self.lambda_timeout_var.get()),

        # IAM settings
        'iam_role_name': self.role_name_var.get(),
        'iam_policy_name': self.policy_name_var.get(),

        # App settings
        'log_level': self.log_level_var.get(),
        'log_file': self.log_file_var.get()
    }

    return {current_profile: profile_config}

def save_settings(self):
    """Save settings to the config file, handling multiple profiles."""
    try:
        current_profile = self.profile_var.get()
        new_profile_config = self.get_current_config()[current_profile]
        config_file = os.path.join(current_dir, 'config', 'app_config.json')
        ensure_directory_exists(os.path.dirname(config_file))

        if not current_profile:
            raise ValueError("No profile name specified.")

        # Load existing config or create an empty dictionary
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                all_profiles_config = json.load(f)
        else:
            all_profiles_config = {}

        # Update or add the new profile config
        all_profiles_config[current_profile] = new_profile_config

        # Save the updated config
        with open(config_file, 'w') as f:
            json.dump(all_profiles_config, f, indent=4)

        self.update_status("Settings saved successfully")
    except Exception as e:
        self.update_status(f"Error saving settings: {str(e)}", error=True)

def reload_settings(self):
    """Reload settings from config file"""
    config = self.load_config()
    if config:
        self.config = config
        self.apply_config(config)
        self.update_status("Settings reloaded")
    else:
        self.update_status("No saved settings found")
        
    def initialize_dashboard(self):
        """Initialize dashboard with empty data"""
        services = ["EC2", "S3", "Lambda", "IAM"]
        for service in services:
            service_id = self.resource_tree.insert("", "end", text=service)
            if service == "EC2":
                self.resource_tree.insert(service_id, "end", values=("Instances", "0", "Not checked"))
            elif service == "S3":
                self.resource_tree.insert(service_id, "end", values=("Buckets", "0", "Not checked"))
                self.resource_tree.insert(service_id, "end", values=("Objects", "0", "Not checked"))
            elif service == "Lambda":
                self.resource_tree.insert(service_id, "end", values=("Functions", "0", "Not checked"))
            elif service == "IAM":
                self.resource_tree.insert(service_id, "end", values=("Roles", "0", "Not checked"))
                self.resource_tree.insert(service_id, "end", values=("Policies", "0", "Not checked"))

    def refresh_resource_status(self):
        """Refresh resource status in dashboard"""
        self.update_status("Refreshing resource status...")
    
    # Clear existing items
    for item in self.resource_tree.get_children():
        self.resource_tree.delete(item)
    
    # Initialize with empty data
    self.initialize_dashboard()
    
    # Check AWS connectivity first
    if not self.check_aws_status():
        self.update_status("Cannot refresh resources: AWS connection failed")
        return
    
    try:
        # EC2 Resources
        ec2_client = get_client('ec2')
        instances = ec2_client.describe_instances()
        instance_count = sum(len(reservation['Instances']) for reservation in instances['Reservations'])
        
        ec2_id = self.resource_tree.insert("", "end", text="EC2")
        self.resource_tree.insert(ec2_id, "end", values=("Instances", str(instance_count), "Active"))
        
        # S3 Resources
        s3_client = get_client('s3')
        buckets = s3_client.list_buckets()
        bucket_count = len(buckets['Buckets'])
        
        s3_id = self.resource_tree.insert("", "end", text="S3")
        self.resource_tree.insert(s3_id, "end", values=("Buckets", str(bucket_count), "Active"))
        
        # If we have a bucket, count objects
        object_count = 0
        bucket_name = self.bucket_name_var.get()
        if bucket_name:
            try:
                objects = s3_client.list_objects_v2(Bucket=bucket_name)
                if 'Contents' in objects:
                    object_count = len(objects['Contents'])
                self.resource_tree.insert(s3_id, "end", values=("Objects", str(object_count), "Active"))
            except Exception:
                self.resource_tree.insert(s3_id, "end", values=("Objects", "0", "Error"))
        else:
            self.resource_tree.insert(s3_id, "end", values=("Objects", "0", "No bucket selected"))
        
        # Lambda Resources
        lambda_client = get_client('lambda')
        functions = lambda_client.list_functions()
        function_count = len(functions['Functions'])
        
        lambda_id = self.resource_tree.insert("", "end", text="Lambda")
        self.resource_tree.insert(lambda_id, "end", values=("Functions", str(function_count), "Active"))
        
        # IAM Resources
        iam_client = get_client('iam')
        roles = iam_client.list_roles()
        role_count = len(roles['Roles'])
        
        policies = iam_client.list_policies(Scope='Local')
        policy_count = len(policies['Policies'])
        
        iam_id = self.resource_tree.insert("", "end", text="IAM")
        self.resource_tree.insert(iam_id, "end", values=("Roles", str(role_count), "Active"))
        self.resource_tree.insert(iam_id, "end", values=("Policies", str(policy_count), "Active"))
        
        self.update_status("Resource status refreshed successfully")
    except Exception as e:
        self.update_status(f"Error refreshing resources: {str(e)}", error=True)

    def create_sample_plot(self):
        self.update_status(f"Error refreshing resources: {str(e)}", error=True)

# ---------- AWS Operations ----------

def setup_all(self):
    """Setup all AWS resources"""
    self.update_status("Setting up all AWS resources...")
    
    success = True
    
    # Setup IAM first since other resources may depend on it
    if not self.setup_iam():
        success = False
    
    # Setup other resources
    if not self.setup_ec2():
        success = False
    
    if not self.setup_s3():
        success = False
    
    if not self.setup_lambda():
        success = False
    
    if success:
        self.update_status("All AWS resources set up successfully")
        self.refresh_resource_status()
    else:
        self.update_status("Some resources failed to set up", error=True)
    
    return success

def setup_iam(self):
    """Setup IAM roles and policies"""
    self.update_status("Setting up IAM resources...")
    
    try:
        role_name = self.role_name_var.get()
        policy_name = self.policy_name_var.get()
        
        # Use the imported setup_iam function
        iam_manager = IAMManager(
            role_name=role_name,
            policy_name=policy_name
        )
        
        result = setup_iam(iam_manager)
        
        if result:
            self.update_status(f"IAM role '{role_name}' and policy '{policy_name}' created successfully")
            self.list_iam_roles()
            return True
        else:
            self.update_status("IAM setup failed", error=True)
            return False
    except Exception as e:
        self.update_status(f"Error setting up IAM: {str(e)}", error=True)
        return False

def list_iam_roles(self):
    """List IAM roles"""
    self.update_status("Listing IAM roles...")
    
    try:
        # Clear existing items
        for item in self.iam_tree.get_children():
            self.iam_tree.delete(item)
        
        iam_client = get_client('iam')
        response = iam_client.list_roles()
        
        for i, role in enumerate(response['Roles']):
            role_name = role['RoleName']
            arn = role['Arn']
            create_date = role['CreateDate'].strftime('%Y-%m-%d %H:%M:%S')
            
            self.iam_tree.insert("", "end", iid=i, values=(role_name, arn, create_date))
        
        self.update_status(f"Listed {len(response['Roles'])} IAM roles")
        return True
    except Exception as e:
        self.update_status(f"Error listing IAM roles: {str(e)}", error=True)
        return False

def delete_selected_role(self):
    """Delete selected IAM role"""
    selected = self.iam_tree.selection()
    if not selected:
        messagebox.showinfo("Selection Required", "Please select a role to delete.")
        return
    
    item = self.iam_tree.item(selected[0])
    role_name = item['values'][0]
    
    confirm = messagebox.askyesno(
        "Confirm Deletion", 
        f"Are you sure you want to delete role '{role_name}'? This cannot be undone."
    )
    
    if confirm:
        self.run_in_thread(self._delete_role, role_name)

def _delete_role(self, role_name):
    """Internal method to delete IAM role"""
    try:
        self.update_status(f"Deleting IAM role '{role_name}'...")

        iam_client = get_client('iam')

        # Detach all attached policies
        try:
            attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)
            for policy in attached_policies['AttachedPolicies']:
                try:
                    iam_client.detach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy['PolicyArn']
                    )
                    self.update_status(f"Detached policy {policy['PolicyName']} from role {role_name}")
                except Exception as detach_e:
                    self.update_status(f"Error detaching policy {policy['PolicyName']} from role {role_name}: {str(detach_e)}", error=True)
        except Exception as list_e:
            self.update_status(f"Error listing attached policies for role {role_name}: {str(list_e)}", error=True)

        # Delete the role
        try:
            iam_client.delete_role(RoleName=role_name)
            self.update_status(f"IAM role '{role_name}' deleted successfully")
        except Exception as delete_e:
            self.update_status(f"Error deleting IAM role {role_name}: {str(delete_e)}", error=True)
        finally:
            self.list_iam_roles()

    except Exception as e:
        self.update_status(f"Error deleting IAM role: {str(e)}", error=True)

def setup_ec2(self):
    """Setup EC2 instances"""
    self.update_status("Setting up EC2 infrastructure...")
    
    try:
        ami_id = self.ami_id_var.get()
        instance_type = self.instance_type_var.get()
        key_name = self.key_pair_var.get()
        
        # Use the imported setup_ec2_infrastructure function
        ec2_manager = EC2Manager(
            ami_id=ami_id,
            instance_type=instance_type,
            key_name=key_name
        )
        
        instance_id = setup_ec2_infrastructure(ec2_manager)
        
        if instance_id:
            self.update_status("EC2 setup completed successfully")
            self.list_ec2()
        else:
            self.update_status("EC2 setup failed", error=True)
    except Exception as e:
        self.update_status(f"Error setting up EC2: {str(e)}", error=True)