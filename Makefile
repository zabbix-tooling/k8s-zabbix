SHELL = bash

activate = source venv/bin/activate

all: deps
.PHONY: all

deps: venv/bin/activate
.PHONY: deps


venv/bin/activate: requirements.txt
	python3 -m venv venv
	@# TODO: installation of wheel solves a pip install error, we have to check if that is needed permamently
	@# because it seems to be a packaging issue
	${activate} && \
		pip install wheel && \
		pip install -r requirements.txt

clean:
	rm -rf venv
.PHONY: clean

check:
	@# run sequentially so the output is easier to read
	${MAKE} --no-print-directory lint
	${MAKE} --no-print-directory type-check
	${MAKE} --no-print-directory test
.PHONY: check


lint: deps
	${activate} && python3 -m flake8 base k8sobjects
.PHONY: lint

type-check: deps
	${activate} && python3 -m mypy --no-color-output --pretty base k8sobjects
.PHONY: type-check

test: deps
	${activate} && python3 -m pytest tests
