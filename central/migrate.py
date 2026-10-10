"""Standalone central migration for a fresh database or existing simulator DB.

Unlike the legacy Alembic environment, this does not load legacy settings/models.
"""
from pathlib import Path
from alembic import command
from alembic.config import Config
from central.app import engine


def main():
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'central/alembic.ini'))
    config.set_main_option('script_location',str(root/'central/migrations'))
    config.set_main_option('sqlalchemy.url',str(engine().url.render_as_string(hide_password=False)).replace('%','%%'))
    command.upgrade(config,'head')


if __name__=='__main__':
    main()
