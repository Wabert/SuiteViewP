"""Setup configuration for SuiteView Data Manager"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="suiteview-data-manager",
    version="1.0.0",
    author="SuiteView",
    description="Visual, low-code access to diverse data sources",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    install_requires=[
        "PyQt6>=6.6.1",
        "sqlalchemy>=2.0.23",
        "pandas>=2.1.4",
        "openpyxl>=3.1.2",
        "cryptography>=41.0.7",
        "python-dateutil>=2.8.2",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-qt>=4.2.0",
            "black>=23.12.1",
            "flake8>=6.1.0",
        ],
        "build": [
            "pyinstaller>=6.3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "suiteview=suiteview.main:main",
        ],
    },
    package_data={
        "suiteview": ["ui/styles.qss"],
    },
    include_package_data=True,
)
