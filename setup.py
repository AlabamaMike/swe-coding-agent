"""Setup script for the SWE Coding Agent package"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="swe-coding-agent",
    version="0.1.0",
    author="SWE Agent Contributors",
    description="Autonomous coding agent for implementation and refactoring tasks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/swe-agent",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-mock>=3.12.0",
            "coverage>=7.3.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
            "mypy>=1.7.0",
        ],
        "rabbitmq": ["pika>=1.3.0", "aio-pika>=9.0.0"],
        "kafka": ["aiokafka>=0.10.0"],
        "redis": ["redis>=5.0.0"],
        "all": ["pika>=1.3.0", "aio-pika>=9.0.0", "aiokafka>=0.10.0", "redis>=5.0.0"],
    },
    entry_points={
        "console_scripts": [
            "swe-agent=coding_agent.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "coding_agent": ["py.typed"],
    },
    zip_safe=False,
)