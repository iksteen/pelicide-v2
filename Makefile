.PHONY: all build-ui dist

all:
	@echo "Please be explicit, use 'make dist'."
	@exit 1

build-ui:
	cd pelicide-ui && \
		yarn install && \
		yarn build --dest ../pelicide/ui

dist: build-ui
	poetry build
