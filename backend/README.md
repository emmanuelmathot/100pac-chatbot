# Chatbot code 🤖

## Prerequisites

To develop within the `chatbot` source code, you will need:

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [docker](https://docs.docker.com/engine/install/)

## Setup

We use uv as a package manager, but also install the local package for dev
environments. Use `scripts/install` the script to install all dependencies
and the local package.

You will need to setup your mistral api key. The easiest way is to

  1. Copy the example env file with `cp .env.example .env`

  2. Edit the `.env` file and fill the value of `MISTRAL_API_KEY` with the
    value provided to you at the beginning of your sprint, it will expire
    on the 3rd of October

Then you are ready to fire up the agent. Run `scripts/api` and `scripts/chat`
in separate terminals. It will fire up streamlit so you can ask for some cool
cat pictures asap 🐱 !

## Scripts To Rule Them All 💍

Within `scripts/` you will find:

- `scripts/install` - Uses `uv` to install all necessary packages

- `scripts/lint` - Uses `ruff` and `mypy` to check codestyle and typing

- `scripts/format` - Uses `ruff` to format code to adhere to codestyle

- `scripts/api` - Uses `uvicorn` to stand up the `chatbot` api (available on `localhost:8000`)

- `scripts/chat` - Uses `streamlit` to stand up the `chatbot` chat interface for easier interactions with the api (available on `localhost:8501`)

- `scripts/test` - Uses `pytest` to run all tests within `tests/`

- `scripts/build-and-push-image` - Uses `docker` to build the image of the chatbot and optionally push it with an optional tag to a registry (e.g `scripts/build-and-push-image --tag=0.0.1 --push`

To invoke any of these:

```bash
cd backend
scripts/<name-of-script>
```
