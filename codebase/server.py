"""VLearn Recall development server entry point."""

from backend.app import create_app


app = create_app()


if __name__ == "__main__":
    app.run()
