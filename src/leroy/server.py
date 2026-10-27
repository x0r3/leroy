"""Start the API with console backpressure isolated from request processing."""

import logging

import uvicorn

from .console_logging import logging_config


def main():
    logging.captureWarnings(True)
    uvicorn.run("leroy.api:create_app", factory=True, host="0.0.0.0", port=8088, log_config=logging_config())


if __name__ == "__main__":
    main()
