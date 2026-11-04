from setuptools import setup

setup(
    name="megarac-commander",
    version="1.0.0",
    packages=["megarac_commander"],
    package_dir={"megarac_commander": "."},
    package_data={"megarac_commander": ["index.html", "ModernJViewerBridge.java"]},
    entry_points={
        "console_scripts": [
            "megarac-commander=megarac_commander.bridge_server:main",
        ],
    },
)
