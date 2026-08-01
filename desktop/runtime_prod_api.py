import os

# Production package always connects to the production backend.
os.environ["TK_SELECTION_API_BASE_URL"] = "http://120.26.207.89:8000"
