MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
TOP ?= logo_dw_openframe

.PHONY: all logo
all: logo

logo:
	python3 script/make_logo.py

.PHONY: logo
