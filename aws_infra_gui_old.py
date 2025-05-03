import os

def rename_file(old_name, new_name):
    try:
        os.rename(old_name, new_name)
        print(f"File '{old_name}' renamed to '{new_name}' successfully.")
    except FileNotFoundError:
        print(f"File '{old_name}' not found.")
    except FileExistsError:
        print(f"File '{new_name}' already exists.")
    except Exception as e:
        print(f"An error occurred: {e}")

rename_file("aws_infra_gui.py", "aws_infra_gui_old.py")