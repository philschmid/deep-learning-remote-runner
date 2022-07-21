
.PHONY: quality style

check_dirs := src 

# Check that source code meets quality standards

quality:
	black --check --line-length 119 --target-version py39 $(check_dirs)
	isort --check-only $(check_dirs)
	flake8 src

# Format source code automatically

style:
	black --line-length 119 --target-version py39 $(check_dirs)
	isort $(check_dirs)