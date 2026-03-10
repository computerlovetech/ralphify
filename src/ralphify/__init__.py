from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ralphify")
except PackageNotFoundError:
    __version__ = "0.0.0"

from ralphify.cli import app


def main():
    app()
