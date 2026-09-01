SPHINXBUILD  ?= sphinx-build -W -b
SPHINXOPTS   ?=
BUILDDIR     ?= _build
SOURCEDIR    ?= .
PYTHON       ?= python3

.PHONY: html doctest screenshots clean

html:
	$(SPHINXBUILD) html $(SOURCEDIR) $(BUILDDIR)/html $(SPHINXOPTS)

doctest:
	$(SPHINXBUILD) doctest $(SOURCEDIR) $(BUILDDIR)/doctest $(SPHINXOPTS)

# The images are committed, so this is a deliberate step rather than a
# prerequisite of `html`: a docs build should not have to import the library.
screenshots:
	$(PYTHON) $(SOURCEDIR)/make_screenshots.py

clean:
	rm -rf $(BUILDDIR)