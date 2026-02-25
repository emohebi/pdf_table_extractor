"""
File utility functions for the PDF Table Extractor.

This module provides helper functions for file and directory operations,
path handling, and filename manipulation.

Example:
    from src.utils.file_utils import ensure_directory, get_output_path
    
    ensure_directory("./output/images")
    output_file = get_output_path("contract.pdf", "output", "json")
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Create a directory if it doesn't exist.
    
    Args:
        path: Directory path to create
    
    Returns:
        Path object for the directory
    
    Example:
        output_dir = ensure_directory("./output/tables")
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean_filename(filename: str, replacement: str = "_") -> str:
    """
    Remove or replace invalid characters from a filename.
    
    Args:
        filename: Original filename
        replacement: Character to replace invalid chars with
    
    Returns:
        Cleaned filename safe for all operating systems
    
    Example:
        clean = clean_filename("Contract: KPMG/2024")  # Returns "Contract_KPMG_2024"
    """
    # Characters not allowed in filenames on various OSes
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    cleaned = re.sub(invalid_chars, replacement, filename)
    
    # Remove leading/trailing spaces and dots
    cleaned = cleaned.strip(". ")
    
    # Collapse multiple replacements
    cleaned = re.sub(f"{re.escape(replacement)}+", replacement, cleaned)
    
    return cleaned


def get_output_path(
    input_file: Union[str, Path],
    output_dir: Union[str, Path],
    extension: str,
    suffix: Optional[str] = None,
    timestamp: bool = False
) -> Path:
    """
    Generate an output file path based on the input file.
    
    Args:
        input_file: Path to the input file
        output_dir: Directory for the output file
        extension: File extension (without dot)
        suffix: Optional suffix to add before extension
        timestamp: Whether to add a timestamp to the filename
    
    Returns:
        Path object for the output file
    
    Example:
        # Input: contract.pdf, output: ./output/contract_extracted.json
        path = get_output_path("contract.pdf", "./output", "json", suffix="extracted")
    """
    input_path = Path(input_file)
    output_path = Path(output_dir)
    
    # Build the output filename
    base_name = input_path.stem
    
    if suffix:
        base_name = f"{base_name}_{suffix}"
    
    if timestamp:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{base_name}_{ts}"
    
    # Clean the filename
    base_name = clean_filename(base_name)
    
    # Ensure extension doesn't have a leading dot
    extension = extension.lstrip(".")
    
    # Create output directory
    ensure_directory(output_path)
    
    return output_path / f"{base_name}.{extension}"


def get_file_size(path: Union[str, Path]) -> int:
    """
    Get the size of a file in bytes.
    
    Args:
        path: Path to the file
    
    Returns:
        File size in bytes
    """
    return Path(path).stat().st_size


def get_file_size_human(path: Union[str, Path]) -> str:
    """
    Get the size of a file in human-readable format.
    
    Args:
        path: Path to the file
    
    Returns:
        Human-readable file size (e.g., "1.5 MB")
    """
    size = get_file_size(path)
    
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    
    return f"{size:.1f} TB"


def copy_file(
    source: Union[str, Path],
    destination: Union[str, Path],
    overwrite: bool = False
) -> Path:
    """
    Copy a file to a new location.
    
    Args:
        source: Source file path
        destination: Destination path (file or directory)
        overwrite: Whether to overwrite existing files
    
    Returns:
        Path to the copied file
    
    Raises:
        FileExistsError: If destination exists and overwrite is False
    """
    source = Path(source)
    destination = Path(destination)
    
    # If destination is a directory, use the source filename
    if destination.is_dir():
        destination = destination / source.name
    
    # Check for existing file
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Destination already exists: {destination}")
    
    # Ensure destination directory exists
    ensure_directory(destination.parent)
    
    # Copy the file
    shutil.copy2(source, destination)
    
    return destination


def list_files(
    directory: Union[str, Path],
    pattern: str = "*",
    recursive: bool = False
) -> list[Path]:
    """
    List files in a directory matching a pattern.
    
    Args:
        directory: Directory to search
        pattern: Glob pattern to match (e.g., "*.pdf")
        recursive: Whether to search subdirectories
    
    Returns:
        List of matching file paths
    
    Example:
        pdfs = list_files("./documents", "*.pdf", recursive=True)
    """
    directory = Path(directory)
    
    if recursive:
        return sorted(directory.rglob(pattern))
    else:
        return sorted(directory.glob(pattern))


def cleanup_directory(
    directory: Union[str, Path],
    pattern: str = "*",
    keep_directory: bool = True
) -> int:
    """
    Remove files from a directory.
    
    Args:
        directory: Directory to clean
        pattern: Pattern for files to remove (default: all files)
        keep_directory: Whether to keep the directory itself
    
    Returns:
        Number of files removed
    """
    directory = Path(directory)
    removed_count = 0
    
    if not directory.exists():
        return 0
    
    # Remove matching files
    for file_path in directory.glob(pattern):
        if file_path.is_file():
            file_path.unlink()
            removed_count += 1
    
    # Optionally remove the directory
    if not keep_directory and directory.exists():
        try:
            directory.rmdir()  # Only removes if empty
        except OSError:
            pass  # Directory not empty
    
    return removed_count
