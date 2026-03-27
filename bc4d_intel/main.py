"""BC4D Intel — entry point."""

import sys, os

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from bc4d_intel.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
