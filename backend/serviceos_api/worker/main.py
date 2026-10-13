"""Run as a separate process: python -m serviceos_api.worker.main"""

import logging

from serviceos_api.settings import Settings
from serviceos_api.worker.runtime import run_worker_forever


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_worker_forever(Settings.from_environment())


if __name__ == "__main__":
    main()
