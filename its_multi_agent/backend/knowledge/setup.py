from pathlib import Path

from setuptools import find_packages, setup


requirements_path = Path(__file__).with_name("requirements.txt")
requirements = [
    line.strip()
    for line in requirements_path.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]

setup(
    name="knowledge",
    version="0.1.0",
    packages=find_packages(),
    install_requires=requirements,
)
