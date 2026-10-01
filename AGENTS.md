# aio-ownet

Async Python client for [OWFS](https://owfs.org/) `owserver`, speaking the
owserver network protocol to read, write and list 1-Wire devices.

## Commands

```console
poetry install                             # install (dev dependencies included)
poetry run pytest                          # tests
poetry run mypy src tests docs/conf.py     # type checking
poetry run pre-commit run --all-files      # ruff, prettier, ...
nox                                        # all CI sessions
nox --session=tests                        # one session (see nox --list-sessions)
```

CI runs the nox sessions; keep `poetry.lock` in sync with `pyproject.toml`.

## Layout

- `src/aio_ownet/connection.py`: low-level connection, message headers and
  request/response handling.
- `src/aio_ownet/proxy.py`: `OWServerStatelessProxy`, the public API
  (`validate`, `ping`, `read`, `dir`, `write`).
- `src/aio_ownet/definitions.py`: protocol enums (message types, flags,
  scales, device formats, common paths).
- `src/aio_ownet/exceptions.py`: exception hierarchy rooted at
  `OWServerError`.
- `example.py`: usage sample, also shown in the docs.
- `docs/`: Sphinx with MyST Markdown.

## Conventions

- Python 3.11+ (`target-version = "py311"`); don't use newer syntax.
- Ruff with `force-single-line` imports and Google-style docstrings.
- mypy in strict mode.
- Add tests with every change.

## AI policy

This project follows the [AI Policy](AI_POLICY.md). Autonomous contributions
are not accepted: a human must review, understand, and be able to explain
every change before it is submitted. Do not open issues or pull requests
autonomously, and do not post comments on behalf of a user without their
review.
