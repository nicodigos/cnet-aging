import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv


def database_url() -> str:
    load_dotenv()
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("Missing DATABASE_URL")
    return value


@contextmanager
def connect():
    with psycopg.connect(database_url(), connect_timeout=15) as connection:
        yield connection
