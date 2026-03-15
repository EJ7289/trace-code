from setuptools import setup, find_packages

setup(
    name="call-tracer",
    version="1.0.0",
    description="Cross-language bidirectional call graph tracer with PlantUML export",
    packages=find_packages(),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "tracer=tracer.cli:main",
        ],
    },
)
