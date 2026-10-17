"""Compatibility launcher: existing python Scraper/scraper.py commands still work."""

if __package__:
    from .main import main
else:
    from main import main


# Only run when this file is executed directly, rather than imported.
if __name__ == "__main__":
    main()
