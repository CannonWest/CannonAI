"""
Setup script for AI Chat Manager backend.
"""
from setuptools import setup, find_packages

setup(
    name="ai-chat-manager-backend",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.103.1",
        "uvicorn>=0.23.2",
        "pydantic>=2.4.2",
        "pydantic-settings>=2.0.3",
        "sqlalchemy>=2.0.21",
        "alembic>=1.12.0",
        "python-dotenv>=1.0.0",
        "websockets>=11.0.3",
        "httpx>=0.25.0",
        "python-multipart>=0.0.6",
    ],
)
