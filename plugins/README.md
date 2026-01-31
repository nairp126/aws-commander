# Plugins Directory

## 1. Purpose

**What it does:** Provides a structure for extending the application's functionality without modifying the core codebase.

**Why it exists:** It allows developers to add new features (represented as tabs in the GUI) in a modular fashion.

## 2. Contents & Key Files

- **`hello_plugin.py`**: A sample plugin implementation.
  - **Logic**: defines a `HelloPluginTab` class that inherits from `BasePluginTab`. It creates a simple UI with a welcome message.

## 3. Usage & Implementation

### Inputs

- **Base Class**: Plugins must inherit from `aws_infra_gui_v2.BasePluginTab`.

### Outputs

- **GUI Component**: The plugin class is instantiated and added as a new tab in the main application window.

### Dependencies

- **Core App**: Depends on `aws_infra_gui_v2` for the base class definition.
- **PyQt5**: Uses PyQt5 widgets for UI construction.
