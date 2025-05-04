from PyQt5.QtWidgets import QLabel, QVBoxLayout
from aws_infra_gui_v2 import BasePluginTab

class HelloPluginTab(BasePluginTab):
    PLUGIN_LABEL = 'Hello Plugin'
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel('Welcome to the Hello Plugin Tab!'))
        self.setLayout(layout) 