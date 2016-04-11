CWD=$(shell pwd)
PYVER ?= 3
noseopts ?= -v

YAML_FILES=$(shell find cloudinit bin tests tools -name "*.yaml" -type f )
YAML_FILES+=$(shell find doc/examples -name "cloud-config*.txt" -type f )

CHANGELOG_VERSION=$(shell $(CWD)/tools/read-version)
CODE_VERSION=$(shell python -c "from cloudinit import version; print version.version_string()")

PIP_INSTALL := pip install

ifeq ($(PYVER),3)
  pyflakes = pyflakes3
  unittests = unittest3
  yaml = yaml
else
ifeq ($(PYVER),2)
  pyflakes = pyflakes
  unittests = unittest
else
  pyflakes = pyflakes pyflakes3
  unittests = unittest unittest3
endif
endif

ifeq ($(distro),)
  distro = redhat
endif

all: check

check: check_version pep8 $(pyflakes) test $(yaml)

pep8:
	@$(CWD)/tools/run-pep8

pyflakes:
	@$(CWD)/tools/run-pyflakes

pyflakes3:
	@$(CWD)/tools/run-pyflakes3
	
unittest: clean_pyc
	nosetests $(noseopts) tests/unittests

unittest3: clean_pyc
	nosetests3 $(noseopts) tests/unittests

pip-requirements:
	@echo "Installing cloud-init dependencies..."
	$(PIP_INSTALL) -r "$@.txt" -q

pip-test-requirements:
	@echo "Installing cloud-init test dependencies..."
	$(PIP_INSTALL) -r "$@.txt" -q

test: $(unittests)

check_version:
	@if [ "$(CHANGELOG_VERSION)" != "$(CODE_VERSION)" ]; then \
	    echo "Error: ChangeLog version $(CHANGELOG_VERSION)" \
	    "not equal to code version $(CODE_VERSION)"; exit 2; \
	    else true; fi

clean_pyc:
	@find . -type f -name "*.pyc" -delete

clean: clean_pyc
	rm -rf /var/log/cloud-init.log /var/lib/cloud/

yaml:
	@$(CWD)/tools/validate-yaml.py $(YAML_FILES)

rpm:
	./packages/brpm --distro $(distro)

deb:
	./packages/bddeb

.PHONY: test pyflakes pyflakes3 clean pep8 rpm deb yaml check_version
.PHONY: pip-test-requirements pip-requirements clean_pyc unittest unittest3
