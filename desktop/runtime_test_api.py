import os

# Test builds always use the isolated test API and must not inherit production
# endpoint variables from the developer machine.
os.environ["TK_SELECTION_API_BASE_URL"] = "http://120.26.207.89:8001"
