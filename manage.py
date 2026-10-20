#!/usr/bin/env python
import os
import sys


def main():
    # On Render (which sets RENDER=true) never fall back to the local, debug settings.
    default = "config.settings.production" if os.environ.get("RENDER") else "config.settings.local"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
