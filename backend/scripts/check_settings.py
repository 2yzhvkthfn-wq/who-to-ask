"""Check that the settings load. Shows the names of the settings, never their values."""

import sys

from pydantic import ValidationError

from utils.logging import logger


def main() -> None:
    """Load the settings and log each setting's name."""
    # 1) Load the settings. The import reads .env, so it sits inside the try
    try:
        from config.settings import settings
    except ValidationError as e:
        # Say which setting is wrong and why, never what its value is
        for error in e.errors(include_input=False):
            name = ".".join(str(part) for part in error["loc"])
            logger.error(f"{name}: {error['msg']}")
        logger.error("Settings NOT OK: fix the lines above in .env")
        sys.exit(1)

    # 2) List each setting by name: "set" was found in .env, "default" comes from settings.py
    for name in type(settings).model_fields:
        source = "set" if name in settings.model_fields_set else "default"
        logger.info(f"{name}: {source}")
    logger.info("Settings OK")


if __name__ == "__main__":
    main()
