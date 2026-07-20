from __future__ import annotations

import argparse
from .config import load_settings
from .runtime import ServerRuntime, configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="M5 AI Dictation local server")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration")
    args = parser.parse_args()
    settings = load_settings(args.config)
    configure_logging(settings.log_dir, settings.diagnostic)
    ServerRuntime(settings).run()


if __name__ == "__main__":
    main()
