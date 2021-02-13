# Install pip-tools for the pip-compile program
pip install pip-tools

# Create a requirements.in file with needed requirements

# Run pip-compile to intake needed dependencies and output pinned versions of _all_ dependencies
pip-compile -o requirements.txt requirements.in
