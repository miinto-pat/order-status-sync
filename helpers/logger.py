import logging

# Define a log file
LOG_FILE = "../app.log"

# Create a logging configuration
logging.basicConfig(
    level=logging.DEBUG,  # Set global log level (DEBUG captures all levels)
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),  # Save logs to a file
        logging.StreamHandler()  # Print logs to console
    ]
)

# Function to get a logger for each module
def get_logger(name):
    return logging.getLogger(name)