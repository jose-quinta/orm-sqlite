import logging
import sys
import os
from typing import Optional

def setup_logger(
  name: Optional[str] = None,
  level: int = logging.INFO,
  log_file: Optional[str] = None
) -> logging.Logger:
  logger = logging.getLogger(name or __name__)
  logger.setLevel(level)

  if logger.handlers:
    return logger

  formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
  )

  console_handler = logging.StreamHandler(sys.stdout)
  console_handler.setLevel(level)
  console_handler.setFormatter(formatter)
  logger.addHandler(console_handler)

  if log_file:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

  return logger

def get_logger(name: str) -> logging.Logger:
  return logging.getLogger(name)
