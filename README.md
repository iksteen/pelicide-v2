# pelicide

An IDE for pelican sites.

## Install instructions

Step 1: Install [poetry](https://github.com/sdispater/poetry#installation).

Step 2: Clone pelicide and its UI.

```
git clone --recurse ssh://git@git.thegraveyard.org:44322/pelicide/pelicide.git
```

Step 3: Install dependencies and build UI.

```
cd pelicide
poetry install
poetry run invoke build-ui
```

Step 4: Install pelican and common plugins.

```
poetry run pip install pelican 'Markdown<3' typogrify
```

Step 5: Run pelicide.

```
poetry run pelicide <path to pelican site directory>
```

Wait until pelicide has settled, open http://localhost:6300/ in your
browser.
