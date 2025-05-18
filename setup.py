import os
import re
from pathlib import Path

import setuptools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

here = Path(__file__).resolve().parent
version_file = here / "handelsregister" / "version.py"
readme_file  = here / "README.md"

# Extract the version string
with version_file.open(encoding="utf-8") as f:
    m = re.search(r'^__version__\s*=\s*"(.*)"', f.read(), re.M)
    if not m:
        raise RuntimeError("Unable to find __version__ in version.py")
    package_version = m.group(1)

# Long description
long_description = readme_file.read_text(encoding="utf-8") \
    if readme_file.exists() else \
    "Python SDK für den Zugriff auf die Handelsregister AI API"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

setuptools.setup(
    name="handelsregister",
    version=package_version,
    author="Handelsregister Team",
    author_email="info@handelsregister.ai",
    url="https://github.com/Handelsregister-AI/handelsregister",
    description="Python SDK für den Zugriff auf die handelsregister.ai API",
    long_description=long_description,
    long_description_content_type="text/markdown",

    # Only the SPDX identifier is needed; do NOT add license_files here —
    # that field generates the rejected “license-file” metadata.
    license="MIT",

    # Packages
    packages=setuptools.find_packages(exclude=("tests", "tests.*")),
    include_package_data=True,

    python_requires=">=3.7",
    install_requires=[
        "httpx>=0.23.0",
        "tqdm>=4.0.0",
        "pandas>=1.0.0",
        "openpyxl>=3.0.0",
        "rich>=13.0.0",
    ],

    entry_points={
        "console_scripts": [
            "handelsregister=handelsregister.cli:main",
        ],
    },

    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
    ],
)
