import logging
from pathlib import Path
from datetime import datetime

# Define the project root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Create the logs directory
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Generate a timestamped log filename
LOG_FILE = datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f") + ".log"
LOG_FILE_PATH = LOG_DIR / LOG_FILE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Initialize project logger
logger = logging.getLogger("StudyingRedhead")