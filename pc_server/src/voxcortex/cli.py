from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_settings, prepare_user_config
from .runtime import ServerRuntime, configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="VoxCortex local AI voice server")
    parser.add_argument("--config", type=Path, help="Path to YAML configuration")
    args = parser.parse_args()
    config_path = args.config.resolve() if args.config else prepare_user_config()
    settings = load_settings(config_path)
    configure_logging(settings.log_dir, settings.diagnostic)
    ServerRuntime(settings).run()


if __name__ == "__main__":
    main()
