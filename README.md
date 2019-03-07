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

## Update instructions

Step 1: Pull pelicide and its UI.

```
git pull --recurse
```

Step 2: Update dependencies and rebuild UI.

```
poetry install
poetry run invoke build-ui
```

## UI development

In production mode, the main `pelicide` process will serve the compiled
front end. When developing on the UI, it's the other way around: webpack's
devserver will proxy requests to the API.

Step 1: Start the service.

```
poetry run pelicide <path to pelican site directory>
```

Please make sure `pelicide` runs on port 6300.

Step 2: Start the UI in development mode.

In a different terminal, run:

```
cd pelicide-ui
yarn run serve
```

Wait until webpack has settled, open http://localhost:8080/ in your
browser.
