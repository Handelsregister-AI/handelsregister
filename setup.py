import os
import re
import setuptools

# Read the version from your package's version.py
here = os.path.abspath(os.path.dirname(__file__))

version_file = os.path.join(here, "handelsregister", "version.py")
with open(version_file, encoding="utf-8") as f:
    version_match = re.search(r'^__version__\s*=\s*"(.*)"', f.read(), re.M)
    if not version_match:
        raise RuntimeError("Unable to find __version__ in version.py")
    package_version = version_match.group(1)

# Read the long description from your README
readme_file = os.path.join(here, "README.md")
try:
    with open(readme_file, encoding="utf-8") as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "A modern Python client for the handelsregister.ai"

# Package name MUST be "handelsregister" not "handelsregister-ai"
setuptools.setup(
    name="handelsregister",
    version=package_version,
    author="Handelsregister.ai",
    author_email="info@handelsregister.ai.com",
    description="A modern Python client for handelsregister.ai",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://handelsregister.ai/",
    license="MIT",
    # Explicitly set the package directory to find handelsregister
    package_dir={"": "."},
    packages=setuptools.find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "httpx>=0.23.0",
        "tqdm>=4.0.0",
    ],
)
