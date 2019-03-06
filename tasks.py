from invoke import task


@task
def update_ui(c, commit=True):
    c.run("git submodule update --remote")
    if commit:
        c.run("git add pelicide-ui")
        c.run("git commit -m 'Update pelicide-ui to latest commit.'")


@task
def build_ui(c):
    with c.cd("pelicide-ui"):
        c.run("yarn install")
        c.run("yarn build --dest ../pelicide/ui")


@task(build_ui)
def dist(c):
    c.run("poetry build")
