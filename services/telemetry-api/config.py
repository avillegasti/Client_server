import yaml
import os
from pathlib import Path

# Base directory for the backend
BASE_DIR = Path(__file__).parent

def load_config(config_file="config.yaml"):
    config_path = BASE_DIR / config_file
    if not config_path.exists():
        # Fallback to current directory if not found in BASE_DIR
        config_path = Path(config_file)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

# Global configuration object
config = load_config()

# Helper to access nested config
def get_config():
    return config
