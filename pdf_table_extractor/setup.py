"""
Setup script for PDF Pricing Table Extractor.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="pdf-table-extractor",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Extract pricing tables from scanned PDF contracts using GPT-4o",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/pdf-table-extractor",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    install_requires=[
        "openai>=1.12.0",
        "PyMuPDF>=1.23.0",
        "Pillow>=10.0.0",
        "pydantic>=2.5.0",
        "tqdm>=4.66.0",
    ],
    extras_require={
        "dotenv": [
            "python-dotenv>=1.0.0",
        ],
        "dev": [
            "pytest>=7.4.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "mypy>=1.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "extract-tables=src.main:cli_main",
        ],
    },
)
