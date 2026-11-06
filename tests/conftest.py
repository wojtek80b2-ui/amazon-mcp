"""Testy zawsze w trybie mock, niezależnie od lokalnego .env (ustawiane przed importem amazon_mcp.config)."""

import os

os.environ["AMAZON_MODE"] = "mock"
