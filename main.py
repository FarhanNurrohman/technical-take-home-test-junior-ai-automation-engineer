"""Application entry point for SouthCity settlement automation."""

import logging


def main() -> None:
    """Run the settlement automation pipeline."""
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info("Settlement automation scaffold is ready.")


if __name__ == "__main__":
    main()