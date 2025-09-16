import os
import shutil

def find_executable(executable_name):
    """
    Locates an executable, first in a project-level 'bin' directory,
    then in the system's PATH.
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    project_bin_path = os.path.join(project_root, "bin")
    
    # Check in project's bin directory
    executable_path = os.path.join(project_bin_path, executable_name)
    if os.path.exists(executable_path) and os.access(executable_path, os.X_OK):
        return executable_path

    # Check in system's PATH
    return shutil.which(executable_name)
